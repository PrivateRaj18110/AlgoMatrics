import { useEffect } from "react";

const ORIGIN = "https://algomatrics.in";

interface SeoProps {
  title: string;
  description?: string;
  /** Path only, e.g. "/login". Rendered as an absolute canonical URL. */
  canonicalPath?: string;
  noindex?: boolean;
}

function upsertHeadTag(selector: string, create: () => HTMLElement): HTMLElement {
  let el = document.head.querySelector<HTMLElement>(selector);
  if (!el) {
    el = create();
    document.head.appendChild(el);
  }
  return el;
}

/**
 * Per-route document metadata for the crawlable public pages. Googlebot
 * indexes the rendered DOM, so titles/canonicals set here are picked up;
 * the static defaults in index.html cover non-rendering crawlers.
 */
export function Seo({ title, description, canonicalPath, noindex = false }: SeoProps) {
  useEffect(() => {
    document.title = title;

    if (description) {
      const meta = upsertHeadTag('meta[name="description"]', () => {
        const el = document.createElement("meta");
        el.setAttribute("name", "description");
        return el;
      });
      meta.setAttribute("content", description);
    }

    if (canonicalPath) {
      const link = upsertHeadTag('link[rel="canonical"]', () => {
        const el = document.createElement("link");
        el.setAttribute("rel", "canonical");
        return el;
      });
      link.setAttribute("href", `${ORIGIN}${canonicalPath}`);
    }

    const robots = document.head.querySelector('meta[name="robots"]');
    if (noindex) {
      const meta = upsertHeadTag('meta[name="robots"]', () => {
        const el = document.createElement("meta");
        el.setAttribute("name", "robots");
        return el;
      });
      meta.setAttribute("content", "noindex");
    } else if (robots) {
      robots.remove();
    }
  }, [title, description, canonicalPath, noindex]);

  return null;
}
