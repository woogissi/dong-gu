"""Convert integration test queries to an AutoRAG QA parquet file.

Existing test queries do not include ground-truth chunks, so this script can
also emit a CSV template for manual labeling.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


DEFAULT_INPUT_PATH = Path("rag/tests/integration/test_queries.json")
DEFAULT_OUTPUT_PATH = Path("rag/evaluation/autorag/data/qa.parquet")
DEFAULT_TEMPLATE_PATH = Path("rag/evaluation/autorag/data/qa_ground_truth_template.csv")
DEFAULT_GROUND_TRUTH_PATH = Path("rag/evaluation/autorag/data/ground_truth.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert test_queries.json to AutoRAG qa.parquet.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT_PATH), help="Input JSON query list.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output QA parquet path.")
    parser.add_argument(
        "--ground-truth",
        default=str(DEFAULT_GROUND_TRUTH_PATH),
        help=(
            "Optional JSON mapping query text or qid to answers/retrieval_gt. "
            "Defaults to rag/evaluation/autorag/data/ground_truth.json when present."
        ),
    )
    parser.add_argument(
        "--template-output",
        default=str(DEFAULT_TEMPLATE_PATH),
        help="CSV template path for manual ground-truth labeling.",
    )
    parser.add_argument(
        "--include-unlabeled",
        action="store_true",
        help="Include rows with empty retrieval_gt. Do not use this output with AutoRAG validate.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    template_path = Path(args.template_output)
    ground_truth_path = Path(args.ground_truth) if args.ground_truth else None
    ground_truth = load_ground_truth(ground_truth_path) if ground_truth_path and ground_truth_path.exists() else {}

    queries = load_queries(input_path)
    all_rows = [to_qa_row(index, query, ground_truth) for index, query in enumerate(queries)]
    rows = all_rows if args.include_unlabeled else [row for row in all_rows if row["retrieval_gt"]]
    validate_retrieval_gt(rows)
    write_parquet(rows, output_path)
    write_ground_truth_template(all_rows, template_path)

    labeled_count = sum(1 for row in all_rows if row["retrieval_gt"])
    skipped_count = len(all_rows) - len(rows)
    print(f"Wrote {len(rows)} QA rows to {output_path}")
    print(f"Wrote labeling template to {template_path}")
    if ground_truth_path and ground_truth_path.exists():
        print(f"Loaded ground-truth labels from {ground_truth_path}")
    else:
        print("No ground-truth label file loaded.")
    print(f"Labeled rows with retrieval_gt: {labeled_count}/{len(all_rows)}")
    print(f"Skipped unlabeled rows in qa.parquet: {skipped_count}")
    if args.include_unlabeled:
        print("Warning: --include-unlabeled can make AutoRAG validate fail with empty retrieval_gt.")


def load_queries(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, list):
        raise ValueError(f"{path} must contain a JSON list of query strings.")
    return [item for item in payload if isinstance(item, str) and item.strip()]


def load_ground_truth(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return payload


def to_qa_row(index: int, query: str, ground_truth: dict[str, Any]) -> dict[str, Any]:
    qid = f"donggu-{index:04d}"
    label = ground_truth.get(qid) or ground_truth.get(query) or {}
    if isinstance(label, list):
        label = {"retrieval_gt": label}
    if not isinstance(label, dict):
        label = {}

    retrieval_gt = normalize_list(label.get("retrieval_gt"))
    answers = normalize_list(label.get("answers") or label.get("generation_gt"))

    return {
        "qid": qid,
        "query": query,
        "answers": answers,
        "generation_gt": answers,
        "retrieval_gt": retrieval_gt,
        "metadata": {
            "source": "rag/tests/integration/test_queries.json",
            "label_status": "labeled" if retrieval_gt else "needs_ground_truth",
            "domain_hint": infer_domain_hint(query),
        },
    }


def normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def validate_retrieval_gt(rows: list[dict[str, Any]]) -> None:
    empty_qids = [row["qid"] for row in rows if not row.get("retrieval_gt")]
    if empty_qids:
        raise ValueError(
            "AutoRAG requires non-empty retrieval_gt for every QA row. "
            f"Empty retrieval_gt qids: {', '.join(empty_qids[:20])}"
        )


def infer_domain_hint(query: str) -> str:
    hints = {
        "수강": "course_registration",
        "장학": "scholarship",
        "기숙": "dormitory",
        "도서관": "library",
        "통학": "shuttle",
        "졸업": "graduation",
        "학사": "academic_calendar",
        "등록": "tuition",
    }
    return next((hint for token, hint in hints.items() if token in query), "unknown")


def write_parquet(rows: list[dict[str, Any]], output_path: Path) -> None:
    try:
        import pandas as pd
    except ImportError as exc:
        raise SystemExit("pandas and pyarrow are required. Install them in the rag service.") from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(output_path, index=False)


def write_ground_truth_template(rows: list[dict[str, Any]], template_path: Path) -> None:
    template_path.parent.mkdir(parents=True, exist_ok=True)
    with template_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["qid", "query", "domain_hint", "retrieval_gt", "answers", "notes"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "qid": row["qid"],
                    "query": row["query"],
                    "domain_hint": row["metadata"]["domain_hint"],
                    "retrieval_gt": ",".join(row["retrieval_gt"]),
                    "answers": " | ".join(row["answers"]),
                    "notes": "",
                }
            )


if __name__ == "__main__":
    main()
