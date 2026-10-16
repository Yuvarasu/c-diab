import json
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, current_user, get_ctx, get_db, limit
from app.api.errors import ApiError
from app.context import AppContext
from app.models import Order
from app.schemas.api import CheckoutIn, CheckoutOut, MockCompleteIn, OrderOut, VerifyIn
from app.services import orders as svc

router = APIRouter(tags=["orders"])


@router.post("/orders/checkout", response_model=CheckoutOut, status_code=201, dependencies=[Depends(limit("checkout", 20, 3600))])
def checkout(body: CheckoutIn, user: Principal = Depends(current_user), db: Session = Depends(get_db),
             ctx: AppContext = Depends(get_ctx)):
    order, session = svc.checkout(ctx, db, user, body)
    return {"order": svc.order_out(order), "payment": session}


@router.get("/orders", response_model=list[OrderOut])
def my_orders(user: Principal = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Order).where(Order.user_id == user.id).order_by(Order.created_at.desc()))
    return [svc.order_out(o) for o in rows]


@router.get("/orders/{order_id}", response_model=OrderOut)
def order(order_id: UUID, user: Principal = Depends(current_user), db: Session = Depends(get_db)):
    o = db.get(Order, order_id)
    if o is None or o.user_id != user.id:
        raise ApiError(404, "not_found", "Order not found.")
    return svc.order_out(o)


@router.post("/payments/verify", response_model=OrderOut)
def verify(body: VerifyIn, user: Principal = Depends(current_user), db: Session = Depends(get_db),
           ctx: AppContext = Depends(get_ctx)):
    return svc.order_out(svc.verify_payment(ctx, db, user, body.order_id, body.provider_payment_id, body.signature))


@router.post("/payments/mock/complete")
def mock_complete(body: MockCompleteIn, user: Principal = Depends(current_user), db: Session = Depends(get_db),
                  ctx: AppContext = Depends(get_ctx)):
    if ctx.payments.name != "mock" or ctx.settings.is_production:
        raise ApiError(404, "not_found", "Not found.")
    return svc.mock_complete(ctx, db, user, body.order_id, body.outcome == "success")


@router.post("/payments/webhook")
async def webhook(request: Request, x_razorpay_signature: str = Header(""), db: Session = Depends(get_db),
                  ctx: AppContext = Depends(get_ctx)):
    raw = await request.body()
    try:
        payload = json.loads(raw)
    except ValueError:
        raise ApiError(400, "bad_request", "Invalid payload.")
    svc.handle_webhook(ctx, db, raw, x_razorpay_signature, payload)
    return {"received": True}
