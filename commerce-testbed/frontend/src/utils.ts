/** Join class names, dropping falsy values. */
export function cn(
  ...classes: (string | false | null | undefined | Record<string, boolean | undefined>)[]
): string {
  const out: string[] = [];
  for (const c of classes) {
    if (!c) continue;
    if (typeof c === "string") out.push(c);
    else
      for (const [k, v] of Object.entries(c)) if (v) out.push(k);
  }
  return out.join(" ");
}

export function formatDate(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
