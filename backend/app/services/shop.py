from sqlalchemy import select

from app.api.errors import ApiError
from app.context import AppContext
from app.models import CartItem, Product, ProductVariant


def stock_status(stock: int) -> str:
    return "out_of_stock" if stock <= 0 else "low_stock" if stock <= 5 else "in_stock"


def unit_price(v: ProductVariant) -> int:
    return v.price_override_paise if v.price_override_paise is not None else v.product.price_paise


def shipping_for(ctx: AppContext, subtotal: int) -> int:
    s = ctx.settings
    return 0 if subtotal == 0 or subtotal >= s.free_shipping_threshold_paise else s.shipping_flat_paise


def product_out(p: Product) -> dict:
    return {**{k: getattr(p, k) for k in ("id", "slug", "name", "description", "intended_use", "materials",
                                          "care_instructions", "shipping_info", "return_info", "price_paise",
                                          "requires_screening")},
            "image_urls": p.image_urls or [], "in_stock": any(v.stock > 0 for v in p.variants),
            "variants": [{"id": v.id, "size": v.size, "stock_status": stock_status(v.stock),
                          "max_quantity": max(0, min(v.stock, 10))} for v in p.variants]}


def list_products(db) -> list[Product]:
    return list(db.scalars(select(Product).where(Product.active.is_(True)).order_by(Product.name)))


def get_active_product(db, product_id) -> Product:
    p = db.get(Product, product_id)
    if p is None or not p.active:
        raise ApiError(404, "not_found", "Product not found.")
    return p


def cart_out(ctx: AppContext, db, user_id) -> dict:
    rows = list(db.scalars(select(CartItem).where(CartItem.user_id == user_id).order_by(CartItem.created_at)))
    items, subtotal, issues, needs_screening = [], 0, False, False
    for c in rows:
        v, p = c.variant, c.variant.product
        available = v.stock if p.active else 0
        ok = available >= c.quantity
        price = unit_price(v)
        issues |= not ok
        needs_screening |= p.requires_screening
        if ok:
            subtotal += price * c.quantity
        items.append({"variant_id": v.id, "product_id": p.id, "product_name": p.name, "size": v.size,
                      "unit_price_paise": price, "quantity": c.quantity, "line_total_paise": price * c.quantity,
                      "available": max(0, available), "in_stock": ok})
    shipping = shipping_for(ctx, subtotal)
    return {"items": items, "subtotal_paise": subtotal, "shipping_paise": shipping, "total_paise": subtotal + shipping,
            "has_issues": issues, "requires_screening": needs_screening}


def put_cart_item(db, user_id, variant_id, quantity: int) -> None:
    v = db.get(ProductVariant, variant_id)
    if v is None or not v.product.active:
        raise ApiError(404, "not_found", "Product not found.")
    if v.stock < quantity:
        raise ApiError(409, "insufficient_stock", f"Only {max(v.stock, 0)} left in size {v.size}.", {"available": v.stock})
    item = db.scalar(select(CartItem).where(CartItem.user_id == user_id, CartItem.variant_id == variant_id))
    if item:
        item.quantity = quantity
    else:
        db.add(CartItem(user_id=user_id, variant_id=variant_id, quantity=quantity))
    db.commit()


def remove_cart_item(db, user_id, variant_id) -> None:
    item = db.scalar(select(CartItem).where(CartItem.user_id == user_id, CartItem.variant_id == variant_id))
    if item:
        db.delete(item)
        db.commit()
