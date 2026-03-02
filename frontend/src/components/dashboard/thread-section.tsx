"use client";

import { useEffect, useRef, useState } from "react";
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
import { runAgent } from "@/lib/api";
import ThreadDetail from "./thread-detail";

interface Props {
  threads: EmailThread[];
  onUpdate: () => void;
  visible: boolean;
}

const REFRESH_INTERVAL = 15_000; // 15s auto-refresh when tab is active

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

export default function ThreadSection({ threads, onUpdate, visible }: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [agentRunning, setAgentRunning] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Auto-refresh threads while the conversations tab is visible
  useEffect(() => {
    if (visible) {
      intervalRef.current = setInterval(() => {
        onUpdate();
      }, REFRESH_INTERVAL);
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [visible, onUpdate]);

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
          agentRunning={agentRunning}
        />
      )}

      {escalated.length > 0 && (
        <ThreadGroup
          label="Escalated"
          threads={escalated}
          onSelect={setSelectedId}
          agentRunning={agentRunning}
        />
      )}

      {waiting.length > 0 && (
        <ThreadGroup
          label="Waiting for Reply"
          threads={waiting}
          onSelect={setSelectedId}
          agentRunning={agentRunning}
          onRunAgent={handleRunAgent}
        />
      )}

      {closed.length > 0 && (
        <ThreadGroup
          label="Closed"
          threads={closed}
          onSelect={setSelectedId}
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
  agentRunning,
  onRunAgent,
}: {
  label: string;
  threads: EmailThread[];
  onSelect: (id: string) => void;
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
  agentRunning,
  onRunAgent,
}: {
  thread: EmailThread;
  onClick: () => void;
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
