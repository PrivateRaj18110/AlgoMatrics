import { useState } from "react";

import { Button, Card, EmptyState, PageHeader } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { useAiAssistant } from "@/lib/hooks";
import { toastError } from "@/stores/toast";

export function AssistantPage() {
  const [question, setQuestion] = useState("");
  const ask = useAiAssistant();
  const answer = ask.data;

  const onAsk = () => {
    const q = question.trim();
    if (!q) return;
    ask.mutate(q, {
      onError: (e) => toastError(e instanceof ApiError ? e.detail : "The assistant is unavailable"),
    });
  };

  return (
    <div>
      <PageHeader
        title="Assistant"
        description="Ask about your strategies, risk, orders, and platform"
      />
      <Card>
        <textarea
          className="h-28 w-full rounded-lg border border-slate-300 bg-transparent p-3 text-sm dark:border-slate-700"
          placeholder="e.g. Why was my last order rejected? What does my risk limit protect against?"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "Enter") onAsk();
          }}
        />
        <div className="mt-3 flex items-center gap-3">
          <Button onClick={onAsk} loading={ask.isPending} disabled={!question.trim()}>
            Ask
          </Button>
          <span className="text-xs text-slate-500">⌘/Ctrl + Enter to send</span>
        </div>
      </Card>

      {answer ? (
        <Card className="mt-6" title="Answer">
          <p className="whitespace-pre-wrap text-sm leading-relaxed">{answer.answer}</p>
          {answer.provider === "null" && (
            <p className="mt-3 text-xs text-amber-600">
              AI is not configured on this platform — showing a placeholder response.
            </p>
          )}
        </Card>
      ) : (
        !ask.isPending && (
          <div className="mt-6">
            <EmptyState
              title="Ask a question to get started"
              body="The assistant explains your strategies, risk, and diagnostics — it never places trades."
            />
          </div>
        )
      )}
    </div>
  );
}
