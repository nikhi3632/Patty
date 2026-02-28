-- Suppliers and outreach emails

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
  resend_id        text,
  generated_at     timestamptz NOT NULL DEFAULT now(),
  edited_at        timestamptz,
  sent_at          timestamptz
);

CREATE INDEX IF NOT EXISTS idx_emails_restaurant ON emails(restaurant_id, status);
CREATE INDEX IF NOT EXISTS idx_emails_supplier ON emails(supplier_id);
