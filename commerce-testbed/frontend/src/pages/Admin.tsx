import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, formatPrice } from "../api";
import { useAuth } from "../context/AuthContext";
import { Button, ErrorBox, LoadingScreen } from "../components/ui";
import { DeveloperPage } from "./Developer";

const sections = [
  ["overview", "Overview"], ["users", "Users"], ["products", "Products"],
  ["orders", "Orders"], ["sessions", "Sessions"], ["api-keys", "API keys"], ["events", "Security events"],
] as const;
type Section = typeof sections[number][0];
type Row = Record<string, string | number | boolean | null>;
interface Records { items: Row[]; columns: string[]; total: number; limit: number; offset: number }
type Overview = Record<string, number | string>;
const labels: Record<string, string> = {
  users: "Registered users", products: "Products", orders: "Orders", active_sessions: "Active sessions",
  order_value_cents: "Order value", api_keys: "API keys", security_events: "Security events",
  high_severity_events: "High severity events", cart_items: "Items in carts",
};
function label(value: string) {
  const monetary = value.endsWith("_cents");
  const title = (monetary ? value.slice(0, -6) : value).replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());
  return monetary ? `${title} (₹)` : title;
}
function display(key: string, value: Row[string]) {
  if (value === null) return "—";
  if (key === "is_admin") return value ? "Admin" : "Customer";
  if (typeof value === "boolean") return value ? "Active" : "Disabled";
  if (key.endsWith("_cents")) return formatPrice(Number(value));
  if (key.endsWith("_at") || key === "ts") return new Date(String(value)).toLocaleString();
  return String(value);
}

