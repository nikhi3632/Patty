# Patty

AI-powered procurement assistant for restaurants. Upload a menu, get price trend alerts, nearby suppliers, and ready-to-send outreach emails.

## Why

Food costs are a restaurant's largest controllable expense — typically 28-35% of revenue. Most operators buy on autopilot: same supplier, same prices, no visibility into whether the market moved in their favor.

Patty watches commodity prices so you don't have to. When beef drops 12% below its normal range, you know before your supplier tells you. When spinach spikes, you can plan around it. The right information at the right time turns purchasing from a cost center into a competitive advantage.

## How it works

1. **Upload a menu** — PDF or photo. Claude extracts every ingredient.
2. **Track prices** — USDA (NASS) and wholesale (MARS) data, refreshed automatically.
3. **Get alerts** — Statistical z-score analysis flags ingredients priced unusually high or low.
4. **Find suppliers** — Google Maps finds nearby vendors matching your ingredients.
5. **Send emails** — AI-drafted, personalized outreach to each supplier. One click to send.

## Tech stack

| Layer | Tech |
|-------|------|
| Frontend | Next.js 16, React 19, Tailwind CSS, Radix UI, Recharts |
| Backend | FastAPI, Python 3.14 |
| Database | Supabase (Postgres + Storage) |
| AI | Claude (menu parsing, email drafting) |
| Pricing | USDA NASS API, USDA MARS wholesale data |
| Suppliers | Tavily (web search), Hunter (email lookup), Google Places (geocoding) |
| Email | Resend (delivery) |

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Frontend (Next.js)                                     │
│  Upload menu · View trends · Send emails                │
└────────────────────────┬────────────────────────────────┘
                         │ REST API
┌────────────────────────▼────────────────────────────────┐
│  Backend (FastAPI)                                      │
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐   │
│  │ Menu Parser │  │ Trend Engine │  │ Supplier      │   │
│  │ (Claude)    │  │ (z-score)    │  │ Finder        │   │
│  └──────┬──────┘  └──────┬───────┘  └──────┬────────┘   │
│         │                │                 │            │
│  ┌──────▼──────┐  ┌──────▼───────┐  ┌──────▼────────┐   │
│  │ Email       │  │ Price        │  │ Geocoding     │   │
│  │ Drafter     │  │ Fetcher      │  │               │   │
│  └─────────────┘  └──────────────┘  └───────────────┘   │
└───┬──────────┬──────────┬──────────┬──────────┬─────────┘
    │          │          │          │          │
    ▼          ▼          ▼          ▼          ▼
 Supabase   Claude    USDA NASS   USDA MARS   Tavily
 (DB +      (LLM)    (farm-gate  (wholesale  (web search)
  Storage)            prices)     prices)
                                               │
                              ┌────────┬───────┘
                              ▼        ▼
                           Hunter    Resend
                           (email    (email
                            lookup)   delivery)
```

## Setup

```bash
make install
```

Create `backend/.env`:

```
# USDA APIs
NASS_API_KEY=
NASS_BASE_URL=https://quickstats.nass.usda.gov/api
MYMARKET_NEWS_API_KEY=
MYMARKET_NEWS_BASE_URL=https://marsapi.ams.usda.gov/services/v1.2

# Database
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
DATABASE_URL=

# Geocoding
GOOGLE_PLACES_API_KEY=

# LLM
ANTHROPIC_API_KEY=

# Supplier Discovery
TAVILY_API_KEY=
HUNTER_API_KEY=

# Email
RESEND_API_KEY=
FROM_EMAIL=onboarding@resend.dev
TEST_EMAIL_OVERRIDE=
```

Create `frontend/.env`:

```
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
NEXT_PUBLIC_GOOGLE_PLACES_API_KEY=
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Run migrations and seed data:

```bash
make db-migrate
make db-seed
```

## Development

```bash
make dev-backend     # FastAPI on :8000
make dev-frontend    # Next.js on :3000
```

## API docs

- **Swagger:** [surprising-reverence-production.up.railway.app/docs](https://surprising-reverence-production.up.railway.app/docs)
- **ReDoc:** [surprising-reverence-production.up.railway.app/redoc](https://surprising-reverence-production.up.railway.app/redoc)

## Commands

```
make test            # Unit tests
make lint            # Ruff + ESLint
make typecheck       # TypeScript
make check           # lint + typecheck
make build           # Production frontend build
```
