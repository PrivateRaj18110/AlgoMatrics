import { Badge, Button, Modal } from "@/components/ui";
import type { MarketSessionWindow } from "@/lib/marketSessions";

interface MarketBlockDetailModalProps {
  session: MarketSessionWindow | null;
  open: boolean;
  onClose: () => void;
}

export function MarketBlockDetailModal({
  session,
  open,
  onClose,
}: MarketBlockDetailModalProps) {
  if (!session) return null;

  return (
    <Modal open={open} onClose={onClose} title="System Market Schedule">
      <div className="space-y-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1 rounded-md bg-blue-500/15 px-2 py-0.5 text-xs font-semibold text-blue-700 dark:text-blue-300">
                <svg className="size-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
                  />
                </svg>
                SYSTEM SCHEDULE
              </span>
              <Badge color="blue">Asia/Kolkata (IST)</Badge>
            </div>
            <h3 className="mt-2 text-lg font-bold text-slate-900 dark:text-white">
              {session.name}
            </h3>
            <p className="text-xs font-medium text-slate-500 dark:text-slate-400">
              {session.startTime} – {session.endTime} IST (NSE / BSE)
            </p>
          </div>
        </div>

        <div className="rounded-lg border border-blue-100 bg-blue-50/50 p-3.5 text-xs text-blue-900 dark:border-blue-900/40 dark:bg-blue-950/30 dark:text-blue-200">
          <p className="font-semibold">{session.description}</p>
          <p className="mt-1 text-slate-600 dark:text-slate-300">
            {session.phase === "pre" &&
              "Pre-open order entry and equilibrium price discovery session for NSE/BSE cash equities."}
            {session.phase === "main" &&
              "Continuous automated matching and trading for equity, derivatives, and currency segments."}
            {session.phase === "post" &&
              "Post-market closing price determination and block trade reporting window."}
          </p>
        </div>

        <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600 dark:border-surface-800 dark:bg-surface-850 dark:text-slate-400">
          <p className="font-medium text-slate-700 dark:text-slate-200">
            System Calendar Notice:
          </p>
          <p className="mt-0.5">
            This block represents official market exchange operating hours. It is an automated system reference schedule and is not linked to active strategy execution, open positions, or VM heartbeats.
          </p>
        </div>

        <div className="mt-6 flex justify-end border-t border-slate-100 pt-4 dark:border-surface-800">
          <Button variant="secondary" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </Modal>
  );
}
