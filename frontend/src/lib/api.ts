const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function url(path: string) {
  return `${API}/api${path}`;
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url(path), init);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

// --- Analyze ---

export interface AnalyzeResult {
  restaurant_id: string;
  nearest_market: string;
  files_uploaded: number;
}

export async function analyze(form: FormData): Promise<AnalyzeResult> {
  const res = await fetch(url("/analyze"), { method: "POST", body: form });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export interface StreamEventResult {
  tracked?: number;
  other?: number;
  skipped?: boolean;
  computed?: number;
  suppliers_found?: number;
  drafted?: number;
  message?: string;
}

export interface StreamEvent {
  step: string;
  status: "running" | "done" | "error";
  result?: StreamEventResult;
}

export function subscribeToStream(
  restaurantId: string,
  onEvent: (event: StreamEvent) => void,
  onError?: (err: Error) => void
): () => void {
  const eventSource = new EventSource(
    url(`/analyze/${restaurantId}/stream`)
  );

  eventSource.onmessage = (msg) => {
    try {
      const event: StreamEvent = JSON.parse(msg.data);
      onEvent(event);
      if (event.step === "complete") {
        eventSource.close();
      }
    } catch {
      // ignore malformed events
    }
  };

  eventSource.onerror = () => {
    eventSource.close();
    onError?.(new Error("Stream connection lost"));
  };

  return () => eventSource.close();
}

export function subscribeToPipeline(
  restaurantId: string,
  onEvent: (event: StreamEvent) => void,
  onError?: (err: Error) => void
): () => void {
  const eventSource = new EventSource(
    url(`/analyze/${restaurantId}/pipeline`)
  );

  eventSource.onmessage = (msg) => {
    try {
      const event: StreamEvent = JSON.parse(msg.data);
      onEvent(event);
      if (event.step === "complete") {
        eventSource.close();
      }
    } catch {
      // ignore malformed events
    }
  };

  eventSource.onerror = () => {
    eventSource.close();
    onError?.(new Error("Pipeline stream connection lost"));
  };

  return () => eventSource.close();
}

// --- Commodities ---

export interface Commodity {
  id: string;
  restaurant_id: string;
  commodity_id: string | null;
  raw_ingredient_name: string;
  status: "tracked" | "other";
  automation_pref: string | null;
  commodities: {
    parent: string;
    display_name: string;
    source: string;
    cadence: string;
    has_price_data: boolean;
  } | null;
}

export interface Restaurant {
  id: string;
  name: string;
  address: string;
  confirmed_at: string | null;
}

export async function getRestaurant(restaurantId: string) {
  return json<{ data: Restaurant }>(`/restaurants/${restaurantId}`);
}

export async function confirmRestaurant(restaurantId: string) {
  return json<{ data: Restaurant }>(`/restaurants/${restaurantId}`, {
    method: "PATCH",
  });
}

export async function listCommodities(restaurantId: string) {
  return json<{ data: Commodity[] }>(
    `/restaurants/${restaurantId}/commodities`
  );
}

export interface RegistryItem {
  parent: string;
  has_price_data: boolean;
}

export async function commodityRegistry() {
  return json<{ data: RegistryItem[] }>("/commodities/registry");
}

export async function demoteCommodity(itemId: string) {
  return json<{ data: Commodity }>(`/restaurant-commodities/${itemId}/demote`, {
    method: "POST",
  });
}

export async function addCommodity(restaurantId: string, ingredient: string) {
  return json<{ data: Commodity }>(
    `/restaurants/${restaurantId}/commodities`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ingredient }),
    }
  );
}

export async function removeCommodity(itemId: string) {
  return json<{ deleted: boolean }>(`/restaurant-commodities/${itemId}`, {
    method: "DELETE",
  });
}


// --- Trends ---

export interface TrendSignal {
  id: string;
  trend_id: string;
  source: "mars" | "nass";
  raw_commodity?: string;
  market?: string;
  current_price: number;
  previous_price: number;
  change_pct: number;
  z_score: number;
  horizon: number;
  unit?: string;
  date_range?: string;
}

export interface Trend {
  id: string;
  restaurant_id: string;
  commodity_id: string;
  parent: string;
  signal: string;
  computed_at: string;
  trend_signals: TrendSignal[];
}

export async function listTrends(restaurantId: string) {
  return json<{ data: Trend[] }>(`/restaurants/${restaurantId}/trends`);
}

// --- Calibrations (System View) ---

export interface Calibration {
  id: string;
  commodity_id: string;
  source: string;
  market: string | null;
  volatility: number;
  autocorrelation_lag: number;
  dynamic_horizon: number;
  mean_change: number;
  std_change: number;
  data_points_used: number;
  series_checksum: string;
  calibrated_at: string;
}

export async function listCalibrations(restaurantId: string) {
  return json<{ data: Calibration[] }>(
    `/restaurants/${restaurantId}/calibrations`
  );
}

// --- Price Series (charts) ---

export interface PriceSeries {
  source: string;
  parent: string;
  unit?: string;
  prices: number[];
  dates: string[];
}

export async function getPriceSeries(
  commodityId: string,
  source: string = "nass",
  market?: string
) {
  const params = new URLSearchParams({ source });
  if (market) params.set("market", market);
  return json<{ data: PriceSeries }>(
    `/commodities/${commodityId}/prices?${params}`
  );
}

// --- Suppliers ---

export interface Supplier {
  id: string;
  name: string;
  address: string | null;
  email: string | null;
  contact_name: string | null;
  contact_title: string | null;
  phone: string | null;
  website: string | null;
  categories: string[];
  source: string;
  distance_miles: number | null;
}

export async function listSuppliers(restaurantId: string) {
  return json<{ data: Supplier[] }>(`/restaurants/${restaurantId}/suppliers`);
}

// --- Emails ---

export interface Email {
  id: string;
  restaurant_id: string;
  supplier_id: string;
  subject: string;
  body: string;
  subject_original: string;
  body_original: string;
  status: "generated" | "draft" | "sent" | "discarded";
  edited_at: string | null;
  sent_at: string | null;
  generated_at: string;
  suppliers: {
    name: string;
    email: string;
    categories: string[];
    distance_miles: number | null;
  };
}

export async function listEmails(restaurantId: string) {
  return json<{ data: Email[] }>(`/restaurants/${restaurantId}/emails`);
}

export async function updateEmail(
  emailId: string,
  updates: { subject?: string; body?: string; status?: string }
) {
  return json<{ data: Email }>(`/emails/${emailId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
}

export async function sendEmail(emailId: string) {
  return json<{ data: Email }>(`/emails/${emailId}/send`, {
    method: "POST",
  });
}

export async function revertEmail(emailId: string) {
  return json<{ data: Email }>(`/emails/${emailId}/revert`, {
    method: "POST",
  });
}

// --- Menu Files ---

export interface MenuFile {
  id: string;
  file_name: string;
  file_type: string;
  storage_path: string;
  uploaded_at: string;
  url: string;
}

export async function listMenuFiles(restaurantId: string) {
  return json<{ data: MenuFile[] }>(`/restaurants/${restaurantId}/menu-files`);
}

// --- Price Refresh ---

export async function refreshPrices(restaurantId: string) {
  return json<{ status: string }>(`/restaurants/${restaurantId}/refresh`, {
    method: "POST",
  });
}

// --- Restaurant Management ---

export async function deleteRestaurant(restaurantId: string) {
  return json<{ deleted: boolean; name: string }>(
    `/restaurants/${restaurantId}`,
    { method: "DELETE" }
  );
}
