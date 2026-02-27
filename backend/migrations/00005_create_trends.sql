CREATE TABLE IF NOT EXISTS trends (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  restaurant_id    uuid NOT NULL REFERENCES restaurants(id),
  commodity_id     uuid NOT NULL REFERENCES commodities(id),
  parent           text NOT NULL,
  nass_current     decimal,
  nass_previous    decimal,
  nass_change_pct  decimal,
  nass_unit        text,
  nass_state       text,
  nass_date_range  text,
  mars_commodity   text,
  mars_market      text,
  mars_current     decimal,
  mars_previous    decimal,
  mars_change_pct  decimal,
  mars_date_range  text,
  signal           text NOT NULL DEFAULT 'stable',
  computed_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE(restaurant_id, commodity_id)
);

CREATE INDEX IF NOT EXISTS idx_trends_restaurant ON trends(restaurant_id, signal);
