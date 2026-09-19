import { Link } from "react-router";

import { BrandMark } from "@/components/BrandMark";
import { useAuth } from "@/stores/auth";

const NAV = [
  { href: "#platform", label: "Platform" },
  { href: "#strategies", label: "Strategies" },
  { href: "#infrastructure", label: "Infrastructure" },
  { href: "#research", label: "Research" },
  { href: "#monitoring", label: "Monitoring" },
  { href: "#security", label: "Security" },
];

export function MarketingFooter() {
  const authenticated = useAuth((state) => state.status) === "authenticated";
  const launchTo = authenticated ? "/app/dashboard" : "/login";

  return (
    <footer className="border-t border-white/8 bg-[#080b11]">
      <div className="mx-auto grid max-w-6xl gap-10 px-4 py-14 sm:px-6 md:grid-cols-[1.4fr_1fr_1fr]">
        <div>
          <BrandMark />
          <p className="mt-4 max-w-sm text-sm leading-relaxed text-slate-500">
            Quantitative infrastructure for systematic markets.
          </p>
        </div>
        <div>
          <p className="text-[11px] tracking-[0.2em] text-slate-500">NAVIGATION</p>
          <ul className="mt-3 space-y-2 text-sm text-slate-400">
            {NAV.map((item) => (
              <li key={item.href}>
                <a className="hover:text-white" href={item.href}>
                  {item.label}
                </a>
              </li>
            ))}
            <li>
              {/* The contact form, not a mailto: the domain has no inbound mail
                  (no MX record), so mail to hello@ would bounce. */}
              <Link className="hover:text-white" to="/contact">
                Contact
              </Link>
            </li>
          </ul>
        </div>
        <div>
          <p className="text-[11px] tracking-[0.2em] text-slate-500">PLATFORM</p>
          <ul className="mt-3 space-y-2 text-sm text-slate-400">
            <li>
              <Link className="hover:text-white" to="/login">
                Login
              </Link>
            </li>
            <li>
              <Link className="hover:text-white" to={launchTo}>
                Launch Platform
              </Link>
            </li>
            <li>
              <Link className="hover:text-white" to="/forgot-password">
                Reset password
              </Link>
            </li>
          </ul>
        </div>
      </div>
      <div className="border-t border-white/6">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-5 text-xs text-slate-600 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p>© {new Date().getFullYear()} ALGOMATRIC. All rights reserved.</p>
          <p>Trading involves risk. Past results do not indicate future performance.</p>
        </div>
      </div>
    </footer>
  );
}
