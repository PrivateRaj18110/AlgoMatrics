// Apply the persisted theme before first paint to avoid a flash.
// Kept as an external file (not inline) so the CSP can stay `script-src 'self'`.
try {
  var stored = localStorage.getItem("am-theme");
  var dark =
    stored === "dark" ||
    ((stored === null || stored === "system") &&
      window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
} catch (e) {}
