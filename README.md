# Patty

AI-powered procurement platform for restaurants. Upload a menu, get price trend alerts, find nearby suppliers, and let an AI agent negotiate pricing over email — all from one dashboard.

[Watch the demo](https://www.loom.com/share/7404ea3e9fe445e1ab0d5ae4bfac2c41)

## Why

Food costs are a restaurant's largest controllable expense — typically 28-35% of revenue. Most operators buy on autopilot: same supplier, same prices, no visibility into whether the market moved in their favor.

Patty watches commodity prices so you don't have to. When beef drops 12% below its normal range, you know before your supplier tells you. When spinach spikes, you can plan around it. And when it's time to reach out to suppliers, an AI agent handles the back-and-forth negotiation — drafting emails, responding to replies, and escalating when it needs your input.

## How it works

1. **Upload a menu** — PDF or photo. Vision LLM extracts every ingredient and maps them to tracked commodities.
2. **Track prices** — USDA farm-gate and wholesale data, refreshed automatically. Z-score analysis flags unusual price movements.
3. **Find suppliers** — Discovers nearby vendors via web search and geocoding, enriches with contact info.
4. **Send outreach** — AI-drafted, personalized emails to each supplier. Review, edit, and send with one click.
5. **AI negotiation agent** — A Claude-powered procurement agent reads supplier replies, drafts follow-ups, escalates when uncertain, and auto-closes stale threads. Supports manual approval or fully autonomous mode.
6. **Real-time updates** — Conversation UI updates instantly via event-driven Supabase Realtime. No polling, no refresh needed.

## Tech stack

| Layer | Tech |
|-------|------|
| Frontend | Next.js, React, TypeScript, Tailwind CSS, Radix UI |
| Backend | FastAPI, Python |
| Database | Supabase (Postgres + Storage + Realtime) |
| AI | Claude (Vision for menu parsing, tool-use agent for email negotiation) |
| Pricing | USDA NASS API (farm-gate), USDA MARS API (wholesale) |
| Suppliers | Tavily (web search), Hunter (email lookup), Google Places (geocoding) |
| Email | Gmail API (OAuth2, send + receive, push notifications via Pub/Sub) |

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Frontend (Next.js)                                          │
│  Upload menu · View trends · Review drafts · Live threads    │
│                          ▲                                   │
│                          │ Supabase Realtime (WebSocket)     │
└────────────────────────┬─┴───────────────────────────────────┘
                         │ REST API + SSE
┌────────────────────────▼─────────────────────────────────────┐
│  Backend (FastAPI)                                           │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │ Menu Parser  │  │ Trend Engine │  │ Supplier Finder    │  │
│  │ (Vision LLM) │  │ (z-score)    │  │ (Tavily + Hunter)  │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬─────────────┘  │
│         │                 │                  │               │
│  ┌──────▼───────┐  ┌──────▼───────┐  ┌──────▼─────────────┐  │
│  │ Email        │  │ Price        │  │ Procurement Agent  │  │
│  │ Drafter      │  │ Fetcher      │  │ (Claude tool-use)  │  │
│  └──────────────┘  └──────────────┘  └──────┬─────────────┘  │
│                                             │                │
│                                    ┌────────▼────────┐       │
│                                    │ Gmail Client    │       │
│                                    │ (send, receive, │       │
│                                    │  threading)     │       │
│                                    └─────────────────┘       │
└───┬──────────┬──────────┬──────────┬──────────┬─────────────-┘
    │          │          │          │          │
    ▼          ▼          ▼          ▼          ▼
 Supabase   Claude    USDA NASS   USDA MARS   Gmail API
 (DB +      (LLM)    (farm-gate  (wholesale  (OAuth2 +
  Realtime)           prices)     prices)     Pub/Sub)
```

## Email Agent

The procurement agent is a Claude tool-use agent that manages supplier conversations:

- **Tools:** `get_thread_history`, `get_restaurant_context`, `get_commodity_prices`, `draft_reply`, `escalate`, `close_thread`
- **Modes:** Manual (owner approves every draft) or Auto (agent sends, escalates when uncertain)
- **Triggers:** Inbound reply via Gmail Pub/Sub webhook, follow-up nudge after 3 days of silence
- **Auto-close:** After 2 unanswered follow-ups, thread closes automatically

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

# Email (Gmail API — credentials in gmail_credentials.json / token.json)
FROM_EMAIL=
TEST_EMAIL_OVERRIDE=
GMAIL_PUBSUB_TOPIC=
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

- **Swagger:** [localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc:** [localhost:8000/redoc](http://localhost:8000/redoc)

## Commands

```
make test            # Unit tests
make lint            # Ruff + ESLint
make typecheck       # TypeScript
make check           # lint + typecheck
make build           # Production frontend build
make db-reset        # Drop all tables and re-run migrations
make db-seed         # Seed commodity registry + prices
```
