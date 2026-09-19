// Display helpers for "who / where / on what" evidence. Presentation only:
// nothing here is used to make a security decision.

/** "Chrome · Windows" from a raw user-agent string. */
export function describeDevice(userAgent: string | null | undefined): string {
  if (!userAgent) return "Unknown device";
  const browser = /Edg\//.test(userAgent)
    ? "Edge"
    : /OPR\//.test(userAgent)
      ? "Opera"
      : /Firefox\//.test(userAgent)
        ? "Firefox"
        : /Chrome\//.test(userAgent)
          ? "Chrome"
          : /Safari\//.test(userAgent)
            ? "Safari"
            : /curl|python|httpx|okhttp|Go-http/i.test(userAgent)
              ? "Script / API"
              : "Browser";
  const os = /Windows/.test(userAgent)
    ? "Windows"
    : /Android/.test(userAgent)
      ? "Android"
      : /iPhone|iPad|iOS/.test(userAgent)
        ? "iOS"
        : /Mac OS X|Macintosh/.test(userAgent)
          ? "macOS"
          : /Linux/.test(userAgent)
            ? "Linux"
            : null;
  return os ? `${browser} · ${os}` : browser;
}

/** Regional-indicator flag for an ISO 3166 alpha-2 code ("IN" → 🇮🇳). */
export function flagEmoji(countryCode: string | null | undefined): string {
  if (!countryCode || !/^[A-Za-z]{2}$/.test(countryCode)) return "";
  return String.fromCodePoint(
    ...countryCode
      .toUpperCase()
      .split("")
      .map((char) => 0x1f1e6 + char.charCodeAt(0) - 65),
  );
}

export interface GeoInfo {
  country?: string | null;
  country_code?: string | null;
  region?: string | null;
  city?: string | null;
}

/** "Mumbai, Maharashtra, India" — whatever parts are known. */
export function describeLocation(geo: GeoInfo | null | undefined): string | null {
  if (!geo) return null;
  const parts = [geo.city, geo.region, geo.country].filter(
    (part, index, all): part is string => Boolean(part) && all.indexOf(part) === index,
  );
  return parts.length ? parts.join(", ") : null;
}
