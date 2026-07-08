import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import {
  Badge,
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  Field,
  Input,
  Modal,
  PageHeader,
  Select,
  SkeletonRows,
  Table,
  Tabs,
  Td,
  Textarea,
  statusColor,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import {
  useAccounts,
  useInstruments,
  useStrategies,
  useStrategyLogs,
  useStrategyRuns,
  useStrategyVersions,
} from "@/lib/hooks";
import { dateTime } from "@/lib/format";
import { toastError, toastSuccess } from "@/stores/toast";
import type { StrategyRun, StrategyVersion } from "@/types/api";

export function StrategyDetailPage() {
  const { strategyId } = useParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const { data: strategies } = useStrategies();
  const { data: versions } = useStrategyVersions(strategyId);
  const { data: runs } = useStrategyRuns({ strategy_id: strategyId });
  const [tab, setTab] = useState("runs");
  const [deployOpen, setDeployOpen] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [logRunId, setLogRunId] = useState<string | null>(null);

  const strategy = strategies?.find((candidate) => candidate.id === strategyId);

  function invalidate() {
    client.invalidateQueries({ queryKey: ["strategy-runs"] });
    client.invalidateQueries({ queryKey: ["strategy-versions"] });
    client.invalidateQueries({ queryKey: ["strategies"] });
  }

  async function transition(run: StrategyRun, action: "start" | "pause" | "resume" | "stop") {
    try {
      await api(`/strategy-runs/${run.id}/${action}`, { method: "POST" });
      invalidate();
      toastSuccess(`Run ${action} requested`);
    } catch (error) {
      toastError(`${action} failed`, error instanceof ApiError ? error.detail : undefined);
    }
  }

  async function duplicate() {
    try {
      const copy = await api<{ id: string }>(`/strategies/${strategyId}/duplicate`, {
        method: "POST",
      });
      client.invalidateQueries({ queryKey: ["strategies"] });
      toastSuccess("Strategy duplicated");
      navigate(`/app/strategies/${copy.id}`);
    } catch (error) {
      toastError("Duplicate failed", error instanceof ApiError ? error.detail : undefined);
    }
  }

  async function remove() {
    try {
      await api(`/strategies/${strategyId}`, { method: "DELETE" });
      client.invalidateQueries({ queryKey: ["strategies"] });
      toastSuccess("Strategy removed");
      navigate("/app/strategies");
    } catch (error) {
      toastError("Delete failed", error instanceof ApiError ? error.detail : undefined);
    }
  }

  if (!strategy) {
    return (
      <div>
        <Link to="/app/strategies" className="text-sm text-accent-500 hover:underline">
          ← Back to strategies
        </Link>
        <Card className="mt-4">
          <SkeletonRows rows={3} cols={2} />
        </Card>
      </div>
    );
  }

  return (
    <div>
      <Link to="/app/strategies" className="text-sm text-accent-500 hover:underline">
        ← Back to strategies
      </Link>
      <PageHeader
        title={strategy.name}
        description={strategy.description || "No description"}
        actions={
          <>
            <Button variant="secondary" size="sm" onClick={() => setUploadOpen(true)}>
              Upload version
            </Button>
            <Button variant="secondary" size="sm" onClick={duplicate}>
              Duplicate
            </Button>
            <Button variant="danger" size="sm" onClick={() => setConfirmDelete(true)}>
              Delete
            </Button>
            <Button size="sm" onClick={() => setDeployOpen(true)}>
              Deploy run
            </Button>
          </>
        }
      />

      <div className="mb-4">
        <Tabs
          tabs={[
            { key: "runs", label: "Runs" },
            { key: "versions", label: "Versions" },
            { key: "config", label: "Details" },
          ]}
          active={tab}
          onChange={setTab}
        />
      </div>

      {tab === "runs" && (
        <Card>
          {!runs || runs.length === 0 ? (
            <EmptyState
              title="No runs yet"
              body="Deploy this strategy to a trading account to start it."
              action={<Button onClick={() => setDeployOpen(true)}>Deploy run</Button>}
            />
          ) : (
            <Table headers={["Version", "Mode", "State", "Instruments", "Started", "Actions"]}>
              {runs.map((run) => (
                <tr key={run.id}>
                  <Td>v{run.strategy_version}</Td>
                  <Td>
                    <Badge color={run.mode === "live" ? "red" : "blue"}>{run.mode}</Badge>
                  </Td>
                  <Td>
                    <div className="flex flex-col gap-0.5">
                      <Badge color={statusColor(run.state)}>{run.state}</Badge>
                      {run.error && <span className="text-[11px] text-loss-500">{run.error}</span>}
                    </div>
                  </Td>
                  <Td className="text-slate-500">{run.instrument_ids.length}</Td>
                  <Td className="text-xs text-slate-400">{dateTime(run.started_at)}</Td>
                  <Td>
                    <div className="flex gap-1">
                      {(run.state === "stopped" || run.state === "failed") && (
                        <Button size="sm" variant="ghost" onClick={() => transition(run, "start")}>
                          Start
                        </Button>
                      )}
                      {run.state === "running" && (
                        <Button size="sm" variant="ghost" onClick={() => transition(run, "pause")}>
                          Pause
                        </Button>
                      )}
                      {run.state === "paused" && (
                        <Button size="sm" variant="ghost" onClick={() => transition(run, "resume")}>
                          Resume
                        </Button>
                      )}
                      {["running", "paused", "starting"].includes(run.state) && (
                        <Button size="sm" variant="ghost" onClick={() => transition(run, "stop")}>
                          Stop
                        </Button>
                      )}
                      <Button size="sm" variant="ghost" onClick={() => setLogRunId(run.id)}>
                        Logs
                      </Button>
                    </div>
                  </Td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
      )}

      {tab === "versions" && (
        <Card>
          {!versions || versions.length === 0 ? (
            <EmptyState title="No versions" />
          ) : (
            <Table headers={["Version", "Source", "Entry point", "Live approved", "Created"]}>
              {versions.map((version) => (
                <tr key={version.id}>
                  <Td className="font-medium">v{version.version}</Td>
                  <Td>
                    <Badge color={version.source === "builtin" ? "blue" : "violet"}>
                      {version.source}
                    </Badge>
                  </Td>
                  <Td className="max-w-xs truncate font-mono text-xs">{version.entry_point}</Td>
                  <Td>
                    {version.approved_for_live ? (
                      <Badge color="green">approved</Badge>
                    ) : (
                      <Badge color="amber">paper only</Badge>
                    )}
                  </Td>
                  <Td className="text-xs text-slate-400">{dateTime(version.created_at)}</Td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
      )}

      {tab === "config" && (
        <Card title="Strategy details">
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <dt className="text-slate-500">Status</dt>
            <dd>
              <Badge color={statusColor(strategy.status)}>{strategy.status}</Badge>
            </dd>
            <dt className="text-slate-500">Latest version</dt>
            <dd>v{strategy.latest_version}</dd>
            <dt className="text-slate-500">Active runs</dt>
            <dd>{strategy.active_runs}</dd>
            <dt className="text-slate-500">Tags</dt>
            <dd className="flex flex-wrap gap-1">
              {strategy.tags.length > 0
                ? strategy.tags.map((tag) => (
                    <Badge key={tag} color="slate">
                      {tag}
                    </Badge>
                  ))
                : "—"}
            </dd>
            <dt className="text-slate-500">Created</dt>
            <dd>{dateTime(strategy.created_at)}</dd>
          </dl>
        </Card>
      )}

      {deployOpen && strategyId && (
        <DeployRunModal
          versions={versions ?? []}
          onClose={() => setDeployOpen(false)}
          onDeployed={() => {
            setDeployOpen(false);
            invalidate();
          }}
        />
      )}

      {uploadOpen && strategyId && (
        <UploadVersionModal
          strategyId={strategyId}
          onClose={() => setUploadOpen(false)}
          onUploaded={() => {
            setUploadOpen(false);
            invalidate();
          }}
        />
      )}

      {logRunId && <LogsModal runId={logRunId} onClose={() => setLogRunId(null)} />}

      <ConfirmDialog
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        onConfirm={remove}
        title="Delete strategy"
        body="This archives the strategy and removes it from your list. Active runs must be stopped first."
        confirmLabel="Delete"
        danger
      />
    </div>
  );
}

function DeployRunModal({
  versions,
  onClose,
  onDeployed,
}: {
  versions: StrategyVersion[];
  onClose: () => void;
  onDeployed: () => void;
}) {
  const { data: accounts } = useAccounts();
  const [search, setSearch] = useState("");
  const { data: instruments } = useInstruments(search);
  const [versionId, setVersionId] = useState(versions[0]?.id ?? "");
  const [accountId, setAccountId] = useState("");
  const [timeframe, setTimeframe] = useState("1m");
  const [selectedInstruments, setSelectedInstruments] = useState<string[]>([]);
  const [params, setParams] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const version = versions.find((candidate) => candidate.id === versionId) ?? versions[0];
  const activeAccounts = (accounts ?? []).filter((account) => account.status === "active");
  const effectiveAccount = accountId || activeAccounts[0]?.id || "";

  function toggleInstrument(id: string) {
    setSelectedInstruments((prev) =>
      prev.includes(id) ? prev.filter((value) => value !== id) : [...prev, id],
    );
  }

  async function submit() {
    if (!effectiveAccount || selectedInstruments.length === 0) {
      setError("Select an account and at least one instrument.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const parsedParams: Record<string, unknown> = {};
      for (const [key, value] of Object.entries(params)) {
        if (value !== "") parsedParams[key] = value;
      }
      await api("/strategy-runs", {
        method: "POST",
        body: {
          strategy_version_id: version?.id,
          account_id: effectiveAccount,
          parameters: parsedParams,
          instrument_ids: selectedInstruments,
          timeframe,
          autostart: true,
        },
      });
      toastSuccess("Strategy run deployed");
      onDeployed();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Deploy failed");
    } finally {
      setSubmitting(false);
    }
  }

  const paramSpecs = version?.manifest.parameters ?? [];

  return (
    <Modal open onClose={onClose} title="Deploy strategy run" wide>
      <div className="space-y-4">
        {error && (
          <div className="rounded-lg border border-loss-500/40 bg-loss-500/10 px-3 py-2 text-sm text-loss-600 dark:text-loss-400">
            {error}
          </div>
        )}
        {versions.length === 0 ? (
          <p className="text-sm text-slate-500">
            This strategy has no versions. Upload code or add a built-in version first.
          </p>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Version">
                <Select value={versionId} onChange={(event) => setVersionId(event.target.value)}>
                  {versions.map((candidate) => (
                    <option key={candidate.id} value={candidate.id}>
                      v{candidate.version} ({candidate.source})
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Account">
                <Select value={effectiveAccount} onChange={(event) => setAccountId(event.target.value)}>
                  {activeAccounts.map((account) => (
                    <option key={account.id} value={account.id}>
                      {account.name} ({account.mode})
                    </option>
                  ))}
                </Select>
              </Field>
            </div>

            <Field label="Timeframe">
              <Select value={timeframe} onChange={(event) => setTimeframe(event.target.value)}>
                <option value="tick">Tick</option>
                <option value="1m">1 minute</option>
                <option value="5m">5 minutes</option>
                <option value="15m">15 minutes</option>
                <option value="1h">1 hour</option>
              </Select>
            </Field>

            <Field label={`Instruments (${selectedInstruments.length} selected)`}>
              <Input
                placeholder="Search…"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
              <div className="mt-2 max-h-40 space-y-1 overflow-y-auto rounded-lg border border-slate-200 p-2 dark:border-surface-700">
                {(instruments ?? []).slice(0, 40).map((instrument) => (
                  <label key={instrument.id} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={selectedInstruments.includes(instrument.id)}
                      onChange={() => toggleInstrument(instrument.id)}
                    />
                    <span className="font-medium">{instrument.symbol}</span>
                    <span className="text-slate-400">{instrument.name}</span>
                  </label>
                ))}
              </div>
            </Field>

            {paramSpecs.length > 0 && (
              <div className="grid grid-cols-2 gap-3">
                {paramSpecs.map((spec) => (
                  <Field key={spec.name} label={spec.name} hint={spec.description}>
                    <Input
                      placeholder={String(spec.default)}
                      value={params[spec.name] ?? ""}
                      onChange={(event) =>
                        setParams((prev) => ({ ...prev, [spec.name]: event.target.value }))
                      }
                    />
                  </Field>
                ))}
              </div>
            )}

            <Button className="w-full" onClick={submit} loading={submitting}>
              Deploy &amp; start
            </Button>
          </>
        )}
      </div>
    </Modal>
  );
}

function UploadVersionModal({
  strategyId,
  onClose,
  onUploaded,
}: {
  strategyId: string;
  onClose: () => void;
  onUploaded: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [entryClass, setEntryClass] = useState("");
  const [paramsJson, setParamsJson] = useState("[]");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!file || !entryClass) {
      setError("Select a Python file and enter the entry class name.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("entry_class", entryClass);
      formData.append("parameters_json", paramsJson);
      await api(`/strategies/${strategyId}/versions/upload`, { method: "POST", formData });
      toastSuccess("Version uploaded (paper-only until approved)");
      onUploaded();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Upload failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal open onClose={onClose} title="Upload strategy version">
      <div className="space-y-4">
        {error && (
          <div className="rounded-lg border border-loss-500/40 bg-loss-500/10 px-3 py-2 text-sm text-loss-600 dark:text-loss-400">
            {error}
          </div>
        )}
        <Field label="Python file" hint="Must subclass the SDK Strategy class">
          <input
            type="file"
            accept=".py,text/x-python"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            className="block w-full text-sm text-slate-500 file:mr-3 file:rounded-md file:border-0 file:bg-accent-600 file:px-3 file:py-1.5 file:text-white"
          />
        </Field>
        <Field label="Entry class" hint="e.g. MyStrategy">
          <Input value={entryClass} onChange={(event) => setEntryClass(event.target.value)} />
        </Field>
        <Field label="Parameters (JSON)" hint="Array of parameter specs; leave [] if none">
          <Textarea value={paramsJson} onChange={(event) => setParamsJson(event.target.value)} />
        </Field>
        <Button className="w-full" onClick={submit} loading={submitting}>
          Upload &amp; validate
        </Button>
      </div>
    </Modal>
  );
}

function LogsModal({ runId, onClose }: { runId: string; onClose: () => void }) {
  const { data: logs, isLoading } = useStrategyLogs(runId);
  return (
    <Modal open onClose={onClose} title="Runtime logs" wide>
      {isLoading ? (
        <SkeletonRows rows={6} cols={1} />
      ) : !logs || logs.length === 0 ? (
        <EmptyState title="No logs yet" body="Logs appear as the strategy processes market data." />
      ) : (
        <div className="max-h-96 space-y-1 overflow-y-auto font-mono text-xs">
          {logs.map((log) => (
            <div key={log.id} className="flex gap-2 border-b border-slate-100 py-1 dark:border-surface-800/60">
              <span className="shrink-0 text-slate-400">{dateTime(log.logged_at)}</span>
              <Badge color={log.level === "warning" || log.level === "error" ? "amber" : "slate"}>
                {log.level}
              </Badge>
              <span>{log.message}</span>
            </div>
          ))}
        </div>
      )}
    </Modal>
  );
}
