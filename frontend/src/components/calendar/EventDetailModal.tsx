import { Button, ConfirmDialog, Modal } from "@/components/ui";
import {
  type CalendarEvent,
  CATEGORY_COLORS,
  useCalendarStore,
} from "@/stores/calendarEvents";
import { useState } from "react";

interface EventDetailModalProps {
  event: CalendarEvent | null;
  open: boolean;
  onClose: () => void;
  onEdit: (event: CalendarEvent) => void;
}

export function EventDetailModal({
  event,
  open,
  onClose,
  onEdit,
}: EventDetailModalProps) {
  const deleteEvent = useCalendarStore((s) => s.deleteEvent);
  const [confirmDelete, setConfirmDelete] = useState(false);

  if (!event) return null;

  const categoryConfig = CATEGORY_COLORS[event.category] || CATEGORY_COLORS.other;

  const handleDelete = () => {
    deleteEvent(event.id);
    setConfirmDelete(false);
    onClose();
  };

  return (
    <>
      <Modal open={open && !confirmDelete} onClose={onClose} title="Event Details">
        <div className="space-y-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
                {event.title}
              </h3>
              <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                {event.date} · {event.startTime} – {event.endTime}
              </p>
            </div>
            <span
              className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${categoryConfig.badge}`}
            >
              <span className={`size-1.5 rounded-full ${categoryConfig.dot}`} />
              {categoryConfig.label}
            </span>
          </div>

          {event.repeat && event.repeat !== "none" && (
            <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
              <svg className="size-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                />
              </svg>
              <span>Repeats: {event.repeat}</span>
            </div>
          )}

          {event.location && (
            <div className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300">
              <svg className="size-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"
                />
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"
                />
              </svg>
              <span>{event.location}</span>
            </div>
          )}

          {event.description && (
            <div className="rounded-lg border border-slate-100 bg-slate-50 p-3 text-xs text-slate-700 dark:border-surface-800 dark:bg-surface-850 dark:text-slate-300">
              <p className="whitespace-pre-wrap">{event.description}</p>
            </div>
          )}

          <div className="mt-6 flex justify-between border-t border-slate-100 pt-4 dark:border-surface-800">
            <Button
              variant="danger"
              size="sm"
              onClick={() => setConfirmDelete(true)}
            >
              Delete
            </Button>
            <div className="flex gap-2">
              <Button variant="secondary" size="sm" onClick={onClose}>
                Close
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={() => {
                  onClose();
                  onEdit(event);
                }}
              >
                Edit Event
              </Button>
            </div>
          </div>
        </div>
      </Modal>

      <ConfirmDialog
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        onConfirm={handleDelete}
        title="Delete Event"
        body={`Are you sure you want to delete "${event.title}"? This action cannot be undone.`}
        confirmLabel="Delete"
        danger
      />
    </>
  );
}
