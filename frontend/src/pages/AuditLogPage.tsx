import { useState } from "react";

import {
  Badge,
  Card,
  EmptyState,
  Field,
  Input,
  PageHeader,
  SkeletonRows,
  Table,
  Td,
} from "@/components/ui";
import { useAuditEvents } from "@/lib/hooks";
import { dateTime } from "@/lib/format";

export function AuditLogPage() {
  const [filter, setFilter] = useState("");
  const { data, isLoading, isError, refetch } = useAuditEvents(filter || undefined);

  return (
    <div>
      <PageHeader
        title="Audit log"
        description="Immutable organization activity for security and operational review"
      />
      <Card>
        <div className="mb-4 max-w-sm">
          <Field label="Action prefix">
            <Input
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              placeholder="orders., brokers., billing."
            />
          </Field>
        </div>
        {isLoading ? (
          <SkeletonRows rows={8} cols={5} />
        ) : isError ? (
          <EmptyState
            title="Audit events could not be loaded"
            action={
              <button className="text-sm text-accent-500 hover:underline" onClick={() => refetch()}>
                Retry
              </button>
            }
          />
        ) : !data || data.items.length === 0 ? (
          <EmptyState title="No matching audit events" />
        ) : (
          <Table headers={["Time", "Action", "Resource", "Actor", "Request"]}>
            {data.items.map((entry) => (
              <tr key={entry.id}>
                <Td className="whitespace-nowrap">{dateTime(entry.occurred_at)}</Td>
                <Td className="font-medium">{entry.action}</Td>
                <Td>
                  <div>{entry.resource_type}</div>
                  <div className="max-w-52 truncate text-xs text-slate-500">{entry.resource_id}</div>
                </Td>
                <Td>
                  <Badge color={entry.actor_type === "user" ? "blue" : "slate"}>
                    {entry.actor_type}
                  </Badge>
                  {entry.actor_user_id && (
                    <div className="mt-1 max-w-36 truncate text-xs text-slate-500">
                      {entry.actor_user_id}
                    </div>
                  )}
                </Td>
                <Td className="max-w-44 truncate text-xs text-slate-500">
                  {entry.request_id ?? "—"}
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}
