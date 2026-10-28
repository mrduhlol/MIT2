import { useEffect, useRef, useState, type FormEvent } from "react";
import { api } from "../api";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorBox,
  Input,
  LoadingScreen,
  Modal,
} from "../components/ui";
import { cn, formatDate } from "../utils";
import type { ApiKey, ApiKeyEnvironment, ApiKeySecret, ApiKeyStatus } from "../types";
import type { BadgeColor } from "../components/ui";

/* ------------------------------ Scope catalog ------------------------------ */

const SCOPES: { value: string; label: string }[] = [
  { value: "security_events:read", label: "Read security events" },
  { value: "security_events:write", label: "Submit security events" },
  { value: "incidents:read", label: "Read security incidents" },
  { value: "users:read", label: "Read pseudonymous account metadata" },
];

const ENVIRONMENTS: {
  value: ApiKeyEnvironment;
  title: string;
  prefix: string;
  hint: string;
}[] = [
  {
    value: "development",
    title: "Development",
    prefix: "sk_test_",
    hint: "Keys start with sk_test_. Use for testing integrations.",
  },
  {
    value: "production",
    title: "Production",
    prefix: "sk_live_",
    hint: "Keys start with sk_live_. Use for live integrations.",
  },
];

/* --------------------------------- Helpers --------------------------------- */

/** Badge color for key status (matches order-status mapping style). */
function apiKeyStatusColor(status: ApiKeyStatus): BadgeColor {
  if (status === "active") return "green";
  if (status === "revoked") return "red";
  return "gray";
}

function environmentColor(environment: ApiKeyEnvironment): BadgeColor {
  return environment === "production" ? "amber" : "gray";
}

/** Copy to clipboard, falling back to a hidden textarea + execCommand. */
async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* fall through to legacy path */
  }
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    ta.remove();
    return ok;
  } catch {
    return false;
  }
}

function ScopeChip({ value }: { value: string }) {
  return (
    <span className="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-600">
      {value}
    </span>
  );
}

/* ------------------------------- Meta display ------------------------------ */

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3">
      <span className="text-slate-500">{label}</span>
      <span className="text-right text-slate-700">{value}</span>
    </div>
  );
}

/* --------------------------------- The page -------------------------------- */

