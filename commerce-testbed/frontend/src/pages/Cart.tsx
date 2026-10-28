import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, formatPrice } from "../api";
import type { Address, Cart, Order } from "../types";
import { useAuth } from "../context/AuthContext";
import { syncCartCount } from "../layout";
import {
  Button,
  Card,
  EmptyState,
  ErrorBox,
  Input,
  LoadingScreen,
  ProductImage,
  Select,
} from "../components/ui";

interface CheckoutSuccess {
  order: Order;
}

export function CartPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [cart, setCart] = useState<Cart | null>(null);
  const [addresses, setAddresses] = useState<Address[]>([]);
  const [addressId, setAddressId] = useState("");
  const [payment, setPayment] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [checkoutError, setCheckoutError] = useState<string | null>(null);
  const [placing, setPlacing] = useState(false);
  const [success, setSuccess] = useState<CheckoutSuccess | null>(null);

  async function reloadCart() {
    try {
      const data = await api<Cart>("/api/cart");
      setCart(data);
      syncCartCount(data.items.reduce((s, it) => s + it.quantity, 0));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load cart");
    }
  }

  useEffect(() => {
    (async () => {
      await reloadCart();
      try {
        const list = await api<Address[]>("/api/me/addresses");
        setAddresses(list);
        const preferred = list.find((a) => a.is_default) ?? list[0];
        if (preferred) setAddressId(preferred.id);
      } catch {
        /* addresses optional until checkout */
      }
      setLoading(false);
    })();
  }, []);

  if (loading) return <LoadingScreen message="Loading your cart…" />;

  /* ----------------------------- success screen ----------------------------- */
  if (success) {
    return (
      <div className="mx-auto max-w-xl py-10 text-center">
        <div className="rounded-xl border border-green-200 bg-white p-10 shadow-md">
          <div className="mx-auto mb-4 grid h-16 w-16 place-items-center rounded-full bg-green-100 text-3xl">
            ✓
          </div>
          <h1 className="text-2xl font-bold text-slate-900">Order placed!</h1>
          <p className="mt-2 text-slate-600">
            Thanks{user?.full_name ? "," + " " + user.full_name : ""}! Your order{" "}
            <span className="font-mono font-semibold text-slate-900">
              #{success.order.id.slice(0, 8)}
            </span>{" "}
            has been received. (This is a testbed — nothing was actually charged.)
          </p>
          <div className="mt-6 flex justify-center gap-3">
            <Button variant="secondary" onClick={() => navigate(`/orders/${success.order.id}`)}>
              View order
            </Button>
            <Button variant="outline" onClick={() => navigate("/")}>
              Keep shopping
            </Button>
          </div>
        </div>
      </div>
    );
  }

  if (error) return <ErrorBox message={error} />;

  if (!cart || cart.items.length === 0) {
    return (
      <EmptyState
        icon="🛒"
        title="Your cart is empty"
        subtitle="Browse the catalog and add some products."
        action={
          <Button onClick={() => navigate("/")}>
            Start shopping
          </Button>
        }
      />
    );
  }

  async function setQty(itemId: string, quantity: number) {
    setCart((c) =>
      c
        ? {
            ...c,
            items: c.items.map((it) =>
              it.id === itemId ? { ...it, quantity: Math.max(1, quantity) } : it,
            ),
          }
        : c,
    );
    try {
      await api(`/api/cart/items/${itemId}`, { method: "PATCH", body: { quantity } });
      await reloadCart();
    } catch {
      await reloadCart();
    }
  }

  async function removeItem(itemId: string) {
    setCart((c) =>
      c
        ? {
            ...c,
            items: c.items.filter((it) => it.id !== itemId),
            total_cents: c.total_cents - (c.items.find((i) => i.id === itemId)?.subtotal_cents ?? 0),
          }
        : c,
    );
    try {
      await api(`/api/cart/items/${itemId}`, { method: "DELETE" });
      await reloadCart();
    } catch {
      await reloadCart();
    }
  }

  async function checkout() {
    setCheckoutError(null);
    if (!addressId) {
      setCheckoutError("Select a shipping address, or add one from Your Account → Addresses.");
      return;
    }
    if (!payment.trim()) {
      setCheckoutError("Enter a (synthetic) payment method, e.g. “Card ending 4242”.");
      return;
    }
    setPlacing(true);
    try {
      const order = await api<Order>("/api/cart/checkout", {
        method: "POST",
        body: { shipping_address_id: addressId, payment_method_display: payment.trim() },
      });
      syncCartCount(0);
      setSuccess({ order });
    } catch (e) {
      setCheckoutError(e instanceof Error ? e.message : "Checkout failed");
    } finally {
      setPlacing(false);
    }
  }

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold text-slate-900">Shopping Cart</h1>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,8fr)_minmax(0,4fr)]">
        {/* line items */}
        <div className="divide-y divide-gray-100 rounded-xl border border-gray-200 bg-white shadow-sm">
          {cart.items.map((item) => (
            <div key={item.id} className="flex gap-4 p-4 sm:p-5">
              <Link
                to={`/product/${item.product.id}`}
                className="grid h-24 w-24 shrink-0 place-items-center rounded-lg bg-gray-50 p-2"
              >
                <ProductImage
                  src={item.product.image_url}
                  alt={item.product.name}
                  className="max-h-full max-w-full"
                />
              </Link>
              <div className="flex min-w-0 flex-1 flex-col">
                <Link
                  to={`/product/${item.product.id}`}
                  className="line-clamp-2 font-semibold text-slate-800 hover:text-accent hover:underline"
                >
                  {item.product.name}
                </Link>
                <p className="mt-0.5 text-xs uppercase tracking-wide text-slate-400">
                  {item.product.category}
                </p>
                <p className="mt-1 text-green-700 text-sm">
                  In stock · {formatPrice(item.product.price_cents)} each
                </p>
                <div className="mt-auto flex items-center gap-3 pt-3">
                  <div className="flex items-center overflow-hidden rounded-lg border border-gray-300">
                    <button
                      onClick={() => setQty(item.id, item.quantity - 1)}
                      className="px-2.5 py-1 text-slate-600 hover:bg-gray-50 disabled:opacity-40"
                      aria-label="Decrease quantity"
                    >
                      −
                    </button>
                    <span className="w-8 text-center text-sm font-medium">
                      {item.quantity}
                    </span>
                    <button
                      onClick={() => setQty(item.id, item.quantity + 1)}
                      className="px-2.5 py-1 text-slate-600 hover:bg-gray-50"
                      aria-label="Increase quantity"
                    >
                      +
                    </button>
                  </div>
                  <button
                    onClick={() => removeItem(item.id)}
                    className="text-sm font-medium text-red-500 hover:underline"
                  >
                    Remove
                  </button>
                </div>
              </div>
              <p className="shrink-0 text-right font-bold text-slate-900">
                {formatPrice(item.subtotal_cents)}
              </p>
            </div>
          ))}
        </div>

        {/* summary */}
        <div className="space-y-4">
          <Card>
            <h2 className="mb-4 text-lg font-bold text-slate-900">Order Summary</h2>
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-slate-600">
                  Items ({cart.items.reduce((s, it) => s + it.quantity, 0)})
                </dt>
                <dd className="font-medium">{formatPrice(cart.total_cents)}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-slate-600">Shipping</dt>
                <dd className="font-medium text-green-700">FREE</dd>
              </div>
              <div className="flex justify-between border-t border-gray-200 pt-3 text-base">
                <dt className="font-bold text-slate-900">Order total</dt>
                <dd className="font-bold text-slate-900">{formatPrice(cart.total_cents)}</dd>
              </div>
            </dl>
          </Card>

          <Card>
            <h2 className="mb-4 text-lg font-bold text-slate-900">Shipping & Payment</h2>
            <div className="space-y-4">
              <Select
                label="Ship to"
                value={addressId}
                onChange={(e) => setAddressId(e.target.value)}
              >
                {addresses.length === 0 && <option value="">No saved addresses</option>}
                {addresses.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.is_default ? "★ " : ""}
                    {a.label} — {a.line1}, {a.city} {a.postal_code}
                  </option>
                ))}
              </Select>
              {addresses.length === 0 && (
                <p className="text-xs text-slate-500">
                  No addresses yet —{" "}
                  <Link to="/account/addresses" className="font-medium text-accent hover:underline">
                    add one in Account → Addresses
                  </Link>{" "}
                  to place an order.
                </p>
              )}
              <Input
                label="Payment method (synthetic)"
                type="text"
                placeholder="Card ending 4242"
                value={payment}
                onChange={(e) => setPayment(e.target.value)}
              />
              <p className="text-xs text-slate-500">
                🧪 This is a hackathon testbed — payment details are purely textual, no real
                transactions occur.
              </p>
              {checkoutError && <ErrorBox message={checkoutError} />}
              <Button className="w-full" size="lg" loading={placing} onClick={checkout}>
                Place your order
              </Button>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
