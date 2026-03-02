"use client";

import { useEffect, useState } from "react";
import {
  MessageSquare,
  Clock,
  AlertTriangle,
  CheckCircle,
  Bot,
  Loader2,
  RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { EmailThread } from "@/lib/api";
import { runAgent, updateThreadMode } from "@/lib/api";
import ThreadDetail from "./thread-detail";

interface Props {
  threads: EmailThread[];
  onUpdate: () => void;
  selectedThreadId?: string | null;
  onClearSelection?: () => void;
}

const stateLabels: Record<string, string> = {
  draft_ready: "Draft Ready",
  waiting_reply: "Waiting",
  outreach_sent: "Sent",
  escalated: "Escalated",
  closed: "Closed",
};

const stateIcons: Record<string, React.ReactNode> = {
  draft_ready: <Bot className="h-3.5 w-3.5 text-blue-500" />,
  waiting_reply: <Clock className="h-3.5 w-3.5 text-amber-500" />,
  outreach_sent: <CheckCircle className="h-3.5 w-3.5 text-green-500" />,
  escalated: <AlertTriangle className="h-3.5 w-3.5 text-red-500" />,
  closed: <CheckCircle className="h-3.5 w-3.5 text-muted-foreground" />,
};

export default function ThreadSection({ threads, onUpdate, selectedThreadId, onClearSelection }: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [agentRunning, setAgentRunning] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  // Auto-select thread from notification deep link
  useEffect(() => {
    if (selectedThreadId) {
      setSelectedId(selectedThreadId);
      onClearSelection?.();
    }
  }, [selectedThreadId, onClearSelection]);

  const selected = threads.find((t) => t.id === selectedId);

  // Group threads by state priority
  const draftReady = threads.filter((t) => t.state === "draft_ready");
  const escalated = threads.filter((t) => t.state === "escalated");
  const waiting = threads.filter((t) => t.state === "waiting_reply" || t.state === "outreach_sent");
  const closed = threads.filter((t) => t.state === "closed");

  async function handleRunAgent(threadId: string) {
    setAgentRunning(threadId);
    try {
      await runAgent(threadId);
      onUpdate();
    } finally {
      setAgentRunning(null);
    }
  }

  async function handleManualRefresh() {
    setRefreshing(true);
    try {
      await onUpdate();
    } finally {
      setRefreshing(false);
    }
  }

  if (threads.length === 0) {
    return (
      <div className="text-center py-8">
        <MessageSquare className="mx-auto h-8 w-8 text-muted-foreground/40" />
        <p className="mt-2 text-sm text-muted-foreground">
          No conversations yet. Send outreach emails to start.
        </p>
      </div>
    );
  }

  // Thread detail view
  if (selected) {
    return (
      <ThreadDetail
        thread={selected}
        onBack={() => setSelectedId(null)}
        onUpdate={onUpdate}
        agentRunning={agentRunning === selected.id}
        onRunAgent={() => handleRunAgent(selected.id)}
      />
    );
  }

  // Thread list view
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          {threads.length} conversation{threads.length !== 1 ? "s" : ""}
        </p>
        <button
          onClick={handleManualRefresh}
          disabled={refreshing}
          className="text-muted-foreground/50 hover:text-muted-foreground transition-colors p-1 rounded"
          title="Refresh"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`} />
        </button>
      </div>

      {draftReady.length > 0 && (
        <ThreadGroup
          label="Needs Review"
          threads={draftReady}
          onSelect={setSelectedId}
          onUpdate={onUpdate}
          agentRunning={agentRunning}
        />
      )}

      {escalated.length > 0 && (
        <ThreadGroup
          label="Escalated"
          threads={escalated}
          onSelect={setSelectedId}
          onUpdate={onUpdate}
          agentRunning={agentRunning}
        />
      )}

      {waiting.length > 0 && (
        <ThreadGroup
          label="Waiting for Reply"
          threads={waiting}
          onSelect={setSelectedId}
          onUpdate={onUpdate}
          agentRunning={agentRunning}
          onRunAgent={handleRunAgent}
        />
      )}

      {closed.length > 0 && (
        <ThreadGroup
          label="Closed"
          threads={closed}
          onSelect={setSelectedId}
          onUpdate={onUpdate}
          agentRunning={agentRunning}
        />
      )}
    </div>
  );
}

function ThreadGroup({
  label,
  threads,
  onSelect,
  onUpdate,
  agentRunning,
  onRunAgent,
}: {
  label: string;
  threads: EmailThread[];
  onSelect: (id: string) => void;
  onUpdate: () => void;
  agentRunning: string | null;
  onRunAgent?: (id: string) => void;
}) {
  return (
    <div className="space-y-2">
      <h3 className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
        {label} ({threads.length})
      </h3>
      {threads.map((thread) => (
        <ThreadRow
          key={thread.id}
          thread={thread}
          onClick={() => onSelect(thread.id)}
          onUpdate={onUpdate}
          agentRunning={agentRunning === thread.id}
          onRunAgent={onRunAgent ? () => onRunAgent(thread.id) : undefined}
        />
      ))}
    </div>
  );
}

function ThreadRow({
  thread,
  onClick,
  onUpdate,
  agentRunning,
  onRunAgent,
}: {
  thread: EmailThread;
  onClick: () => void;
  onUpdate: () => void;
  agentRunning: boolean;
  onRunAgent?: () => void;
}) {
  const lastMessage = thread.messages[thread.messages.length - 1];
  const inboundCount = thread.messages.filter((m) => m.direction === "inbound").length;
  const hasDraft = thread.messages.some((m) => m.draft_body && !m.final_body);

  // Find the escalation reason if escalated
  const escalationMsg = thread.state === "escalated"
    ? thread.messages.find((m) => m.agent_reasoning && !m.draft_body)
    : null;

  return (
    <div
      className="flex items-center gap-3 rounded-lg border px-4 py-3 hover:bg-muted/30 transition-colors cursor-pointer"
      onClick={onClick}
    >
      <div className="shrink-0">
        {stateIcons[thread.state] ?? <MessageSquare className="h-3.5 w-3.5" />}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate font-medium text-sm">
            {thread.suppliers?.name ?? "Unknown Supplier"}
          </span>
          <Badge variant="outline" className="text-[10px] shrink-0">
            {stateLabels[thread.state] ?? thread.state}
          </Badge>
          {hasDraft && (
            <Badge className="text-[10px] shrink-0 bg-blue-100 text-blue-700 hover:bg-blue-100">
              Draft
            </Badge>
          )}
          <button
            onClick={async (e) => {
              e.stopPropagation();
              const next = thread.approval_mode === "auto" ? "manual" : "auto";
              await updateThreadMode(thread.id, next);
              onUpdate();
            }}
            className={`rounded-full px-2 py-0.5 text-[10px] font-medium transition-colors shrink-0 ${
              thread.approval_mode === "auto"
                ? "bg-green-100 text-green-700 hover:bg-green-200"
                : "bg-muted text-muted-foreground hover:bg-muted/80"
            }`}
          >
            {thread.approval_mode === "auto" ? "Auto" : "Manual"}
          </button>
        </div>
        <p className="truncate text-xs text-muted-foreground mt-0.5">
          {lastMessage
            ? `${lastMessage.direction === "inbound" ? "Them" : "You"}: ${
                (lastMessage.draft_body || lastMessage.final_body || lastMessage.body).slice(0, 80)
              }`
            : "No messages yet"}
        </p>
        {thread.state === "escalated" && escalationMsg && (
          <p className="truncate text-xs text-red-500 mt-0.5">
            {escalationMsg.agent_reasoning}
          </p>
        )}
        {thread.state === "closed" && thread.closed_reason && (
          <p className="truncate text-xs text-muted-foreground mt-0.5">
            {thread.closed_outcome ? `${thread.closed_outcome.replace("_", " ")}: ` : ""}
            {thread.closed_reason}
          </p>
        )}
      </div>
      <div className="shrink-0 flex items-center gap-2">
        {inboundCount > 0 && (
          <span className="text-xs text-muted-foreground">
            {inboundCount} repl{inboundCount === 1 ? "y" : "ies"}
          </span>
        )}
        {thread.state === "draft_ready" && !hasDraft && onRunAgent && (
          <Button
            size="sm"
            variant="outline"
            className="text-xs"
            disabled={agentRunning}
            onClick={(e) => {
              e.stopPropagation();
              onRunAgent();
            }}
          >
            {agentRunning ? (
              <Loader2 className="mr-1 h-3 w-3 animate-spin" />
            ) : (
              <Bot className="mr-1 h-3 w-3" />
            )}
            Draft
          </Button>
        )}
      </div>
    </div>
  );
}
