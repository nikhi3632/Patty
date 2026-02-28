-- Menu parsing and restaurant ↔ commodity link

CREATE TABLE IF NOT EXISTS restaurant_commodities (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  restaurant_id       uuid NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
  commodity_id        uuid REFERENCES commodities(id) ON DELETE SET NULL,
  raw_ingredient_name text NOT NULL,
  status              text NOT NULL DEFAULT 'tracked',
  automation_pref     text,
  user_confirmed      boolean NOT NULL DEFAULT false,
  added_by            text NOT NULL DEFAULT 'system',
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  UNIQUE(restaurant_id, commodity_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_rc_other
  ON restaurant_commodities(restaurant_id, raw_ingredient_name)
  WHERE status = 'other';

CREATE INDEX IF NOT EXISTS idx_rc_restaurant_status
  ON restaurant_commodities(restaurant_id, status);

CREATE TABLE IF NOT EXISTS menu_parses (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  restaurant_id     uuid NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
  status            text NOT NULL DEFAULT 'completed',
  raw_llm_response  jsonb NOT NULL,
  parsed_at         timestamptz NOT NULL DEFAULT now()
);
