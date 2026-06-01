from app.db.mock_repo import MockRepository


def test_seeds_loaded():
    repo = MockRepository.get_instance()
    problems = repo.list_problems()
    assert len(problems) == 74
    ids = {p["id"] for p in problems}
    assert {"problem-1", "problem-3", "problem-121"}.issubset(ids)


def test_get_problem_returns_none_for_missing():
    repo = MockRepository.get_instance()
    assert repo.get_problem("does-not-exist") is None


def test_get_problem_returns_full_record():
    repo = MockRepository.get_instance()
    p = repo.get_problem("problem-1")
    assert p is not None
    assert p["function_name"] == "two_sum"
    assert "test_code" in p
    assert "starter_code" in p


def test_fishing_chances_default_zero():
    repo = MockRepository.get_instance()
    assert repo.get_fishing_chances("anyone") == 0


def test_add_fishing_chances_accumulates():
    repo = MockRepository.get_instance()
    assert repo.add_fishing_chances("u1", 1) == 1
    assert repo.add_fishing_chances("u1", 2) == 3
    assert repo.get_fishing_chances("u1") == 3
    assert repo.get_fishing_chances("u2") == 0


def test_record_submission_returns_id():
    repo = MockRepository.get_instance()
    sub_id = repo.record_submission("u1", "problem-1", True, "code")
    assert isinstance(sub_id, str)
    assert len(sub_id) > 0


def test_list_submissions_filters_by_user():
    repo = MockRepository.get_instance()
    repo.record_submission("u1", "problem-1", True, "code1")
    repo.record_submission("u2", "problem-1", False, "code2")
    repo.record_submission("u1", "problem-3", True, "code3")

    u1_subs = repo.list_submissions("u1")
    assert len(u1_subs) == 2
    assert all(s["user_id"] == "u1" for s in u1_subs)


def test_singleton_returns_same_instance():
    a = MockRepository.get_instance()
    b = MockRepository.get_instance()
    assert a is b


def test_user_roles_and_seen_kittens_are_tracked():
    repo = MockRepository.get_instance()
    repo.set_user_role("teacher-1", "cat")
    repo.add_tokens("kitten-1", 3)
    repo.add_fishing_chances("kitten-2", 1)

    assert repo.get_user_role("unknown") == "kitten"
    assert repo.list_user_ids_by_role("cat") == ["teacher-1"]
    kittens = repo.list_user_ids_by_role("kitten")
    assert "kitten-1" in kittens
    assert "kitten-2" in kittens
    assert "teacher-1" not in kittens


def test_invalid_user_role_is_rejected():
    repo = MockRepository.get_instance()
    try:
        repo.set_user_role("user-1", "dog")
    except ValueError as exc:
        assert "unknown role" in str(exc)
        return
    assert False, "expected role validation error"


def test_duplicate_uncaught_problem_is_not_added_twice():
    repo = MockRepository.get_instance()
    problem = repo.get_problem("problem-1")
    assert repo.add_uncaught_problem("kitten-1", problem, 5) is True
    assert repo.add_uncaught_problem("kitten-1", problem, 5) is False


def test_reset_instance_clears_state():
    repo = MockRepository.get_instance()
    repo.add_fishing_chances("u1", 5)
    MockRepository.reset_instance()
    fresh = MockRepository.get_instance()
    assert fresh.get_fishing_chances("u1") == 0
