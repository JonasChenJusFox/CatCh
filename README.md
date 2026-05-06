# CatCh

[![game-service](https://github.com/swe-students-spring2026/5-final-fish_likes_cat-1/actions/workflows/game-service.yml/badge.svg)](https://github.com/swe-students-spring2026/5-final-fish_likes_cat-1/actions/workflows/game-service.yml)
[![grader-service](https://github.com/swe-students-spring2026/5-final-fish_likes_cat-1/actions/workflows/grader-service.yml/badge.svg)](https://github.com/swe-students-spring2026/5-final-fish_likes_cat-1/actions/workflows/grader-service.yml)
[![auth-service](https://github.com/swe-students-spring2026/5-final-fish_likes_cat-1/actions/workflows/auth-service.yml/badge.svg)](https://github.com/swe-students-spring2026/5-final-fish_likes_cat-1/actions/workflows/auth-service.yml)
[![teacher-service](https://github.com/swe-students-spring2026/5-final-fish_likes_cat-1/actions/workflows/teacher-service.yml/badge.svg)](https://github.com/swe-students-spring2026/5-final-fish_likes_cat-1/actions/workflows/teacher-service.yml)
[![integration](https://github.com/swe-students-spring2026/5-final-fish_likes_cat-1/actions/workflows/integration.yml/badge.svg)](https://github.com/swe-students-spring2026/5-final-fish_likes_cat-1/actions/workflows/integration.yml)
[![frontend-app](https://github.com/swe-students-spring2026/5-final-fish_likes_cat-1/actions/workflows/frontend-app.yml/badge.svg)](https://github.com/swe-students-spring2026/5-final-fish_likes_cat-1/actions/workflows/frontend-app.yml)

CatCh is a gamified programming practice platform. Students (kittens) solve coding problems to earn fishing chances, then use those chances to catch fish from a pond. Common fish sell directly for tokens; uncommon and rarer fish can be listed on the marketplace, displayed in the aquarium, and used for collection leaderboards. Teachers (cats) create public or private ponds and manage coding problems without participating in the token economy.

## Live Deployment

Deployed on Digital Ocean: **[CatCh live app](https://catch-a8gtz.ondigitalocean.app)**

| Service | URL |
|---|---|
| Web app | [CatCh live app](https://catch-a8gtz.ondigitalocean.app) |
| game-service | [game-service API](https://catch-a8gtz.ondigitalocean.app/jonaschenjusfox-catch-game-servi) |
| grader-service | [grader-service API](https://catch-a8gtz.ondigitalocean.app/jonaschenjusfox-catch-grader-ser) |
| auth-service | [auth-service API](https://catch-a8gtz.ondigitalocean.app/jonaschenjusfox-catch-auth-servi) |
| teacher-service | [teacher-service API](https://catch-a8gtz.ondigitalocean.app/jonaschenjusfox-catch-teacher-se) |
| integration | [integration API](https://catch-a8gtz.ondigitalocean.app/jonaschenjusfox-catch-integration) |

## Team

| Name | GitHub |
|---|---|
| Celia Liang | [@liangchuxin](https://github.com/liangchuxin) |
| Grace Yin | [@gy28611](https://github.com/gy28611) |
| Hollan Yuan | [@hwyuanzi](https://github.com/hwyuanzi) |
| Jonas Chen | [@JonasChenJusFox](https://github.com/JonasChenJusFox) |
| Meili Liang | [@ml8397](https://github.com/ml8397) |

## Subsystems

| Subsystem | Role | Tech | Port | Image |
|---|---|---|---|---|
| `game-service` | Quiz, fishing, aquarium, marketplace, leaderboards, ponds | FastAPI, MongoDB | 8000 | [jonaschenjusfox/catch-game-service](https://hub.docker.com/r/jonaschenjusfox/catch-game-service) |
| `grader-service` | Sandboxed Python execution and unit-test grading | FastAPI | 8001 | [jonaschenjusfox/catch-grader-service](https://hub.docker.com/r/jonaschenjusfox/catch-grader-service) |
| `auth-service` | Username/password sign-up, login, password reset, logout, JWT issuance | FastAPI, MongoDB | 8002 | [jonaschenjusfox/catch-auth-service](https://hub.docker.com/r/jonaschenjusfox/catch-auth-service) |
| `teacher-service` | Cat-side pond and problem CRUD | FastAPI, MongoDB | 8003 | [jonaschenjusfox/catch-teacher-service](https://hub.docker.com/r/jonaschenjusfox/catch-teacher-service) |
| `integration` | Product-rule and integration health endpoints | FastAPI | 8004 | [jonaschenjusfox/catch-integration](https://hub.docker.com/r/jonaschenjusfox/catch-integration) |
| `frontend/app` | React web client served behind Nginx | React, Vite | 3000 | [jonaschenjusfox/catch-web-app](https://hub.docker.com/r/jonaschenjusfox/catch-web-app) |
| `mongo` | Shared database | MongoDB 7 | 27017 | [mongo](https://hub.docker.com/_/mongo) |

## Locally-run

```bash
git clone git@github.com:swe-students-spring2026/5-final-fish_likes_cat-1.git
cd 5-final-fish_likes_cat-1
cp .env.example .env
```

Edit `.env` and replace placeholder values such as `JWT_SECRET`,
`MONGO_URL`, `MONGO_INITDB_ROOT_PASSWORD`, and the `VITE_*` frontend API URLs
for your local or deployed environment. For local Docker testing, the frontend
URLs should point at `localhost` services:

```env
VITE_GAME_SERVICE_URL=http://localhost:8000
VITE_AUTH_SERVICE_URL=http://localhost:8002
VITE_TEACHER_SERVICE_URL=http://localhost:8003
VITE_INTEGRATION_SERVICE_URL=http://localhost:8004
```

Then build and run the full app:

```bash
docker compose up --build
```

Open the [local web app](http://localhost:3000).

The first screen supports three auth actions:

- `Sign Up` creates a kitten or cat account with username, email, and password.
- `Log In` signs in with username and password.
- `Forgot` resets the password after matching the username and email.

Passwords are hashed by auth-service before storage. The app no longer sends
email verification codes and does not require SMTP credentials.

Docker installs the service dependencies inside each image, so `pipenv install`
is not required for this Docker workflow.

To stop:

```bash
docker compose down       # keep mongo data
docker compose down -v    # also drop mongo volume
```

Requires Docker Desktop and Git. For local dev outside Docker you also need Python 3.12 + Pipenv + Node.js 20+.

## Environment Variables

Copy `.env.example` to `.env` before the first run. The committed `.env.example` ships placeholder values; the real `.env` for grading is delivered separately to course admins per the assignment's confidential-config policy.

| Variable | Used By | Purpose |
|---|---|---|
| `JWT_SECRET`, `JWT_ALGORITHM`, `JWT_EXPIRY_HOURS` | auth-service | JWT signing |
| `PASSWORD_HASH_ITERATIONS` | auth-service | Optional PBKDF2 iteration count for stored password hashes; defaults to `210000` |
| `GRADER_SERVICE_URL`, `GAME_SERVICE_URL`, `TEACHER_SERVICE_URL`, `AUTH_SERVICE_URL`, `FRONTEND_URL` | every service | Inter-service URLs (Digital Ocean in production, localhost in dev) |
| `VITE_GAME_SERVICE_URL`, `VITE_AUTH_SERVICE_URL`, `VITE_TEACHER_SERVICE_URL`, `VITE_INTEGRATION_SERVICE_URL` | frontend/app | API URLs embedded into the React build |
| `GAME_SERVICE_PORT` | game-service | Port game-service listens on |
| `DB_BACKEND` | game-service | `mongo` for full demo, `mock` for in-memory smoke tests |
| `MONGO_URL`, `MONGO_DB` | game-service, auth-service, teacher-service | MongoDB connection string and database name |
| `MONGO_INITDB_ROOT_PASSWORD` | mongo | Root password for the bundled mongo container |
| `ALLOWED_ORIGINS` | every backend | Comma-separated CORS allow-list |
| `GRADER_TIMEOUT_SECONDS` | grader-service | Wall-clock timeout per `/grade` request |
| `WEB_APP_PORT` | frontend/app | Host port mapped to the Nginx container |
| `LOG_LEVEL` | every backend | Python log level |

Old `.env` files may still contain `SMTP_SERVER`, `SMTP_PORT`, `SENDER_EMAIL`,
`SENDER_PASSWORD`, or `AUTH_DEMO_MODE`. Those values are ignored by the current
auth-service and can be removed.

If Mongo was previously started with a different root password, reset the local
volume before rebuilding:

```bash
docker compose down -v
docker compose up --build
```

## Auth API

Auth-service exposes username/password endpoints:

| Endpoint | Purpose |
|---|---|
| `POST /auth/signup` | Create a kitten or cat account and return a JWT |
| `POST /auth/login` | Sign in with username and password |
| `POST /auth/forgot-password` | Reset a password when username and email match |
| `POST /auth/logout` | Acknowledge client-side sign-out |
| `POST /auth/verify-token` | Validate an existing JWT |
| `POST /auth/refresh-token` | Refresh a valid JWT |

Example signup:

```bash
curl -X POST http://localhost:8002/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"username":"JJ","email":"jj@example.com","password":"password123","role":"cat"}'
```

Example login:

```bash
curl -X POST http://localhost:8002/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"JJ","password":"password123"}'
```

JWTs carry the user's `user_id`, `username`, `email`, `role`, permissions, and
expiration. Username/password proves identity at login time; the JWT carries
that identity to the rest of the app after login.

## Starter Data

Committed at `data/`:

- `judgeable_problems.json` — 74 coding problems with starter code, hidden tests, and reference solutions
- `fish_species.json` — 50 fish species with rarity, prices, sell values
- `fish_images/` — fish PNGs served at `/fish_images/<species_id>.png`

When `DB_BACKEND=mongo` and the `problems` or `fish_species` collection is empty, game-service auto-seeds from these files on startup. To force a re-seed:

```bash
docker compose down -v
docker compose up --build
```

## Local Development

Use this path only when running services directly on your machine instead of
through Docker. Each backend service runs the same way from its own directory:

```bash
cd <service-name>
pipenv install --dev
pipenv run uvicorn app.main:app --reload --port <port>
```

Frontend:

```bash
cd frontend/app
npm install
npm run dev    # local Vite dev server
```

The [local Vite dev server](http://localhost:5173) is only for development. The
deployed web app runs at [CatCh live app](https://catch-a8gtz.ondigitalocean.app).

## Testing

Each Python subsystem must hit 80% coverage in CI:

```bash
cd <service-name>
pipenv run python -m black --check .
pipenv run python -m pylint app tests
pipenv run pytest --cov=app --cov-report=term-missing --cov-fail-under=80
```

Frontend build check:

```bash
cd frontend/app && npm run build
```

For the focused auth-service checks:

```bash
cd auth-service
pipenv run pytest tests/test_auth.py
pipenv run python -m black --check app tests
pipenv run python -m pylint app tests
```

