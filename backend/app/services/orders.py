import logging

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.api.errors import ApiError
from app.context import AppContext
from app.models import CartItem, Order, OrderItem, Payment, ProductVariant
from app.services.audit import audit
from app.services.screenings import get_eligibility
from app.services.shop import shipping_for, unit_price

log = logging.getLogger("cdiab.orders")

TRANSITIONS = {
    "pending_payment": {"cancelled"},
    "payment_failed": set(),
    "paid": {"processing", "cancelled"},
    "processing": {"shipped", "cancelled"},
    "shipped": {"delivered"},
    "delivered": set(),
    "cancelled": set(),
}


def order_out(o: Order) -> dict:
    pay = o.payments[-1].status if o.payments else "created"
    return {"id": o.id, "status": o.status, "payment_status": pay, "subtotal_paise": o.subtotal_paise,
            "shipping_paise": o.shipping_paise, "total_paise": o.total_paise, "currency": o.currency,
            "shipping_name": o.shipping_name, "shipping_phone": o.shipping_phone, "address": o.address,
            "delivery_instructions": o.delivery_instructions, "items": o.items, "created_at": o.created_at}


def _session(ctx: AppContext, o: Order) -> dict:
    p = o.payments[-1]
    public = {"provider": p.provider}
    if p.provider == "razorpay":
        public["key_id"] = ctx.settings.razorpay_key_id
    return {"provider": p.provider, "provider_order_id": p.provider_order_id, "amount_paise": p.amount_paise,
            "currency": o.currency, "public": public}


def release_stock(db, order: Order) -> None:
    for it in order.items:
        if it.variant_id:
            v = db.get(ProductVariant, it.variant_id)
            if v:
                v.stock += it.quantity


def checkout(ctx: AppContext, db, user, data) -> tuple[Order, dict]:
    existing = db.scalar(select(Order).where(Order.user_id == user.id, Order.idempotency_key == data.idempotency_key))
    if existing:  # same request replayed: never create a second order
        return existing, _session(ctx, existing)
    cart = list(db.scalars(select(CartItem).where(CartItem.user_id == user.id)))
    if not cart:
        raise ApiError(409, "cart_empty", "Your cart is empty.")
    ids = sorted(c.variant_id for c in cart)
    variants = {v.id: v for v in db.scalars(select(ProductVariant).where(ProductVariant.id.in_(ids))
                                           .order_by(ProductVariant.id).with_for_update())}
    screening_id = None
    if any(variants[c.variant_id].product.requires_screening for c in cart):
        decision = get_eligibility(ctx, db, user.id)  # always evaluated server side; client flags are ignored
        if data.screening_id and data.screening_id != decision.screening_id:
            raise ApiError(409, "screening_superseded", "A newer screening exists. Please use your latest screening.")
        if not decision.eligible:
            raise ApiError(403, "not_eligible", decision.message, {"reason_code": decision.reason_code})
        screening_id = decision.screening_id
    subtotal, lines = 0, []
    for c in cart:
        v = variants[c.variant_id]
        if not v.product.active or v.stock < c.quantity:
            raise ApiError(409, "insufficient_stock", f"{v.product.name} (size {v.size}) is no longer available in that quantity.",
                           {"variant_id": str(v.id), "available": max(0, v.stock)})
        price = unit_price(v)  # prices always come from the database
        subtotal += price * c.quantity
        lines.append((v, c.quantity, price))
    shipping = shipping_for(ctx, subtotal)
    order = Order(user_id=user.id, screening_id=screening_id, status="pending_payment", subtotal_paise=subtotal,
                  shipping_paise=shipping, total_paise=subtotal + shipping, shipping_name=data.shipping_name,
                  shipping_phone=data.shipping_phone, delivery_instructions=data.delivery_instructions,
                  address={"line1": data.address_line1, "line2": data.address_line2, "city": data.city,
                           "state": data.state, "pincode": data.pincode},
                  idempotency_key=data.idempotency_key)
    for v, qty, price in lines:
        order.items.append(OrderItem(variant_id=v.id, product_name=v.product.name, size=v.size,
                                     unit_price_paise=price, quantity=qty))
        v.stock -= qty  # reserve stock; released again if payment fails or the order is cancelled
    try:
        db.add(order)
        db.flush()
        po = ctx.payments.create_order(str(order.id), order.total_paise)
    except IntegrityError:
        db.rollback()
        again = db.scalar(select(Order).where(Order.user_id == user.id, Order.idempotency_key == data.idempotency_key))
        if again:
            return again, _session(ctx, again)
        raise
    except Exception:
        db.rollback()
        log.exception("payment provider order creation failed")
        raise ApiError(502, "payment_unavailable", "Payments are unavailable right now. Please try again.")
    db.add(Payment(order_id=order.id, provider=ctx.payments.name, provider_order_id=po.provider_order_id,
                   amount_paise=order.total_paise))
    audit(db, user.id, "order_created", "order", order.id, total_paise=order.total_paise)
    db.commit()
    db.refresh(order)
    return order, _session(ctx, order)


