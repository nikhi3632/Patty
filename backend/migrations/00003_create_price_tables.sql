CREATE TABLE IF NOT EXISTS commodity_prices (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  commodity       text NOT NULL,
  short_desc      text NOT NULL,
  price           decimal NOT NULL,
  unit            text NOT NULL,
  year            int NOT NULL,
  month           int NOT NULL,
  state           text,
  agg_level       text NOT NULL,
  fetched_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE(commodity, short_desc, year, month, state)
);

CREATE TABLE IF NOT EXISTS wholesale_prices (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  commodity       text NOT NULL,
  terminal_market text NOT NULL,
  report_date     date NOT NULL,
  low_price       decimal,
  high_price      decimal,
  mostly_low      decimal,
  mostly_high     decimal,
  package         text,
  origin          text,
  variety         text,
  organic         boolean,
  slug_id         int NOT NULL,
  fetched_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE(commodity, terminal_market, report_date, package, origin)
);

CREATE INDEX IF NOT EXISTS idx_commodity_prices_lookup ON commodity_prices(commodity, state, year DESC, month DESC);
CREATE INDEX IF NOT EXISTS idx_wholesale_prices_lookup ON wholesale_prices(commodity, terminal_market, report_date DESC);
