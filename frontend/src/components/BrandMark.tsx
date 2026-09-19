import { clsx } from "clsx";
import { Link } from "react-router";

export function BrandMark({
  className,
  to = "/",
  compact = false,
}: {
  className?: string;
  to?: string;
  compact?: boolean;
}) {
  return (
    <Link
      to={to}
      className={clsx("group inline-flex items-center gap-2.5 text-current", className)}
      aria-label="ALGOMATRIC home"
    >
      <span className="relative flex size-7 items-center justify-center" aria-hidden>
        <svg viewBox="0 0 28 28" className="size-7">
          <rect width="28" height="28" rx="7" fill="#1497b5" fillOpacity="0.18" />
          <rect x="0.5" y="0.5" width="27" height="27" rx="6.5" stroke="#3dd0ea" strokeOpacity="0.45" fill="none" />
          <circle cx="8" cy="18" r="1.6" fill="#3dd0ea" />
          <circle cx="14" cy="8" r="1.7" fill="#e2f8fd" />
          <circle cx="20" cy="18" r="1.6" fill="#34d399" />
          <path d="M8 18 L14 8 L20 18" stroke="#9adff0" strokeWidth="1.2" fill="none" />
        </svg>
      </span>
      {!compact && (
        <span className="font-semibold tracking-[0.12em] text-[12px] sm:tracking-[0.18em] sm:text-[13px]">ALGOMATRIC</span>
      )}
    </Link>
  );
}
