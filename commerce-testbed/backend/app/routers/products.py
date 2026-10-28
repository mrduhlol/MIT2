"""Product catalog endpoints (public)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Product
from ..schemas import ProductListResponse, ProductOut

router = APIRouter()


@router.get("", response_model=ProductListResponse)
def list_products(
    q: str | None = None,
    category: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
):
    """List products with optional search (q), category filter, and paging."""
    page = max(1, page)
    page_size = min(max(1, page_size), 100)

    query = db.query(Product)
    if q:
        like = f"%{q}%"
        query = query.filter(Product.name.ilike(like) | Product.description.ilike(like))
    if category:
        query = query.filter(Product.category == category)

    total = query.count()
    items = (
        query.order_by(Product.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ProductListResponse(
        items=[ProductOut.model_validate(p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/categories", response_model=list[str])
def list_categories(db: Session = Depends(get_db)):
    rows = db.query(Product.category).distinct().order_by(Product.category).all()
    return [r[0] for r in rows]


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product
