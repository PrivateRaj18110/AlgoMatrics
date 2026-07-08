import { useMemo, useState } from "react";

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
  Td,
} from "@/components/ui";
import { ApiError } from "@/lib/api";
import {
  useAddWatchlistItem,
  useCreateWatchlist,
  useDeleteWatchlist,
  useInstruments,
  useQuotes,
  useRemoveWatchlistItem,
  useRenameWatchlist,
  useWatchlists,
} from "@/lib/hooks";
import { pnlClass, toNumber } from "@/lib/format";
import { toastError, toastSuccess } from "@/stores/toast";
import type { Watchlist } from "@/types/api";

export function WatchlistsPage() {
  const { data: watchlists, isLoading } = useWatchlists();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [renameOpen, setRenameOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [name, setName] = useState("");
  const [search, setSearch] = useState("");
  const [instrumentId, setInstrumentId] = useState("");

  const createWatchlist = useCreateWatchlist();
  const renameWatchlist = useRenameWatchlist();
  const deleteWatchlist = useDeleteWatchlist();
  const addItem = useAddWatchlistItem();
  const removeItem = useRemoveWatchlistItem();
  const { data: instruments } = useInstruments(search);

  const lists = watchlists ?? [];
  const active: Watchlist | undefined =
    lists.find((list) => list.id === selectedId) ?? lists[0];

  const instrumentIds = useMemo(
    () => (active?.items ?? []).map((item) => item.instrument_id),
    [active],
  );
  const { data: quotes } = useQuotes(instrumentIds, instrumentIds.length > 0);
  const quoteByInstrument = useMemo(
    () => new Map((quotes ?? []).map((quote) => [quote.instrument_id, quote])),
    [quotes],
  );

  async function submitCreate() {
    const cleaned = name.trim();
    if (!cleaned) return;
    try {
      const created = await createWatchlist.mutateAsync(cleaned);
      setSelectedId(created.id);
      setName("");
      setCreateOpen(false);
      toastSuccess("Watchlist created");
    } catch (error) {
      toastError("Could not create watchlist", error instanceof ApiError ? error.detail : undefined);
    }
  }

  async function submitRename() {
    const cleaned = name.trim();
    if (!cleaned || !active) return;
    try {
      await renameWatchlist.mutateAsync({ watchlistId: active.id, name: cleaned });
      setRenameOpen(false);
      toastSuccess("Watchlist renamed");
    } catch (error) {
      toastError("Could not rename watchlist", error instanceof ApiError ? error.detail : undefined);
    }
  }

  async function submitDelete() {
    if (!active) return;
    try {
      await deleteWatchlist.mutateAsync(active.id);
      setSelectedId(null);
      setDeleteOpen(false);
      toastSuccess("Watchlist removed");
    } catch (error) {
      toastError("Could not remove watchlist", error instanceof ApiError ? error.detail : undefined);
    }
  }

  async function submitAddItem() {
    if (!active || !instrumentId) return;
    try {
      await addItem.mutateAsync({ watchlistId: active.id, instrumentId });
      setInstrumentId("");
      setSearch("");
      toastSuccess("Instrument added");
    } catch (error) {
      toastError("Could not add instrument", error instanceof ApiError ? error.detail : undefined);
    }
  }

  async function handleRemoveItem(itemId: string) {
    if (!active) return;
    try {
      await removeItem.mutateAsync({ watchlistId: active.id, itemId });
    } catch (error) {
      toastError("Could not remove instrument", error instanceof ApiError ? error.detail : undefined);
    }
  }

  return (
    <div>
      <PageHeader
        title="Watchlists"
        description="Track instruments with live quotes across your organization"
        actions={
          <Button
            onClick={() => {
              setName("");
              setCreateOpen(true);
            }}
          >
            New watchlist
          </Button>
        }
      />

      {isLoading ? (
        <Card>
          <SkeletonRows rows={5} cols={4} />
        </Card>
      ) : lists.length === 0 ? (
        <Card>
          <EmptyState
            title="No watchlists yet"
            body="Create a watchlist to follow instruments and their live prices."
            action={<Button onClick={() => setCreateOpen(true)}>New watchlist</Button>}
          />
        </Card>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[220px_1fr]">
          <Card className="h-fit">
            <ul className="space-y-1">
              {lists.map((list) => (
                <li key={list.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(list.id)}
                    className={
                      list.id === active?.id
                        ? "flex w-full items-center justify-between rounded-lg bg-accent-500/10 px-3 py-2 text-sm font-medium text-accent-600 dark:text-accent-300"
                        : "flex w-full items-center justify-between rounded-lg px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-surface-800"
                    }
                  >
                    <span className="truncate">{list.name}</span>
                    <Badge color="slate">{list.items.length}</Badge>
                  </button>
                </li>
              ))}
            </ul>
          </Card>

          <Card
            title={active?.name}
            actions={
              active && (
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => {
                      setName(active.name);
                      setRenameOpen(true);
                    }}
                  >
                    Rename
                  </Button>
                  <Button size="sm" variant="danger" onClick={() => setDeleteOpen(true)}>
                    Delete
                  </Button>
                </div>
              )
            }
          >
            <div className="mb-4 flex flex-col gap-2 sm:flex-row">
              <Input
                placeholder="Search symbol to add…"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                className="sm:max-w-xs"
              />
              <Select
                value={instrumentId}
                onChange={(event) => setInstrumentId(event.target.value)}
                className="sm:max-w-xs"
              >
                <option value="">Select an instrument…</option>
                {(instruments ?? []).map((instrument) => (
                  <option key={instrument.id} value={instrument.id}>
                    {instrument.symbol} — {instrument.name}
                  </option>
                ))}
              </Select>
              <Button onClick={submitAddItem} disabled={!instrumentId} loading={addItem.isPending}>
                Add
              </Button>
            </div>

            {!active || active.items.length === 0 ? (
              <EmptyState
                title="No instruments"
                body="Search above to add instruments to this watchlist."
              />
            ) : (
              <Table headers={["Symbol", "Name", "Last", "Change", ""]}>
                {active.items.map((item) => {
                  const quote = quoteByInstrument.get(item.instrument_id);
                  const change = toNumber(quote?.change_pct);
                  return (
                    <tr key={item.id}>
                      <Td className="font-medium">{item.symbol}</Td>
                      <Td className="text-slate-500">{item.name}</Td>
                      <Td className="tabular-nums">{quote?.last ?? "—"}</Td>
                      <Td className={`tabular-nums ${pnlClass(change)}`}>
                        {quote?.change_pct ? `${change.toFixed(2)}%` : "—"}
                      </Td>
                      <Td>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleRemoveItem(item.id)}
                          aria-label={`Remove ${item.symbol}`}
                        >
                          Remove
                        </Button>
                      </Td>
                    </tr>
                  );
                })}
              </Table>
            )}
          </Card>
        </div>
      )}

      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title="New watchlist">
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            void submitCreate();
          }}
        >
          <Field label="Name" required>
            <Input
              value={name}
              onChange={(event) => setName(event.target.value)}
              maxLength={120}
              autoFocus
            />
          </Field>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={createWatchlist.isPending} disabled={!name.trim()}>
              Create
            </Button>
          </div>
        </form>
      </Modal>

      <Modal open={renameOpen} onClose={() => setRenameOpen(false)} title="Rename watchlist">
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            void submitRename();
          }}
        >
          <Field label="Name" required>
            <Input
              value={name}
              onChange={(event) => setName(event.target.value)}
              maxLength={120}
              autoFocus
            />
          </Field>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setRenameOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={renameWatchlist.isPending} disabled={!name.trim()}>
              Save
            </Button>
          </div>
        </form>
      </Modal>

      <ConfirmDialog
        open={deleteOpen}
        onClose={() => setDeleteOpen(false)}
        onConfirm={submitDelete}
        title="Delete watchlist"
        body={`Delete "${active?.name}"? This removes the watchlist and its instruments.`}
        confirmLabel="Delete"
        danger
        loading={deleteWatchlist.isPending}
      />
    </div>
  );
}