def _locked_order(db, order_id) -> Order | None:
    return db.scalar(select(Order).where(Order.id == order_id).with_for_update())


def _mark_paid(db, order: Order, payment: Payment, provider_payment_id: str) -> None:
    clash = db.scalar(select(Payment).where(Payment.provider == payment.provider,
                                            Payment.provider_payment_id == provider_payment_id, Payment.id != payment.id))
    if clash:
        raise ApiError(409, "payment_already_used", "This payment was already applied to another order.")
    payment.provider_payment_id, payment.status = provider_payment_id, "paid"
    order.status = "paid"
    bought = [i.variant_id for i in order.items if i.variant_id]
    db.execute(delete(CartItem).where(CartItem.user_id == order.user_id, CartItem.variant_id.in_(bought)))
    audit(db, order.user_id, "payment_confirmed", "order", order.id, provider=payment.provider)


def _mark_failed(db, order: Order, payment: Payment, provider_payment_id: str | None) -> None:
    payment.status = "failed"
    if provider_payment_id and not payment.provider_payment_id:
        payment.provider_payment_id = provider_payment_id
    order.status = "payment_failed"
    release_stock(db, order)
    audit(db, order.user_id, "payment_failed", "order", order.id)


def verify_payment(ctx: AppContext, db, user, order_id, provider_payment_id: str, signature: str) -> Order:
    order = _locked_order(db, order_id)
    if order is None or order.user_id != user.id:
        raise ApiError(404, "not_found", "Order not found.")
    if order.status == "paid" or order.status in ("processing", "shipped", "delivered"):
        return order  # idempotent: already confirmed
    if order.status != "pending_payment":
        raise ApiError(409, "order_not_payable", "This order can no longer be paid.")
    payment = order.payments[-1]
    if not ctx.payments.verify_signature(payment.provider_order_id, provider_payment_id, signature):
        audit(db, user.id, "payment_signature_rejected", "order", order.id)
        db.commit()
        raise ApiError(400, "invalid_signature", "Payment could not be verified.")
    fetched = ctx.payments.fetch_payment(provider_payment_id)  # second check with the provider itself
    if fetched is None or fetched.order_id != payment.provider_order_id or fetched.amount_paise != order.total_paise:
        raise ApiError(400, "payment_not_confirmed", "Payment could not be confirmed.")
    if fetched.status != "captured":
        raise ApiError(402, "payment_not_captured", "Payment was not completed.")
    _mark_paid(db, order, payment, provider_payment_id)
    db.commit()
    db.refresh(order)
    return order


def mock_complete(ctx: AppContext, db, user, order_id, success: bool) -> dict:
    """DEVELOPMENT ONLY: plays the role of the customer paying on a gateway."""
    order = db.get(Order, order_id)
    if order is None or order.user_id != user.id:
        raise ApiError(404, "not_found", "Order not found.")
    if order.status != "pending_payment":
        raise ApiError(409, "order_not_payable", "This order can no longer be paid.")
    payment = order.payments[-1]
    pid, sig = ctx.payments.simulate(payment.provider_order_id, success)  # type: ignore[attr-defined]
    if not success:
        locked = _locked_order(db, order_id)
        _mark_failed(db, locked, locked.payments[-1], pid)
        db.commit()
        return {"status": "failed"}
    return {"status": "authorized", "provider_payment_id": pid, "signature": sig}


def handle_webhook(ctx: AppContext, db, raw: bytes, signature: str, payload: dict) -> None:
    if not ctx.payments.verify_webhook(raw, signature):
        raise ApiError(401, "invalid_signature", "Invalid webhook signature.")
    ev = ctx.payments.parse_webhook(payload)
    if ev is None:
        return
    payment = db.scalar(select(Payment).where(Payment.provider == ctx.payments.name,
                                              Payment.provider_order_id == ev.provider_order_id))
    if payment is None:
        return
    order = _locked_order(db, payment.order_id)
    if ev.kind == "payment.captured":
        if ev.amount_paise is not None and ev.amount_paise != order.total_paise:
            audit(db, None, "webhook_amount_mismatch", "order", order.id)
        elif order.status == "pending_payment":
            _mark_paid(db, order, payment, ev.provider_payment_id)
        elif order.status in ("payment_failed", "cancelled"):
            audit(db, None, "payment_captured_on_closed_order", "order", order.id)  # needs manual refund
    elif ev.kind == "payment.failed" and order.status == "pending_payment":
        _mark_failed(db, order, payment, ev.provider_payment_id)
    db.commit()


def set_status(db, admin, order_id, new_status: str) -> Order:
    order = _locked_order(db, order_id)
    if order is None:
        raise ApiError(404, "not_found", "Order not found.")
    if new_status not in TRANSITIONS.get(order.status, set()):
        raise ApiError(409, "invalid_transition", f"Cannot change an order from {order.status} to {new_status}.")
    if new_status == "cancelled":
        release_stock(db, order)
    audit(db, admin.id, "order_status_changed", "order", order.id, from_status=order.status, to_status=new_status)
    order.status = new_status
    db.commit()
    db.refresh(order)
    return order
