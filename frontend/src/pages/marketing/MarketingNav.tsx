import { clsx } from "clsx";
import { useEffect, useState } from "react";
import { Link } from "react-router";

import { BrandMark } from "@/components/BrandMark";
import { useAuth } from "@/stores/auth";

const LINKS = [
  { href: "#platform", label: "Platform" },
  { href: "#strategies", label: "Strategies" },
  { href: "#infrastructure", label: "Infrastructure" },
  { href: "#research", label: "Research" },
  { href: "#monitoring", label: "Monitoring" },
  { href: "#security", label: "Security" },
];

export function MarketingNav() {
  const status = useAuth((state) => state.status);
  const authenticated = status === "authenticated";
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const launchTo = authenticated ? "/app/dashboard" : "/login";

  return (
    <header
      className={clsx(
        "fixed inset-x-0 top-0 z-50 transition-[background-color,border-color,backdrop-filter] duration-300",
        scrolled
          ? "border-b border-white/8 bg-surface-950/75 backdrop-blur-md"
          : "border-b border-transparent bg-transparent",
      )}
    >
      <div className="mx-auto flex h-14 max-w-6xl min-w-0 items-center justify-between gap-3 px-4 sm:px-6">
        <BrandMark className="min-w-0 shrink" />
        <nav className="hidden items-center gap-6 lg:flex" aria-label="Primary">
          {LINKS.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="text-[13px] text-slate-400 transition-colors hover:text-white focus-visible:rounded-sm focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-accent-400"
            >
              {link.label}
            </a>
          ))}
        </nav>
        <div className="ml-auto flex shrink-0 items-center gap-2">
          <div className="hidden items-center gap-2 sm:flex">
            <Link
              to="/login"
              className="rounded-lg px-3 py-1.5 text-[13px] text-slate-300 transition-colors hover:bg-white/5 hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400"
            >
              Login
            </Link>
            <Link
              to={launchTo}
              className="rounded-lg border border-accent-400/30 bg-accent-500/15 px-3.5 py-1.5 text-[13px] font-medium text-accent-200 transition hover:border-accent-300/50 hover:bg-accent-400/20 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400"
            >
              Launch Platform
            </Link>
          </div>
          <button
            type="button"
            className="rounded-md border border-white/55 bg-slate-950/90 p-2 text-white shadow-sm hover:bg-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400 lg:hidden"
            aria-expanded={open}
            aria-controls="mobile-nav"
            aria-label={open ? "Close menu" : "Open menu"}
            onClick={() => setOpen((value) => !value)}
          >
          <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor">
            {open ? (
              <path strokeWidth="1.6" strokeLinecap="round" d="M6 6l12 12M18 6L6 18" />
            ) : (
              <path strokeWidth="1.6" strokeLinecap="round" d="M4 7h16M4 12h16M4 17h16" />
            )}
          </svg>
        </button>
        </div>
      </div>
      {open && (
        <div id="mobile-nav" className="border-t border-white/8 bg-surface-950/95 px-4 py-4 lg:hidden">
          <nav className="flex flex-col gap-1" aria-label="Mobile">
            {LINKS.map((link) => (
              <a
                key={link.href}
                href={link.href}
                onClick={() => setOpen(false)}
                className="rounded-lg px-3 py-2 text-sm text-slate-300 hover:bg-white/5"
              >
                {link.label}
              </a>
            ))}
            <Link to="/login" className="rounded-lg px-3 py-2 text-sm text-slate-300 hover:bg-white/5" onClick={() => setOpen(false)}>
              Login
            </Link>
            <Link
              to={launchTo}
              className="mt-1 rounded-lg bg-accent-600 px-3 py-2 text-center text-sm font-medium text-white"
              onClick={() => setOpen(false)}
            >
              Launch Platform
            </Link>
          </nav>
        </div>
      )}
    </header>
  );
}
