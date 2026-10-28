import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, formatPrice } from "../api";
import type { Order } from "../types";
import {
  Badge,
  Button,
  EmptyState,
  ErrorBox,
  LoadingScreen,
  statusColor,
} from "../components/ui";
import { PageTitle } from "../layout";
import { formatDate } from "../utils";

export function OrdersPage() {
  const [orders, setOrders] = useState<Order[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Order[]>("/api/orders")
      .then((o) => setOrders(Array.isArray(o) ? o : []))
      .catch((e) => setError(e?.message ?? "Failed to load orders"));
  }, []);

  if (error) return <ErrorBox message={error} />;
  if (!orders) return <LoadingScreen message="Loading your orders…" />;

  if (orders.length === 0) {
    return (
      <EmptyState
        icon="📦"
        title="No orders yet"
        subtitle="When you place an order it will show up here."
        action={
          <Link to="/">
            <Button>Start shopping</Button>
          </Link>
        }
      />
    );
  }

  return (
    <div>
      <PageTitle title="Your Orders" />
      <div className="space-y-4">
        {orders.map((order) => (
          <Link
            key={order.id}
            to={`/orders/${order.id}`}
            className="block rounded-xl border border-gray-200 bg-white shadow-sm transition hover:shadow-md"
          >
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-t-xl border-b border-gray-200 bg-gray-50 px-5 py-3 text-sm">
              <div className="flex flex-wrap gap-x-8 gap-y-1">
                <div>
                  <p className="text-xs uppercase text-slate-500">Order placed</p>
                  <p className="font-medium text-slate-800">{formatDate(order.created_at)}</p>
                </div>
                <div>
                  <p className="text-xs uppercase text-slate-500">Total</p>
                  <p className="font-medium text-slate-800">{formatPrice(order.total_cents)}</p>
                </div>
                <div>
                  <p className="text-xs uppercase text-slate-500">Order #</p>
                  <p className="font-mono font-medium text-slate-800">{order.id}</p>
                </div>
              </div>
              <Badge color={statusColor(order.status)}>{order.status}</Badge>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-4 px-5 py-4">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-slate-700">
                  {order.items.length} item{order.items.length !== 1 ? "s" : ""}:{" "}
                  <span className="truncate font-normal text-slate-600">
                    {order.items.map((i) => i.name_snapshot).slice(0, 3).join(", ")}
                    {order.items.length > 3 && ", …"}
                  </span>
                </p>
              </div>
              <span className="text-sm font-medium text-accent hover:underline">View details →</span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

export function OrderDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [order, setOrder] = useState<Order | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    api<Order>(`/api/orders/${id}`)
      .then(setOrder)
      .catch((e) => setError(e?.message ?? "Order not found"));
  }, [id]);

  if (error)
    return (
      <div className="mx-auto max-w-md py-10 text-center">
        <ErrorBox message={error} />
        <Link to="/orders" className="mt-4 inline-block text-sm font-medium text-accent hover:underline">
          ← Back to orders
        </Link>
      </div>
    );
  if (!order) return <LoadingScreen message="Loading order…" />;

  const subtotal = order.items.reduce(
    (sum, it) => sum + it.price_cents * it.quantity,
    0,
  );

  const addr = order.shipping_address as
    | {
        label?: string;
        line1?: string;
        line2?: string;
        city?: string;
        state?: string;
        postal_code?: string;
        country?: string;
      }
    | null
    | undefined;

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-4">
        <Link to="/orders" className="text-sm font-medium text-accent hover:underline">
          ← All orders
        </Link>
      </div>

      <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-green-200 bg-green-50 px-5 py-4">
        <div>
          <h1 className="text-xl font-bold text-slate-900">
            Order #{order.id}
          </h1>
          <p className="text-sm text-slate-600">Placed {formatDate(order.created_at)}</p>
        </div>
        <Badge color={statusColor(order.status)} className="text-sm">
          {order.status}
        </Badge>
      </div>

      <div className="grid gap-6 md:grid-cols-[minmax(0,7fr)_minmax(0,4fr)]">
        <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
          <h2 className="border-b border-gray-100 px-5 py-3 text-lg font-bold text-slate-900">
            Items
          </h2>
          <ul className="divide-y divide-gray-100">
            {order.items.map((item, i) => (
              <li key={i} className="flex items-center justify-between gap-4 px-5 py-4">
                <div className="min-w-0">
                  <p className="font-medium text-slate-800">{item.name_snapshot}</p>
                  <p className="text-sm text-slate-500">
                    Qty: {item.quantity} × {formatPrice(item.price_cents)}
                  </p>
                </div>
                <p className="shrink-0 font-bold text-slate-900">
                  {formatPrice(item.price_cents * item.quantity)}
                </p>
              </li>
            ))}
          </ul>
          <div className="flex justify-between border-t border-gray-200 px-5 py-4">
            <span className="font-bold text-slate-900">Total</span>
            <span className="font-bold text-slate-900">{formatPrice(order.total_cents)}</span>
          </div>
        </div>

        <div className="space-y-4">
          {addr && (addr.line1 || addr.label) && (
            <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
              <h3 className="mb-2 text-sm font-bold uppercase tracking-wide text-slate-500">
                Shipping address
              </h3>
              <p className="text-sm leading-relaxed text-slate-700">
                {addr.label && <span className="font-semibold">{addr.label}<br /></span>}
                {addr.line1}<br />
                {addr.line2 && <>{addr.line2}<br /></>}
                {addr.city}
                {addr.state ? `, ${addr.state}` : ""} {addr.postal_code}
                {addr.country && <><br />{addr.country}</>}
              </p>
            </div>
          )}
          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm text-sm">
            <h3 className="mb-2 text-sm font-bold uppercase tracking-wide text-slate-500">
              Payment
            </h3>
            <p className="text-slate-700">
              {order.payment_method_display ?? "Synthetic payment method"}
            </p>
            <dl className="mt-3 space-y-1 text-slate-600">
              <div className="flex justify-between">
                <dt>Items subtotal</dt>
                <dd>{formatPrice(subtotal)}</dd>
              </div>
              <div className="flex justify-between">
                <dt>Shipping</dt>
                <dd className="text-green-700">FREE</dd>
              </div>
            </dl>
          </div>
          <Button variant="outline" className="w-full" onClick={() => navigate("/")}>
            Reorder these picks
          </Button>
        </div>
      </div>
    </div>
  );
}
