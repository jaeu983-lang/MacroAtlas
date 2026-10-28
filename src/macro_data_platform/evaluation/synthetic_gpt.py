"""Explicit GPT-driven synthetic candidate-search trials; no real feedback is sent."""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from time import perf_counter_ns
from uuid import uuid4

import requests

from macro_data_platform.config import Settings
from macro_data_platform.discovery.series_search import rank_candidates
from macro_data_platform.evaluation.cases import load_corpus
from macro_data_platform.evaluation.synthetic_feedback import SyntheticFeedbackStore
from macro_data_platform.workflow_contracts import DataRequest

QUESTION_INSTRUCTION = (
    "Create synthetic macroeconomic data search questions, in English. Return only a JSON array "
    "of objects with exactly id and question. Make each question independently answerable as "
    "a search for a series; do not use real user information."
)
REVIEW_INSTRUCTION = (
    "Review only the candidate-search results supplied. Return only a JSON array with exactly "
    "id, outcome and feedback for every question. outcome must be answered, needs_correction, "
    "or unresolved. If candidates satisfy the search, use answered and feedback null. "
    "If evidence is insufficient use unresolved and feedback null. Only when there is a specific "
    "problem use needs_correction and a concise feedback string. Never claim a value was retrieved."
)


def _response_text(payload):
    pieces = [part.get("text") for item in payload.get("output", [])
              if item.get("type") == "message" for part in item.get("content", [])
              if part.get("type") == "output_text" and isinstance(part.get("text"), str)]
    if len(pieces) != 1 or len(pieces[0]) > 100_000:
        raise ValueError("GPT returned an invalid structured response")
    try:
        return json.loads(pieces[0])
    except json.JSONDecodeError as exc:
        raise ValueError("GPT returned invalid JSON") from exc


def _call_gpt(key, model, instruction, data):
    proxies = {scheme: value for scheme in ("http", "https")
               if (value := (os.environ.get(f"{scheme.upper()}_PROXY")
                             or os.environ.get(f"{scheme}_proxy")))}
    verify = os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("CURL_CA_BUNDLE") or True
    with requests.Session() as session:
        session.trust_env = False
        with session.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": model, "input": instruction + "\n" + json.dumps(data, ensure_ascii=False),
                  "max_output_tokens": 4000}, timeout=45, allow_redirects=False,
            proxies=proxies, verify=verify, stream=True,
        ) as response:
            if response.status_code != 200:
                raise ValueError("GPT request failed")
            body = bytearray()
            for chunk in response.iter_content(chunk_size=65536):
                body.extend(chunk)
                if len(body) > 1_000_000:
                    raise ValueError("GPT response exceeded the response budget")
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("GPT returned invalid JSON") from exc
    return _response_text(payload), payload.get("usage", {})


def generate(settings, *, model, count, api_key, call=_call_gpt):
    """Run two explicit calls around real offline candidate searches and record a separate batch."""
    if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}", model):
        raise ValueError("invalid model")
    if type(count) is not int or not 1 <= count <= 5:
        raise ValueError("count must be 1 to 5")
    if not isinstance(api_key, str) or not api_key:
        raise ValueError("OPENAI_API_KEY is required for an explicit live GPT run")
    start = perf_counter_ns()
    corpus = load_corpus(settings.project_root / "tests/fixtures/evaluation/v2",
                         repo_root=settings.project_root)
    model_start = perf_counter_ns()
    questions, usage1 = call(api_key, model, QUESTION_INSTRUCTION, {"count": count})
    model_ns = perf_counter_ns() - model_start
    if not isinstance(questions, list) or len(questions) != count:
        raise ValueError("GPT question count mismatch")
    seen, observations = set(), []
    for item in questions:
        if (not isinstance(item, dict) or set(item) != {"id", "question"}
                or not isinstance(item["id"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", item["id"])
                or item["id"] in seen or not isinstance(item["question"], str)
                or not 1 <= len(item["question"].strip()) <= 2000):
            raise ValueError("invalid GPT question")
        seen.add(item["id"])
        ranked = rank_candidates(DataRequest(item["id"], item["question"]), corpus.candidates, limit=3)
        results = [{"candidate_id": row["candidate"].candidate_id, "score": row["score"],
                    "match_status": row["match_status"]} for row in ranked]
        observations.append({**item, "results": results})
    model_start = perf_counter_ns()
    reviews, usage2 = call(api_key, model, REVIEW_INSTRUCTION, observations)
    model_ns += perf_counter_ns() - model_start
    if not isinstance(reviews, list) or len(reviews) != count:
        raise ValueError("GPT review count mismatch")
    by_id = {}
    for review in reviews:
        if (not isinstance(review, dict) or set(review) != {"id", "outcome", "feedback"}
                or not isinstance(review["id"], str) or review["id"] not in seen
                or review["id"] in by_id):
            raise ValueError("GPT review key mismatch")
        by_id[review["id"]] = review
    run_id = str(uuid4())
    cases = [{"case_id": f"gpt-{run_id}-{index}", "question": item["question"],
              "observed_answer": {"scope": "candidate_search_only", "results": item["results"]},
              "answer_origin": "engine", "outcome": by_id[item["id"]]["outcome"],
              "feedback": by_id[item["id"]]["feedback"], "generator": f"openai-{model}",
              "engine_version": "rank-candidates-baseline", "catalog_sha256": corpus.catalog_sha256}
             for index, item in enumerate(observations)]
    def token_count(key):
        values = [usage1.get(key), usage2.get(key)]
        return sum(values) if all(type(x) is int and x >= 0 for x in values) else None
    total_ns = perf_counter_ns() - start
    run = {"run_id": run_id, "model": model,
           "prompt_sha256": hashlib.sha256((QUESTION_INSTRUCTION + REVIEW_INSTRUCTION).encode()).hexdigest(),
           "elapsed_ms": model_ns // 1_000_000,
           "local_elapsed_ms": max(0, total_ns - model_ns) // 1_000_000,
           "input_tokens": token_count("input_tokens"), "output_tokens": token_count("output_tokens")}
    result = SyntheticFeedbackStore(settings).import_cases(cases, run=run)
    return {**result, "run_id": run_id, "model_elapsed_ms": run["elapsed_ms"],
            "local_elapsed_ms": run["local_elapsed_ms"],
            "input_tokens": run["input_tokens"], "output_tokens": run["output_tokens"],
            "cost_usd": None}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--model", required=True)
    parser.add_argument("--count", type=int, default=2)
    parser.add_argument("--live", action="store_true", required=True)
    args = parser.parse_args(argv)
    try:
        result = generate(Settings(args.project_root), model=args.model, count=args.count,
                          api_key=os.environ.get("OPENAI_API_KEY"))
    except requests.RequestException:
        print(json.dumps({"status": "ERROR", "reason": "GPT request failed"}))
        return 1
    except (ValueError, TypeError) as exc:
        print(json.dumps({"status": "ERROR", "reason": str(exc)}))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
