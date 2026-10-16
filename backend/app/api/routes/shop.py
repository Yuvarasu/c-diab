from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import Principal, current_user, get_ctx, get_db
from app.context import AppContext
from app.schemas.api import CartOut, CartPut, ProductOut
from app.services import shop

router = APIRouter(tags=["shop"])


@router.get("/products", response_model=list[ProductOut])
def products(_: Principal = Depends(current_user), db: Session = Depends(get_db)):
    return [shop.product_out(p) for p in shop.list_products(db)]


@router.get("/products/{product_id}", response_model=ProductOut)
def product(product_id: UUID, _: Principal = Depends(current_user), db: Session = Depends(get_db)):
    return shop.product_out(shop.get_active_product(db, product_id))


@router.get("/cart", response_model=CartOut)
def get_cart(user: Principal = Depends(current_user), db: Session = Depends(get_db), ctx: AppContext = Depends(get_ctx)):
    return shop.cart_out(ctx, db, user.id)


@router.put("/cart/items", response_model=CartOut)
def put_item(body: CartPut, user: Principal = Depends(current_user), db: Session = Depends(get_db),
             ctx: AppContext = Depends(get_ctx)):
    shop.put_cart_item(db, user.id, body.variant_id, body.quantity)
    return shop.cart_out(ctx, db, user.id)


@router.delete("/cart/items/{variant_id}", response_model=CartOut)
def delete_item(variant_id: UUID, user: Principal = Depends(current_user), db: Session = Depends(get_db),
                ctx: AppContext = Depends(get_ctx)):
    shop.remove_cart_item(db, user.id, variant_id)
    return shop.cart_out(ctx, db, user.id)
