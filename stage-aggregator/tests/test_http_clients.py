import json
import httpx
import pytest
from pydantic import ValidationError
from aggregator.evaluation import AnthropicEvaluator
from aggregator.models import Evaluation
from aggregator.tracker import Tracker, validate_tracker_url


@pytest.mark.parametrize("url", ["http://public.example.com", "https://user:pass@example.com", "https://example.com/api", "https://example.com?q=1", "file:///tmp"])
def test_unsafe_tracker_origin(url):
    with pytest.raises(ValueError):
        validate_tracker_url(url)


def test_local_and_https_origins():
    assert validate_tracker_url("http://127.0.0.1:8000/") == "http://127.0.0.1:8000"
    assert validate_tracker_url("https://tracker.example.com") == "https://tracker.example.com"


@pytest.mark.parametrize("score", [-1, 101, "80", True])
def test_invalid_llm_scores(offer, score):
    def respond(request):
        assert request.url.host == "api.anthropic.com"
        assert request.headers["anthropic-version"] == "2023-06-01"
        assert "x-api-key" in request.headers
        return httpx.Response(200, json={"stop_reason": "tool_use", "content": [{"type": "tool_use", "name": "evaluation", "input": {"score": score, "reason": "Exemple"}}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ValidationError):
            AnthropicEvaluator(client, "test-only", "test-model").evaluate(offer, "Python")


def test_llm_valid_and_truncated(offer):
    def respond(request):
        payload = json.loads(request.content)
        assert payload["tool_choice"]["name"] == "evaluation"
        return httpx.Response(200, json={"stop_reason": "tool_use", "content": [{"type": "tool_use", "name": "evaluation", "input": {"score": 85, "reason": "Python et SQL correspondent au profil."}}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        assert AnthropicEvaluator(client, "test-only", "test-model").evaluate(offer, "Python").score == 85
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"stop_reason": "max_tokens"}))) as client:
        with pytest.raises(ValueError):
            AnthropicEvaluator(client, "test-only", "test-model").evaluate(offer, "Python")


def test_http_import_and_conflict_recovery(offer):
    created = {"company": None, "application": None, "posts": 0}
    def respond(request):
        assert request.headers["x-api-key"] == "tracker-test-key"
        path = request.url.path
        if request.method == "GET" and path == "/companies":
            return httpx.Response(200, json=[created["company"]] if created["company"] else [])
        if request.method == "POST" and path == "/companies":
            payload = json.loads(request.content)
            created["company"] = {"id": 5, **payload}
            return httpx.Response(409, json={"detail": "Concurrent creation"})
        if request.method == "GET" and path == "/applications":
            return httpx.Response(200, json=[created["application"]] if created["application"] else [])
        if request.method == "POST" and path == "/applications":
            payload = json.loads(request.content)
            assert payload["sent_on"] is None and payload["status"] == "a_considerer"
            assert payload["external_id"] == offer.external_id
            assert payload["company_id"] == 5
            created["application"] = {"id": 10, **payload}
            created["posts"] += 1
            return httpx.Response(409, json={"detail": "Concurrent creation"})
        pytest.fail(str(request.url))
    with httpx.Client(base_url="https://tracker.example.com", headers={"X-API-Key": "tracker-test-key"}, transport=httpx.MockTransport(respond)) as client:
        tracker = Tracker(client)
        evaluation = Evaluation(score=80, reason="Python")
        assert tracker.import_offer(offer, evaluation, "rules") == 10
        assert tracker.import_offer(offer, evaluation, "rules") == 10
        assert created["posts"] == 1


def test_old_tracker_rejected():
    schemas = {"components": {"schemas": {"Status": {"enum": ["envoyee"]}}}}
    with httpx.Client(base_url="https://tracker.example.com", transport=httpx.MockTransport(lambda r: httpx.Response(200, json=schemas))) as client:
        with pytest.raises(ValueError, match="2.1"):
            Tracker(client).check()
