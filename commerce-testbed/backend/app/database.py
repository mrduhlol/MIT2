import os
from contextvars import ContextVar, Token
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from .config import get_settings
from .models import Base, Product

_settings = get_settings()

_is_sqlite = _settings.DATABASE_URL.startswith("sqlite")

engine = create_engine(
    _settings.DATABASE_URL,
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

    import psycopg

    def connect_from_hyperdrive():
        binding = _worker_hyperdrive.get()
        if binding is None:
            raise RuntimeError("Hyperdrive is unavailable for this request")
        return psycopg.connect(
            host=binding.host,
            port=int(binding.port),
            user=binding.user,
            password=binding.password,
            dbname=binding.database,
            sslmode="disable",
        )

    engine = create_engine(
        "postgresql+psycopg://",
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

    with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            # Serialize schema/catalog setup across simultaneously starting Workers.
            connection.execute(text("SELECT pg_advisory_xact_lock(73420819)"))
        Base.metadata.create_all(connection)
        with Session(bind=connection, expire_on_commit=False) as db:
            if db.query(Product).count() == 0:
                _seed_products(db)


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
