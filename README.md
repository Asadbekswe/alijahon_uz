# Alijahon — onlayn do'kon va hamkorlik platformasi

Django storefront with an affiliate ("oqim") programme, operator call-centre workflow and courier delivery board.
Customers order with cash-on-delivery; operators confirm orders by phone; couriers deliver; affiliates earn a payout
for every delivered order that came through their stream link.

## Architecture

```
root/                  Django project (settings, urls, wsgi)
apps/
  models/              Product, Category, ProductImage, Review, Order, Stream, Favorite, Transaction, SiteSettings,
                       User (+ proxy models per role/status for the admin)
  services.py          Business operations that must stay consistent: place_orders, change_order_status,
                       claim_order, request_withdrawal (row locks + conditional UPDATEs, no races)
  cart.py              Session cart (lines keyed by product + stream)
  views/               product_views (home, catalog, PDP, quick view, market), shop_views (cart, checkout, orders,
                       streams, statistics), auth_views (auth, account, operator & courier boards), utils_views
  forms.py             All forms; StyledFormMixin applies the design-system classes & phone masks
  admin/               Custom AdminSite with sales dashboard, grouped navigation, model admins
  management/commands/seed_dev_data.py   Idempotent development data (+ seed_images.py illustration renderer)
  static/store/        Design system: css/app.css, js/app.js (interactions), js/charts.js (SVG charts), admin/
  tests/               pytest suite (services, views/permissions, seed)
templates/             Storefront, account/partner panel, operator, courier, admin, error pages
compose.yaml           Development stack (web + MySQL 8.4 + Redis 7)
compose.prod.yaml      Production-style stack (gunicorn + whitenoise)
```

**Stack:** Python 3.12, Django 5.2 LTS, MySQL 8.4, Redis 7 (cache, sessions, login rate limiting), gunicorn,
WhiteNoise, vanilla JS (no build step), CKEditor 5, Rosetta.

### Order lifecycle

`new → ready → delivering → delivered`, with side exits `cant_phone`, `canceled`, `broken`, `archived`.
Allowed transitions live in `Order.TRANSITIONS`; every status change goes through
`apps.services.change_order_status`, which:

- returns reserved stock to the warehouse when an order is cancelled;
- credits the affiliate's balance (`payout × quantity`) exactly once when an order is delivered.

Stock is reserved at checkout with a conditional `UPDATE … WHERE quantity >= n`, and prices/payouts are
snapshotted on the order (`Order.price`, `Order.payout`).

### Roles

| Role | Area | Access rule |
|---|---|---|
| Customer / affiliate (`user`) | storefront, `/profile/`, partner panel (`/admin-page/…`, `/payment/`) | login |
| Operator | `/operator-page/` — claim, call, update, create orders | `OperatorRequiredMixin` |
| Courier | `/currier-page/` — take ready orders, report delivery | `CurrierRequiredMixin` |
| Admin / staff | `/admin/` — dashboard, catalogue, orders, payouts | Django admin |

## Local development (Docker)

Requirements: Docker with Compose v2.

```bash
make env        # creates .env with random secrets (never committed)
make up         # builds and starts web, MySQL and Redis; migrations run automatically
make seed       # idempotent demo data (safe to run repeatedly)
```

Open <http://localhost:8010> (admin: <http://localhost:8010/admin/>).

Ports are configurable in `.env` (`WEB_PORT`, default 8010; `DB_HOST_PORT`, default 3317, bound to 127.0.0.1).
The stack is fully isolated: its own `alijahon-dev` network, `mysql_data` volume and `alijahon_dev` database.
**Never point the development stack at the production database.**

Useful commands:

```bash
make logs                 # follow web logs
make test                 # pytest (uses a throwaway test_* MySQL database)
make lint                 # flake8
make migrate / make makemigrations
make shell
docker compose down -v    # stop and DELETE the dev database volume
```

### Development test accounts

Created by `manage.py seed_dev_data` (development only; passwords come from `.env` — the values below are the ones
`make env` writes):

| Role | Phone (login) | Password |
|---|---|---|
| Admin (superuser) | `900000001` | `Admin-dev-2026` |
| Customer & affiliate | `900000002` | `Customer-dev-2026` |
| Operator | `900000003` | `Staff-dev-2026` |
| Courier | `900000004` | `Staff-dev-2026` |

Log in with the 9 local digits or the full `+998 (90) 000-00-02` form.

The seed creates 14 regions with districts, 6 categories, 36 products (each with 3 generated studio-style images,
specifications, prices, discounts, stock and affiliate payouts), 90 reviews, 4 streams, 72 orders across all statuses
over the last 45 days, an active competition and sample payout requests. Every row is matched by a natural key
(phone, slug, name, reserved phone range `99000NNNN` for orders), so re-running updates in place instead of
duplicating. It refuses to run when `DJANGO_DEBUG` is off.

