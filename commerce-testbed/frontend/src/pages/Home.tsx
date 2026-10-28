import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, formatPrice } from "../api";
import { useAuth } from "../context/AuthContext";
import { syncCartCount } from "../layout";
import type { Paginated, Product } from "../types";
import {
  Button,
  EmptyState,
  ErrorBox,
  LoadingScreen,
  ProductImage,
} from "../components/ui";
import { cn } from "../utils";

function addToCart(productId: string, quantity = 1) {
  return api("/api/cart/items", { method: "POST", body: { product_id: productId, quantity } });
}

/* ------------------------------- ProductCard ------------------------------- */

export function ProductCard({ product }: { product: Product }) {
  const { token } = useAuth();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [added, setAdded] = useState(false);

  async function onAdd(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (!token) {
      navigate(`/login?next=${encodeURIComponent("/product/" + product.id)}`);
      return;
    }
    setBusy(true);
    try {
      const cart = await addToCart(product.id, 1);
      syncCartCount(
        (cart as { items: { quantity: number }[] }).items.reduce(
          (s, it) => s + it.quantity,
          0,
        ),
      );
      setAdded(true);
      setTimeout(() => setAdded(false), 1500);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Link
      to={`/product/${product.id}`}
      className="group flex flex-col overflow-hidden rounded-xl border border-gray-200 bg-white transition-colors hover:border-teal-500"
    >
      <div className="relative flex aspect-[5/4] items-center justify-center overflow-hidden bg-gray-50 p-4">
        <ProductImage
          src={product.image_url}
          alt={product.name}
          className="h-full w-full transition-transform duration-200 group-hover:scale-105"
        />
      </div>
      <div className="flex flex-1 flex-col gap-1.5 border-t border-gray-100 p-4">
        <p className="text-xs font-medium uppercase tracking-wide text-accent">
          {product.category}
        </p>
        <h3 className="line-clamp-2 min-h-10 text-sm font-semibold text-slate-800 group-hover:text-accent">
          {product.name}
        </h3>
        <p className="text-lg font-bold text-slate-900">
          {formatPrice(product.price_cents)}
        </p>
        <div className="mt-auto pt-2">
          <Button
            size="sm"
            variant="cta"
            className="w-full"
            loading={busy}
            onClick={onAdd}
            aria-label={`Add ${product.name} to cart`}
          >
            {added ? "✓ Added to cart" : "Add to cart"}
          </Button>
        </div>
      </div>
    </Link>
  );
}

/* --------------------------------- HomePage -------------------------------- */

const PAGE_SIZE = 12;

export function HomePage() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const category = params.get("category") ?? "";
  const page = Math.max(1, Number(params.get("page") ?? "1") || 1);

  const [categories, setCategories] = useState<string[]>([]);
  const [data, setData] = useState<Paginated<Product> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);


  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    const sp = new URLSearchParams();
    if (q) sp.set("q", q);
    if (category) sp.set("category", category);
    sp.set("page", String(page));
    sp.set("page_size", String(PAGE_SIZE));
    api<Paginated<Product>>(`/api/products?${sp.toString()}`)
      .then((result) => {
        if (!result || !Array.isArray(result.items) || !Number.isFinite(result.total)) {
          throw new Error("The catalog could not be loaded. Please try again.");
        }
        if (!active) return;
        setData(result);
        // Load optional filters after products, keeping the initial request sequential.
        void api<string[]>("/api/products/categories")
          .then((values) => { if (active && Array.isArray(values)) setCategories(values); })
          .catch(() => {});
      })
      .catch((e) => { if (active) setError(e?.message ?? "Failed to load products"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [q, category, page, reload]);

  const totalPages = useMemo(
    () => (data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1),
    [data],
  );

  function update(next: { q?: string; category?: string; page?: number }) {
    const sp = new URLSearchParams();
    const nq = next.q !== undefined ? next.q : q;
    const ncat = next.category !== undefined ? next.category : category;
    const npage =
      next.page !== undefined
        ? next.page
        : next.q !== undefined || next.category !== undefined
          ? 1
          : page;
    if (nq) sp.set("q", nq);
    if (ncat) sp.set("category", ncat);
    if (npage && npage > 1) sp.set("page", String(npage));
    setParams(sp);
  }

  return (
    <div>
      <section className="mb-8 flex flex-col justify-between gap-4 border-b border-gray-200 pb-7 sm:flex-row sm:items-end">
        <div><p className="mb-2 text-sm font-medium text-accent">Your everyday shop</p>
          <h1 className="text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">Find a little something.</h1>
          <p className="mt-3 max-w-xl text-sm leading-relaxed text-slate-500">Explore essentials for home, work, and everything in between.</p>
        </div>
        {(q || category) && <Button variant="outline" onClick={() => setParams(new URLSearchParams())}>Clear filters</Button>}
      </section>
      <div className="mb-5 flex flex-wrap gap-2">
        <button
          onClick={() => update({ category: "", page: 1 })}
          className={cn(
            "rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors",
            !category
              ? "border-accent bg-teal-50 text-accent"
              : "border-gray-300 bg-white text-slate-600 hover:border-slate-400",
          )}
        >
          All
        </button>
        {categories.map((c) => (
          <button
            key={c}
            onClick={() => update({ category: c, page: 1 })}
            className={cn(
              "rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors",
              category === c
                ? "border-accent bg-teal-50 text-accent"
                : "border-gray-300 bg-white text-slate-600 hover:border-slate-400",
            )}
          >
            {c}
          </button>
        ))}
      </div>

      {loading ? (
        <LoadingScreen message="Loading products…" />
      ) : error ? (
        <div role="alert" className="space-y-4">
          <ErrorBox message={error} />
          <Button onClick={() => setReload((value) => value + 1)}>Retry loading products</Button>
        </div>
      ) : !data || data.items.length === 0 ? (
        <EmptyState
          icon="🔍"
          title="No products found"
          subtitle={
            q || category
              ? "Try a different search term or category."
              : "This catalog looks empty right now."
          }
          action={
            (q || category) && (
              <Button variant="outline" onClick={() => setParams(new URLSearchParams())}>
                Clear filters
              </Button>
            )
          }
        />
      ) : (
        <>
          <p className="mb-3 text-sm text-slate-500">
            {data.total} result{data.total !== 1 ? "s" : ""}
            {q && <> for “{q}”</>}
            {category && <> in {category}</>}
          </p>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
            {data.items.map((p) => (
              <ProductCard key={p.id} product={p} />
            ))}
          </div>

          {totalPages > 1 && (
            <div className="mt-8 flex items-center justify-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => update({ page: page - 1 })}
              >
                ← Prev
              </Button>
              <span className="px-2 text-sm text-slate-600">
                Page {page} of {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => update({ page: page + 1 })}
              >
                Next →
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export { addToCart };
