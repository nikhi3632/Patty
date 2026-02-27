CREATE TABLE IF NOT EXISTS suppliers (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  restaurant_id   uuid NOT NULL REFERENCES restaurants(id),
  name            text NOT NULL,
  email           text,
  contact_name    text,
  contact_title   text,
  phone           text,
  website         text,
  categories      text[] NOT NULL DEFAULT '{}',
  distance_miles  decimal,
  discovered_at   timestamptz NOT NULL DEFAULT now(),
  source          text NOT NULL DEFAULT 'tavily'
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_suppliers_dedup
  ON suppliers(restaurant_id, website)
  WHERE website IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_suppliers_restaurant ON suppliers(restaurant_id);
