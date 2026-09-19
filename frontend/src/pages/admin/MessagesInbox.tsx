// Messages sent through the public "Contact us" form.

import { clsx } from "clsx";
import { useState } from "react";

import { Glyph } from "@/components/icons";
import { Badge, Button, Card, EmptyState, SkeletonRows, Tabs } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { describeLocation, flagEmoji } from "@/lib/device";
import { dateTime, timeAgo } from "@/lib/format";
import { useContactMessages, useResolveContactMessage } from "@/lib/hooks";
import { toastError, toastSuccess } from "@/stores/toast";
import type { ContactMessage } from "@/types/api";

const TOPIC_LABEL: Record<string, string> = {
  access: "Account access",
  support: "Support",
  partnership: "Partnership",
  other: "Other",
};

export function MessagesInbox() {
  const [status, setStatus] = useState<"open" | "resolved">("open");
  const { data, isLoading, isError, error } = useContactMessages(status);

  return (
    <Card
      title="Contact messages"
      subtitle="From the public contact form. Replies go from your own mailbox."
      icon={<Glyph name="mail" className="size-3.5" />}
      actions={
        <Tabs
          tabs={[
            { key: "open", label: "Open" },
            { key: "resolved", label: "Resolved" },
          ]}
          active={status}
          onChange={(key) => setStatus(key as "open" | "resolved")}
        />
      }
      bodyClassName="p-2"
    >
      {isLoading ? (
        <SkeletonRows rows={4} cols={3} />
      ) : isError ? (
        <EmptyState
          title="Messages could not be loaded"
          body={error instanceof ApiError ? error.detail : undefined}
        />
      ) : !data || data.length === 0 ? (
        <EmptyState
          icon={<Glyph name="inbox" className="size-5" />}
          title={status === "open" ? "Inbox zero" : "Nothing resolved yet"}
          body={status === "open" ? "New messages are also e-mailed to every platform admin." : undefined}
        />
      ) : (
        <ul className="divide-y divide-slate-100 dark:divide-white/[0.05]">
          {data.map((message) => (
            <MessageRow key={message.id} message={message} />
          ))}
        </ul>
      )}
    </Card>
  );
}

function MessageRow({ message }: { message: ContactMessage }) {
  const [open, setOpen] = useState(false);
  const resolve = useResolveContactMessage();
  const location = describeLocation(message.geo);
  const reply = `mailto:${message.email}?subject=${encodeURIComponent(`Re: your ALGOMATRIC enquiry`)}`;

  return (
    <li className="px-3 py-3">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-start gap-3 text-left"
        aria-expanded={open}
      >
        <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-accent-500/10 text-xs font-semibold text-accent-600 ring-1 ring-accent-500/20 dark:text-accent-300">
          {message.name.slice(0, 2).toUpperCase()}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-2">
            <span className="font-medium text-slate-800 dark:text-slate-100">{message.name}</span>
            <span className="text-xs text-slate-500">{message.email}</span>
            <Badge color="blue">{TOPIC_LABEL[message.topic] ?? message.topic}</Badge>
          </span>
          <span
            className={clsx(
              "mt-1 block text-sm text-slate-600 dark:text-slate-300",
              !open && "line-clamp-1",
            )}
          >
            {message.message}
          </span>
        </span>
        <span className="shrink-0 text-xs text-slate-500" title={dateTime(message.created_at)}>
          {timeAgo(message.created_at)}
        </span>
      </button>
      {open && (
        <div className="mt-3 ml-12 flex flex-wrap items-center justify-between gap-3">
          <span className="text-xs text-slate-500">
            {message.ip_address ?? "IP not recorded"}
            {location && ` · ${flagEmoji(message.geo?.country_code)} ${location}`}
          </span>
          <span className="flex gap-2">
            <a
              href={reply}
              className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 px-3 text-xs font-medium text-slate-700 hover:bg-slate-50 dark:border-white/10 dark:text-slate-200 dark:hover:bg-white/[0.06]"
            >
              <Glyph name="mail" className="size-3.5" />
              Reply
            </a>
            {message.status === "open" && (
              <Button
                size="sm"
                variant="success"
                loading={resolve.isPending}
                onClick={() =>
                  resolve.mutate(message.id, {
                    onSuccess: () => toastSuccess("Marked resolved"),
                    onError: (error) =>
                      toastError(
                        "Could not update",
                        error instanceof ApiError ? error.detail : undefined,
                      ),
                  })
                }
              >
                Mark resolved
              </Button>
            )}
          </span>
        </div>
      )}
    </li>
  );
}
