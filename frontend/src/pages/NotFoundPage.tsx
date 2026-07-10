import { Link } from "react-router";

import { Seo } from "@/components/Seo";
import { Button } from "@/components/ui";

export function NotFoundPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-surface-50 text-center dark:bg-surface-950">
      <Seo title="Page not found — Algo Matrics" noindex />
      <p className="text-6xl font-bold text-accent-500">404</p>
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
