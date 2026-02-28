-- Commodity registry and price data (NASS + MARS)

CREATE TABLE IF NOT EXISTS commodities (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  parent          text NOT NULL,
  display_name    text NOT NULL,
  raw_name        text NOT NULL,
  source          text NOT NULL,
  source_params   jsonb NOT NULL DEFAULT '{}',
  unit            text,
  cadence         text NOT NULL,
  active          boolean NOT NULL DEFAULT true,
  has_price_data  boolean NOT NULL DEFAULT false,
  markets_covered text[] NOT NULL DEFAULT '{}',
  aliases         text[] NOT NULL DEFAULT '{}',
  last_refreshed  timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE(raw_name, source)
);

CREATE INDEX IF NOT EXISTS idx_commodities_source_parent ON commodities(source, parent);

CREATE TABLE IF NOT EXISTS commodity_prices (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  commodity       text NOT NULL,
  short_desc      text NOT NULL,
  price           numeric(12,4) NOT NULL,
  unit            text NOT NULL,
  year            int NOT NULL,
  month           int NOT NULL,
  state           text,
  agg_level       text NOT NULL,
  fetched_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE(commodity, short_desc, year, month, state)
);

CREATE INDEX IF NOT EXISTS idx_commodity_prices_lookup
  ON commodity_prices(commodity, state, year DESC, month DESC);

CREATE TABLE IF NOT EXISTS wholesale_prices (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  commodity       text NOT NULL,
  terminal_market text NOT NULL,
  report_date     date NOT NULL,
  low_price       numeric(12,4),
  high_price      numeric(12,4),
  mostly_low      numeric(12,4),
  mostly_high     numeric(12,4),
  package         text,
  origin          text,
  variety         text,
  organic         boolean,
  slug_id         int NOT NULL,
  fetched_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE(commodity, terminal_market, report_date, package, origin)
);

CREATE INDEX IF NOT EXISTS idx_wholesale_prices_lookup
  ON wholesale_prices(commodity, terminal_market, report_date DESC);
