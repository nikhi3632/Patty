"use client";

import { useState } from "react";
import type { Email } from "@/lib/api";
import EmailCard from "./email-card";

interface Props {
  emails: Email[];
  onUpdate: () => void;
}

export default function EmailSection({ emails, onUpdate }: Props) {
  const active = emails.filter(
    (e) => e.status === "generated" || e.status === "draft"
  );
  const sent = emails.filter((e) => e.status === "sent");
  const [expandedId, setExpandedId] = useState<string | undefined>(
    active[0]?.id
  );

  if (active.length === 0 && sent.length === 0) return null;

  return (
    <div className="space-y-3">
      {active.length > 0 && (
        <h2 className="text-base font-medium">
          Reach out &mdash; {active.length} email{active.length !== 1 ? "s" : ""} ready
        </h2>
      )}
      {active.map((email) => (
        <EmailCard
          key={email.id}
          email={email}
          expanded={expandedId === email.id}
          onToggle={() =>
            setExpandedId((prev) =>
              prev === email.id ? undefined : email.id
            )
          }
          onUpdate={onUpdate}
        />
      ))}
      {sent.length > 0 && (
        <>
          <p className="text-xs text-muted-foreground pt-1">
            {sent.length} sent
          </p>
          {sent.map((email) => (
            <EmailCard
              key={email.id}
              email={email}
              expanded={expandedId === email.id}
              onToggle={() =>
                setExpandedId((prev) =>
                  prev === email.id ? undefined : email.id
                )
              }
              onUpdate={onUpdate}
            />
          ))}
        </>
      )}
    </div>
  );
}
