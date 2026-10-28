export interface User {
  id: string;
  email: string;
  full_name: string;
  phone?: string | null;
  is_admin: boolean;
}

export interface Product {
  id: string;
  name: string;
  description: string;
  category: string;
  price_cents: number;
  image_url: string;
}

export interface CartItem {
  id: string;
  product: Product;
  quantity: number;
  subtotal_cents: number;
}

export interface Cart {
  items: CartItem[];
  total_cents: number;
}

export interface Address {
  id: string;
  label: string;
  line1: string;
  line2: string;
  city: string;
  state: string;
  postal_code: string;
  country: string;
  is_default: boolean;
}

export interface Session {
  id: string;
  created_at: string;
  expires_at: string;
  revoked: boolean;
  ip?: string | null;
  user_agent?: string | null;
}

export interface OrderItem {
  name_snapshot: string;
  price_cents: number;
  quantity: number;
}

export interface Order {
  id: string;
  created_at: string;
  status: string;
  total_cents: number;
  items: OrderItem[];
  payment_method_display?: string | null;
  shipping_address?: Record<string, unknown> | null;
  [key: string]: unknown;
}

export type ApiKeyEnvironment = "development" | "production";

export type ApiKeyStatus = "active" | "expired" | "revoked";

export interface ApiKey {
  id: string;
  key_id: string;
  name: string;
  environment: ApiKeyEnvironment;
  scopes: string[];
  visible_prefix: string;
  status: ApiKeyStatus;
  created_at: string;
  expires_at?: string | null;
  revoked_at?: string | null;
  last_used_at?: string | null;
}

export interface ApiKeySecret {
  key: ApiKey;
  /** Full plaintext key — returned only on create/rotate, never again. */
  secret: string;
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
