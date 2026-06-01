# game-service

Backend service for quiz, fishing, market and leaderboard.

This service is the main business logic layer. It does not run student code itself; that's the job of `grader-service`. game-service handles HTTP routing, repository access (Mongo or in-memory mock), and orchestration.

## Status

- [x] FastAPI skeleton with CORS
- [x] Quiz routes with 5-attempt limit, solution reveal, Uncaught Fish history
- [x] In-memory mock repository, seeded from `data/judgeable_problems.json`
- [x] grader-service HTTP client
- [x] Fishing, market, aquarium, and leaderboard routers
- [x] pytest suite (target ≥ 80% coverage)
- [ ] Mongo repository (phase 2, owned by DB teammate)
- [ ] JWT auth (phase 3, after auth-service exists)

## Run locally

```bash
cd game-service
pipenv install --dev

cp .env.example .env  # adjust if needed
pipenv run uvicorn app.main:app --reload --port 8000
```

Visit http://localhost:8000/docs for interactive API docs.

For the `/quiz/problems/{id}/submit` endpoint to actually grade code, `grader-service` must also be running on the URL specified by `GRADER_SERVICE_URL` (default http://localhost:8001).

## Run tests

```bash
pytest --cov=app --cov-report=term-missing
```

Tests use `httpx.MockTransport` and `unittest.mock` to avoid hitting real grader-service or mongo.

## Repository abstraction

All persistence goes through `app/db/repository.py`, a `Protocol` interface. Two implementations:

- `MockRepository` (`app/db/mock_repo.py`) — in-memory dict, loads `data/judgeable_problems.json`. Used in local development and tests.
- `MongoRepository` (`app/db/mongo_repo.py`) — MongoDB implementation used by Docker Compose and deployed environments.

Switch via env var: `DB_BACKEND=mock` or `DB_BACKEND=mongo`.

## Problem dataset

Runtime problems come from `data/judgeable_problems.json`. The committed dataset contains 74 executable coding-practice entries. Each judgeable entry contains:

- `id`, `title`, `difficulty`, `fishing_reward`
- `function_name` — the function the student must implement
- `instructions` — markdown problem statement
- `starter_code` — initial template shown to the student
- `test_code` — `unittest.TestCase` class definition (server-side only, never returned via API)
- `solution_code` — revealed only after the configured attempt limit
- `max_attempts` — defaults to 5
- `source`, `source_url` — attribution

When a student submits, game-service sends `{student_code, test_code}` to grader-service, which assembles them into a runnable script and reports pass/fail. game-service grants `fishing_reward` chances on pass. After five failed attempts, game-service reveals `solution_code`, records the problem in `/quiz/uncaught/{user_id}`, and removes 1 Cat Can Token.

## Contracts with other services

**grader-service** (HTTP, internal):
- `POST /grade` with `{language, student_code, test_code}` — returns `{passed, tests_run, tests_passed, failed_test, error_message}`

**auth-service** (HTTP, planned):
- game-service expects an `Authorization: Bearer <jwt>` header on writeable routes (phase 3)
- For phase 1, `user_id` is taken from the request body and defaults to `"demo_user"`

**mongo** (TCP, planned):
- Connection via `MONGO_URL` env var
- Database name from `MONGO_DB` env var
- Collections: `problems`, `users`, `submissions`, `fishing_chances`, `inventory`, `market_listings`, `tokens`, `uncaught_problems` (Mongo schema to be finalized in phase 2)
