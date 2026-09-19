// AI-CIO · Daily briefing (owner only): the morning e-mail, kept as a daily log.
// Every briefing is stored whether or not e-mail delivery is configured, so this
// tab is the archive; it can also preview or send today's on demand.

import { useState } from "react";

import { Glyph } from "@/components/icons";
import { Badge, Button, Card, EmptyState, Select, SkeletonRows } from "@/components/ui";
import { useBriefingAction, useBriefingArchive } from "@/lib/movers";

import { istDay, istStamp } from "./parts";

export function BriefingTab() {
  const [date, setDate] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const archive = useBriefingArchive(date);
  const action = useBriefingAction();
  const data = archive.data;

  if (archive.isLoading) return <SkeletonRows rows={5} cols={2} />;
  if (!data) {
    return (
      <Card>
        <EmptyState title="Briefings are unavailable" body="The briefing service did not answer." />
      </Card>
    );
  }
  const shown = preview ?? data.briefing?.html ?? null;
  const sent = action.isSuccess && action.variables === true;

  return (
    <div className="space-y-4">
      {data.delivery !== "smtp" ? (
        <div className="flex items-start gap-3 rounded-2xl border border-amber-500/30 bg-amber-500/[0.07] px-4 py-3 text-sm text-amber-800 dark:text-amber-200">
          <Glyph name="mail" className="mt-0.5 size-4 shrink-0" />
          <p>
            E-mail is not set up on the server yet, so briefings are saved here but not delivered.
            Set <code className="font-data text-xs">EMAIL_BACKEND=smtp</code> and the{" "}
            <code className="font-data text-xs">SMTP_*</code> settings in the server&apos;s{" "}
            <code className="font-data text-xs">.env</code> to start receiving them.
          </p>
        </div>
      ) : null}

      <Card
        title="Morning briefing"
        subtitle="Written about 09:10 IST each trading day, after the pre-open auction and before the open"
        icon={<Glyph name="mail" className="size-3.5" />}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {data.dates.length ? (
              <div className="w-44">
                <Select
                  aria-label="Briefing date"
                  value={date ?? ""}
                  onChange={(event) => {
                    setPreview(null);
                    setDate(event.target.value || null);
                  }}
                >
                  <option value="">Latest</option>
                  {data.dates.map((day) => (
                    <option key={day} value={day}>
                      {istDay(day)}
                    </option>
                  ))}
                </Select>
              </div>
            ) : null}
            <Button
              size="sm"
              variant="secondary"
              loading={action.isPending && action.variables === false}
              onClick={() => action.mutate(false, { onSuccess: (result) => setPreview(result.html) })}
            >
              Preview today&apos;s
            </Button>
            <Button
              size="sm"
              loading={action.isPending && action.variables === true}
              onClick={() => action.mutate(true, { onSuccess: () => setPreview(null) })}
            >
              Send today&apos;s now
            </Button>
          </div>
        }
      >
        {sent ? (
          <p className="mb-3 text-xs text-profit-700 dark:text-profit-400" role="status">
            Today&apos;s briefing was {data.delivery === "smtp" ? "queued for delivery" : "saved"} and logged.
          </p>
        ) : null}
        {preview ? (
          <p className="mb-3 flex items-center gap-2 text-xs text-slate-500">
            <Badge color="blue">Preview</Badge> Not sent. This is what today&apos;s briefing looks like right now.
          </p>
        ) : data.briefing ? (
          <dl className="mb-3 grid gap-x-6 gap-y-1 text-xs text-slate-500 sm:grid-cols-3">
            <div>
              <dt className="inline">Subject: </dt>
              <dd className="inline font-medium text-slate-700 dark:text-slate-200">{data.briefing.subject}</dd>
            </div>
            <div>
              <dt className="inline">Written: </dt>
              <dd className="inline font-data">{istStamp(data.briefing.sent_at)} IST</dd>
            </div>
            <div>
              <dt className="inline">To: </dt>
              <dd className="inline">
                {data.briefing.recipients.length ? data.briefing.recipients.join(", ") : "nobody (no owner e-mail found)"}
                {data.briefing.delivery !== "smtp" ? " · kept here only" : ""}
              </dd>
            </div>
          </dl>
        ) : null}
        {shown ? (
          <iframe
            title="Briefing"
            sandbox=""
            srcDoc={shown}
            className="h-[70vh] min-h-[520px] w-full rounded-xl border border-slate-200 bg-slate-100 dark:border-white/10"
          />
        ) : (
          <EmptyState
            title="No briefing yet"
            body="The first one is written at about 09:10 IST on the next trading day. You can preview today's now."
          />
        )}
      </Card>
    </div>
  );
}
