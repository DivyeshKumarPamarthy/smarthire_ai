"""
Module 10, Slices 3-6 — the recruiter and admin surfaces, over real HTTP.

These tests exist to enforce decisions, not to exercise arithmetic. The
arithmetic is covered by the pure unit tests; what can only be checked here is
whether a role actually receives what the visibility table says it may, and
whether the binding constraints on comparison hold against a real request.
"""

import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE = "http://127.0.0.1:8000/api"

ACCOUNTS = {
    "candidate": ("candidate.demo@smarthire.dev", "Candidate@123"),
    "recruiter": ("recruiter.demo@smarthire.dev", "Recruiter@123"),
    "admin": ("admin.demo@smarthire.dev", "Admin@123"),
}


def token(role: str) -> str:
    email, password = ACCOUNTS[role]
    response = requests.post(
        f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=20
    )
    response.raise_for_status()
    return response.json()["access_token"]


def auth(role: str) -> dict:
    return {"Authorization": f"Bearer {token(role)}"}


@pytest.fixture(scope="module")
def recruiter():
    return auth("recruiter")


@pytest.fixture(scope="module")
def candidate_id(recruiter):
    rows = requests.get(
        f"{BASE}/analytics/recruiter/candidates", headers=recruiter, timeout=30
    ).json()
    assert rows, "no candidates in the database to test against"
    return rows[0]["user_id"]


