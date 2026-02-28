-- Trend analysis and calibrations

CREATE TABLE IF NOT EXISTS commodity_calibrations (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  commodity_id          uuid NOT NULL REFERENCES commodities(id) ON DELETE CASCADE,
  source                text NOT NULL,
  market                text,
  volatility            numeric(12,6),
  autocorrelation_lag   integer,
  dynamic_horizon       integer NOT NULL,
  mean_change           numeric(12,6) NOT NULL,
  std_change            numeric(12,6) NOT NULL,
  data_points_used      integer NOT NULL,
  series_checksum       text,
  calibrated_at         timestamptz NOT NULL DEFAULT now(),
  UNIQUE(commodity_id, source, market)
);

CREATE INDEX IF NOT EXISTS idx_calibrations_commodity
  ON commodity_calibrations(commodity_id);

CREATE TABLE IF NOT EXISTS trends (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  restaurant_id    uuid NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
  commodity_id     uuid NOT NULL REFERENCES commodities(id) ON DELETE CASCADE,
  parent           text NOT NULL,
  signal           text NOT NULL DEFAULT 'stable',
  computed_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE(restaurant_id, commodity_id)
);

CREATE INDEX IF NOT EXISTS idx_trends_restaurant ON trends(restaurant_id, signal);

CREATE TABLE IF NOT EXISTS trend_signals (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  trend_id        uuid NOT NULL REFERENCES trends(id) ON DELETE CASCADE,
  source          text NOT NULL,
  raw_commodity   text,
  market          text,
  current_price   numeric(12,4),
  previous_price  numeric(12,4),
  change_pct      numeric(8,4),
  z_score         numeric(8,4),
  horizon         integer,
  unit            text,
  date_range      text,
  UNIQUE(trend_id, source)
);

CREATE INDEX IF NOT EXISTS idx_trend_signals_trend ON trend_signals(trend_id);
