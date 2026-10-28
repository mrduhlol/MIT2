import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "./context/AuthContext";
import { api } from "./api";
import type { Address, Cart } from "./types";
import { cn } from "./utils";

/* --------------------------------- Icons ----------------------------------- */
/* Small drawn icon set (stroke-based, consistent weight) for the brand chrome. */

const iconProps = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

function SearchIcon({ className }: { className?: string }) {
  return (
    <svg {...iconProps} className={className}>
      <circle cx="11" cy="11" r="6.5" />
      <path d="M16 16l4.5 4.5" />
    </svg>
  );
}

function CartIcon({ className }: { className?: string }) {
  return (
    <svg {...iconProps} className={className}>
      <path d="M3 4h2l2.4 11.2a1.6 1.6 0 0 0 1.6 1.3h7.9a1.6 1.6 0 0 0 1.6-1.2L20.5 8H6" />
      <circle cx="10" cy="20" r="1.4" />
      <circle cx="17.5" cy="20" r="1.4" />
    </svg>
  );
}

function PinIcon({ className }: { className?: string }) {
  return (
    <svg {...iconProps} className={className}>
      <path d="M12 21s-6.5-5.4-6.5-10a6.5 6.5 0 1 1 13 0c0 4.6-6.5 10-6.5 10z" />
      <circle cx="12" cy="10.5" r="2.2" />
    </svg>
  );
}

function MenuIcon({ className }: { className?: string }) {
  return (
    <svg {...iconProps} className={className}>
      <path d="M4 6.5h16M4 12h16M4 17.5h16" />
    </svg>
  );
}

/* ------------------------------ Amezon wordmark ----------------------------- */

export function AmezonLogo({ className }: { className?: string }) {
  return (
    <span className={cn("relative inline-flex flex-col items-start", className)}>
      <span className="text-xl font-bold leading-none tracking-tight">amezon</span>
      <svg
        viewBox="0 0 64 11"
        className="mt-[3px] h-2 w-full text-[#FF9900]"
        fill="none"
        aria-hidden="true"
      >
        <path
          d="M2 2.5C17 10 44 10 59 2"
          stroke="currentColor"
          strokeWidth="3"
          strokeLinecap="round"
        />
        <path
          d="M56.2 1.2l4.2 0.6-1.5 3.4"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  );
}

/* ------------------------------ Header ------------------------------------- */

const DEPARTMENTS = ["Electronics", "Home & Kitchen", "Books", "Sports", "Toys", "Beauty"];

