import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import {
  Badge,
  Button,
  Card,
  EmptyState,
  Field,
  Input,
  Modal,
  PageHeader,
  Select,
  SkeletonRows,
  Textarea,
  statusColor,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { useBuiltinStrategies, useStrategies } from "@/lib/hooks";
import { dateOnly } from "@/lib/format";
import { toastSuccess } from "@/stores/toast";

export function StrategiesPage() {
  const { data: strategies, isLoading } = useStrategies();
  const [createOpen, setCreateOpen] = useState(false);
  const client = useQueryClient();

  return (
    <div>
      <PageHeader
        title="Strategies"
        description="Author, version, and deploy trading strategies"
        actions={<Button onClick={() => setCreateOpen(true)}>New strategy</Button>}
      />

      {isLoading ? (
        <Card>
          <SkeletonRows rows={4} cols={4} />
        </Card>
      ) : !strategies || strategies.length === 0 ? (
        <Card>
          <EmptyState
            title="No strategies yet"
            body="Start from a built-in strategy (SMA crossover, RSI reversion, momentum breakout) or upload your own."
            action={<Button onClick={() => setCreateOpen(true)}>Create a strategy</Button>}
          />
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {strategies.map((strategy) => (
            <Link key={strategy.id} to={`/app/strategies/${strategy.id}`}>
              <Card className="h-full transition-colors hover:border-accent-500">
                <div className="flex items-start justify-between">
                  <h3 className="font-semibold">{strategy.name}</h3>
                  <Badge color={statusColor(strategy.status)}>{strategy.status}</Badge>
                </div>
                <p className="mt-1 line-clamp-2 text-sm text-slate-500">
                  {strategy.description || "No description"}
                </p>
                <div className="mt-3 flex flex-wrap gap-1">
                  {strategy.tags.map((tag) => (
                    <Badge key={tag} color="slate">
                      {tag}
                    </Badge>
                  ))}
                </div>
                <div className="mt-3 flex items-center justify-between text-xs text-slate-400">
                  <span>v{strategy.latest_version} · {dateOnly(strategy.created_at)}</span>
                  {strategy.active_runs > 0 && (
                    <Badge color="green">{strategy.active_runs} running</Badge>
                  )}
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}

      <CreateStrategyModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={() => {
          setCreateOpen(false);
          client.invalidateQueries({ queryKey: ["strategies"] });
        }}
      />
    </div>
  );
}

function CreateStrategyModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const { data: builtins } = useBuiltinStrategies();
  const [mode, setMode] = useState<"builtin" | "blank">("builtin");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [entryPoint, setEntryPoint] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      const chosenBuiltin = mode === "builtin" ? entryPoint || builtins?.[0]?.entry_point : null;
      const finalName =
        name || (chosenBuiltin ? builtins?.find((b) => b.entry_point === chosenBuiltin)?.name : "");
      await api("/strategies", {
        method: "POST",
        body: {
          name: finalName || "Untitled strategy",
          description,
          tags: tags
            .split(",")
            .map((tag) => tag.trim())
            .filter(Boolean),
          builtin_entry_point: chosenBuiltin,
        },
      });
      toastSuccess("Strategy created");
      setName("");
      setDescription("");
      setTags("");
      onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to create");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Create strategy">
      <div className="space-y-4">
        {error && (
          <div className="rounded-lg border border-loss-500/40 bg-loss-500/10 px-3 py-2 text-sm text-loss-600 dark:text-loss-400">
            {error}
          </div>
        )}
        <div className="grid grid-cols-2 gap-2">
          <button
            onClick={() => setMode("builtin")}
            className={
              mode === "builtin"
                ? "rounded-lg border-2 border-accent-500 py-2 text-sm font-medium"
                : "rounded-lg border border-slate-300 py-2 text-sm dark:border-surface-700"
            }
          >
            From built-in
          </button>
          <button
            onClick={() => setMode("blank")}
            className={
              mode === "blank"
                ? "rounded-lg border-2 border-accent-500 py-2 text-sm font-medium"
                : "rounded-lg border border-slate-300 py-2 text-sm dark:border-surface-700"
            }
          >
            Blank (upload later)
          </button>
        </div>

        {mode === "builtin" && (
          <Field label="Built-in template">
            <Select value={entryPoint} onChange={(event) => setEntryPoint(event.target.value)}>
              {(builtins ?? []).map((builtin) => (
                <option key={builtin.entry_point} value={builtin.entry_point}>
                  {builtin.name} — {builtin.description}
                </option>
              ))}
            </Select>
          </Field>
        )}

        <Field label="Name" hint="Defaults to the template name">
          <Input value={name} onChange={(event) => setName(event.target.value)} />
        </Field>
        <Field label="Description">
          <Textarea value={description} onChange={(event) => setDescription(event.target.value)} />
        </Field>
        <Field label="Tags" hint="Comma-separated">
          <Input value={tags} onChange={(event) => setTags(event.target.value)} placeholder="trend, intraday" />
        </Field>
        <Button className="w-full" onClick={submit} loading={submitting}>
          Create strategy
        </Button>
      </div>
    </Modal>
  );
}
