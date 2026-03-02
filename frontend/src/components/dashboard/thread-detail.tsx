"use client";

import { useState } from "react";
import {
  ArrowLeft,
  Bot,
  User,
  Send,
  Pencil,
  Loader2,
  AlertTriangle,
  Info,
  XCircle,
  CheckCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import type { EmailThread, EmailMessage } from "@/lib/api";
import { approveDraft, updateThreadMode, closeThread } from "@/lib/api";

interface Props {
  thread: EmailThread;
  onBack: () => void;
  onUpdate: () => void;
  agentRunning: boolean;
  onRunAgent: () => void;
}

export default function ThreadDetail({
  thread,
  onBack,
  onUpdate,
  agentRunning,
  onRunAgent,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [editSubject, setEditSubject] = useState("");
  const [editBody, setEditBody] = useState("");
  const [sending, setSending] = useState(false);
  const [closing, setClosing] = useState(false);

  // Find the pending draft (has draft_body but no final_body)
  const draft = thread.messages.find((m) => m.draft_body && !m.final_body);

  function startEdit() {
    if (!draft) return;
    setEditSubject(draft.subject ?? "");
    setEditBody(draft.draft_body ?? "");
    setEditing(true);
  }

  async function handleApprove(edited?: boolean) {
    setSending(true);
    try {
      if (edited) {
        await approveDraft(thread.id, {
          subject: editSubject,
          body: editBody,
        });
      } else {
        await approveDraft(thread.id);
      }
      setEditing(false);
      onUpdate();
    } finally {
      setSending(false);
    }
  }

  async function handleClose() {
    setClosing(true);
    try {
      await closeThread(thread.id, "Closed by owner", "owner_closed");
      onUpdate();
    } finally {
      setClosing(false);
    }
  }

  // Conversation messages (exclude pending drafts from the timeline)
  const timeline = thread.messages.filter(
    (m) => !(m.draft_body && !m.final_body)
  );

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button
          onClick={onBack}
          className="rounded-md p-1.5 hover:bg-muted/50 transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
        <div className="min-w-0 flex-1">
          <h3 className="font-medium text-sm truncate">
            {thread.suppliers?.name ?? "Unknown Supplier"}
          </h3>
          <p className="text-xs text-muted-foreground">
            {thread.suppliers?.email}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Badge variant="outline" className="text-[10px]">
            {thread.state.replace("_", " ")}
          </Badge>
          <button
            onClick={async () => {
              const next = thread.approval_mode === "auto" ? "manual" : "auto";
              await updateThreadMode(thread.id, next);
              onUpdate();
            }}
            className={`rounded-full px-2 py-0.5 text-[10px] font-medium transition-colors ${
              thread.approval_mode === "auto"
                ? "bg-green-100 text-green-700 hover:bg-green-200"
                : "bg-muted text-muted-foreground hover:bg-muted/80"
            }`}
          >
            {thread.approval_mode === "auto" ? "Auto" : "Manual"}
          </button>
        </div>
      </div>

      {/* Conversation timeline */}
      <div className="space-y-3">
        {timeline.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
      </div>

      {/* Escalation notice */}
      {thread.state === "escalated" && (
        <div className="rounded-md border border-red-200 bg-red-50 p-3 space-y-1">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-red-500" />
            <span className="text-sm font-medium text-red-700">Escalated</span>
          </div>
          {thread.messages.find((m) => m.agent_reasoning && !m.draft_body) && (
            <p className="text-xs text-red-600">
              {thread.messages.find((m) => m.agent_reasoning && !m.draft_body)?.agent_reasoning}
            </p>
          )}
        </div>
      )}

      {/* Closed notice */}
      {thread.state === "closed" && (
        <div className="rounded-md border border-muted bg-muted/30 p-3 space-y-1">
          <div className="flex items-center gap-2">
            <CheckCircle className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-medium">Closed</span>
            {thread.closed_outcome && (
              <Badge variant="outline" className="text-[10px]">
                {thread.closed_outcome.replace("_", " ")}
              </Badge>
            )}
          </div>
          {thread.closed_reason && (
            <p className="text-xs text-muted-foreground">
              {thread.closed_reason}
            </p>
          )}
        </div>
      )}

      {/* Draft review */}
      {draft && (
        <div className="rounded-md border border-blue-200 bg-blue-50/50 p-4 space-y-3">
          <div className="flex items-center gap-2">
            <Bot className="h-4 w-4 text-blue-600" />
            <span className="text-sm font-medium text-blue-700">
              Agent Draft
            </span>
          </div>

          {/* Reasoning */}
          {draft.agent_reasoning && (
            <div className="flex gap-2 rounded-md bg-blue-100/50 p-2">
              <Info className="h-3.5 w-3.5 text-blue-500 mt-0.5 shrink-0" />
              <p className="text-xs text-blue-700">{draft.agent_reasoning}</p>
            </div>
          )}

          {editing ? (
            <div className="space-y-2">
              <Input
                value={editSubject}
                onChange={(e) => setEditSubject(e.target.value)}
                className="text-sm bg-white"
                placeholder="Subject"
              />
              <Textarea
                value={editBody}
                onChange={(e) => setEditBody(e.target.value)}
                rows={6}
                className="text-sm bg-white"
              />
              <div className="flex gap-2">
                <Button
                  size="sm"
                  disabled={sending}
                  onClick={() => handleApprove(true)}
                >
                  {sending ? (
                    <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />
                  ) : (
                    <Send className="mr-1.5 h-3 w-3" />
                  )}
                  Send Edited
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setEditing(false)}
                >
                  Cancel
                </Button>
              </div>
            </div>
          ) : (
            <>
              <div className="rounded-md bg-white p-3 border">
                <p className="text-sm font-medium">{draft.subject}</p>
                <p className="mt-1.5 whitespace-pre-wrap text-sm text-muted-foreground">
                  {draft.draft_body}
                </p>
              </div>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  disabled={sending}
                  onClick={() => handleApprove()}
                >
                  {sending ? (
                    <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />
                  ) : (
                    <Send className="mr-1.5 h-3 w-3" />
                  )}
                  Approve & Send
                </Button>
                <Button size="sm" variant="outline" onClick={startEdit}>
                  <Pencil className="mr-1.5 h-3 w-3" />
                  Edit
                </Button>
              </div>
            </>
          )}
        </div>
      )}

      {/* Run agent button when in draft_ready state but no draft yet */}
      {thread.state === "draft_ready" && !draft && (
        <Button
          size="sm"
          variant="outline"
          disabled={agentRunning}
          onClick={onRunAgent}
          className="w-full"
        >
          {agentRunning ? (
            <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />
          ) : (
            <Bot className="mr-1.5 h-3 w-3" />
          )}
          {agentRunning ? "Agent is thinking..." : "Generate Draft Reply"}
        </Button>
      )}

      {/* Close thread button — visible on all non-closed threads */}
      {thread.state !== "closed" && (
        <Button
          size="sm"
          variant="ghost"
          className="w-full text-muted-foreground hover:text-red-600"
          disabled={closing}
          onClick={handleClose}
        >
          {closing ? (
            <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />
          ) : (
            <XCircle className="mr-1.5 h-3 w-3" />
          )}
          Close Conversation
        </Button>
      )}
    </div>
  );
}

function MessageBubble({ message }: { message: EmailMessage }) {
  const isInbound = message.direction === "inbound";
  const displayBody = message.final_body || message.body;

  return (
    <div className={`flex gap-2 ${isInbound ? "" : "flex-row-reverse"}`}>
      <div className="shrink-0 mt-1">
        {isInbound ? (
          <div className="rounded-full bg-muted p-1.5">
            <User className="h-3 w-3 text-muted-foreground" />
          </div>
        ) : (
          <div className="rounded-full bg-primary/10 p-1.5">
            <Bot className="h-3 w-3 text-primary" />
          </div>
        )}
      </div>
      <div
        className={`max-w-[80%] rounded-lg px-3 py-2 ${
          isInbound
            ? "bg-muted/50 text-foreground"
            : "bg-primary/10 text-foreground"
        }`}
      >
        {message.subject && (
          <p className="text-xs font-medium mb-1">{message.subject}</p>
        )}
        <p className="text-sm whitespace-pre-wrap">{displayBody}</p>
        <p className="text-[10px] text-muted-foreground mt-1">
          {new Date(message.created_at).toLocaleString([], {
            month: "short",
            day: "numeric",
            hour: "numeric",
            minute: "2-digit",
          })}
          {message.owner_edited && " (edited)"}
        </p>
      </div>
    </div>
  );
}