### Environment variables

See `.env.example` for the full list. Key ones:

| Variable | Purpose |
|---|---|
| `DJANGO_DEBUG` | `1` in development only |
| `DJANGO_SECRET_KEY` | required when debug is off |
| `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` | comma separated |
| `DB_ENGINE`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | MySQL connection |
| `DB_ROOT_PASSWORD` | MySQL container root password (compose only) |
| `REDIS_URL` | enables Redis cache/sessions; falls back to in-memory cache |
| `DJANGO_SERVE_MEDIA` | let Django serve `/media/` (dev / single-host installs) |
| `DJANGO_SECURE_SSL_REDIRECT`, `DJANGO_HSTS_SECONDS`, `DJANGO_SECURE_COOKIES` | HTTPS hardening |
| `LOGIN_RATE_LIMIT`, `LOGIN_RATE_WINDOW` | failed logins allowed per phone+IP per window |
| `STORE_SUPPORT_PHONE` | support number shown in the footer (hidden when empty) |
| `SEED_*` | development seed credentials |

### Running without Docker

```bash
uv venv -p 3.12 && uv pip install -r requirements.txt -r requirements-dev.txt   # mysqlclient needs libmysqlclient-dev
docker compose up -d db redis       # or any local MySQL 8
python manage.py migrate && python manage.py seed_dev_data && python manage.py runserver
```

Dependencies are pinned in `requirements.txt` / `requirements-dev.txt`, compiled from `requirements*.in`
(`uv pip compile -U requirements.in -o requirements.txt`).

## Migrations

Migrations are now **committed** (`apps/migrations/`); previously they were gitignored and generated on each
server, which makes schema history non-reproducible.

**One-time step on an existing server** that has its own locally generated migration files:

1. Back up the database.
2. Move the server's untracked `apps/migrations/0*.py` files out of the way (otherwise `git pull` refuses to
   overwrite them).
3. The new `0001_initial` describes a changed schema (new tables `ProductImage`, `Review`; new columns on
   `Product`, `Category`, `Order`; `Favorite` no longer has `name/slug`; corrected `created_at/updated_at`), so it
   cannot simply be faked against the old tables. On a **staging copy** of the production database:
   compare the live tables with `python manage.py sqlmigrate apps 0001`, apply the missing `ALTER TABLE`/`CREATE TABLE`
   statements, then record the migrations with `python manage.py migrate apps --fake` and verify with
   `python manage.py makemigrations --check`. Repeat on production only after staging works.

## Production deployment

Using the included compose file (recommended):

```bash
cp .env.example .env.prod      # then fill real values: DJANGO_DEBUG=0, secret key, hosts, DB credentials
docker compose -f compose.prod.yaml --env-file .env.prod up -d --build
```

- `web` runs gunicorn (3 workers) on 127.0.0.1:8000, migrates on start (`RUN_MIGRATIONS=1`), health-checked at
  `/healthz/`. Static files are hashed and served by WhiteNoise with far-future caching.
- Put nginx/Caddy with TLS in front and serve `/media/` from the `media_data` volume
  (or set `DJANGO_SERVE_MEDIA=1` for a small single host).
- Set `DJANGO_SECURE_SSL_REDIRECT=1` and `DJANGO_HSTS_SECONDS=31536000` once HTTPS works.
  `manage.py check --deploy` passes apart from the opt-in HSTS subdomain/preload warnings.

The existing GitHub workflow (`.github/workflows/cicd.yaml`) only runs `git pull` and restarts a systemd service.
With the new dependencies and committed migrations, the server also needs
`pip install -r requirements.txt && python manage.py migrate && python manage.py collectstatic --noinput`
on each deploy — update the workflow (or switch it to the compose stack) before the next push to `main`.

## Testing

```bash
make test
```

42 tests cover order placement and stock reservation, rollback on partial failure, stream pricing and payouts,
status-transition rules, single payout credit, restocking, exclusive operator claims, withdrawals, slug stability,
catalogue filters and search, cart → checkout → order, validation, quick orders, login (no silent auto-registration),
rate limiting, registration, POST-only logout/favourites, role-based access (403 for wrong roles), operator and
courier flows, data isolation between affiliates/customers, the admin dashboard and seed idempotency.

## Notes for the owner

- Storefront copy states policies (14-day returns, official warranty, 1–3 day delivery). Confirm these match the real
  business terms before going live.
- UI strings are Uzbek (Latin) and wrapped for translation, but the repository contains no `.po` files yet; run
  `make makemessage`, translate with Rosetta (`/rosetta/`, staff only) and `make compile`.
- Not implemented (the data model has no support yet): product variants (size/colour), multiple saved addresses
  (the profile keeps one default address that pre-fills checkout), online card payment (checkout is cash on
  delivery as before).
