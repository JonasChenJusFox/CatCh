# CatCh

[![game-service](https://github.com/swe-students-spring2026/5-final-fish_likes_cat-1/actions/workflows/game-service.yml/badge.svg)](https://github.com/swe-students-spring2026/5-final-fish_likes_cat-1/actions/workflows/game-service.yml)
[![grader-service](https://github.com/swe-students-spring2026/5-final-fish_likes_cat-1/actions/workflows/grader-service.yml/badge.svg)](https://github.com/swe-students-spring2026/5-final-fish_likes_cat-1/actions/workflows/grader-service.yml)
[![auth-service](https://github.com/swe-students-spring2026/5-final-fish_likes_cat-1/actions/workflows/auth-service.yml/badge.svg)](https://github.com/swe-students-spring2026/5-final-fish_likes_cat-1/actions/workflows/auth-service.yml)
[![teacher-service](https://github.com/swe-students-spring2026/5-final-fish_likes_cat-1/actions/workflows/teacher-service.yml/badge.svg)](https://github.com/swe-students-spring2026/5-final-fish_likes_cat-1/actions/workflows/teacher-service.yml)
[![integration](https://github.com/swe-students-spring2026/5-final-fish_likes_cat-1/actions/workflows/integration.yml/badge.svg)](https://github.com/swe-students-spring2026/5-final-fish_likes_cat-1/actions/workflows/integration.yml)
[![frontend-app](https://github.com/swe-students-spring2026/5-final-fish_likes_cat-1/actions/workflows/frontend-app.yml/badge.svg)](https://github.com/swe-students-spring2026/5-final-fish_likes_cat-1/actions/workflows/frontend-app.yml)

CatCh is a gamified programming practice platform. Students (kittens) solve coding problems to earn fishing chances, then cast fishing chances to catch fish from a pond. Common fish sell directly for tokens; rarer fish go on the marketplace, fill the medal wall, and drive the leaderboards. Teachers (cats) create public or private ponds and write the coding problems inside them, earning fishing chances per problem authored.

## Live Deployment

Deployed on Digital Ocean: **https://catch-a8gtz.ondigitalocean.app**

| Service | URL |
|---|---|
| Web app | https://catch-a8gtz.ondigitalocean.app |
| game-service | [https://catch-a8gtz.ondigitalocean.app/jonaschenjusfox-catch-game-service](https://catch-a8gtz.ondigitalocean.app/jonaschenjusfox-catch-game-service) |
| grader-service | [https://catch-a8gtz.ondigitalocean.app/jonaschenjusfox-catch-grader-service](https://catch-a8gtz.ondigitalocean.app/jonaschenjusfox-catch-grader-service) |
| auth-service | [https://catch-a8gtz.ondigitalocean.app/jonaschenjusfox-catch-auth-service](https://catch-a8gtz.ondigitalocean.app/jonaschenjusfox-catch-auth-service) |
| teacher-service | [https://catch-a8gtz.ondigitalocean.app/jonaschenjusfox-catch-teacher-service](https://catch-a8gtz.ondigitalocean.app/jonaschenjusfox-catch-teacher-service) |

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
| `auth-service` | Email verification, role-aware sign-in, JWT issuance | FastAPI, MongoDB | 8002 | [jonaschenjusfox/catch-auth-service](https://hub.docker.com/r/jonaschenjusfox/catch-auth-service) |
| `teacher-service` | Cat-side pond and problem CRUD | FastAPI, MongoDB | 8003 | [jonaschenjusfox/catch-teacher-service](https://hub.docker.com/r/jonaschenjusfox/catch-teacher-service) |
| `integration` | Product-rule and integration health endpoints | FastAPI | 8004 | [jonaschenjusfox/catch-integration](https://hub.docker.com/r/jonaschenjusfox/catch-integration) |
| `frontend/app` | React web client served behind Nginx | React, Vite | 3000 | [jonaschenjusfox/catch-frontend](https://hub.docker.com/r/jonaschenjusfox/catch-frontend) |
| `mongo` | Shared database | MongoDB 7 | 27017 | [mongo](https://hub.docker.com/_/mongo) |

## Run

```bash
git clone https://github.com/swe-students-spring2026/5-final-fish_likes_cat-1.git
cd 5-final-fish_likes_cat-1
cp .env.example .env
docker compose up --build
```

Open http://localhost:3000.

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
| `SMTP_SERVER`, `SMTP_PORT` | auth-service | SMTP host and port for verification email |
| `SENDER_EMAIL`, `SENDER_PASSWORD` | auth-service | Mailbox that sends verification codes |
| `AUTH_DEMO_MODE` | auth-service | When `true`, the verification code is returned in the API response (no email sent) |
| `JWT_SECRET`, `JWT_ALGORITHM`, `JWT_EXPIRY_HOURS` | auth-service | JWT signing |
| `GRADER_SERVICE_URL`, `GAME_SERVICE_URL`, `TEACHER_SERVICE_URL`, `AUTH_SERVICE_URL`, `FRONTEND_URL` | every service | Inter-service URLs (Digital Ocean in production, localhost in dev) |
| `GAME_SERVICE_PORT` | game-service | Port game-service listens on |
| `DB_BACKEND` | game-service | `mongo` for full demo, `mock` for in-memory smoke tests |
| `MONGO_URL`, `MONGO_DB` | game-service, auth-service, teacher-service | MongoDB connection string and database name |
| `MONGO_INITDB_ROOT_PASSWORD` | mongo | Root password for the bundled mongo container |
| `ALLOWED_ORIGINS` | every backend | Comma-separated CORS allow-list |
| `GRADER_TIMEOUT_SECONDS` | grader-service | Wall-clock timeout per `/grade` request |
| `WEB_APP_PORT` | frontend/app | Host port mapped to the Nginx container |
| `LOG_LEVEL` | every backend | Python log level |

## Starter Data

Committed at `data/`:

- `judgeable_problems.json` — 79 coding problems with starter code, hidden tests, and reference solutions
- `fish_species.json` — 50 fish species with rarity, prices, sell values
- `fish_images/` — fish PNGs served at `/fish_images/<species_id>.png`

When `DB_BACKEND=mongo` and the `problems` or `fish_species` collection is empty, game-service auto-seeds from these files on startup. To force a re-seed:

```bash
docker compose down -v
docker compose up --build
```

## Local Development

Each backend service runs the same way from its own directory:

```bash
cd <service-name>
pipenv install --dev
pipenv run uvicorn app.main:app --reload --port <port>
```

Frontend:

```bash
cd frontend/app
npm install
npm run dev    # http://localhost:5173
```

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
