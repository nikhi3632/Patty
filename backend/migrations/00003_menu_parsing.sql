-- Menu parsing and restaurant ↔ commodity link

CREATE TABLE IF NOT EXISTS restaurant_commodities (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  restaurant_id       uuid NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
  commodity_id        uuid REFERENCES commodities(id) ON DELETE SET NULL,
  raw_ingredient_name text NOT NULL,
  status              text NOT NULL DEFAULT 'tracked',
  original_status     text,
  automation_pref     text,
  added_by            text NOT NULL DEFAULT 'system',
  deleted_at          timestamptz,
  deleted_by          text,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_active_restaurant_commodity
  ON restaurant_commodities(restaurant_id, commodity_id)
  WHERE deleted_at IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_rc_other
  ON restaurant_commodities(restaurant_id, raw_ingredient_name)
  WHERE status = 'other' AND deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_rc_restaurant_status
  ON restaurant_commodities(restaurant_id, status);

CREATE TABLE IF NOT EXISTS menu_parses (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  restaurant_id     uuid NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
  status            text NOT NULL DEFAULT 'completed',
  raw_llm_response  jsonb NOT NULL,
  parsed_at         timestamptz NOT NULL DEFAULT now()
);
