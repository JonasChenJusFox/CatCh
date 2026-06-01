from unittest.mock import AsyncMock, patch

import httpx

EASY_PROBLEM_ID = "problem-1"
MEDIUM_PROBLEM_ID = "problem-3"
PASSING_CODE = "def two_sum(nums, target): return [0, 1]"

# --- GET /quiz/problems ---


def test_list_problems(client):
    resp = client.get("/quiz/problems")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 74
    for p in data:
        assert set(p.keys()) == {
            "id",
            "title",
            "difficulty",
            "fishing_reward",
            "completed",
            "exhausted",
            "attempts_used",
        }


def test_list_problems_does_not_expose_test_code(client):
    resp = client.get("/quiz/problems")
    assert resp.status_code == 200
    for p in resp.json():
        assert "test_code" not in p
        assert "starter_code" not in p


# --- GET /quiz/problems/{id} ---


def test_get_problem_404_for_missing(client):
    resp = client.get("/quiz/problems/does-not-exist")
    assert resp.status_code == 404


def test_get_problem_returns_starter_and_instructions(client):
    resp = client.get(f"/quiz/problems/{EASY_PROBLEM_ID}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == EASY_PROBLEM_ID
    assert data["function_name"] == "two_sum"
    assert "two_sum" in data["starter_code"]
    assert "array" in data["instructions"].lower()


def test_get_problem_does_not_expose_test_code(client):
    resp = client.get(f"/quiz/problems/{EASY_PROBLEM_ID}")
    assert "test_code" not in resp.json()


# --- POST /quiz/problems/{id}/submit ---


@patch("app.routers.quiz.grader_client", new_callable=lambda: AsyncMock())
def test_submit_passes_grants_fishing_reward(mock_grader, client):
    mock_grader.grade.return_value = {
        "passed": True,
        "tests_run": 9,
        "tests_passed": 9,
    }

    resp = client.post(
        f"/quiz/problems/{EASY_PROBLEM_ID}/submit",
        json={"code": PASSING_CODE, "user_id": "u1"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["passed"] is True
    assert data["fishing_reward_granted"] == 1
    assert data["new_fishing_chances"] == 1


@patch("app.routers.quiz.grader_client", new_callable=lambda: AsyncMock())
def test_submit_accumulates_fishing_chances(mock_grader, client):
    mock_grader.grade.return_value = {"passed": True, "tests_run": 9, "tests_passed": 9}

    client.post(
        f"/quiz/problems/{EASY_PROBLEM_ID}/submit",
        json={"code": PASSING_CODE, "user_id": "u1"},
    )
    resp = client.post(
        f"/quiz/problems/{MEDIUM_PROBLEM_ID}/submit",
        json={"code": "def length_of_longest_substring(s): return 3", "user_id": "u1"},
    )
    assert resp.status_code == 200
    assert resp.json()["new_fishing_chances"] == 3  # 1 + 2


@patch("app.routers.quiz.grader_client", new_callable=lambda: AsyncMock())
def test_submit_fails_no_reward(mock_grader, client):
    mock_grader.grade.return_value = {
        "passed": False,
        "tests_run": 9,
        "tests_passed": 3,
        "failed_test": "test_example_one",
    }

    resp = client.post(
        f"/quiz/problems/{EASY_PROBLEM_ID}/submit",
        json={"code": PASSING_CODE},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["passed"] is False
    assert data["fishing_reward_granted"] == 0
    assert data["new_fishing_chances"] is None
    assert data["failed_test"] == "test_example_one"
    assert data["solution_revealed"] is False


@patch("app.routers.quiz.grader_client", new_callable=lambda: AsyncMock())
def test_submit_reveals_solution_after_five_failed_attempts(mock_grader, client):
    mock_grader.grade.return_value = {
        "passed": False,
        "tests_run": 9,
        "tests_passed": 0,
        "failed_test": "test_example_one",
    }

    final_response = None
    for _ in range(5):
        final_response = client.post(
            f"/quiz/problems/{EASY_PROBLEM_ID}/submit",
            json={"code": PASSING_CODE, "user_id": "u2"},
        )

    assert final_response is not None
    assert final_response.status_code == 200
    data = final_response.json()
    assert data["passed"] is False
    assert data["attempts_used"] == 5
    assert data["attempts_remaining"] == 0
    assert data["solution_revealed"] is True
    assert "def two_sum" in data["solution_code"]
    assert data["added_to_uncaught_fish"] is True
    assert data["tokens_lost"] == 1

    uncaught = client.get("/quiz/uncaught/u2")
    assert uncaught.status_code == 200
    saved_problem = uncaught.json()[0]
    assert saved_problem["problem_id"] == EASY_PROBLEM_ID
    assert saved_problem["instructions"]


def test_submit_404_for_missing_problem(client):
    resp = client.post(
        "/quiz/problems/does-not-exist/submit",
        json={"code": "x = 1"},
    )
    assert resp.status_code == 404


@patch("app.routers.quiz.grader_client", new_callable=lambda: AsyncMock())
def test_submit_502_when_grader_unreachable(mock_grader, client):
    mock_grader.grade.side_effect = httpx.ConnectError("connection refused")

    resp = client.post(
        f"/quiz/problems/{EASY_PROBLEM_ID}/submit",
        json={"code": "x = 1"},
    )
    assert resp.status_code == 502


def test_submit_rejects_empty_code(client):
    resp = client.post(
        f"/quiz/problems/{EASY_PROBLEM_ID}/submit",
        json={"code": ""},
    )
    # Pydantic min_length=1 should reject this with 422
    assert resp.status_code == 422


@patch("app.routers.quiz.grader_client", new_callable=lambda: AsyncMock())
def test_reset_quiz_attempts_makes_problem_replayable(mock_grader, client):
    mock_grader.grade.return_value = {"passed": True, "tests_run": 1, "tests_passed": 1}

    first_response = client.post(
        f"/quiz/problems/{EASY_PROBLEM_ID}/submit",
        json={"code": PASSING_CODE, "user_id": "replay_user"},
    )
    assert first_response.status_code == 200

    duplicate_response = client.post(
        f"/quiz/problems/{EASY_PROBLEM_ID}/submit",
        json={"code": PASSING_CODE, "user_id": "replay_user"},
    )
    assert duplicate_response.status_code == 409

    reset_response = client.post(
        "/quiz/reset",
        json={"user_id": "replay_user", "problem_ids": [EASY_PROBLEM_ID]},
    )
    assert reset_response.status_code == 200

    replay_response = client.post(
        f"/quiz/problems/{EASY_PROBLEM_ID}/submit",
        json={"code": PASSING_CODE, "user_id": "replay_user"},
    )
    assert replay_response.status_code == 200


# --- /health ---


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
