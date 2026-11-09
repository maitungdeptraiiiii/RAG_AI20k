"""Kiểm tra hợp đồng dữ liệu fixtures và câu hỏi tuần 2, không chạy detector.

Đây là quality gate cho dữ liệu nhãn, không phải implementation PII/numeric
detector; vì vậy không vi phạm quy tắc người tạo fixture không viết detector.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = ROOT / "data/team-4.2/fixtures"
QUESTION_FILE = ROOT / "evals/team-4.2/datasets/w02_fixture_questions.jsonl"
BENCHMARK_FILE = ROOT / "evals/team-4.2/datasets/benchmark_doi_thuong_w02.jsonl"


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def validate_fixtures(errors: list[str]) -> None:
    manifest = load_jsonl(FIXTURE_DIR / "manifest.jsonl")
    labels = load_jsonl(FIXTURE_DIR / "labels.jsonl")
    ids = [item.get("fixture_id") for item in manifest]
    label_ids = [item.get("fixture_id") for item in labels]
    require(len(manifest) == 25, f"Cần 25 fixtures, có {len(manifest)}", errors)
    require(len(set(ids)) == len(ids), "fixture_id bị trùng trong manifest", errors)
    require(set(ids) == set(label_ids), "manifest và labels không cùng fixture_id", errors)
    allowed_status = {"duplicate", "needs_review", "activated", "failed"}
    allowed_dedup = {"link_existing", "continue", "review"}
    for item in manifest:
        fixture_id = item.get("fixture_id", "?")
        require(item.get("schema_version") == "w02.v1", f"{fixture_id}: sai schema_version", errors)
        source_path = FIXTURE_DIR / item.get("source_path", "")
        require(source_path.is_file() and source_path.resolve().is_relative_to((FIXTURE_DIR / "raw").resolve()),
                f"{fixture_id}: raw artifact thiếu hoặc nằm ngoài raw/", errors)
        version = item.get("version", {})
        require(version.get("approval") in {"approved", "pending", "rejected"}, f"{fixture_id}: approval thiếu/sai", errors)
        require(bool(item.get("collected_at")), f"{fixture_id}: thiếu collected_at", errors)
    for label in labels:
        expected = label.get("expected", {})
        fixture_id = label.get("fixture_id", "?")
        require("ingest_status" in expected and "dedup_action" in expected,
                f"{fixture_id}: thiếu expected ingest/dedup", errors)
        require(expected.get("ingest_status") in allowed_status, f"{fixture_id}: ingest_status không hợp lệ", errors)
        require(expected.get("dedup_action") in allowed_dedup, f"{fixture_id}: dedup_action không hợp lệ", errors)
        if expected.get("ingest_status") == "activated":
            require(not expected.get("review_required"), f"{fixture_id}: activated không thể còn review_required", errors)
        if expected.get("ingest_status") == "needs_review":
            require(expected.get("review_required") is True, f"{fixture_id}: needs_review phải có review_required", errors)
        if expected.get("ingest_status") == "duplicate":
            require(expected.get("new_chunk_count") == 0, f"{fixture_id}: duplicate phải có new_chunk_count=0", errors)


def validate_questions(errors: list[str]) -> None:
    questions = load_jsonl(QUESTION_FILE)
    ids = [question.get("id") for question in questions]
    allowed_types = {"lookup", "paraphrase", "multi", "out_of_scope"}
    allowed_surfaces = {"answer", "review"}
    require(len(set(ids)) == len(ids), "question id bị trùng", errors)
    for question in questions:
        question_id = question.get("id", "?")
        require(question.get("type") in allowed_types, f"{question_id}: type không hợp lệ", errors)
        require(question.get("split") in {"dev", "test"}, f"{question_id}: split không hợp lệ", errors)
        require(question.get("data_snapshot"), f"{question_id}: thiếu data_snapshot", errors)
        surface = question.get("evaluation_surface", "answer")
        require(surface in allowed_surfaces, f"{question_id}: evaluation_surface không hợp lệ", errors)
        require("gold_chunk_ids" not in question, f"{question_id}: không được khóa gold theo chunk_id", errors)
        if question.get("type") == "out_of_scope":
            require(not question.get("gold"), f"{question_id}: out_of_scope không có gold", errors)
            require(question.get("expected_behavior") == "abstain", f"{question_id}: OOS phải abstain", errors)
        else:
            require(bool(question.get("gold")) and bool(question.get("evidence")), f"{question_id}: thiếu gold/evidence", errors)
        if surface == "review":
            require(question.get("expected_behavior") == "clarify", f"{question_id}: review surface phải clarify", errors)
            require(any(item.get("version_scope") == "review_only" for item in question.get("evidence", [])),
                    f"{question_id}: review surface thiếu evidence review_only", errors)


def validate_carryover_benchmark(errors: list[str]) -> None:
    if not BENCHMARK_FILE.is_file():
        errors.append("thiếu benchmark_doi_thuong_w02.jsonl; chạy prepare_w02_benchmark.py")
        return
    records = load_jsonl(BENCHMARK_FILE)
    ids = [record.get("id") for record in records]
    require(len(set(ids)) == len(ids), "carryover benchmark có id trùng", errors)
    require(sum(record.get("type") == "multi" and record.get("split") == "test" for record in records) == 27,
            "carryover benchmark phải có đúng 27 multi trong test", errors)
    for record in records:
        record_id = record.get("id", "?")
        require("gold_chunk_ids" not in record, f"{record_id}: carryover gold không được khóa theo chunk_id", errors)
        require(record.get("gold_schema") == "source_section.v1", f"{record_id}: sai gold_schema", errors)
        if record.get("type") == "out_of_scope":
            require(record.get("gold") == [] and record.get("expected_behavior") == "abstain",
                    f"{record_id}: out_of_scope phải gold rỗng và abstain", errors)
        else:
            require(bool(record.get("gold")) and record.get("evidence") == record.get("gold"),
                    f"{record_id}: gold/evidence không ổn định", errors)


def main() -> int:
    errors: list[str] = []
    validate_fixtures(errors)
    validate_questions(errors)
    validate_carryover_benchmark(errors)
    if errors:
        print("W02 data validation failed:")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print("W02 data validation passed: fixtures, fixture questions, and carryover benchmark are consistent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
