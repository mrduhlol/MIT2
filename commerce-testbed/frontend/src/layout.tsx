import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "./context/AuthContext";
import { api } from "./api";
import type { Cart } from "./types";
import { cn } from "./utils";

/* --------------------------------- Header --------------------------------- */

export function Header() {
  const { user, token, logout } = useAuth();
  const [cartCount, setCartCount] = useState(0);
  const [menuOpen, setMenuOpen] = useState(false);
  const [query, setQuery] = useState("");
  const navigate = useNavigate();
  const location = useLocation();
  const menuRef = useRef<HTMLDivElement>(null);

  // sync cart badge from cart responses cached in localStorage (see CartContext section)
  useEffect(() => {
    const sync = () => {
      const raw = localStorage.getItem("ct_cart_count");
      setCartCount(raw ? Number(raw) || 0 : 0);
    };
    sync();
    window.addEventListener("ct-cart-sync", sync);
    return () => window.removeEventListener("ct-cart-sync", sync);
  }, []);

  useEffect(() => setQuery(new URLSearchParams(location.search).get("q") ?? ""), [location.search]);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  async function bumpCartCount() {
    if (!token) return;
    try {
      const cart = await api<Cart>("/api/cart");
      syncCartCount(cart.items.reduce((sum, it) => sum + it.quantity, 0));
      setCartCount(cart.items.reduce((sum, it) => sum + it.quantity, 0));
    } catch {
      /* ignore */
    }
  }

  // refresh badge whenever route changes
  useEffect(() => {
    void bumpCartCount();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname, token]);

  function submitSearch(e: React.FormEvent) {
    e.preventDefault();
    navigate(`/?q=${encodeURIComponent(query.trim())}`);
  }

  return (
    <header className="sticky top-0 z-40 border-b border-slate-800 bg-navy text-white shadow">
      <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-2.5 sm:gap-5">
        <Link to="/" className="flex shrink-0 items-center gap-2 rounded-lg px-1 py-1 hover:opacity-90">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent font-black text-navy">
            Z
          </span>
          <span className="hidden text-lg font-bold tracking-tight sm:block">
            ShopZone
          </span>
        </Link>

        <form className="flex min-w-0 flex-1" onSubmit={submitSearch}>
          <div className="flex w-full overflow-hidden rounded-lg shadow-sm ring-1 ring-transparent focus-within:ring-2 focus-within:ring-accent">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search products…"
              aria-label="Search products"
              className="min-w-0 flex-1 rounded-l-lg border-0 bg-white px-3 py-2 text-sm text-slate-800 placeholder-slate-400 focus:outline-none"
            />
            <button
              type="submit"
              aria-label="Search"
              className="rounded-r-lg bg-amber-400 px-4 text-navy transition-colors hover:bg-accent hover:text-white"
            >
              🔍
            </button>
          </div>
        </form>

        <nav className="flex shrink-0 items-center gap-1">
          {user ? (
            <div className="relative" ref={menuRef}>
              <button
                onClick={() => setMenuOpen((o) => !o)}
                aria-haspopup="menu"
                aria-expanded={menuOpen}
                className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm font-medium text-white hover:bg-navy-light"
              >
                <span className="grid h-7 w-7 place-items-center rounded-full bg-accent text-xs font-bold uppercase">
                  {user.full_name?.[0] ?? user.email[0]}
                </span>
                <span className="hidden max-w-[10rem] truncate md:block">
                  {user.full_name || user.email}
                </span>
                <svg className="h-4 w-4 opacity-70" viewBox="0 0 20 20" fill="currentColor">
                  <path d="M5.5 8l4.5 5 4.5-5z" />
                </svg>
              </button>
              {menuOpen && (
                <div
                  role="menu"
                  className="absolute right-0 mt-2 w-52 overflow-hidden rounded-xl border border-gray-200 bg-white text-slate-800 shadow-lg"
                >
                  <div className="border-b border-gray-100 px-4 py-2.5">
                    <p className="truncate text-sm font-semibold">{user.full_name}</p>
                    <p className="truncate text-xs text-slate-500">{user.email}</p>
                  </div>
                  {[
                    { to: "/account", label: "Your Account" },
                    { to: "/orders", label: "Your Orders" },
                    { to: "/cart", label: "Your Cart" },
                  ].map((item) => (
                    <Link
                      key={item.to}
                      role="menuitem"
                      to={item.to}
                      onClick={() => setMenuOpen(false)}
                      className="block px-4 py-2.5 text-sm hover:bg-gray-50"
                    >
                      {item.label}
                    </Link>
                  ))}
                  <button
                    role="menuitem"
                    onClick={async () => {
                      setMenuOpen(false);
                      await logout();
                      navigate("/");
                    }}
                    className="block w-full border-t border-gray-100 px-4 py-2.5 text-left text-sm text-red-600 hover:bg-red-50"
                  >
                    Log out
                  </button>
                </div>
              )}
            </div>
          ) : (
            <>
              <Link
                to="/login"
                className="rounded-lg px-3 py-2 text-sm font-medium text-white hover:bg-navy-light"
              >
                Login
              </Link>
              <Link
                to="/register"
                className="hidden rounded-lg bg-accent px-3 py-2 text-sm font-medium text-white hover:bg-accent-dark sm:block"
              >
                Register
              </Link>
            </>
          )}
          <Link
            to="/cart"
            className="relative flex items-center rounded-lg px-3 py-2 text-sm font-medium hover:bg-navy-light"
          >
            🛒
            {cartCount > 0 && (
              <span className="absolute -top-0.5 right-0.5 grid h-5 min-w-5 place-items-center rounded-full bg-accent px-1 text-xs font-bold">
                {cartCount}
              </span>
            )}
          </Link>
        </nav>
      </div>
    </header>
  );
}

