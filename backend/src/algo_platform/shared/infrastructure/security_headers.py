"""OWASP security response headers.

The policy is a pure function of the environment so it is unit testable; the
middleware just applies the returned mapping. HSTS is only emitted where TLS is
guaranteed (staging/production) so local http development is not broken.
"""

from __future__ import annotations

# A conservative default CSP for a JSON API. The API serves no HTML of its own
# except the dev-only Swagger UI; `frame-ancestors 'none'` and `default-src
# 'none'` keep the surface minimal while allowing the docs page to function.
_API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
_DOCS_CSP = (
    "default-src 'none'; img-src 'self' data:; script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
)

_HSTS = "max-age=63072000; includeSubDomains; preload"

_TLS_ENVIRONMENTS = frozenset({"staging", "production"})


def security_headers(app_env: str, *, is_docs: bool = False) -> dict[str, str]:
    """Return the security headers to apply for a response.

    ``is_docs`` relaxes the CSP for the interactive API docs (dev/test only),
    which need inline scripts/styles to render.
    """

    headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Resource-Policy": "same-origin",
        "Permissions-Policy": "geolocation=(), microphone=(), camera=(), payment=()",
        "Content-Security-Policy": _DOCS_CSP if is_docs else _API_CSP,
    }
    if app_env in _TLS_ENVIRONMENTS:
        headers["Strict-Transport-Security"] = _HSTS
    return headers
