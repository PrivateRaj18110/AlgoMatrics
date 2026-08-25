import { clsx } from "clsx";

interface ProgressRingProps {
  percentage: number;
  size?: number;
  strokeWidth?: number;
  colorClass?: string;
  label?: string;
  valueText?: string;
  subText?: string;
}

export function ProgressRing({
  percentage,
  size = 110,
  strokeWidth = 9,
  colorClass = "text-accent-500",
  label,
  valueText,
  subText,
}: ProgressRingProps) {
  const radius = (size - strokeWidth) / 2;
  const circumference = radius * 2 * Math.PI;
  const clamped = Math.min(100, Math.max(0, percentage));
  const strokeDashoffset = circumference - (clamped / 100) * circumference;

  return (
    <div className="flex flex-col items-center text-center">
      <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
        <svg className="size-full -rotate-90" viewBox={`0 0 ${size} ${size}`}>
          {/* Background track */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            stroke="currentColor"
            strokeWidth={strokeWidth}
            fill="transparent"
            className="text-slate-100 dark:text-surface-800"
          />
          {/* Progress bar */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            stroke="currentColor"
            strokeWidth={strokeWidth}
            fill="transparent"
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            strokeLinecap="round"
            className={clsx("transition-all duration-500", colorClass)}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center p-2 text-center">
          <span className="text-sm font-bold tracking-tight text-slate-900 tabular-nums dark:text-slate-100">
            {valueText ?? `${Math.round(clamped)}%`}
          </span>
          {subText && (
            <span className="text-[10px] text-slate-500 dark:text-slate-400">
              {subText}
            </span>
          )}
        </div>
      </div>
      {label && (
        <span className="mt-1.5 text-xs font-medium text-slate-600 dark:text-slate-300">
          {label}
        </span>
      )}
    </div>
  );
}
