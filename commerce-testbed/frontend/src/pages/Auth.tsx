import { useState, type FormEvent, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { AmezonLogo } from "../layout";
import { ApiError } from "../api";
import { Button, Input } from "../components/ui";

function AuthCard({ title, subtitle, children }: { title: string; subtitle?: ReactNode; children: ReactNode }) {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center px-4 py-10">
      <Link to="/" className="mb-6 flex items-center gap-2 text-slate-900">
        <span className="grid h-10 w-10 place-items-center rounded-xl bg-navy pb-0.5">
          <span className="text-xl font-bold leading-none text-white">a</span>
        </span>
        <AmezonLogo />
      </Link>
      <div className="w-full rounded-xl border border-gray-200 bg-white p-8 shadow-md">
        <h1 className="mb-1 text-xl font-bold text-slate-900">{title}</h1>
        {subtitle && <p className="mb-5 text-sm text-slate-500">{subtitle}</p>}
        {children}
      </div>
      <p className="mt-6 text-center text-xs text-slate-500">
        Hackathon test environment — data is synthetic.
      </p>
    </div>
  );
}

function useNextDestination(): string {
  const location = useLocation();
  const next = new URLSearchParams(location.search).get("next");
  return next && next.startsWith("/") ? next : "/";
}

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const next = useNextDestination();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(email.trim(), password);
      navigate(next, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthCard title="Log in" subtitle="Welcome back to Amezon">
      <form onSubmit={onSubmit} className="space-y-4">
        <Input
          label="Email"
          type="email"
          required
          autoComplete="email"
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <Input
          label="Password"
          type="password"
          required
          autoComplete="current-password"
          placeholder="••••••••"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        )}
        <Button type="submit" loading={busy} className="w-full" size="lg">
          Log in
        </Button>
      </form>
      <p className="mt-5 text-center text-sm text-slate-600">
        New to Amezon?{" "}
        <Link to="/register" className="font-medium text-accent hover:underline">
          Create an account
        </Link>
      </p>
    </AuthCard>
  );
}

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const next = useNextDestination();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    if (password.length < 6) {
      setError("Password must be at least 6 characters.");
      return;
    }
    setBusy(true);
    try {
      await register(email.trim(), password, fullName.trim());
      navigate(next, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Registration failed. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthCard title="Create account" subtitle="Shop millions of (synthetic) products">
      <form onSubmit={onSubmit} className="space-y-4">
        <Input
          label="Full name"
          type="text"
          required
          autoComplete="name"
          placeholder="Ada Lovelace"
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
        />
        <Input
          label="Email"
          type="email"
          required
          autoComplete="email"
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <Input
          label="Password"
          type="password"
          required
          autoComplete="new-password"
          placeholder="At least 6 characters"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <Input
          label="Re-enter password"
          type="password"
          required
          autoComplete="new-password"
          placeholder="••••••••"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
        />
        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        )}
        <Button type="submit" loading={busy} className="w-full" size="lg">
          Create your Amezon account
        </Button>
      </form>
      <p className="mt-5 text-center text-sm text-slate-600">
        Already have an account?{" "}
        <Link to="/login" className="font-medium text-accent hover:underline">
          Log in
        </Link>
      </p>
    </AuthCard>
  );
}
