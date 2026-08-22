import { useMemo, useState } from "react";

import { Button, Card, EmptyState, Field, Input, PageHeader, Select } from "@/components/ui";
import { useArchiveTask, useCreateTask, useUpdateTask, useWorkspaceTasks } from "@/lib/hooks";
import { formatTradingTime } from "@/lib/time";
import type { WorkspaceTask } from "@/types/api";

function startOfTodayUtc(): Date {
  const now = new Date();
  return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
}

function bucket(task: WorkspaceTask): "today" | "upcoming" | "completed" {
  if (task.completed_at) return "completed";
  if (!task.due_at) return "today";
  const due = new Date(task.due_at);
  const today = startOfTodayUtc();
  const tomorrow = new Date(today.getTime() + 24 * 60 * 60 * 1000);
  if (due < tomorrow) return "today";
  return "upcoming";
}

export function TodoPage() {
  const { data, isLoading, isError } = useWorkspaceTasks();
  const create = useCreateTask();
  const update = useUpdateTask();
  const archive = useArchiveTask();
  const [title, setTitle] = useState("");
  const [priority, setPriority] = useState("normal");
  const [dueAt, setDueAt] = useState("");
  const [tag, setTag] = useState("");

  const groups = useMemo(() => {
    const items = (data ?? []).filter((task) => !task.archived_at);
    return {
      today: items.filter((task) => bucket(task) === "today"),
      upcoming: items.filter((task) => bucket(task) === "upcoming"),
      completed: items.filter((task) => bucket(task) === "completed"),
    };
  }, [data]);

  async function addTask() {
    const next = title.trim();
    if (!next) return;
    await create.mutateAsync({
      title: next,
      priority,
      due_at: dueAt ? new Date(dueAt).toISOString() : null,
      tag: tag.trim() || null,
    });
    setTitle("");
    setDueAt("");
    setTag("");
  }

  return (
    <div className="space-y-4">
      <PageHeader title="To Do" description="Simple tasks stored on the server for this organization." />
      <Card>
        <form
          className="grid gap-3 sm:grid-cols-4"
          onSubmit={(event) => {
            event.preventDefault();
            void addTask();
          }}
        >
          <Field label="Task">
            <Input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Check Google engine" />
          </Field>
          <Field label="Priority">
            <Select value={priority} onChange={(event) => setPriority(event.target.value)}>
              <option value="low">Low</option>
              <option value="normal">Normal</option>
              <option value="high">High</option>
            </Select>
          </Field>
          <Field label="Due (local input, stored UTC)">
            <Input type="datetime-local" value={dueAt} onChange={(event) => setDueAt(event.target.value)} />
          </Field>
          <Field label="Tag">
            <Input value={tag} onChange={(event) => setTag(event.target.value)} placeholder="ops" />
          </Field>
          <div className="flex items-end">
            <Button type="submit" loading={create.isPending} disabled={!title.trim()}>
              Add
            </Button>
          </div>
        </form>
      </Card>
      {isLoading ? (
        <Card>
          <p className="text-sm text-slate-500">Loading tasks…</p>
        </Card>
      ) : isError ? (
        <EmptyState title="Could not load tasks" />
      ) : (
        <>
          <TaskGroup
            title="Today"
            tasks={groups.today}
            onToggle={(task) => update.mutate({ id: task.id, completed: !task.completed_at })}
            onArchive={(task) => archive.mutate(task.id)}
            onRename={(task, next) => update.mutate({ id: task.id, title: next })}
          />
          <TaskGroup
            title="Upcoming"
            tasks={groups.upcoming}
            onToggle={(task) => update.mutate({ id: task.id, completed: !task.completed_at })}
            onArchive={(task) => archive.mutate(task.id)}
            onRename={(task, next) => update.mutate({ id: task.id, title: next })}
          />
          <TaskGroup
            title="Completed"
            tasks={groups.completed}
            onToggle={(task) => update.mutate({ id: task.id, completed: !task.completed_at })}
            onArchive={(task) => archive.mutate(task.id)}
            onRename={(task, next) => update.mutate({ id: task.id, title: next })}
          />
        </>
      )}
    </div>
  );
}

function TaskGroup({
  title,
  tasks,
  onToggle,
  onArchive,
  onRename,
}: {
  title: string;
  tasks: WorkspaceTask[];
  onToggle: (task: WorkspaceTask) => void;
  onArchive: (task: WorkspaceTask) => void;
  onRename: (task: WorkspaceTask, title: string) => void;
}) {
  return (
    <Card>
      <h2 className="mb-3 text-sm font-semibold">{title}</h2>
      {tasks.length === 0 ? (
        <p className="text-sm text-slate-500">No data available.</p>
      ) : (
        <ul className="space-y-2">
          {tasks.map((task) => (
            <li key={task.id} className="flex items-start gap-2">
              <input
                type="checkbox"
                checked={Boolean(task.completed_at)}
                onChange={() => onToggle(task)}
                className="mt-1"
                aria-label={`Complete ${task.title}`}
              />
              <input
                className="flex-1 rounded border border-transparent bg-transparent px-1 text-sm hover:border-slate-300"
                defaultValue={task.title}
                onBlur={(event) => {
                  const next = event.target.value.trim();
                  if (next && next !== task.title) onRename(task, next);
                }}
              />
              <span className="text-xs uppercase text-slate-400">{task.priority}</span>
              {task.due_at ? <span className="text-xs text-slate-500">{formatTradingTime(task.due_at)}</span> : null}
              <button type="button" className="text-xs text-loss-500" onClick={() => onArchive(task)}>
                Archive
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
