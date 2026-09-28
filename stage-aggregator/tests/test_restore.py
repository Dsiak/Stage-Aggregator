import importlib.util
import io
import json
import zipfile
from pathlib import Path

import pytest
from aggregator.state import State


@pytest.fixture
def restore(monkeypatch, tmp_path):
    path = Path(__file__).resolve().parents[1] / "scripts/restore_state.py"
    spec = importlib.util.spec_from_file_location("restore_state", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_REPOSITORY", "example/aggregator")
    monkeypatch.setenv("DEFAULT_BRANCH", "main")
    monkeypatch.delenv("INITIALIZE_STATE", raising=False)
    return module


def test_missing_state_fails_closed(restore, monkeypatch):
    monkeypatch.setattr(restore, "gh_api", lambda url: b'{"artifacts": []}')
    with pytest.raises(RuntimeError):
        restore.main()
    monkeypatch.setenv("INITIALIZE_STATE", "true")
    restore.main()


def test_restore_expected_file_only(restore, monkeypatch, tmp_path):
    state = State(str(tmp_path / "source.db"))
    state.close()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("aggregator.db", (tmp_path / "source.db").read_bytes())
        archive.writestr("../unexpected.txt", "never extract")
    artifacts = {"artifacts": [{"id": 1, "expired": False, "workflow_run": {"head_branch": "main"}},
                               {"id": 2, "expired": False, "workflow_run": {"head_branch": "untrusted-branch"}}]}
    def response(url):
        if url.endswith("/1/zip"):
            return buffer.getvalue()
        assert "?name=aggregator-state" in url
        return json.dumps(artifacts).encode()
    monkeypatch.setattr(restore, "gh_api", response)
    restore.main()
    assert Path("state/aggregator.db").exists()
    assert not Path("unexpected.txt").exists()
