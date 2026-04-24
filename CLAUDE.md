# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Run dev server (port 5050)
python run.py

# Database initialization (first time)
python init_db.py
python init_admin_roles.py

# Production
hypercorn run:asgi_app --bind 0.0.0.0:8080
```

No test framework or linting tools are configured.

## Architecture

Flask REST API for an e-commerce furniture platform. Blueprint-based modular routing with SQLAlchemy ORM on PostgreSQL (hosted on Supabase).

**Entry points:**
- `app.py` — Flask app factory, CORS setup, blueprint registration, `/health` endpoint
- `run.py` — Dev server on port 5050
- `routes/__init__.py` — Central hub registering all 31 blueprints with URL prefixes
- `config.py` — All configuration from environment variables

**Module layout:**
- `models/` — 32 SQLAlchemy models (product catalog, orders, users, admin, wallet, CRM, blog, promos)
- `routes/` — 31 Flask blueprints, one per domain
- `utils/` — Email service (Resend) and templates

**Key routes:**
- `routes/public_api.py` — Large public-facing API with API key auth (~164KB)
- `routes/orders.py` — Complex order processing with MercadoPago payment integration (~125KB)
- `routes/admin_stats.py` — Admin analytics/dashboard (~41KB)

**Database connection:** Configured for Supabase transaction mode (port 6543) with pooling (size=5, max_overflow=3, recycle=3600s, pre-ping=True).

**External integrations:**
- **Supabase** — Image storage (`product-images` and `hero-images` buckets); client in `supabase_client.py`
- **MercadoPago** — Payment processing in orders flow
- **Resend** — Transactional email via `utils/email_service.py`
- **ip-api.com** — IP geolocation for locality detection (45 req/min free tier)

**Auth patterns:**
- Admin routes: JWT via `PyJWT`, roles via `AdminRole` model
- User routes: JWT tokens issued at registration/login
- Public API: API key in request header

**Multi-locality pricing:** Products have prices per `Locality`. The `detect-locality` blueprint uses IP geolocation to set the user's locality, which affects visible prices and delivery zones. `DEFAULT_LOCALITY_ID` env var is the fallback.

**CORS:** Manually implemented via `after_request` hook in `app.py` (not Flask-CORS).

## Environment Variables

Copy `.env.example` or configure the following in `.env`:

```
DATABASE_URL=postgresql://user:pass@host:6543/bausing
SECRET_KEY=...
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_KEY=<service-role-key>
MP_ACCESS_TOKEN=...
MP_PUBLIC_KEY=...
RESEND_API_KEY=...
RESEND_FROM_EMAIL=...
FRONTEND_URL=http://localhost:3000
BACKEND_URL=http://localhost:5050
DEBUG_MODE=true
DEFAULT_LOCALITY_ID=<uuid>
```
