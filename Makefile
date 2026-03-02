.PHONY: install dev-backend dev-frontend dev build clean db-migrate db-reset db-seed lint lint-frontend fmt test test-integration typecheck check

# Install all dependencies
install:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
	cd frontend && npm install

# Run backend (port 8000)
dev-backend:
	cd backend && source .venv/bin/activate && uvicorn main:app --reload --port 8000

# Run frontend (port 3000)
dev-frontend:
	cd frontend && npm run dev

# Run both (requires two terminals — use make dev-backend & make dev-frontend)
dev:
	@echo "Run in two terminals:"
	@echo "  make dev-backend"
	@echo "  make dev-frontend"

# Build frontend
build:
	cd frontend && npm run build

# Run all migrations in order
db-migrate:
	@export $$(grep '^DATABASE_URL=' backend/.env | xargs) && \
	for f in backend/migrations/*.sql; do \
		echo "Running $$f..."; \
		psql "$$DATABASE_URL" -f "$$f"; \
	done

# Drop ALL tables and recreate schema
db-reset:
	@export $$(grep '^DATABASE_URL=' backend/.env | xargs) && \
	psql "$$DATABASE_URL" -c "DROP TABLE IF EXISTS notifications, email_messages, email_threads, emails, restaurant_suppliers, suppliers, trend_signals, commodity_calibrations, trends, menu_parses, restaurant_commodities, wholesale_prices, commodity_prices, commodities, menu_files, restaurants CASCADE;"
	$(MAKE) db-migrate

# Seed static reference data (commodity registry + prices — slow, run once)
db-seed:
	cd backend && .venv/bin/python seeds/seed.py

# Lint backend + frontend
lint:
	cd backend && .venv/bin/ruff check .
	cd frontend && npm run lint

# Lint frontend only
lint-frontend:
	cd frontend && npm run lint

# Typecheck frontend
typecheck:
	cd frontend && npx tsc --noEmit

# Full check: lint + typecheck (run before committing)
check:
	$(MAKE) lint
	$(MAKE) typecheck

# Format backend
fmt:
	cd backend && .venv/bin/ruff format .

# Run fast tests (no external API calls)
test:
	cd backend && .venv/bin/python -m pytest tests/ -v

# Run all tests including integration (hits Claude + Supabase)
test-integration:
	cd backend && .venv/bin/python -m pytest tests/ -v -m integration

# Clean build artifacts
clean:
	rm -rf frontend/dist frontend/.next backend/__pycache__
