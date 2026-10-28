"""Shopping cart endpoints and checkout."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..audit import log_event
from ..database import get_db
from ..deps import get_auth
from ..models import Address, CartItem, Order, OrderItem, Product, User, utcnow
from ..schemas import (
    CartItemAdd,
    CartItemOut,
    CartItemUpdate,
    CartOut,
    CheckoutRequest,
    ProductOut,
)

router = APIRouter()


def _current_user_dep(auth: tuple = Depends(get_auth)) -> User:
    user, _payload = auth
    return user


def _cart_out(db: Session, user: User) -> CartOut:
    items = (
        db.query(CartItem)
        .filter(CartItem.user_id == user.id)
        .order_by(CartItem.id)
        .all()
    )
    total = 0
    out_items = []
    for item in items:
        subtotal = item.product.price_cents * item.quantity
        total += subtotal
        out_items.append(
            CartItemOut(
                id=item.id,
                product=ProductOut.model_validate(item.product),
                quantity=item.quantity,
                subtotal_cents=subtotal,
            )
        )
    return CartOut(items=out_items, total_cents=total)


@router.get("", response_model=CartOut)
def get_cart(user: User = Depends(_current_user_dep), db: Session = Depends(get_db)):
    return _cart_out(db, user)


@router.post("/items", response_model=CartOut, status_code=201)
def add_item(
    body: CartItemAdd,
    request: Request,
    user: User = Depends(_current_user_dep),
    db: Session = Depends(get_db),
):
    """Add a product to the cart (merges quantity if already present)."""
    product = db.query(Product).filter(Product.id == body.product_id).first()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    item = (
        db.query(CartItem)
        .filter(CartItem.user_id == user.id, CartItem.product_id == body.product_id)
        .first()
    )
    if item:
        item.quantity += body.quantity
    else:
        item = CartItem(user_id=user.id, product_id=body.product_id, quantity=body.quantity)
        db.add(item)
    db.commit()

    log_event(
        db, request, "cart_updated",
        pseudo_user=user.pseudo_id,
        details={"product_id": body.product_id, "quantity": item.quantity, "action": "add"},
    )
    return _cart_out(db, user)


def _get_owned_cart_item(db: Session, user: User, item_id: int) -> CartItem:
    item = (
        db.query(CartItem)
        .filter(CartItem.id == item_id, CartItem.user_id == user.id)
        .first()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Cart item not found")
    return item


@router.patch("/items/{item_id}", response_model=CartOut)
def update_item(
    item_id: int,
    body: CartItemUpdate,
    request: Request,
    user: User = Depends(_current_user_dep),
    db: Session = Depends(get_db),
):
    item = _get_owned_cart_item(db, user, item_id)
    item.quantity = body.quantity
    db.commit()
    log_event(
        db, request, "cart_updated",
        pseudo_user=user.pseudo_id,
        details={"item_id": item.id, "quantity": item.quantity, "action": "update"},
    )
    return _cart_out(db, user)


@router.delete("/items/{item_id}", response_model=CartOut)
def remove_item(
    item_id: int,
    request: Request,
    user: User = Depends(_current_user_dep),
    db: Session = Depends(get_db),
):
    item = _get_owned_cart_item(db, user, item_id)
    db.delete(item)
    db.commit()
    log_event(
        db, request, "cart_updated",
        pseudo_user=user.pseudo_id,
        details={"product_id": item.product_id, "action": "remove"},
    )
    return _cart_out(db, user)


@router.post("/checkout", response_model=dict)
def checkout(
    body: CheckoutRequest,
    request: Request,
    user: User = Depends(_current_user_dep),
    db: Session = Depends(get_db),
):
    """Create an order from the cart; clears the cart and decrements stock.

    payment_method_display is a synthetic display string only (e.g.
    "card ending 4242"); no real payment data is ever processed or stored.
    """
    address = (
        db.query(Address)
        .filter(Address.id == body.shipping_address_id, Address.user_id == user.id)
        .first()
    )
    if address is None:
        raise HTTPException(status_code=404, detail="Shipping address not found")

    items = (
        db.query(CartItem)
        .filter(CartItem.user_id == user.id)
        .order_by(CartItem.id)
        .all()
    )
    if not items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    # Stock check first so we fail without side effects.
    for item in items:
        product = item.product
        if product is None:
            raise HTTPException(status_code=400, detail="Product no longer exists")
        if product.stock < item.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock for {product.name}",
            )

    total = 0
    order = Order(
        user_id=user.id,
        status="placed",
        total_cents=0,
        payment_method=body.payment_method_display,
    )
    db.add(order)
    db.flush()

    for item in items:
        product = item.product
        product.stock -= item.quantity
        line_total = product.price_cents * item.quantity
        total += line_total
        db.add(
            OrderItem(
                order_id=order.id,
                product_id=product.id,
                name_snapshot=product.name,
                price_cents=product.price_cents,
                quantity=item.quantity,
            )
        )
    order.total_cents = total

    # Clear the cart.
    for item in items:
        db.delete(item)

    db.commit()
    db.refresh(order)

    log_event(
        db, request, "order_placed",
        pseudo_user=user.pseudo_id,
        details={"order_id": order.id, "total_cents": order.total_cents},
    )
    return {"order": {"id": order.id, "status": order.status,
                      "total_cents": order.total_cents}}
