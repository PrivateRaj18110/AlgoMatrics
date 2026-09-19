import { Link } from "react-router";

import { BrandMark } from "@/components/BrandMark";
import { Seo } from "@/components/Seo";
import { Button } from "@/components/ui";

export function NotFoundPage() {
  return (
    <div className="am-radial flex min-h-screen flex-col items-center justify-center gap-4 bg-surface-950 px-6 text-center text-slate-100">
      <Seo title="Page not found — ALGOMATRIC" noindex />
      <BrandMark />
      <p className="font-mono text-6xl font-semibold text-accent-400">404</p>
      <p className="text-lg font-medium">Page not found</p>
      <p className="max-w-sm text-sm text-slate-500">
        The page you are looking for does not exist or has moved.
      </p>
      <div className="flex gap-2">
        <Link to="/">
          <Button variant="secondary">Home</Button>
        </Link>
        <Link to="/app/dashboard">
          <Button>Go to dashboard</Button>
        </Link>
      </div>
    </div>
  );
}