export function syncCartCount(count: number) {
  localStorage.setItem("ct_cart_count", String(count));
  window.dispatchEvent(new Event("ct-cart-sync"));
}

/* ---------------------------------- Layout --------------------------------- */

export function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <Header />
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">{children}</main>
      <footer className="mt-8 bg-navy-light py-6 text-center text-xs text-slate-400">
        ShopZone — hackathon testbed storefront. Synthetic payments, no real charges.
      </footer>
    </div>
  );
}

/* ------------------------------- Page title -------------------------------- */

export function PageTitle({ title, action }: { title: string; action?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
      <h1 className="text-2xl font-bold text-slate-900">{title}</h1>
      {action}
    </div>
  );
}

/* --------------------------------- Guards ---------------------------------- */

export function RequireAuth({ children }: { children: ReactNode }) {
  const { token, loading } = useAuth();
  const location = useLocation();
  if (loading) return null; // wait for session check
  if (!token) return <LoginRedirect state={location} />;
  return <>{children}</>;
}

function LoginRedirect({ state }: { state: Pick<ReturnType<typeof useLocation>, "pathname" | "search"> }) {
  const navigate = useNavigate();
  useEffect(() => {
    navigate(`/login?next=${encodeURIComponent(state.pathname + state.search)}`, {
      replace: true,
    });
  }, [navigate, state]);
  return null;
}

/* ---------------------------- Active nav link ------------------------------ */

export function NavTab({ to, exact = false, children }: { to: string; exact?: boolean; children: ReactNode }) {
  return (
    <NavLink
      to={to}
      end={exact}
      className={({ isActive }) =>
        cn(
          "rounded-lg px-3 py-2 text-sm font-medium transition-colors",
          isActive
            ? "bg-gray-100 text-slate-900"
            : "text-slate-600 hover:bg-gray-50 hover:text-slate-900",
        )
      }
    >
      {children}
    </NavLink>
  );
}

export function AccountLayout() {
  const { user } = useAuth();
  return (
    <div>
      <PageTitle title="Your Account" />
      {!user && <p className="mb-4 text-sm text-slate-500">Loading your details…</p>}
      <div className="flex flex-col gap-6 md:flex-row">
        <aside className="md:w-56 md:shrink-0">
          <nav className="flex flex-col gap-1 rounded-xl border border-gray-200 bg-white p-2 shadow-sm md:sticky md:top-20">
            <NavTab to="/account" exact>👤 Profile</NavTab>
            <NavTab to="/account/addresses">📍 Addresses</NavTab>
            <NavTab to="/account/sessions">🔐 Sessions</NavTab>
            <NavTab to="/account/settings">⚙️ Settings</NavTab>
            <NavTab to="/account/developer">🔑 Developer</NavTab>
          </nav>
        </aside>
        <div className="min-w-0 flex-1">
          {/* nested routes render here */}
          <Outlet />
        </div>
      </div>
    </div>
  );
}