export function AdminPage() {
  const { user } = useAuth();
  const [section, setSection] = useState<Section>("overview");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [records, setRecords] = useState<Records | null>(null);
  const [offset, setOffset] = useState(0);
  const [showAllKeys, setShowAllKeys] = useState(false);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const allowed = user?.is_admin;

  useEffect(() => {
    if (user && !allowed) { setLoading(false); return; }
    if (section === "api-keys" && !showAllKeys) { setLoading(false); setError(null); return; }
    let active = true;
    setLoading(true); setError(null);
    const path = section === "overview" ? "/api/admin/overview"
      : `/api/admin/records/${section}?limit=25&offset=${offset}&q=${encodeURIComponent(search)}`;
    api<Overview | Records>(path).then((data) => {
      if (!active) return;
      if (section === "overview") setOverview(data as Overview);
      else setRecords(data as Records);
    }).catch((e) => { if (active) setError(e.message || "Unable to load this dashboard."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [section, offset, search, refresh, allowed, user, showAllKeys]);

  function selectSection(value: Section) {
    setSection(value); setOffset(0); setQuery(""); setSearch(""); setRecords(null);
  }
  function onSearch(event: FormEvent) { event.preventDefault(); setOffset(0); setSearch(query); }
  async function action(row: Row) {
    const verb = section === "users" ? (row.is_active ? "Disable" : "Enable") : "Revoke";
    if (!window.confirm(`${verb} this ${section === "users" ? "user account" : "access"}?`)) return;
    setBusy(true); setError(null);
    try {
      const path = section === "users" ? `/api/admin/users/${row.id}` : `/api/admin/${section}/${row.id}/revoke`;
      await api(path, { method: section === "users" ? "PATCH" : "POST", body: section === "users" ? { is_active: !row.is_active } : undefined });
      setRefresh((value) => value + 1);
    } catch (e) { setError(e instanceof Error ? e.message : "Action failed. Please refresh before trying again."); }
    finally { setBusy(false); }
  }

  if (user && !allowed) return <div className="py-10"><ErrorBox message="Administrator access is required." /><Link to="/" className="mt-4 inline-block underline">Return to storefront</Link></div>;
  return (
    <section className="py-6 md:py-10">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div><h1 className="text-3xl font-bold text-navy">Admin portal</h1><p className="mt-2 text-sm text-slate-600">Manage Amezon accounts, commerce, and security activity.</p></div>
        <Button variant="outline" disabled={loading || busy} onClick={() => setRefresh((value) => value + 1)}>Refresh dashboard</Button>
      </div>
      <nav aria-label="Admin dashboards" className="mb-6 flex gap-1 overflow-x-auto border-b border-gray-200 pb-2">
        {sections.map(([key, title]) => <button key={key} onClick={() => selectSection(key)} aria-current={section === key ? "page" : undefined}
          className={`shrink-0 rounded-lg px-4 py-2 text-sm font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent ${section === key ? "bg-navy text-white" : "text-slate-700 hover:bg-gray-100"}`}>{title}</button>)}
      </nav>
      {error && <div className="mb-5"><ErrorBox message={error} /><Button variant="outline" className="mt-3" onClick={() => setRefresh((value) => value + 1)}>Retry dashboard</Button></div>}
      {section === "api-keys" && <div className="mb-8 space-y-6">
        <DeveloperPage onKeysChanged={() => setRefresh((value) => value + 1)} />
        <div className="border-t border-gray-200 pt-6">
          <h2 className="mb-2 text-lg font-bold text-navy">All account API keys</h2>
          <p className="mb-3 text-sm text-slate-600">Review key metadata and revoke access across all accounts. Secret values are never included.</p>
          <Button variant="outline" onClick={() => setShowAllKeys((value) => !value)}>{showAllKeys ? "Hide all account keys" : "View all account keys"}</Button>
        </div>
      </div>}
      {section === "api-keys" && !showAllKeys ? null : loading ? <LoadingScreen message="Loading dashboard…" /> : section === "overview" && overview ? <>
        <dl className="grid grid-cols-2 gap-x-8 gap-y-6 border-b border-gray-200 pb-8 md:grid-cols-3">
          {Object.entries(labels).map(([key, title]) => <div key={key}><dt className="text-sm font-medium text-slate-600">{title}</dt><dd className="mt-2 text-3xl font-bold tabular-nums text-navy">{key.endsWith("_cents") ? formatPrice(Number(overview[key])) : Number(overview[key]).toLocaleString()}</dd></div>)}
        </dl>
        <div className="mt-6 flex flex-wrap gap-x-8 gap-y-3 text-sm text-slate-700"><p>API: <strong>{String(overview.status)}</strong></p><p>Database: <strong>{String(overview.database)}</strong></p><p>Updated: {new Date(String(overview.updated_at)).toLocaleString()}</p><a href="/docs" className="underline">API documentation</a></div>
        <p className="mt-6 max-w-2xl text-sm text-slate-600">This test environment processes synthetic payments. Security events retain their app, synthetic, or external source labels.</p>
      </> : section !== "overview" && <>
        <form onSubmit={onSearch} className="mb-5 flex flex-wrap items-center gap-3"><label htmlFor="admin-search" className="text-sm font-medium">Search {sections.find(([key]) => key === section)?.[1].toLowerCase()}</label><input id="admin-search" value={query} onChange={(event) => setQuery(event.target.value)} maxLength={100} className="min-w-0 flex-1 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-accent" placeholder="Name, email, status, or event type" /><Button variant="secondary" type="submit">Search</Button></form>
        {section === "users" && <p className="mb-4 max-w-3xl text-sm text-slate-600">Demo passwords are shown only for explicitly seeded synthetic shoppers. Normal account passwords cannot be displayed. A dash means unavailable or changed.</p>}
        {records && <><p className="mb-3 text-sm text-slate-600">{records.total.toLocaleString()} records · newest first</p>
          <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white"><table className="w-full text-left text-sm"><caption className="sr-only">{section} records</caption><thead className="bg-gray-50 text-slate-600"><tr>{records.columns.map((column) => <th scope="col" key={column} className="whitespace-nowrap px-4 py-3 font-semibold">{label(column)}</th>)}{["users", "sessions", "api-keys"].includes(section) && <th scope="col" className="px-4 py-3">Actions</th>}</tr></thead><tbody className="divide-y divide-gray-100">{records.items.map((row) => <tr key={String(row.id)} className="hover:bg-gray-50">{records.columns.map((column) => <td key={column} className="max-w-xs px-4 py-3 text-slate-700"><span className="block break-words">{display(column, row[column])}</span></td>)}{["users", "sessions", "api-keys"].includes(section) && <td className="px-4 py-3"><Button size="sm" variant="outline" disabled={busy || (section === "users" && Boolean(row.is_admin)) || (section !== "users" && row.revoked_at !== null)} onClick={() => void action(row)}>{section === "users" ? (row.is_active ? "Disable" : "Enable") : row.revoked_at ? "Revoked" : "Revoke"}</Button></td>}</tr>)}</tbody></table>{!records.items.length && <p className="p-8 text-center text-slate-600">No matching records.</p>}</div>
          <div className="mt-4 flex items-center justify-between gap-4"><Button variant="outline" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 25))}>Previous</Button><span className="text-sm text-slate-600">Page {Math.floor(offset / 25) + 1}</span><Button variant="outline" disabled={offset + 25 >= records.total} onClick={() => setOffset(offset + 25)}>Next</Button></div>
        </>}
      </>}
    </section>
  );
}
