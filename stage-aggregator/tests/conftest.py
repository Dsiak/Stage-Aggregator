from datetime import date
import pytest
from aggregator.models import Offer
from aggregator.state import State


@pytest.fixture
def offer():
    return Offer(source="Test", source_id="1", title="Stage Python backend", company="Exemple",
                 location="Canada", published_on=date.today(), url="https://example.com/jobs/1",
                 description="Stage rémunéré Python FastAPI SQL backend au Canada.")


@pytest.fixture
def state():
    state = State(":memory:")
    yield state
    state.close()

