import { useTheme } from "@/stores/theme";

export function ThemeToggle() {
  const mode = useTheme((state) => state.mode);
  const setMode = useTheme((state) => state.setMode);
  const next = mode === "dark" ? "light" : mode === "light" ? "system" : "dark";
  const label = mode === "dark" ? "🌙" : mode === "light" ? "☀️" : "🖥️";

  return (
    <button
      onClick={() => setMode(next)}
      className="rounded-md p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-surface-800"
      aria-label={`Switch theme (current: ${mode})`}
      title={`Theme: ${mode}`}
    >
      <span aria-hidden>{label}</span>
    </button>
  );
}
