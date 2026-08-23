import { useState } from "react";
import { Button, Field, Input, Modal, Select, Textarea } from "@/components/ui";
import {
  type CalendarEvent,
  type EventCategory,
  type NewCalendarEventInput,
  type RepeatOption,
  useCalendarStore,
} from "@/stores/calendarEvents";

interface EventModalProps {
  open: boolean;
  onClose: () => void;
  initialDate?: string;
  initialStartTime?: string;
  editingEvent?: CalendarEvent | null;
}

function EventFormContent({
  editingEvent,
  initialDate,
  initialStartTime,
  onClose,
}: {
  editingEvent?: CalendarEvent | null;
  initialDate?: string;
  initialStartTime?: string;
  onClose: () => void;
}) {
  const addEvent = useCalendarStore((s) => s.addEvent);
  const updateEvent = useCalendarStore((s) => s.updateEvent);

  const getDefaults = () => {
    if (editingEvent) {
      return {
        title: editingEvent.title,
        date: editingEvent.date,
        startTime: editingEvent.startTime,
        endTime: editingEvent.endTime,
        category: editingEvent.category,
        description: editingEvent.description || "",
        location: editingEvent.location || "",
        repeat: editingEvent.repeat || ("none" as RepeatOption),
      };
    }
    const today = new Date();
    const defaultDateStr =
      initialDate ||
      `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;

    const start = initialStartTime || "09:00";
    const [sh, sm] = start.split(":").map(Number);
    const eh = Math.min(23, (sh || 9) + 1);
    const end = `${String(eh).padStart(2, "0")}:${String(sm || 0).padStart(2, "0")}`;

    return {
      title: "",
      date: defaultDateStr,
      startTime: start,
      endTime: end,
      category: "personal" as EventCategory,
      description: "",
      location: "",
      repeat: "none" as RepeatOption,
    };
  };

  const initialValues = getDefaults();
  const [title, setTitle] = useState(initialValues.title);
  const [date, setDate] = useState(initialValues.date);
  const [startTime, setStartTime] = useState(initialValues.startTime);
  const [endTime, setEndTime] = useState(initialValues.endTime);
  const [category, setCategory] = useState<EventCategory>(initialValues.category);
  const [description, setDescription] = useState(initialValues.description);
  const [location, setLocation] = useState(initialValues.location);
  const [repeat, setRepeat] = useState<RepeatOption>(initialValues.repeat);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      setError("Please enter an event title");
      return;
    }
    if (!date) {
      setError("Please select a date");
      return;
    }
    if (startTime >= endTime) {
      setError("End time must be after start time");
      return;
    }

    const payload: NewCalendarEventInput = {
      title: title.trim(),
      date,
      startTime,
      endTime,
      category,
      description: description.trim() || undefined,
      location: location.trim() || undefined,
      repeat,
    };

    if (editingEvent) {
      updateEvent(editingEvent.id, payload);
    } else {
      addEvent(payload);
    }

    onClose();
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {error && (
        <div className="rounded-lg bg-loss-500/10 p-3 text-xs font-medium text-loss-600 dark:text-loss-400">
          {error}
        </div>
      )}

      <Field label="Event Title" required>
        <Input
          placeholder="e.g. Morning Gym, Market Strategy Sync, Team Meeting"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          autoFocus
        />
      </Field>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Field label="Date" required>
          <Input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
        </Field>

        <Field label="Start Time" required>
          <Input
            type="time"
            value={startTime}
            onChange={(e) => setStartTime(e.target.value)}
          />
        </Field>

        <Field label="End Time" required>
          <Input
            type="time"
            value={endTime}
            onChange={(e) => setEndTime(e.target.value)}
          />
        </Field>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Category" required>
          <Select
            value={category}
            onChange={(e) => setCategory(e.target.value as EventCategory)}
          >
            <option value="personal">Personal</option>
            <option value="fitness">Fitness</option>
            <option value="gym">Gym</option>
            <option value="meeting">Meeting</option>
            <option value="work">Work</option>
            <option value="trading">Trading</option>
            <option value="research">Research</option>
            <option value="appointment">Appointment</option>
            <option value="other">Other</option>
          </Select>
        </Field>

        <Field label="Repeat">
          <Select
            value={repeat}
            onChange={(e) => setRepeat(e.target.value as RepeatOption)}
          >
            <option value="none">Does not repeat</option>
            <option value="daily">Daily</option>
            <option value="weekdays">Every weekday (Mon–Fri)</option>
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
          </Select>
        </Field>
      </div>

      <Field label="Location (Optional)">
        <Input
          placeholder="e.g. Office, Gym, Zoom link, Trading Desk"
          value={location}
          onChange={(e) => setLocation(e.target.value)}
        />
      </Field>

      <Field label="Description / Notes (Optional)">
        <Textarea
          placeholder="Add agendas, checklist, or preparation notes..."
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          className="min-h-20"
        />
      </Field>

      <div className="mt-6 flex justify-end gap-2 border-t border-slate-100 pt-4 dark:border-surface-800">
        <Button variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" variant="primary">
          {editingEvent ? "Save Changes" : "Create Event"}
        </Button>
      </div>
    </form>
  );
}

export function EventModal({
  open,
  onClose,
  initialDate,
  initialStartTime,
  editingEvent,
}: EventModalProps) {
  if (!open) return null;

  const key = editingEvent?.id ?? `${initialDate ?? ""}-${initialStartTime ?? ""}`;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={editingEvent ? "Edit Calendar Event" : "Create Calendar Event"}
    >
      <EventFormContent
        key={key}
        editingEvent={editingEvent}
        initialDate={initialDate}
        initialStartTime={initialStartTime}
        onClose={onClose}
      />
    </Modal>
  );
}
