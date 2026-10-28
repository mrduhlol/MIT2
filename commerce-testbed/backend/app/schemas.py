from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# ---------- Auth ----------

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1, max_length=255)

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    phone: str | None
    pseudo_id: str
    created_at: datetime
    is_active: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)

    @field_validator("new_password")
    @classmethod
    def new_password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v


# ---------- Profile ----------

class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=64)


# ---------- Addresses ----------

class AddressIn(BaseModel):
    label: str = Field(min_length=1, max_length=64)
    line1: str = Field(min_length=1, max_length=255)
    line2: str | None = None
    city: str = Field(min_length=1, max_length=128)
    state: str = Field(min_length=1, max_length=128)
    postal_code: str = Field(min_length=1, max_length=32)
    country: str = Field(min_length=1, max_length=128)
    is_default: bool = False


class AddressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    label: str
    line1: str
    line2: str | None
    city: str
    state: str
    postal_code: str
    country: str
    is_default: bool


# ---------- Sessions ----------

class SessionOut(BaseModel):
    id: int
    created_at: datetime
    expires_at: datetime
    revoked: bool
    ip: str | None
    user_agent: str | None


# ---------- Products ----------

class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    category: str
    price_cents: int
    image_url: str
    stock: int


class ProductListResponse(BaseModel):
    items: list[ProductOut]
    total: int
    page: int
    page_size: int


# ---------- Cart ----------

class CartItemAdd(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1)


class CartItemUpdate(BaseModel):
    quantity: int = Field(ge=1)


class CartItemOut(BaseModel):
    id: int
    product: ProductOut
    quantity: int
    subtotal_cents: int


class CartOut(BaseModel):
    items: list[CartItemOut]
    total_cents: int


# ---------- Orders ----------

class CheckoutRequest(BaseModel):
    shipping_address_id: int
    payment_method_display: str = Field(min_length=1, max_length=128)


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    name_snapshot: str
    price_cents: int
    quantity: int


class OrderOut(BaseModel):
    id: int
    created_at: datetime
    status: str
    total_cents: int
    payment_method: str
    items: list[OrderItemOut]


# ---------- Security events ----------

class EventOut(BaseModel):
    ts: str
    request_id: str | None
    source: str
    event_type: str
    severity: str
    pseudo_user: str | None
    ip: str | None
    user_agent: str | None
    details: dict[str, Any] | str | None


class FeedResponse(BaseModel):
    events: list[EventOut]
