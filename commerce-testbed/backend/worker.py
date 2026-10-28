"""FastAPI Worker; Cloudflare serves React assets outside the API routes."""

from workers import asgi
from app.database import configure_hyperdrive

# Configure before importing routers that capture the session factory.
configure_hyperdrive()

from app.main import app  # noqa: E402

Default = asgi.entrypoint(app)
