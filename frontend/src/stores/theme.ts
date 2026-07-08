import { create } from "zustand";

export type ThemeMode = "dark" | "light" | "system";

interface ThemeState {
  mode: ThemeMode;
  setMode: (mode: ThemeMode) => void;
}

const STORAGE_KEY = "am-theme";

function apply(mode: ThemeMode): void {
  const dark =
    mode === "dark" ||
    (mode === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
}

const initial = (localStorage.getItem(STORAGE_KEY) as ThemeMode | null) ?? "system";
apply(initial);

window
  .matchMedia("(prefers-color-scheme: dark)")
  .addEventListener("change", () => apply(useTheme.getState().mode));

export const useTheme = create<ThemeState>((set) => ({
  mode: initial,
  setMode: (mode) => {
    localStorage.setItem(STORAGE_KEY, mode);
    apply(mode);
    set({ mode });
  },
}));
