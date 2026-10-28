import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, formatPrice } from "../api";
import { useAuth } from "../context/AuthContext";
import { syncCartCount } from "../layout";
import type { Cart, Product } from "../types";
import {
  Badge,
  Button,
  ErrorBox,
  LoadingScreen,
  ProductImage,
} from "../components/ui";

export function ProductPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { token } = useAuth();
  const [product, setProduct] = useState<Product | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [quantity, setQuantity] = useState(1);
  const [busy, setBusy] = useState(false);
  const [added, setAdded] = useState(false);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    setError(null);
    api<Product>(`/api/products/${id}`)
      .then(setProduct)
      .catch((e) => setError(e?.message ?? "Product not found"))
      .finally(() => setLoading(false));
  }, [id]);

  async function onAdd() {
    if (!id) return;
    if (!token) {
      navigate(`/login?next=${encodeURIComponent(`/product/${id}`)}`);
      return;
    }
    setBusy(true);
    try {
      const cart = await api<Cart>("/api/cart/items", {
        method: "POST",
        body: { product_id: id, quantity },
      });
      syncCartCount(cart.items.reduce((s, it) => s + it.quantity, 0));
      setAdded(true);
      setTimeout(() => setAdded(false), 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add to cart");
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <LoadingScreen message="Loading product…" />;
  if (error)
    return (
      <div className="mx-auto max-w-md py-10 text-center">
        <ErrorBox message={error} />
        <Link to="/" className="mt-4 inline-block text-sm font-medium text-accent hover:underline">
          ← Back to shopping
        </Link>
      </div>
    );
  if (!product) return null;

  return (
    <div>
      <nav className="mb-4 text-sm text-slate-500">
        <Link to="/" className="hover:text-accent hover:underline">Home</Link>
        <span className="mx-1.5">/</span>
        <Link to={`/?category=${encodeURIComponent(product.category)}`} className="hover:text-accent hover:underline">
          {product.category}
        </Link>
        <span className="mx-1.5">/</span>
        <span className="text-slate-700">{product.name}</span>
      </nav>

      <div className="grid gap-8 rounded-xl border border-gray-200 bg-white p-6 shadow-sm md:grid-cols-2 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <div className="flex aspect-square items-center justify-center overflow-hidden rounded-xl bg-gray-50 p-8">
          <ProductImage src={product.image_url} alt={product.name} className="h-full w-full" />
        </div>

        <div className="flex flex-col">
          <Badge color="amber" className="w-fit">{product.category}</Badge>
          <h1 className="mt-2 text-2xl font-bold text-slate-900">{product.name}</h1>
          <p className="mt-1 text-sm text-slate-500">
            Sold by ShopZone · <span className="text-green-700">In stock</span>
          </p>

          <div className="my-4 border-y border-gray-100 py-4">
            <span className="text-3xl font-bold text-slate-900">
              {formatPrice(product.price_cents)}
            </span>
            <span className="ml-2 text-sm text-slate-400">
              ({formatPrice(product.price_cents)} each, no real charges)
            </span>
          </div>

          <p className="whitespace-pre-line leading-relaxed text-slate-600">
            {product.description || "No description available."}
          </p>

          <div className="mt-auto flex flex-wrap items-center gap-3 pt-6">
            <div className="flex items-center rounded-lg border border-gray-300 shadow-sm">
              <button
                onClick={() => setQuantity((n) => Math.max(1, n - 1))}
                className="px-3 py-2 text-lg text-slate-600 hover:bg-gray-50"
                aria-label="Decrease quantity"
              >
                −
              </button>
              <input
                type="number"
                min={1}
                max={99}
                value={quantity}
                onChange={(e) =>
                  setQuantity(Math.min(99, Math.max(1, Number(e.target.value) || 1)))
                }
                className="w-12 border-0 text-center text-sm focus:outline-none focus:ring-0"
                aria-label="Quantity"
              />
              <button
                onClick={() => setQuantity((n) => Math.min(99, n + 1))}
                className="px-3 py-2 text-lg text-slate-600 hover:bg-gray-50"
                aria-label="Increase quantity"
              >
                +
              </button>
            </div>
            <Button size="lg" loading={busy} onClick={onAdd}>
              {added ? "✓ Added to cart" : "Add to cart"}
            </Button>
            {added && (
              <Button variant="outline" size="lg" onClick={() => navigate("/cart")}>
                Go to cart →
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
