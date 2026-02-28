"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Check, Pencil, X, Send } from "lucide-react";
import {
  updateEmail,
  sendEmail as sendEmailApi,
  revertEmail,
  type Email,
} from "@/lib/api";
import AccordionCard from "./accordion-card";

interface Props {
  email: Email;
  expanded: boolean;
  onToggle: () => void;
  onUpdate: () => void;
}

export default function EmailCard({ email, expanded, onToggle, onUpdate }: Props) {
  const [editing, setEditing] = useState(false);
  const [subject, setSubject] = useState(email.subject);
  const [body, setBody] = useState(email.body);
  const [sending, setSending] = useState(false);
  const [saving, setSaving] = useState(false);

  if (email.status === "sent") {
    const sentTrigger = (
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <Check className="h-3.5 w-3.5 text-green-600 shrink-0" />
          <span className="truncate font-medium text-sm">{email.suppliers?.name}</span>
        </div>
        <p className="truncate text-xs text-muted-foreground mt-0.5 pl-[22px]">
          &ldquo;{email.subject}&rdquo;
          {email.sent_at && (
            <span className="ml-1.5 text-muted-foreground/60">
              &middot; sent {new Date(email.sent_at).toLocaleDateString()}{" "}
              {new Date(email.sent_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit", timeZoneName: "short" })}
            </span>
          )}
        </p>
      </div>
    );

    return (
      <AccordionCard expanded={expanded} onToggle={onToggle} trigger={sentTrigger}>
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">{email.suppliers?.email}</p>
          <div className="rounded-md bg-muted/50 p-3">
            <p className="text-sm font-medium">{email.subject}</p>
            <p className="mt-1.5 whitespace-pre-wrap text-sm text-muted-foreground">
              {email.body}
            </p>
          </div>
        </div>
      </AccordionCard>
    );
  }

  async function handleSave() {
    setSaving(true);
    try {
      await updateEmail(email.id, { subject, body });
      setEditing(false);
      onUpdate();
    } finally {
      setSaving(false);
    }
  }

  async function handleRevert() {
    await revertEmail(email.id);
    setSubject(email.subject_original);
    setBody(email.body_original);
    setEditing(false);
    onUpdate();
  }

  async function handleSend() {
    setSending(true);
    try {
      await sendEmailApi(email.id);
      onUpdate();
    } finally {
      setSending(false);
    }
  }

  const trigger = (
    <>
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <Send className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
          <span className="truncate font-medium text-sm">{email.suppliers?.name}</span>
          {email.suppliers?.distance_miles != null && (
            <span className="text-xs text-muted-foreground shrink-0">
              {email.suppliers.distance_miles} mi
            </span>
          )}
        </div>
        <p className="truncate text-xs text-muted-foreground mt-0.5 pl-[22px]">
          &ldquo;{email.subject}&rdquo;
        </p>
      </div>
      {email.edited_at && (
        <Badge variant="outline" className="text-[10px] shrink-0">Edited</Badge>
      )}
    </>
  );

  return (
    <AccordionCard
      expanded={expanded}
      onToggle={() => { if (!editing) onToggle(); }}
      trigger={trigger}
    >
      <div className="space-y-3">
        <p className="text-xs text-muted-foreground">
          {email.suppliers?.email}
        </p>

        {editing ? (
          <div className="space-y-2">
            <Input
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              className="text-sm"
            />
            <Textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={8}
              className="text-sm"
            />
            <div className="flex gap-2">
              <Button size="sm" disabled={saving} onClick={handleSave}>
                {saving ? "Saving..." : "Save"}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  setSubject(email.subject);
                  setBody(email.body);
                  setEditing(false);
                }}
              >
                Cancel
              </Button>
              {email.edited_at && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={handleRevert}
                  className="text-muted-foreground"
                >
                  Revert
                </Button>
              )}
            </div>
          </div>
        ) : (
          <>
            <div className="rounded-md bg-muted/50 p-3">
              <p className="text-sm font-medium">{email.subject}</p>
              <p className="mt-1.5 whitespace-pre-wrap text-sm text-muted-foreground line-clamp-4">
                {email.body}
              </p>
            </div>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
                <Pencil className="mr-1.5 h-3 w-3" />
                Edit
              </Button>
              <Button size="sm" disabled={sending} onClick={handleSend}>
                <Send className="mr-1.5 h-3 w-3" />
                {sending ? "Sending..." : "Send"}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="text-muted-foreground"
                onClick={async () => {
                  await updateEmail(email.id, { status: "discarded" });
                  onUpdate();
                }}
              >
                <X className="mr-1.5 h-3 w-3" />
                Discard
              </Button>
            </div>
          </>
        )}
      </div>
    </AccordionCard>
  );
}
