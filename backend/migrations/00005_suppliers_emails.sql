-- Suppliers, outreach emails, threads, messages, notifications

CREATE TABLE IF NOT EXISTS suppliers (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name            text NOT NULL,
  address         text,
  email           text,
  contact_name    text,
  contact_title   text,
  phone           text,
  website         text,
  categories      text[] NOT NULL DEFAULT '{}',
  discovered_at   timestamptz NOT NULL DEFAULT now(),
  source          text NOT NULL DEFAULT 'tavily'
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_suppliers_website
  ON suppliers(website)
  WHERE website IS NOT NULL;

CREATE TABLE IF NOT EXISTS restaurant_suppliers (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  restaurant_id   uuid NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
  supplier_id     uuid NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
  distance_miles  numeric(10,2),
  linked_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE(restaurant_id, supplier_id)
);

CREATE INDEX IF NOT EXISTS idx_rs_restaurant ON restaurant_suppliers(restaurant_id);
CREATE INDEX IF NOT EXISTS idx_rs_supplier ON restaurant_suppliers(supplier_id);

CREATE TABLE IF NOT EXISTS emails (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  restaurant_id    uuid NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
  supplier_id      uuid NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
  to_email         text NOT NULL,
  to_name          text,
  from_email       text NOT NULL,
  subject          text NOT NULL,
  subject_original text NOT NULL,
  body             text NOT NULL,
  body_original    text NOT NULL,
  status           text NOT NULL DEFAULT 'generated',
  gmail_message_id text,
  gmail_thread_id  text,
  generated_at     timestamptz NOT NULL DEFAULT now(),
  edited_at        timestamptz,
  sent_at          timestamptz
);

CREATE INDEX IF NOT EXISTS idx_emails_restaurant ON emails(restaurant_id, status);
CREATE INDEX IF NOT EXISTS idx_emails_supplier ON emails(supplier_id);

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

-- Notifications for restaurant owners

CREATE TABLE IF NOT EXISTS notifications (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  restaurant_id   uuid NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
  thread_id       uuid REFERENCES email_threads(id) ON DELETE CASCADE,
  type            text NOT NULL,
  title           text NOT NULL,
  body            text,
  read            boolean NOT NULL DEFAULT false,
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_notifications_restaurant
  ON notifications(restaurant_id, read, created_at DESC);

-- Enable Supabase Realtime for instant frontend updates
ALTER PUBLICATION supabase_realtime ADD TABLE email_threads;
ALTER PUBLICATION supabase_realtime ADD TABLE email_messages;