export function DeveloperPage() {
  const [keys, setKeys] = useState<ApiKey[] | null>(null);
  const [error, setError] = useState<string | null>(null); // load error
  const [actionError, setActionError] = useState<string | null>(null); // rotate/revoke error
  const [notice, setNotice] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  // create dialog
  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState("");
  const [environment, setEnvironment] = useState<ApiKeyEnvironment>("development");
  const [scopes, setScopes] = useState<string[]>([]);
  const [expiresAt, setExpiresAt] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  // one-time secret modal (create + rotate)
  const [secretData, setSecretData] = useState<ApiKeySecret | null>(null);
  const [secretMode, setSecretMode] = useState<"created" | "rotated">("created");
  const [copied, setCopied] = useState(false);

  // snippet copy
  const [snippetCopied, setSnippetCopied] = useState(false);

  const noticeTimer = useRef<number | undefined>(undefined);

  function showNotice(message: string) {
    setNotice(message);
    window.clearTimeout(noticeTimer.current);
    noticeTimer.current = window.setTimeout(() => setNotice(null), 4000);
  }

  function load() {
    api<{ items: ApiKey[] }>("/api/api-keys")
      .then((res) => setKeys(Array.isArray(res.items) ? res.items : []))
      .catch((e) => setError(e?.message ?? "Failed to load API keys"));
  }

  useEffect(load, []);

  /* ------------------------------- Actions ------------------------------- */

  async function rotate(k: ApiKey) {
    if (
      !window.confirm(
        `Rotate key "${k.name}"?\n\nThe current key stops working immediately, and the new secret is shown only once.`,
      )
    )
      return;
    setBusyId(k.id);
    setActionError(null);
    try {
      const res = await api<ApiKeySecret>(`/api/api-keys/${k.id}/rotate`, { method: "POST" });
      load();
      showNotice(`Key "${k.name}" rotated.`);
      setCopied(false);
      setSecretMode("rotated");
      setSecretData(res);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to rotate key");
    } finally {
      setBusyId(null);
    }
  }

  async function revoke(k: ApiKey) {
    if (
      !window.confirm(
        `Revoke key "${k.name}"?\n\nIntegrations using this key (${k.scopes.join(", ")}) lose access immediately. This cannot be undone.`,
      )
    )
      return;
    setBusyId(k.id);
    setActionError(null);
    try {
      await api<{ ok: boolean }>(`/api/api-keys/${k.id}`, { method: "DELETE" });
      setKeys((list) =>
        list
          ? list.map((x) =>
              x.id === k.id
                ? { ...x, status: "revoked" as ApiKeyStatus, revoked_at: new Date().toISOString() }
                : x,
            )
          : list,
      );
      showNotice(`Key "${k.name}" revoked — integrations using it lost access immediately.`);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to revoke key");
    } finally {
      setBusyId(null);
    }
  }

  function toggleScope(value: string) {
    setScopes((s) => (s.includes(value) ? s.filter((x) => x !== value) : [...s, value]));
  }

  function validateForm(): string | null {
    const trimmed = name.trim();
    if (!trimmed) return "Name is required.";
    if (trimmed.length > 128) return "Name must be 128 characters or fewer.";
    if (scopes.length === 0) return "Select at least one permission.";
    if (expiresAt) {
      const d = new Date(`${expiresAt}T23:59:59`);
      if (Number.isNaN(d.getTime()) || d.getTime() <= Date.now())
        return "Expiry must be a future date.";
    }
    return null;
  }

  async function createKey(e: FormEvent) {
    e.preventDefault();
    const err = validateForm();
    if (err) {
      setFormError(err);
      return;
    }
    setCreating(true);
    setFormError(null);
    try {
      const res = await api<ApiKeySecret>("/api/api-keys", {
        method: "POST",
        body: {
          name: name.trim(),
          environment,
          scopes,
          expires_at: expiresAt ? new Date(`${expiresAt}T23:59:59`).toISOString() : null,
        },
      });
      setCreateOpen(false);
      setName("");
      setScopes([]);
      setExpiresAt("");
      setEnvironment("development");
      load();
      showNotice(`API key "${res.key.name}" created.`);
      setCopied(false);
      setSecretMode("created");
      setSecretData(res);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to create API key");
    } finally {
      setCreating(false);
    }
  }

  const canSubmit = name.trim().length > 0 && scopes.length > 0;

  const host = window.location.host;
  const snippet = `curl -H "Authorization: Bearer sk_test_..." https://${host}/api/security/events?limit=10`;
  const tomorrow = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString().slice(0, 10);

  /* -------------------------------- Render -------------------------------- */

  return (
    <div className="space-y-4">
      {/* Header */}
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-bold text-slate-900">API Keys</h2>
            <p className="text-sm text-slate-500">
              Keys authenticate external integrations — e.g. your AI SOC submitting security
              events. Grant the minimum permissions each integration needs.
            </p>
          </div>
          <Button
            onClick={() => {
              setFormError(null);
              setCreateOpen(true);
            }}
          >
            + Create API Key
          </Button>
        </div>
      </Card>

      {notice && (
        <div className="rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">
          ✓ {notice}
        </div>
      )}

      {error ? (
        <div className="space-y-4">
          <ErrorBox message={error} />
          <Button variant="outline" onClick={load}>Retry</Button>
        </div>
      ) : keys === null ? (
        <LoadingScreen message="Loading API keys…" />
      ) : keys.length === 0 ? (
        <EmptyState
          icon="🔑"
          title="No API keys yet"
          subtitle="Create a key to let external tools call the API on your behalf. You'll see the full secret exactly once — copy it then — and use it as “Authorization: Bearer <key>”. Revoke a key to disable it instantly. Follow least privilege: give each integration only the permissions it needs."
          action={<Button onClick={() => setCreateOpen(true)}>Create your first key</Button>}
        />
      ) : (
        <>
          {actionError && <ErrorBox message={actionError} />}

          {/* Desktop: dense table */}
          <Card className="hidden overflow-x-auto p-0 md:block">
            <table className="w-full min-w-[52rem] text-left text-sm">
              <thead className="border-b border-gray-200 bg-gray-50 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-4 py-3">Name</th>
                  <th className="px-4 py-3">Environment</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Permissions</th>
                  <th className="px-4 py-3">Created</th>
                  <th className="px-4 py-3">Last used</th>
                  <th className="px-4 py-3">Expires</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {keys.map((k) => (
                  <tr key={k.id} className="align-top hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <span className="font-medium text-slate-900">{k.name}</span>
                      <span className="block font-mono text-xs text-slate-400">
                        {k.visible_prefix ?? k.key_id}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <Badge color={environmentColor(k.environment)}>
                        {k.environment === "production" ? "Production" : "Development"}
                      </Badge>
                    </td>
                    <td className="px-4 py-3">
                      <Badge color={apiKeyStatusColor(k.status)} className="capitalize">
                        {k.status}
                      </Badge>
                      {k.status === "revoked" && k.revoked_at && (
                        <span className="mt-1 block text-xs text-slate-400">
                          {formatDate(k.revoked_at)}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex max-w-[16rem] flex-wrap gap-1">
                        {k.scopes.map((s) => (
                          <ScopeChip key={s} value={s} />
                        ))}
                      </div>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-slate-700">
                      {formatDate(k.created_at)}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-slate-700">
                      {k.last_used_at ? formatDate(k.last_used_at) : "Never"}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-slate-700">
                      {k.expires_at ? formatDate(k.expires_at) : "Never"}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-right">
                      {k.status === "revoked" ? (
                        <span className="text-xs text-slate-400">—</span>
                      ) : (
                        <div className="flex justify-end gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            loading={busyId === k.id}
                            onClick={() => rotate(k)}
                          >
                            Rotate
                          </Button>
                          <Button
                            variant="danger"
                            size="sm"
                            loading={busyId === k.id}
                            onClick={() => revoke(k)}
                          >
                            Revoke
                          </Button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>

          {/* Mobile: stacked cards */}
          <div className="space-y-3 md:hidden">
            {keys.map((k) => (
              <Card key={k.id} className="space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="font-bold text-slate-900">{k.name}</p>
                    <p className="font-mono text-xs text-slate-400">{k.visible_prefix ?? k.key_id}</p>
                  </div>
                  <div className="flex gap-1">
                    <Badge color={environmentColor(k.environment)}>
                      {k.environment === "production" ? "Production" : "Development"}
                    </Badge>
                    <Badge color={apiKeyStatusColor(k.status)} className="capitalize">
                      {k.status}
                    </Badge>
                  </div>
                </div>
                <div className="flex flex-wrap gap-1">
                  {k.scopes.map((s) => (
                    <ScopeChip key={s} value={s} />
                  ))}
                </div>
                <div className="space-y-1 text-sm">
                  <MetaRow label="Created" value={formatDate(k.created_at)} />
                  <MetaRow label="Last used" value={k.last_used_at ? formatDate(k.last_used_at) : "Never"} />
                  <MetaRow label="Expires" value={k.expires_at ? formatDate(k.expires_at) : "Never"} />
                  {k.status === "revoked" && k.revoked_at && (
                    <MetaRow label="Revoked" value={formatDate(k.revoked_at)} />
                  )}
                </div>
                {k.status !== "revoked" && (
                  <div className="flex gap-2 pt-1">
                    <Button
                      variant="outline" size="sm"
                      loading={busyId === k.id}
                      onClick={() => rotate(k)}
                    >
                      Rotate
                    </Button>
                    <Button
                      variant="danger" size="sm"
                      loading={busyId === k.id}
                      onClick={() => revoke(k)}
                    >
                      Revoke
                    </Button>
                  </div>
                )}
              </Card>
            ))}
          </div>
        </>
      )}

      {/* Integration snippet */}
      <Card>
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-bold text-slate-900">Use a key from your integration</h3>
            <p className="text-xs text-slate-500">Send the key as a bearer token on every request.</p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={async () => {
              const ok = await copyText(snippet);
              if (ok) {
                setSnippetCopied(true);
                window.setTimeout(() => setSnippetCopied(false), 2000);
              }
            }}
          >
            {snippetCopied ? "Copied ✓" : "📋 Copy"}
          </Button>
        </div>
        <pre className="mt-3 overflow-x-auto rounded-lg bg-slate-900 p-3 text-xs leading-relaxed text-slate-100">
          <code>{snippet}</code>
        </pre>
        <p className="mt-2 text-xs text-slate-500">
          Full API reference: <code className="font-mono">/docs</code> on the backend, or the
          backend README.
        </p>
      </Card>

      {/* Create dialog */}
      <Modal
        open={createOpen}
        title="Create API key"
        onClose={() => setCreateOpen(false)}
        footer={
          <>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button onClick={createKey} disabled={!canSubmit} loading={creating}>
              Create key
            </Button>
          </>
        }
        wide
      >
        <form onSubmit={createKey} className="space-y-4">
          <div>
            <Input
              label="Name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. SOC agent — staging"
              maxLength={128}
            />
            <p className="mt-1 text-xs text-slate-400">{name.length}/128</p>
          </div>

          <div>
            <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
              Environment
            </span>
            <div className="grid grid-cols-2 gap-3">
              {ENVIRONMENTS.map((env) => (
                <button
                  key={env.value}
                  type="button"
                  onClick={() => setEnvironment(env.value)}
                  className={cn(
                    "rounded-lg border p-3 text-left transition-colors",
                    environment === env.value
                      ? "border-accent bg-accent/5 ring-1 ring-accent/40"
                      : "border-gray-300 bg-white hover:bg-gray-50",
                  )}
                >
                  <span className="block text-sm font-semibold text-slate-900">{env.title}</span>
                  <span className="block font-mono text-xs text-slate-500">{env.prefix}…</span>
                  <span className="mt-1 block text-xs text-slate-500">{env.hint}</span>
                </button>
              ))}
            </div>
            <p className="mt-1 text-xs text-slate-500">
              Use Development keys for testing.
            </p>
          </div>

          <div>
            <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
              Permissions
            </span>
            <div className="space-y-2">
              {SCOPES.map((scope) => (
                <label
                  key={scope.value}
                  className={cn(
                    "flex cursor-pointer items-start gap-3 rounded-lg border p-2.5",
                    scopes.includes(scope.value)
                      ? "border-accent/40 bg-accent/5"
                      : "border-gray-200 hover:bg-gray-50",
                  )}
                >
                  <input
                    type="checkbox"
                    checked={scopes.includes(scope.value)}
                    onChange={() => toggleScope(scope.value)}
                    className="mt-0.5 h-4 w-4 shrink-0 rounded border-gray-300 text-accent focus:ring-accent/40"
                  />
                  <span>
                    <ScopeChip value={scope.value} />
                    <span className="mt-1 block text-xs text-slate-600">{scope.label}</span>
                  </span>
                </label>
              ))}
            </div>
          </div>

          <Input
            label="Expiry (optional)"
            type="date"
            min={tomorrow}
            value={expiresAt}
            onChange={(e) => setExpiresAt(e.target.value)}
          />

          {formError && <ErrorBox message={formError} />}
          <button type="submit" className="hidden" aria-hidden="true" />
        </form>
      </Modal>

      {/* One-time secret modal (create + rotate) */}
      <Modal
        open={secretData !== null}
        title={secretMode === "rotated" ? "Key rotated" : "API key created"}
        onClose={() => setSecretData(null)}
        footer={
          <>
            <Button
              onClick={async () => {
                if (secretData && (await copyText(secretData.secret))) {
                  setCopied(true);
                  window.setTimeout(() => setCopied(false), 2500);
                }
              }}
            >
              {copied ? "Copied ✓" : "Copy"}
            </Button>
            <Button variant="outline" onClick={() => setSecretData(null)}>
              Done
            </Button>
          </>
        }
      >
        {secretData && (
          <div className="space-y-4">
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-sm text-amber-800">
              ⚠️ This is the only time the full key is shown — copy it now, it cannot be
              recovered.
            </div>
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                Secret for “{secretData.key.name}”
              </p>
              <input
                readOnly
                value={secretData.secret}
                onFocus={(e) => e.currentTarget.select()}
                className="w-full overflow-x-auto rounded-lg border border-gray-300 bg-gray-50 px-3 py-2 font-mono text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-accent/30"
              />
            </div>
            <p className="text-sm text-slate-500">
              Store it in your secrets manager and send it as{" "}
              <code className="rounded bg-gray-100 px-1 font-mono text-xs">
                Authorization: Bearer &lt;key&gt;
              </code>
              .
            </p>
          </div>
        )}
      </Modal>
    </div>
  );
}
