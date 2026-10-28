import os
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings
from .models import Base, Product

_settings = get_settings()

_is_sqlite = _settings.DATABASE_URL.startswith("sqlite")

engine = create_engine(
    _settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _sqlite_path() -> str | None:
    """Extract filesystem path from a sqlite URL, or None (memory/other dialect)."""
    url = _settings.DATABASE_URL
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return None
    path = url[len(prefix):]
    if path == "" or path == ":memory:":
        return None
    return path


def init_db() -> None:
    """Create tables and seed default products if the product table is empty."""
    path = _sqlite_path()
    if path:
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)

    from . import seed_data  # noqa: F401  (ensures module importable)

    Base.metadata.create_all(engine)

    with SessionLocal() as db:
        if db.query(Product).count() == 0:
            _seed_products(db)


def _seed_products(db: Session) -> None:
    from .seed_data import PRODUCTS

    for name, category, price_cents, description, stock in PRODUCTS:
        product = Product(
            name=name,
            category=category,
            price_cents=price_cents,
            description=description,
            stock=stock,
        )
        db.add(product)
        # Flush to obtain the id for a stable image URL.
        db.flush()
        product.image_url = f"https://picsum.photos/seed/{product.id}/400/300"
    db.commit()


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
