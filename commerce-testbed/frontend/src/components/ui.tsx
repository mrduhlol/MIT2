import { useEffect, useState, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from "react";
import { cn } from "../utils";

/* ---------------------------------- Button --------------------------------- */

type ButtonVariant = "primary" | "secondary" | "danger" | "ghost" | "outline" | "cta";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: "sm" | "md" | "lg";
  loading?: boolean;
}

const buttonStyles: Record<ButtonVariant, string> = {
  primary:
    "bg-accent hover:bg-accent-dark text-white shadow-sm focus-visible:ring-accent/50",
  cta: "bg-cta hover:bg-cta-dark text-navy border border-[#e7c007] shadow-sm focus-visible:ring-cta/60",
  secondary:
    "bg-navy-light hover:bg-navy text-white shadow-sm focus-visible:ring-navy/50",
  danger:
    "bg-red-600 hover:bg-red-700 text-white shadow-sm focus-visible:ring-red-500/50",
  ghost:
    "bg-transparent hover:bg-gray-100 text-slate-700 focus-visible:ring-slate-300",
  outline:
    "bg-white hover:bg-gray-50 text-slate-700 border border-gray-300 shadow-sm hover:shadow focus-visible:ring-slate-400",
};

const buttonSizes = {
  sm: "px-2.5 py-1.5 text-xs",
  md: "px-4 py-2 text-sm",
  lg: "px-5 py-2.5 text-sm",
};

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  className,
  disabled,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 disabled:pointer-events-none disabled:opacity-50",
        buttonStyles[variant],
        buttonSizes[size],
        className,
      )}
      disabled={disabled || loading}
      {...rest}
    >
      {loading && <Spinner className="h-3.5 w-3.5" />}
      {children}
    </button>
  );
}

/* ---------------------------------- Input ---------------------------------- */

export function Label({ children }: { children: ReactNode }) {
  return (
    <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
      {children}
    </label>
  );
}

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
}

export function Input({ label, className, ...rest }: InputProps) {
  return (
    <div>
      {label && <Label>{label}</Label>}
      <input
        className={cn(
          "w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-slate-800 placeholder-slate-400 shadow-sm transition-colors focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30 disabled:bg-gray-100",
          className,
        )}
        {...rest}
      />
    </div>
  );
}

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
}

export function Select({ label, className, children, ...rest }: SelectProps) {
  return (
    <div>
      {label && <Label>{label}</Label>}
      <select
        className={cn(
          "w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-slate-800 shadow-sm focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30",
          className,
        )}
        {...rest}
      >
        {children}
      </select>
    </div>
  );
}

/* ----------------------------------- Card ---------------------------------- */

interface CardProps {
  children: ReactNode;
  className?: string;
}

export function Card({ children, className }: CardProps) {
  return (
    <div
      className={cn(
        "rounded-xl border border-gray-200 bg-white p-5 shadow-sm",
        className,
      )}
    >
      {children}
    </div>
  );
}

/* ---------------------------------- Badge ---------------------------------- */

export type BadgeColor = "gray" | "green" | "amber" | "blue" | "red";

interface BadgeProps {
  children: ReactNode;
  color?: BadgeColor;
  className?: string;
}

const badgeColors: Record<BadgeColor, string> = {
  gray: "bg-gray-100 text-gray-600 ring-gray-200",
  green: "bg-green-100 text-green-700 ring-green-200",
  amber: "bg-amber-100 text-amber-700 ring-amber-200",
  blue: "bg-blue-100 text-blue-700 ring-blue-200",
  red: "bg-red-100 text-red-700 ring-red-200",
};

export function Badge({ children, color = "gray", className }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset",
        badgeColors[color],
        className,
      )}
    >
      {children}
    </span>
  );
}

/** Map an order status string to a badge color. */
export function statusColor(status: string): BadgeColor {
  const s = status.toLowerCase();
  if (["delivered", "shipped", "completed", "paid"].includes(s)) return "green";
  if (["pending", "processing", "placed"].includes(s)) return "amber";
  if (["cancelled", "canceled", "failed", "refunded"].includes(s)) return "red";
  return "blue";
}

/* --------------------------------- Spinner --------------------------------- */

export function Spinner({ className }: { className?: string }) {
  return (
    <svg
      className={cn("h-5 w-5 animate-spin text-accent", className)}
      viewBox="0 0 24 24"
      fill="none"
      aria-label="Loading"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-90"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
      />
    </svg>
  );
}

export function LoadingScreen({ message = "Loading…" }: { message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-24 text-slate-500">
      <Spinner />
      <p className="text-sm">{message}</p>
    </div>
  );
}

/* --------------------------------- ErrorBox -------------------------------- */

export function ErrorBox({ message }: { message?: string | null }) {
  if (!message) return null;
  return (
    <div
      className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
      role="alert"
    >
      {message}
    </div>
  );
}

/* ------------------------------- ProductImage ------------------------------ */

const PLACEHOLDER =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300"><rect width="100%" height="100%" fill="#f1f5f9"/><rect x="90" y="120" width="120" height="80" rx="8" fill="#cbd5e1"/><circle cx="125" cy="140" r="10" fill="#94a3b8"/><path d="M100 190l30-30 20 20 25-30 25 40z" fill="#94a3b8"/></svg>`,
  );

export function ProductImage({
  src,
  alt,
  className,
}: {
  src: string | null | undefined;
  alt: string;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);
  const effective = failed || !src ? PLACEHOLDER : src;
  return (
    <img
      src={effective}
      alt={alt}
      loading="lazy"
      onError={() => setFailed(true)}
      className={cn("bg-gray-100 object-contain", className)}
    />
  );
}

/* -------------------------------- EmptyState ------------------------------- */

export function EmptyState({
  icon = "🗂️",
  title,
  subtitle,
  action,
}: {
  icon?: string;
  title: string;
  subtitle?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-gray-300 bg-white px-6 py-16 text-center">
      <span className="text-4xl">{icon}</span>
      <p className="text-base font-semibold text-slate-700">{title}</p>
      {subtitle && <p className="max-w-sm text-sm text-slate-500">{subtitle}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

/* ---------------------------------- Modal ---------------------------------- */

interface ModalProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  /** Optional footer row (usually cancel/confirm buttons). */
  footer?: ReactNode;
  wide?: boolean;
}

export function Modal({ open, title, onClose, children, footer, wide }: ModalProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <div className="absolute inset-0 bg-slate-900/50" onClick={onClose} />
      <div
        className={cn(
          "relative flex max-h-[85vh] w-full flex-col rounded-xl bg-white shadow-xl",
          wide ? "max-w-2xl" : "max-w-lg",
        )}
      >
        <div className="flex items-center justify-between border-b border-gray-200 px-5 py-4">
          <h3 className="font-bold text-slate-900">{title}</h3>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="-mr-1 rounded-lg p-1 text-slate-400 hover:bg-gray-100 hover:text-slate-600"
          >
            ✕
          </button>
        </div>
        <div className="overflow-y-auto px-5 py-4">{children}</div>
        {footer && (
          <div className="flex justify-end gap-3 border-t border-gray-200 px-5 py-4">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
