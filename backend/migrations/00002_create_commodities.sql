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
  last_refreshed  timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE(raw_name, source)
);
