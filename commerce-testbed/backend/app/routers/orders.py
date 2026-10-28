"""Order listing and detail endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_auth
from ..models import Order, User
from ..schemas import OrderItemOut, OrderOut

router = APIRouter()


def _current_user_dep(auth: tuple = Depends(get_auth)) -> User:
    user, _payload = auth
    return user


def _order_out(order: Order) -> OrderOut:
    return OrderOut(
        id=order.id,
        created_at=order.created_at,
        status=order.status,
        total_cents=order.total_cents,
        payment_method=order.payment_method,
        items=[OrderItemOut.model_validate(i) for i in order.items],
    )


@router.get("", response_model=list[OrderOut])
def list_orders(user: User = Depends(_current_user_dep), db: Session = Depends(get_db)):
    """List the current user's orders, newest first."""
    orders = (
        db.query(Order)
        .filter(Order.user_id == user.id)
        .order_by(Order.created_at.desc(), Order.id.desc())
        .all()
    )
    return [_order_out(o) for o in orders]


@router.get("/{order_id}", response_model=OrderOut)
def get_order(
    order_id: int,
    user: User = Depends(_current_user_dep),
    db: Session = Depends(get_db),
):
    order = (
        db.query(Order)
        .filter(Order.id == order_id, Order.user_id == user.id)
        .first()
    )
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return _order_out(order)
