// Lightweight, dependency-free real-user monitoring. Collects a handful of Web
// Vitals plus client errors and ships them to the backend RUM endpoint, which
// folds them into Prometheus. Everything is best-effort and feature-detected so
// an unsupported browser silently records nothing rather than throwing.

import { API_BASE, correlationId } from "@/lib/api";

type MetricName = "CLS" | "LCP" | "FCP" | "TTFB" | "LoadTime";

interface RumMetric {
  name: MetricName;
  value: number;
}
interface RumError {
  kind: "error" | "unhandledrejection";
}

const metrics: RumMetric[] = [];
const errors: RumError[] = [];
let sent = false;

function record(name: MetricName, value: number): void {
  if (Number.isFinite(value) && value >= 0) {
    metrics.push({ name, value: Math.round(value * 1000) / 1000 });
  }
}

function flush(): void {
  if (sent || (metrics.length === 0 && errors.length === 0)) return;
  sent = true;
  const payload = JSON.stringify({ metrics, errors });
  const url = `${API_BASE}/rum`;
  try {
    // sendBeacon survives page unload; fall back to a keepalive fetch.
    if (navigator.sendBeacon) {
      navigator.sendBeacon(url, new Blob([payload], { type: "application/json" }));
    } else {
      void fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Correlation-ID": correlationId() },
        body: payload,
        keepalive: true,
      });
    }
  } catch {
    // RUM must never affect the app.
  }
}

function observe(type: string, cb: (entry: PerformanceEntry) => void): void {
  try {
    const observer = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) cb(entry);
    });
    observer.observe({ type, buffered: true } as PerformanceObserverInit);
  } catch {
    // Entry type unsupported in this browser.
  }
}

export function initTelemetry(): void {
  if (typeof window === "undefined") return;

  // Navigation timing: TTFB and total load time.
  observe("navigation", (entry) => {
    const nav = entry as PerformanceNavigationTiming;
    record("TTFB", nav.responseStart);
    if (nav.loadEventEnd > 0) record("LoadTime", nav.loadEventEnd);
  });

  // First Contentful Paint.
  observe("paint", (entry) => {
    if (entry.name === "first-contentful-paint") record("FCP", entry.startTime);
  });

  // Largest Contentful Paint — keep the latest reported value.
  let lcp = 0;
  observe("largest-contentful-paint", (entry) => {
    lcp = entry.startTime;
  });

  // Cumulative Layout Shift — sum shifts that were not user initiated.
  let cls = 0;
  observe("layout-shift", (entry) => {
    const shift = entry as PerformanceEntry & { value: number; hadRecentInput: boolean };
    if (!shift.hadRecentInput) cls += shift.value;
  });

  window.addEventListener("error", () => errors.push({ kind: "error" }));
  window.addEventListener("unhandledrejection", () =>
    errors.push({ kind: "unhandledrejection" }),
  );

  // Flush once the page is being hidden/unloaded, finalising LCP and CLS.
  const finalise = (): void => {
    if (lcp > 0) record("LCP", lcp);
    record("CLS", cls);
    flush();
  };
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") finalise();
  });
  window.addEventListener("pagehide", finalise);
}
