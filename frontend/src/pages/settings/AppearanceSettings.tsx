import { Card } from "@/components/ui";
import { type ThemeMode, useTheme } from "@/stores/theme";

const OPTIONS: Array<{ value: ThemeMode; label: string; description: string }> = [
  { value: "dark", label: "Dark", description: "Low-light trading interface" },
  { value: "light", label: "Light", description: "Bright, high-contrast interface" },
  { value: "system", label: "System", description: "Follow your OS preference" },
];

export function AppearanceSettings() {
  const mode = useTheme((state) => state.mode);
  const setMode = useTheme((state) => state.setMode);

  return (
    <div className="max-w-xl">
      <Card title="Appearance">
        <div className="grid gap-3 sm:grid-cols-3">
          {OPTIONS.map((option) => (
            <button
              key={option.value}
              onClick={() => setMode(option.value)}
              className={
                mode === option.value
                  ? "rounded-lg border-2 border-accent-500 p-4 text-left"
                  : "rounded-lg border border-slate-200 p-4 text-left dark:border-surface-700"
              }
            >
              <p className="font-medium">{option.label}</p>
              <p className="mt-1 text-xs text-slate-400">{option.description}</p>
            </button>
          ))}
        </div>
      </Card>
    </div>
  );
}
