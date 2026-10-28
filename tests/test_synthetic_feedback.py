import sqlite3

import pytest

from macro_data_platform.config import Settings
from macro_data_platform.evaluation.cases import load_corpus
from macro_data_platform.evaluation.synthetic_feedback import SyntheticFeedbackStore
from macro_data_platform.evaluation.synthetic_gpt import _call_gpt, generate
from macro_data_platform.evaluation.synthetic_gpt import main as gpt_main


def case(case_id="case-1", **changes):
    result = {"case_id": case_id, "question": "Find a GDP series", "observed_answer": {"ids": []},
              "answer_origin": "engine", "outcome": "answered", "feedback": None,
              "generator": "codex-gpt6", "engine_version": "candidate-search-v2",
              "catalog_sha256": "a" * 64}
    result.update(changes)
    return result


def test_synthetic_is_separate_and_sufficient_answers_have_no_forced_feedback(tmp_path):
    settings = Settings(tmp_path)
    store = SyntheticFeedbackStore(settings)
    assert store.import_cases([case(), case("case-2", outcome="needs_correction",
                                             feedback="Wrong candidate returned.")])["inserted"] == 2
    assert store.import_cases([case()])["inserted"] == 0
    assert store.list_cases()[0]["feedback"] is None
    assert not settings.database_path.exists()
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT DISTINCT origin FROM synthetic_interactions").fetchall() == [
            ("gpt_synthetic",)]


def test_bad_feedback_and_conflicting_ids_do_not_partially_import(tmp_path):
    store = SyntheticFeedbackStore(Settings(tmp_path))
    with pytest.raises(ValueError, match="must not invent"):
        store.import_cases([case(feedback="unnecessary")])
    store.import_cases([case()])
    with pytest.raises(ValueError, match="conflicts"):
        store.import_cases([case("new"), case(question="changed")])
    assert len(store.list_cases()) == 1


def test_synthetic_db_cannot_alias_user_db(tmp_path):
    settings = Settings(tmp_path)
    settings.database_path.parent.mkdir(parents=True)
    settings.database_path.touch()
    try:
        (settings.database_path.parent / "synthetic_feedback.sqlite").symlink_to(settings.database_path)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(ValueError, match="symlink"):
        SyntheticFeedbackStore(settings)


def test_explicit_gpt_trial_runs_engine_and_preserves_no_feedback(tmp_path, monkeypatch):
    corpus = load_corpus("tests/fixtures/evaluation/v2", repo_root=".")
    monkeypatch.setattr("macro_data_platform.evaluation.synthetic_gpt.load_corpus",
                        lambda *args, **kwargs: corpus)
    calls = []

    def fake_gpt(key, model, instruction, data):
        calls.append(data)
        if len(calls) == 1:
            return ([{"id": "q1", "question": "US GDP per capita"}],
                    {"input_tokens": 5, "output_tokens": 7})
        assert data[0]["results"]
        return ([{"id": "q1", "outcome": "answered", "feedback": None}],
                {"input_tokens": 8, "output_tokens": 4})

    settings = Settings(tmp_path)
    result = generate(settings, model="test-model", count=1, api_key="test-key", call=fake_gpt)
    assert result["submitted"] == 1 and result["input_tokens"] == 13
    stored = SyntheticFeedbackStore(settings).list_cases()
    assert stored[0]["answer_origin"] == "engine" and stored[0]["feedback"] is None
    assert not settings.database_path.exists()
    with sqlite3.connect(settings._inside("data/synthetic_feedback.sqlite")) as db:
        assert db.execute("SELECT count(*), cost_usd FROM synthetic_runs").fetchone() == (1, None)
    assert SyntheticFeedbackStore(settings).list_runs()[0]["input_tokens"] == 13


def test_gpt_review_key_mismatch_is_rejected_before_any_database_write(tmp_path, monkeypatch):
    corpus = load_corpus("tests/fixtures/evaluation/v2", repo_root=".")
    monkeypatch.setattr("macro_data_platform.evaluation.synthetic_gpt.load_corpus",
                        lambda *args, **kwargs: corpus)
    calls = iter([([{"id": "q1", "question": "GDP"}], {}),
                  ([{"id": "other", "outcome": "answered", "feedback": None}], {})])
    with pytest.raises(ValueError, match="review key mismatch"):
        generate(Settings(tmp_path), model="test-model", count=1, api_key="test-key",
                 call=lambda *args: next(calls))
    assert not (tmp_path / "data" / "synthetic_feedback.sqlite").exists()


def test_gpt_transport_uses_explicit_key_and_validates_output(monkeypatch):
    class Response:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def iter_content(self, chunk_size):
            import json

            yield json.dumps({"output": [{"type": "message", "content": [
                {"type": "output_text", "text": '[{"id":"q1","question":"GDP"}]'}]}],
                "usage": {"input_tokens": 2, "output_tokens": 3}}).encode()

    class Session:
        trust_env = True

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, **kwargs):
            assert self.trust_env is False
            assert url == "https://api.openai.com/v1/responses"
            assert kwargs["headers"]["Authorization"] == "Bearer test-key"
            assert kwargs["allow_redirects"] is False and kwargs["stream"] is True
            return Response()

    monkeypatch.setattr("macro_data_platform.evaluation.synthetic_gpt.requests.Session", Session)
    rows, usage = _call_gpt("test-key", "test-model", "instruction", {"count": 1})
    assert rows == [{"id": "q1", "question": "GDP"}] and usage["output_tokens"] == 3


def test_missing_api_key_does_not_create_database_or_call_gpt(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert gpt_main(["--project-root", str(tmp_path), "--model", "test-model", "--live"]) == 1
    assert "OPENAI_API_KEY" in capsys.readouterr().out
    assert not (tmp_path / "data" / "synthetic_feedback.sqlite").exists()
