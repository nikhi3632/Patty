CREATE TABLE IF NOT EXISTS emails (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  restaurant_id    uuid NOT NULL REFERENCES restaurants(id),
  supplier_id      uuid NOT NULL REFERENCES suppliers(id),
  to_email         text NOT NULL,
  to_name          text,
  from_email       text NOT NULL,
  subject          text NOT NULL,
  subject_original text NOT NULL,
  body             text NOT NULL,
  body_original    text NOT NULL,
  status           text NOT NULL DEFAULT 'generated',
  resend_id        text,
  generated_at     timestamptz NOT NULL DEFAULT now(),
  edited_at        timestamptz,
  sent_at          timestamptz
);

CREATE INDEX IF NOT EXISTS idx_emails_restaurant ON emails(restaurant_id, status);
CREATE INDEX IF NOT EXISTS idx_emails_supplier ON emails(supplier_id);