class TestRecruiterCandidatePerformance:
    def test_recruiter_can_read_a_candidates_performance(self, recruiter, candidate_id):
        r = requests.get(
            f"{BASE}/analytics/recruiter/candidates/{candidate_id}/performance",
            headers=recruiter, timeout=30,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["user_id"] == candidate_id
        assert "skills" in body and "trend" in body

    def test_practice_recommendations_are_not_in_the_recruiter_payload(
        self, recruiter, candidate_id
    ):
        """
        The visibility decision, enforced rather than documented. Coaching
        addressed to the candidate must not reach a recruiter: the weakness is
        shown as a number, and a number carries its uncertainty in a way a
        prescription does not.
        """
        body = requests.get(
            f"{BASE}/analytics/recruiter/candidates/{candidate_id}/performance",
            headers=recruiter, timeout=30,
        ).json()
        assert "practice_recommendations" not in (body.get("weak_areas") or {})
        assert "practice_recommendations" not in repr(body)

    def test_learning_resources_are_not_in_the_recruiter_payload(
        self, recruiter, candidate_id
    ):
        body = requests.get(
            f"{BASE}/analytics/recruiter/candidates/{candidate_id}/performance",
            headers=recruiter, timeout=30,
        ).json()
        assert "learning_resources" not in (body.get("weak_areas") or {})
        assert "learning_resources" not in repr(body)

    def test_the_weakness_itself_is_still_shown(self, recruiter, candidate_id):
        """Withholding the advice must not mean withholding the evidence."""
        weak = requests.get(
            f"{BASE}/analytics/recruiter/candidates/{candidate_id}/performance",
            headers=recruiter, timeout=30,
        ).json()["weak_areas"]
        if weak.get("available"):
            assert "weakest_axis" in weak
            assert "graded_answers" in weak

    def test_a_candidate_cannot_read_another_candidates_performance(self, candidate_id):
        r = requests.get(
            f"{BASE}/analytics/recruiter/candidates/{candidate_id}/performance",
            headers=auth("candidate"), timeout=30,
        )
        assert r.status_code == 403

    def test_unknown_candidate_is_404(self, recruiter):
        r = requests.get(
            f"{BASE}/analytics/recruiter/candidates/99999999/performance",
            headers=recruiter, timeout=30,
        )
        assert r.status_code == 404


class TestNoModuleSixLeaks:
    """
    Module 6 is measured in the candidate's own browser and is therefore
    forgeable. It may sit beside one interview being read; it may never feed a
    surface that compares people.
    """

    FORBIDDEN = (
        "eye_contact", "gaze", "expression", "emotion",
        "confidence_percent", "look_aways", "engagement", "behavior",
    )

    def test_no_module_6_field_reaches_the_recruiter_performance_view(
        self, recruiter, candidate_id
    ):
        blob = repr(requests.get(
            f"{BASE}/analytics/recruiter/candidates/{candidate_id}/performance",
            headers=recruiter, timeout=30,
        ).json()).lower()
        for field in self.FORBIDDEN:
            assert field not in blob, field

    def test_no_module_6_field_reaches_comparison(self, recruiter, candidate_id):
        ids = [r["user_id"] for r in requests.get(
            f"{BASE}/analytics/recruiter/candidates", headers=recruiter, timeout=30
        ).json()][:2]
        if len(ids) < 2:
            pytest.skip("needs two candidates")
        blob = repr(requests.get(
            f"{BASE}/analytics/recruiter/compare",
            params={"user_ids": ",".join(map(str, ids))},
            headers=recruiter, timeout=30,
        ).json()).lower()
        for field in self.FORBIDDEN:
            assert field not in blob, field

    def test_no_module_6_field_reaches_shortlist_insights(self, recruiter):
        blob = repr(requests.get(
            f"{BASE}/analytics/recruiter/shortlist-insights",
            headers=recruiter, timeout=60,
        ).json()).lower()
        for field in self.FORBIDDEN:
            assert field not in blob, field


class TestComparisonBindingDecisions:
    """Gate 2's two binding additions, enforced server-side."""

    @pytest.fixture(scope="class")
    def ids(self, recruiter):
        rows = requests.get(
            f"{BASE}/analytics/recruiter/candidates", headers=recruiter, timeout=30
        ).json()
        if len(rows) < 2:
            pytest.skip("needs at least two candidates")
        return [r["user_id"] for r in rows[:3]]

    def test_compare_rejects_one_candidate(self, recruiter, ids):
        """One is not a comparison; it is the single view with new framing."""
        r = requests.get(
            f"{BASE}/analytics/recruiter/compare",
            params={"user_ids": str(ids[0])}, headers=recruiter, timeout=30,
        )
        assert r.status_code == 400

    def test_compare_rejects_five_candidates(self, recruiter, ids):
        r = requests.get(
            f"{BASE}/analytics/recruiter/compare",
            params={"user_ids": ",".join(str(i) for i in (ids * 3)[:5])},
            headers=recruiter, timeout=30,
        )
        assert r.status_code == 400

    def test_compare_preserves_selection_order(self, recruiter, ids):
        """
        Binding: the interface must not rank people on a recruiter's behalf.
        Requested order is returned order, whatever the scores say.
        """
        if len(ids) < 3:
            pytest.skip("needs three candidates")
        wanted = [ids[2], ids[0], ids[1]]
        body = requests.get(
            f"{BASE}/analytics/recruiter/compare",
            params={"user_ids": ",".join(map(str, wanted))},
            headers=recruiter, timeout=30,
        ).json()
        assert [c["user_id"] for c in body["candidates"]] == wanted

    def test_compare_exposes_no_sort_parameter(self, recruiter, ids):
        """A sort= query must be inert, not honoured."""
        wanted = [ids[1], ids[0]]
        body = requests.get(
            f"{BASE}/analytics/recruiter/compare",
            params={"user_ids": ",".join(map(str, wanted)), "sort": "score"},
            headers=recruiter, timeout=30,
        ).json()
        assert [c["user_id"] for c in body["candidates"]] == wanted

    def test_response_carries_no_rank_or_position(self, recruiter, ids):
        """
        Nothing in the *data* may be used to order candidates.

        The explanatory note is excluded from this scan on purpose: it contains
        the word "rank" precisely because it denies ranking, and an earlier
        version of this test failed on its own disclaimer.
        """
        body = requests.get(
            f"{BASE}/analytics/recruiter/compare",
            params={"user_ids": ",".join(map(str, ids[:2]))},
            headers=recruiter, timeout=30,
        ).json()

        data = {k: v for k, v in body.items() if k != "note"}
        blob = repr(data).lower()
        for word in ("rank", "position", "placing", "score_order"):
            assert word not in blob, f"{word!r} present in comparison data"

        # And the note must actually say so.
        assert "does not rank" in body["note"].lower()
        assert "cannot be sorted" in body["note"].lower()

    def test_every_comparison_cell_carries_answers_graded_and_provisional(
        self, recruiter, ids
    ):
        """
        Binding, and a fairness requirement rather than a courtesy: side by
        side, a candidate with one graded answer must not read as equivalent to
        one with twelve.
        """
        body = requests.get(
            f"{BASE}/analytics/recruiter/compare",
            params={"user_ids": ",".join(map(str, ids[:2]))},
            headers=recruiter, timeout=30,
        ).json()
        assert body["candidates"]
        for entry in body["candidates"]:
            assert entry["cells"]
            for cell in entry["cells"]:
                assert "answers_graded" in cell
                assert isinstance(cell["provisional"], bool)

    def test_compare_rejects_nonsense_ids(self, recruiter):
        r = requests.get(
            f"{BASE}/analytics/recruiter/compare",
            params={"user_ids": "abc,def"}, headers=recruiter, timeout=30,
        )
        assert r.status_code == 400


class TestShortlistInsights:
    def test_every_insight_over_http_carries_evidence(self, recruiter):
        body = requests.get(
            f"{BASE}/analytics/recruiter/shortlist-insights",
            headers=recruiter, timeout=60,
        ).json()
        for insight in body["insights"]:
            assert insight["evidence"].strip()

    def test_the_note_disclaims_a_recommendation(self, recruiter):
        body = requests.get(
            f"{BASE}/analytics/recruiter/shortlist-insights",
            headers=recruiter, timeout=60,
        ).json()
        assert "not a recommendation" in body["note"].lower()

    def test_candidates_cannot_read_shortlist_insights(self):
        r = requests.get(
            f"{BASE}/analytics/recruiter/shortlist-insights",
            headers=auth("candidate"), timeout=30,
        )
        assert r.status_code == 403


class TestAdminAIMonitoring:
    def test_admin_can_read_ai_monitoring(self):
        r = requests.get(f"{BASE}/analytics/admin/ai", headers=auth("admin"), timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert "total_calls" in body
        assert "quota_failures" in body
        assert "window_start" in body

    def test_the_window_is_labelled_as_since_restart_not_uptime(self):
        body = requests.get(
            f"{BASE}/analytics/admin/ai", headers=auth("admin"), timeout=30
        ).json()
        assert "restart" in body["note"].lower()
        assert "uptime" not in body["note"].lower().replace("not uptime", "")

    def test_recruiters_cannot_read_ai_monitoring(self, recruiter):
        r = requests.get(f"{BASE}/analytics/admin/ai", headers=recruiter, timeout=30)
        assert r.status_code == 403

    def test_no_candidate_identity_in_the_monitoring_payload(self):
        """
        Operational data only. An admin debugging a spent quota needs the count
        and the operation, not whose interview it was.
        """
        blob = repr(requests.get(
            f"{BASE}/analytics/admin/ai", headers=auth("admin"), timeout=30
        ).json()).lower()
        for field in ("candidate", "user_id", "email", "transcript", "prompt"):
            assert field not in blob, field