export function Header() {
  const { user, token, logout } = useAuth();
  const [cartCount, setCartCount] = useState(0);
  const [menuOpen, setMenuOpen] = useState(false);
  const [query, setQuery] = useState("");
  const navigate = useNavigate();
  const location = useLocation();
  const isAdminPortal = location.pathname.startsWith("/admin");
  const menuRef = useRef<HTMLDivElement>(null);
  const [deliverCity, setDeliverCity] = useState<string | null>(null);

  // Fetch the default address once per login for the "Deliver to" chip.
  useEffect(() => {
    if (!token || isAdminPortal) {
      setDeliverCity(null);
      return;
    }
    api<Address[]>("/api/me/addresses")
      .then((list) => {
        const preferred = list.find((a) => a.is_default) ?? list[0];
        setDeliverCity(preferred?.city ?? null);
      })
      .catch(() => setDeliverCity(null));
  }, [token, isAdminPortal]);

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
    if (!token || isAdminPortal) return;
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
      <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-2 sm:gap-4">
        <Link to="/" className="flex shrink-0 items-center gap-2 rounded-lg px-1.5 py-1 text-white hover:opacity-90">
          <AmezonLogo />
        </Link>

        <Link
          to={user ? "/account/addresses" : "/login?next=%2Faccount%2Faddresses"}
          className="hidden shrink-0 items-center gap-1 rounded-lg px-2 py-1 text-xs text-white hover:bg-navy-light md:flex"
        >
          <PinIcon className="h-4 w-4 self-center text-slate-200" />
          <span className="leading-tight">
            <span className="block text-[11px] text-slate-300">{user ? "Deliver to" : "Hello"}</span>
            <span className="block max-w-[9rem] truncate font-bold">
              {user ? (deliverCity ?? "add address") : "sign in"}
            </span>
          </span>
        </Link>

        <form className="flex min-w-0 flex-1" onSubmit={submitSearch}>
          <div className="flex w-full overflow-hidden rounded-md shadow-sm ring-1 ring-transparent focus-within:ring-2 focus-within:ring-cta">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search Amezon…"
              aria-label="Search Amezon"
              className="min-w-0 flex-1 border-0 bg-white px-3 py-2 text-sm text-slate-800 placeholder-slate-400 focus:outline-none"
            />
            <button
              type="submit"
              aria-label="Search"
              className="bg-cta px-4 text-navy transition-colors hover:bg-cta-dark"
            >
              <SearchIcon className="h-5 w-5" />
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
                    ...(user.is_admin ? [{ to: "/admin", label: "Admin portal" }] : []),
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
            className="relative flex items-end gap-1.5 rounded-lg px-2.5 py-1.5 text-sm font-bold text-white hover:bg-navy-light"
          >
            <span className="relative">
              <CartIcon className="h-6 w-6" />
              {cartCount > 0 && (
                <span className="absolute -top-1 left-1/2 grid h-4 min-w-4 -translate-x-1/2 place-items-center rounded-full bg-cta px-0.5 text-[10px] font-bold text-navy">
                  {cartCount}
                </span>
              )}
            </span>
            <span className="hidden sm:block">Cart</span>
          </Link>
        </nav>
      </div>

      {/* department sub-navigation */}
      <div className="border-t border-navy-light bg-navy-light text-white">
        <div className="mx-auto flex max-w-7xl items-center gap-0.5 overflow-x-auto px-2 py-1 text-sm sm:px-4">
          <Link
            to="/"
            className="flex shrink-0 items-center gap-1.5 rounded px-2 py-1.5 font-medium hover:bg-white/10"
          >
            <MenuIcon className="h-4 w-4" />
            All
          </Link>
          {DEPARTMENTS.map((c) => (
            <Link
              key={c}
              to={`/?category=${encodeURIComponent(c)}`}
              className={cn(
                "shrink-0 rounded px-2 py-1.5 hover:bg-white/10",
                new URLSearchParams(location.search).get("category") === c
                  ? "bg-white/10 font-semibold ring-1 ring-white/30"
                  : "",
              )}
            >
              {c}
            </Link>
          ))}
        </div>
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
      <footer>
        <button
          onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
          className="w-full bg-[#37475a] py-3 text-sm font-medium text-white transition-colors hover:bg-[#485769]"
        >
          Back to top
        </button>
        <div className="bg-navy-light text-slate-200">
          <div className="mx-auto grid max-w-7xl gap-8 px-4 py-10 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <AmezonLogo className="text-white" />
              <p className="mt-3 max-w-xs text-xs leading-relaxed text-slate-400">
                A working marketplace testbed for the AI Cyber Defense Agent:
                real backend, real database, observable security events.
              </p>
            </div>
            <div>
              <h3 className="mb-2 text-sm font-bold text-white">Your Amezon</h3>
              <ul className="space-y-1.5">
                <li><Link to="/account" className="hover:underline">Your Account</Link></li>
                <li><a href="/images/products/credits.html" className="hover:underline">Product image credits</a></li>
                <li><Link to="/orders" className="hover:underline">Your Orders</Link></li>
                <li><Link to="/account/addresses" className="hover:underline">Saved Addresses</Link></li>
                <li><Link to="/cart" className="hover:underline">Your Cart</Link></li>
              </ul>
            </div>
            <div>
              <h3 className="mb-2 text-sm font-bold text-white">Amezon for Builders</h3>
              <ul className="space-y-1.5">
                <li><Link to="/account/developer" className="hover:underline">Developer API Keys</Link></li>
                <li>
                  <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer" className="hover:underline">
                    API Documentation
                  </a>
                </li>
                <li>
                  <a href="http://localhost:8000/api/security/health" target="_blank" rel="noreferrer" className="hover:underline">
                    Service Health
                  </a>
                </li>
              </ul>
            </div>
            <div>
              <h3 className="mb-2 text-sm font-bold text-white">Testbed Notices</h3>
              <ul className="space-y-1.5 text-xs leading-relaxed text-slate-400">
                <li>All payments are synthetic — no real charges.</li>
                <li>Security events are logged pseudonymously for the AI SOC feed.</li>
                <li>Amezon is a hackathon project and is not affiliated with Amazon.</li>
              </ul>
            </div>
          </div>
        </div>
        <div className="bg-navy py-4 text-center text-xs text-slate-400">
          © {new Date().getFullYear()} Amezon — hackathon testbed storefront. Synthetic payments, no real charges.
        </div>
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
