import { useEffect, useState, type FormEvent } from "react";
import { api, clearToken } from "../api";
import { useAuth } from "../context/AuthContext";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorBox,
  Input,
  LoadingScreen,
} from "../components/ui";
import { formatDate } from "../utils";
import type { Address, Session } from "../types";

/* --------------------------------- Profile --------------------------------- */

export function ProfilePage() {
  const { user, setUser } = useAuth();
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const me = await api<{ id: string; email: string; full_name: string; phone?: string }>(
          "/api/me",
        );
        setFullName(me.full_name ?? "");
        setPhone(me.phone ?? "");
        setEmail(me.email);
        setUser(me);
      } catch {
        // fall back to context user
        if (user) {
          setFullName(user.full_name ?? "");
          setPhone(user.phone ?? "");
          setEmail(user.email);
        }
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const updated = await api<{ id: string; email: string; full_name: string; phone?: string }>(
        "/api/me",
        { method: "PUT", body: { full_name: fullName, phone } },
      );
      setUser({ ...user, ...updated });
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save profile");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <h2 className="mb-1 text-lg font-bold text-slate-900">Profile</h2>
      <p className="mb-5 text-sm text-slate-500">Basic details shown with your orders.</p>
      <form onSubmit={onSubmit} className="max-w-lg space-y-4">
        <Input label="Email" value={email} disabled />
        <Input
          label="Full name"
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          placeholder="Your name"
          required
        />
        <Input
          label="Phone"
          type="tel"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          placeholder="+1 555 0100"
        />
        {error && <ErrorBox message={error} />}
        {saved && (
          <div className="rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">
            ✓ Profile updated
          </div>
        )}
        <Button type="submit" loading={busy}>Save changes</Button>
      </form>
    </Card>
  );
}

/* -------------------------------- Addresses -------------------------------- */

const emptyForm = {
  label: "",
  line1: "",
  line2: "",
  city: "",
  state: "",
  postal_code: "",
  country: "USA",
  is_default: false,
};

