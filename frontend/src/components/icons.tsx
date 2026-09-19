// A small, consistent stroke icon set (24px grid, 1.7 stroke). Decorative by
// default: every glyph is aria-hidden, so the surrounding text carries meaning.

import { clsx } from "clsx";

export const GLYPHS = {
  wallet: "M3 7a2 2 0 012-2h13v4M3 7v10a2 2 0 002 2h15V9H5a2 2 0 01-2-2zM16 14h.01",
  trendUp: "M3 17l6-6 4 4 8-8M15 7h6v6",
  trendDown: "M3 7l6 6 4-4 8 8M15 17h6v-6",
  layers: "M12 3l9 5-9 5-9-5 9-5zM3 13l9 5 9-5",
  pulse: "M3 12h4l3 8 4-16 3 8h4",
  server: "M4 4h16v6H4zM4 14h16v6H4zM8 7h.01M8 17h.01",
  history: "M3 12a9 9 0 109-9 9.7 9.7 0 00-6.7 2.7L3 8M3 3v5h5M12 7v5l3 2",
  receipt: "M6 3h12v18l-3-2-3 2-3-2-3 2zM9 8h6M9 12h6",
  chart: "M3 3v18h18M7 15l4-4 3 3 6-7",
  bolt: "M13 2L4 14h7l-1 8 9-12h-7z",
  rocket: "M5 15c-1.5 1.5-2 5-2 5s3.5-.5 5-2M9 11a14 14 0 017-8h5v5a14 14 0 01-8 7l-4-4zM15 9h.01",
  list: "M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01",
  mail: "M4 5h16a1 1 0 011 1v12a1 1 0 01-1 1H4a1 1 0 01-1-1V6a1 1 0 011-1zM3 7l9 6 9-6",
  lock: "M6 11h12a1 1 0 011 1v8a1 1 0 01-1 1H6a1 1 0 01-1-1v-8a1 1 0 011-1zM8 11V7a4 4 0 118 0v4",
  eye: "M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12zM12 15a3 3 0 100-6 3 3 0 000 6z",
  eyeOff:
    "M3 3l18 18M10.6 5.1A9.8 9.8 0 0112 5c6.5 0 10 7 10 7a17 17 0 01-3 3.9M6.6 6.6A17 17 0 002 12s3.5 7 10 7a9.6 9.6 0 005.4-1.6M9.9 9.9a3 3 0 004.2 4.2",
  shield: "M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7z",
  flask: "M9 3h6M10 3v6L4.5 18.5A1.7 1.7 0 006 21h12a1.7 1.7 0 001.5-2.5L14 9V3M7 15h10",
  radar: "M12 3a9 9 0 109 9M12 7a5 5 0 105 5M12 12l7-7",
  arrowLeft: "M19 12H5M11 18l-6-6 6-6",
  arrowRight: "M5 12h14M13 6l6 6-6 6",
  alert: "M12 3l10 18H2zM12 10v4M12 17h.01",
  database: "M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3",
  inbox: "M4 13l2.5-7h11L20 13M4 13v6h16v-6M4 13h5l1 2h4l1-2h5",
  clock: "M12 3a9 9 0 100 18 9 9 0 000-18zM12 7v5l3 2",
  signal: "M5 12.5a10 10 0 0114 0M8.5 16a5 5 0 017 0M12 19.5h.01M2 9a14.5 14.5 0 0120 0",
  eyeSource: "M12 5c-6.5 0-10 7-10 7s3.5 7 10 7 10-7 10-7-3.5-7-10-7zM12 9v6M9 12h6",
} as const;

export type GlyphName = keyof typeof GLYPHS;

export function Glyph({
  name,
  className,
  strokeWidth = 1.7,
}: {
  name: GlyphName;
  className?: string;
  strokeWidth?: number;
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={clsx("shrink-0", className ?? "size-4")}
      fill="none"
      stroke="currentColor"
      aria-hidden
    >
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={strokeWidth} d={GLYPHS[name]} />
    </svg>
  );
}
