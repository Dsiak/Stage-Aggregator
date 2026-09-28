from datetime import date, timedelta
import pytest
from aggregator.config import Config
from aggregator.filtering import filter_reason
from aggregator.models import Evaluation, normalize
from aggregator.pipeline import run_pipeline
from aggregator.evaluation import RulesEvaluator
from aggregator.sources import parse_remotive
from aggregator.notify import notify_pending

PROFILE = "Python FastAPI SQL Git pytest backend"


@pytest.mark.parametrize("change,fragment", [
    ({"location": "USA"}, "Localisation"),
    ({"description": "Unpaid Python internship"}, "Non rémunéré"),
    ({"published_on": date.today()-timedelta(days=40)}, "Date"),
    ({"published_on": date.today()+timedelta(days=1)}, "Date"),
    ({"title": "Sales", "description": "Sales manager"}, "Pas de stage"),
    ({"title": "Stage marketing", "description": "Stage en publicité"}, "mot-clé"),
])
def test_filters(offer, change, fragment):
    assert fragment in filter_reason(offer.model_copy(update=change), Config())


def test_matching_offer(offer):
    assert filter_reason(offer, Config()) is None
    assert normalize("  DÉVELOPPEMENT  Python ") == "developpement python"


def test_duplicate_fingerprint(offer, state):
    variant = offer.model_copy(update={"source_id": "2", "title": " STAGE  PYTHON BACKEND "})
    assert variant.fingerprint == offer.fingerprint
    state.add(offer)
    state.add(variant)
    assert len(state.pending()) == 1


def test_html_collection_and_invalid_rows():
    payload = {"jobs": [{"id": 1, "title": "Stage", "company_name": "X", "candidate_required_location": "Canada",
                         "publication_date": "2026-01-01T12:00:00Z", "url": "https://example.com",
                         "description": "<p>Python <strong>SQL</strong></p>"}, {"id": 2}]}
    offers, invalid = parse_remotive(payload)
    assert offers[0].description == "Python SQL" and invalid == 1
    with pytest.raises(ValueError):
        parse_remotive({"unexpected": []})
    with pytest.raises(ValueError):
        parse_remotive({"jobs": [{"id": 2}]})


class TrackerStub:
    def __init__(self):
        self.imports = 0
        self.items = {}
    def find_application(self, external_id):
        return self.items.get(external_id)
    def import_offer(self, offer, evaluation, evaluator):
        self.imports += 1
        self.items[offer.external_id] = {"id": 99}
        return 99


def test_pipeline_dedup_and_notification(offer, state):
    tracker = TrackerStub()
    result = run_pipeline([offer, offer], Config(), PROFILE, state, RulesEvaluator(), tracker)
    assert result["imported"] == 1 and tracker.imports == 1
    again = run_pipeline([offer], Config(), PROFILE, state, RulesEvaluator(), tracker)
    assert again["evaluated"] == 0 and again["imported"] == 0
    messages = []
    assert notify_pending(state, 1, messages.append) == 1
    assert "https://example.com/jobs/1" in messages[0]
    assert "rules" in messages[0]
    assert notify_pending(state, 1, messages.append) == 0


def test_lost_state_reconciles_without_llm(offer, state):
    tracker = TrackerStub()
    tracker.items[offer.external_id] = {"id": 1}
    result = run_pipeline([offer], Config(), PROFILE, state, RulesEvaluator(), tracker)
    assert result["reconciled"] == 1 and result["evaluated"] == 0
    assert state.notifications() == []


def test_failure_retried_using_cached_score(offer, state):
    class Broken(TrackerStub):
        def import_offer(self, *args):
            raise TimeoutError("secret-never-store")
    first = run_pipeline([offer], Config(), PROFILE, state, RulesEvaluator(), Broken())
    assert first["errors"] == 1
    assert state.get(offer.fingerprint)["last_error"] == "TimeoutError"
    next_run = run_pipeline([], Config(), PROFILE, state, RulesEvaluator(), TrackerStub())
    assert next_run["evaluated"] == 0 and next_run["imported"] == 1


def test_failed_llm_counts_toward_budget(offer, state):
    class Broken:
        name = "anthropic"
        def evaluate(self, *args):
            raise ValueError("bad output")
    offers = [offer, offer.model_copy(update={"title": "Stage Python 2"})]
    result = run_pipeline(offers, Config(max_evaluations=1), PROFILE, state, Broken())
    assert result["errors"] == 1 and result["evaluated"] == 1
    assert len(state.pending()) == 2


def test_notification_failure_keeps_pending(offer, state):
    run_pipeline([offer], Config(), PROFILE, state, RulesEvaluator(), TrackerStub())
    def broken(body):
        raise RuntimeError("SMTP unavailable")
    with pytest.raises(RuntimeError):
        notify_pending(state, 1, broken)
    assert len(state.notifications()) == 1
    assert notify_pending(state, 1, lambda body: None) == 1


def test_weekly_digest_waits(offer, state):
    from aggregator.state import now
    run_pipeline([offer], Config(), PROFILE, state, RulesEvaluator(), TrackerStub())
    state.db.execute("INSERT INTO metadata VALUES ('last_digest', ?)", (now(),))
    state.db.commit()
    assert notify_pending(state, 7, lambda body: pytest.fail("too early")) == 0
    assert len(state.notifications()) == 1


def test_state_survives_restart(offer, tmp_path):
    from aggregator.state import State
    path = str(tmp_path / "state.db")
    state = State(path)
    state.add(offer)
    state.update(offer.fingerprint, status="imported", application_id=4)
    state.close()
    reopened = State(path)
    assert reopened.get(offer.fingerprint)["application_id"] == 4
    reopened.close()


def test_recovery_with_evaluation_preserves_pending_notification(offer, state):
    tracker = TrackerStub()
    # L'évaluation a été sauvegardée avant une réponse HTTP perdue.
    state.add(offer)
    state.update(offer.fingerprint, status="selected", evaluation=Evaluation(score=80, reason="Python").model_dump_json(), evaluator="rules")
    tracker.items[offer.external_id] = {"id": 9}
    run_pipeline([offer], Config(), PROFILE, state, RulesEvaluator(), tracker)
    assert len(state.notifications()) == 1
