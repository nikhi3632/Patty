-- Email threads and messages for the procurement agent

CREATE TABLE IF NOT EXISTS email_threads (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  restaurant_id   uuid NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
  supplier_id     uuid NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
  gmail_thread_id text,
  state           text NOT NULL DEFAULT 'outreach_sent',
  approval_mode   text NOT NULL DEFAULT 'manual',
  closed_reason   text,
  closed_outcome  text,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ethreads_restaurant ON email_threads(restaurant_id, state);
CREATE INDEX IF NOT EXISTS idx_ethreads_supplier ON email_threads(supplier_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ethreads_gmail ON email_threads(gmail_thread_id)
  WHERE gmail_thread_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS email_messages (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  thread_id         uuid NOT NULL REFERENCES email_threads(id) ON DELETE CASCADE,
  direction         text NOT NULL,
  gmail_message_id  text,
  sender            text NOT NULL,
  recipient         text NOT NULL,
  subject           text,
  body              text NOT NULL,
  classified_intent text,
  agent_reasoning   text,
  draft_body        text,
  final_body        text,
  owner_edited      boolean NOT NULL DEFAULT false,
  auto_sent         boolean NOT NULL DEFAULT false,
  created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_emessages_thread ON email_messages(thread_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_emessages_gmail ON email_messages(gmail_message_id)
  WHERE gmail_message_id IS NOT NULL;
