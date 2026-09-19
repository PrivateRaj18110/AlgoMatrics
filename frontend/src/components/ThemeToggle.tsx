import { useTheme } from "@/stores/theme";

export function ThemeToggle() {
  const mode = useTheme((state) => state.mode);
  const setMode = useTheme((state) => state.setMode);
  const next = mode === "dark" ? "light" : mode === "light" ? "system" : "dark";

  return (
    <button
      onClick={() => setMode(next)}
      className="rounded-md p-2 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400 dark:hover:bg-white/5 dark:hover:text-white"
      aria-label={`Switch theme (current: ${mode})`}
      title={`Theme: ${mode}`}
    >
      {mode === "light" ? (
        <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" aria-hidden>
          <circle cx="12" cy="12" r="4" strokeWidth="1.6" />
          <path strokeWidth="1.6" strokeLinecap="round" d="M12 3v2M12 19v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M3 12h2M19 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
        </svg>
      ) : mode === "dark" ? (
        <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" aria-hidden>
          <path strokeWidth="1.6" d="M16 13a6 6 0 01-7-7 6.5 6.5 0 1010.2 6.8A5.5 5.5 0 0116 13z" />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" aria-hidden>
          <rect x="3" y="5" width="18" height="14" rx="2" strokeWidth="1.6" />
          <path strokeWidth="1.6" d="M8 19h8" />
        </svg>
      )}
    </button>
  );
}