export function AddressesPage() {
  const [addresses, setAddresses] = useState<Address[] | null>(null);
  const [editingId, setEditingId] = useState<string | "new" | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function load() {
    api<Address[]>("/api/me/addresses")
      .then((a) => setAddresses(Array.isArray(a) ? a : []))
      .catch((e) => setError(e?.message ?? "Failed to load addresses"));
  }

  useEffect(load, []);

  function startNew() {
    setForm(emptyForm);
    setEditingId("new");
    setError(null);
  }

  function startEdit(a: Address) {
    setForm({
      label: a.label,
      line1: a.line1,
      line2: a.line2 ?? "",
      city: a.city,
      state: a.state ?? "",
      postal_code: a.postal_code,
      country: a.country ?? "",
      is_default: a.is_default,
    });
    setEditingId(a.id);
    setError(null);
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body = { ...form, line2: form.line2 || null };
    try {
      if (editingId === "new") await api("/api/me/addresses", { method: "POST", body });
      else await api(`/api/me/addresses/${editingId}`, { method: "PUT", body });
      setEditingId(null);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save address");
    } finally {
      setBusy(false);
    }
  }

  async function remove(a: Address) {
    if (!window.confirm(`Delete address "${a.label}"?`)) return;
    try {
      await api(`/api/me/addresses/${a.id}`, { method: "DELETE" });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete address");
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold text-slate-900">Saved addresses</h2>
            <p className="text-sm text-slate-500">Choose where your test orders ship.</p>
          </div>
          <Button size="sm" onClick={startNew} disabled={editingId === "new"}>
            + Add address
          </Button>
        </div>
      </Card>

      {error && <ErrorBox message={error} />}
      {editingId && (
        <Card>
          <h3 className="mb-4 font-bold text-slate-900">
            {editingId === "new" ? "Add" : "Edit"} address
          </h3>
          <form onSubmit={save} className="grid max-w-2xl gap-4 sm:grid-cols-2">
            <Input label="Label" value={form.label} required placeholder="Home, Work…"
              onChange={(e) => setForm({ ...form, label: e.target.value })} />
            <Input label="Street address" value={form.line1} required placeholder="123 Main St"
              onChange={(e) => setForm({ ...form, line1: e.target.value })} />
            <Input label="Apt, suite (optional)" value={form.line2}
              onChange={(e) => setForm({ ...form, line2: e.target.value })} />
            <Input label="City" value={form.city} required
              onChange={(e) => setForm({ ...form, city: e.target.value })} />
            <Input label="State / region" value={form.state}
              onChange={(e) => setForm({ ...form, state: e.target.value })} />
            <Input label="Postal code" value={form.postal_code} required
              onChange={(e) => setForm({ ...form, postal_code: e.target.value })} />
            <Input label="Country" value={form.country}
              onChange={(e) => setForm({ ...form, country: e.target.value })} />
            <label className="flex items-center gap-2 self-end text-sm text-slate-700">
              <input
                type="checkbox"
                checked={form.is_default}
                onChange={(e) => setForm({ ...form, is_default: e.target.checked })}
                className="h-4 w-4 rounded border-gray-300 text-accent focus:ring-accent/40"
              />
              Make default address
            </label>
            <div className="flex gap-3 sm:col-span-2">
              <Button type="submit" loading={busy}>Save address</Button>
              <Button type="button" variant="outline" onClick={() => setEditingId(null)}>
                Cancel
              </Button>
            </div>
          </form>
        </Card>
      )}

      {addresses === null ? (
        <LoadingScreen message="Loading addresses…" />
      ) : addresses.length === 0 ? (
        <EmptyState
          icon="📍"
          title="No addresses saved"
          subtitle="Add a shipping address to enable checkout."
          action={editingId !== "new" && <Button onClick={startNew}>Add your first address</Button>}
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {addresses.map((a) => (
            <Card key={a.id} className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="font-bold text-slate-900">{a.label}</span>
                {a.is_default && <Badge color="green">Default</Badge>}
              </div>
              <p className="text-sm leading-relaxed text-slate-600">
                {a.line1}{a.line2 ? `, ${a.line2}` : ""}
                <br />
                {a.city}{a.state ? `, ${a.state}` : ""} {a.postal_code}
                {a.country ? <><br />{a.country}</> : null}
              </p>
              <div className="mt-auto flex gap-2 pt-2">
                <Button variant="outline" size="sm" onClick={() => startEdit(a)}>Edit</Button>
                <Button variant="danger" size="sm" onClick={() => remove(a)}>Delete</Button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

/* --------------------------------- Sessions -------------------------------- */

export function SessionsPage() {
  const [sessions, setSessions] = useState<Session[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [revokingAll, setRevokingAll] = useState(false);

  function load() {
    api<Session[]>("/api/me/sessions")
      .then((s) => setSessions(Array.isArray(s) ? s.filter((x) => !x.revoked) : []))
      .catch((e) => setError(e?.message ?? "Failed to load sessions"));
  }

  useEffect(load, []);

  async function revoke(id: string) {
    setBusyId(id);
    setError(null);
    try {
      await api(`/api/me/sessions/${id}`, { method: "DELETE" });
      // If we just revoked *our own* session, the next API call 401s and the
      // api client bounces to /login automatically.
      setSessions((list) => (list ? list.filter((x) => x.id !== id) : list));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to revoke session");
    } finally {
      setBusyId(null);
    }
  }

  async function revokeAllOthers() {
    if (!sessions) return;
    setRevokingAll(true);
    setError(null);
    for (const s of sessions) {
      try {
        await api(`/api/me/sessions/${s.id}`, { method: "DELETE" });
      } catch (err) {
        // If the server killed *our* session in the batch, subsequent calls 401 and the
        // api client redirects to /login — prefer graceful local sign-out.
        setError(err instanceof Error ? err.message : "Failed to revoke all sessions");
        break;
      }
      setSessions((list) => (list ? list.filter((x) => x.id !== s.id) : list));
    }
    setRevokingAll(false);
    load();
  }

  if (error) {
    return (
      <div className="space-y-4">
        <ErrorBox message={error} />
        <Button variant="outline" onClick={load}>Retry</Button>
      </div>
    );
  }
  if (!sessions) return <LoadingScreen message="Loading sessions…" />;

  return (
    <div className="space-y-4">
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-bold text-slate-900">Active sessions</h2>
            <p className="text-sm text-slate-500">
              Devices signed into your account. Revoking all also signs you out here.
            </p>
          </div>
          <Button variant="danger" size="sm" loading={revokingAll} onClick={revokeAllOthers}>
            Revoke all others
          </Button>
        </div>
      </Card>

      {sessions.length === 0 ? (
        <EmptyState icon="🔐" title="No active sessions" />
      ) : (
        <Card className="overflow-x-auto p-0">
          <table className="w-full min-w-[48rem] text-left text-sm">
            <thead className="border-b border-gray-200 bg-gray-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">Created</th>
                <th className="px-4 py-3">Expires</th>
                <th className="px-4 py-3">IP</th>
                <th className="px-4 py-3">Device</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {sessions.map((s) => (
                <tr key={s.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 whitespace-nowrap text-slate-700">{formatDate(s.created_at)}</td>
                  <td className="px-4 py-3 whitespace-nowrap text-slate-700">{formatDate(s.expires_at)}</td>
                  <td className="px-4 py-3 font-mono text-slate-600">{s.ip ?? "—"}</td>
                  <td className="max-w-[16rem] truncate px-4 py-3 text-slate-600" title={s.user_agent ?? ""}>
                    {s.user_agent ?? "Unknown device"}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Button
                      variant="outline" size="sm"
                      loading={busyId === s.id}
                      onClick={() => revoke(s.id)}
                    >
                      Revoke
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
      <p className="text-xs text-slate-500">
        💡 Sessions listed by the API don't carry a “current” flag — revoking one usually signs
        that device out. Revoking all will sign you out of this browser too.
      </p>
    </div>
  );
}

/* --------------------------------- Settings -------------------------------- */

export function SettingsPage() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setDone(false);
    if (next !== confirm) {
      setError("New passwords do not match.");
      return;
    }
    if (next.length < 6) {
      setError("New password must be at least 6 characters.");
      return;
    }
    setBusy(true);
    try {
      await api("/api/me/password", {
        method: "PUT",
        body: { current_password: current, new_password: next },
      });
      setDone(true);
      setCurrent("");
      setNext("");
      setConfirm("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to change password");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <h2 className="text-lg font-bold text-slate-900">Change password</h2>
        <p className="mb-5 text-sm text-slate-500">
          Your other sessions stay signed in (testbed behaviour).
        </p>
        <form onSubmit={onSubmit} className="max-w-lg space-y-4">
          <Input
            label="Current password"
            type="password"
            required
            autoComplete="current-password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
          />
          <Input
            label="New password"
            type="password"
            required
            autoComplete="new-password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
          />
          <Input
            label="Confirm new password"
            type="password"
            required
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
          />
          {error && <ErrorBox message={error} />}
          {done && (
            <div className="rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">
              ✓ Password changed
            </div>
          )}
          <Button type="submit" loading={busy}>Update password</Button>
        </form>
      </Card>

      <Card className="border-red-100">
        <h2 className="text-lg font-bold text-slate-900">Danger zone</h2>
        <p className="mb-4 text-sm text-slate-500">Sign out of this browser immediately.</p>
        <Button
          variant="danger"
          onClick={async () => {
            await api("/api/auth/logout", { method: "POST" }).catch(() => {});
            clearToken();
            window.location.assign("/login");
          }}
        >
          Log out now
        </Button>
      </Card>
    </div>
  );
}
