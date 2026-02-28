-- Restaurants and menu file uploads

CREATE TABLE IF NOT EXISTS restaurants (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name            text NOT NULL,
  address         text NOT NULL,
  lat             numeric(10,6) NOT NULL,
  lng             numeric(10,6) NOT NULL,
  state           text,
  nearest_market  text,
  cuisine_type    text,
  confirmed_at    timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS menu_files (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  restaurant_id   uuid NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
  file_type       text NOT NULL,
  storage_path    text NOT NULL,
  file_name       text NOT NULL,
  uploaded_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_menu_files_restaurant ON menu_files(restaurant_id);
