import os
from contextvars import ContextVar, Token
from typing import Iterator

from sqlalchemy import case, create_engine, or_, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from .config import get_settings
from .models import Base, Product
from .product_images import PRODUCT_IMAGES

_settings = get_settings()


def _database_url(value: str):
    """Use the existing psycopg 3 driver for Neon PostgreSQL URLs."""
    url = make_url(value)
    if url.drivername in ("postgres", "postgresql"):
        url = url.set(drivername="postgresql+psycopg")
    return url


_is_sqlite = _settings.DATABASE_URL.startswith("sqlite")

engine = create_engine(
    _database_url(_settings.DATABASE_URL),
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
_worker_mode = False
_worker_hyperdrive: ContextVar[object | None] = ContextVar(
    "commerce_testbed_hyperdrive", default=None
)
_database_initialized = False


def configure_hyperdrive() -> None:
    """Configure SQLAlchemy to open PostgreSQL connections through Hyperdrive."""
    global engine, _worker_mode

    import pg8000.dbapi

    def connect_from_hyperdrive():
        binding = _worker_hyperdrive.get()
        if binding is None:
            raise RuntimeError("Hyperdrive is unavailable for this request")
        return pg8000.dbapi.connect(
            host=binding.host,
            port=int(binding.port),
            user=binding.user,
            password=binding.password,
            database=binding.database,
            ssl_context=False,
        )

    engine = create_engine(
        "postgresql+pg8000://",
        creator=connect_from_hyperdrive,
        poolclass=NullPool,
    )
    SessionLocal.configure(bind=engine)
    _worker_mode = True


def bind_hyperdrive(binding: object) -> Token[object | None]:
    return _worker_hyperdrive.set(binding)


def reset_hyperdrive(token: Token[object | None]) -> None:
    _worker_hyperdrive.reset(token)


def is_worker_mode() -> bool:
    return _worker_mode


def _sqlite_path() -> str | None:
    """Extract filesystem path from a sqlite URL, or None (memory/other dialect)."""
    if engine.dialect.name != "sqlite":
        return None
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

    # Schema setup uses Neon's direct connection; normal queries stay pooled.
    schema_engine = engine
    if not _worker_mode and engine.dialect.name == "postgresql" and _settings.DATABASE_URL_UNPOOLED:
        schema_engine = create_engine(_database_url(_settings.DATABASE_URL_UNPOOLED), poolclass=NullPool)
    try:
        _initialize_schema(schema_engine)
    finally:
        if schema_engine is not engine:
            schema_engine.dispose()


def _initialize_schema(schema_engine) -> None:
    with schema_engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            # Serialize schema/catalog setup across simultaneously starting Workers.
            connection.execute(text("SELECT pg_advisory_xact_lock(73420819)"))
        Base.metadata.create_all(connection)
        with Session(bind=connection, expire_on_commit=False) as db:
            if db.query(Product).count() == 0:
                _seed_products(db)
        # Backfill legacy random photos atomically without touching prices or stock.
        connection.execute(update(Product).where(
            Product.name.in_(PRODUCT_IMAGES),
            or_(Product.image_url.like("https://picsum.photos/%"), Product.image_url == "", Product.image_url.is_(None)),
        ).values(image_url=case(PRODUCT_IMAGES, value=Product.name)))


def ensure_db_initialized() -> None:
    """Initialize once on the first Worker request, when bindings are available."""
    global _database_initialized
    if not _database_initialized:
        init_db()
        _database_initialized = True


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
        product.image_url = PRODUCT_IMAGES[name]
    db.commit()


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
