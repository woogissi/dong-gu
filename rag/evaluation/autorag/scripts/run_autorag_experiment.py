"""Run an AutoRAG experiment in a reproducible output directory."""

from __future__ import annotations

import argparse
import subprocess
from datetime import datetime
from pathlib import Path


DEFAULT_QA_PATH = Path("rag/evaluation/autorag/data/qa.parquet")
DEFAULT_CORPUS_PATH = Path("rag/evaluation/autorag/data/corpus.parquet")
DEFAULT_RESULTS_DIR = Path("rag/evaluation/autorag/results")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run AutoRAG validate/evaluate for Donggu offline experiments.")
    parser.add_argument("--config", required=True, help="AutoRAG config YAML path.")
    parser.add_argument("--qa", default=str(DEFAULT_QA_PATH), help="qa.parquet path.")
    parser.add_argument("--corpus", default=str(DEFAULT_CORPUS_PATH), help="corpus.parquet path.")
    parser.add_argument("--results-dir", default=str(DEFAULT_RESULTS_DIR), help="Base results directory.")
    parser.add_argument("--project-dir", default="", help="Explicit AutoRAG project dir. Defaults to timestamped results.")
    parser.add_argument("--validate", action="store_true", help="Run autorag validate instead of evaluate.")
    parser.add_argument(
        "--full-ingest",
        default="True",
        choices=["True", "False", "true", "false"],
        help="Forwarded to AutoRAG evaluate.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = require_file(Path(args.config), "config")
    qa_path = require_file(Path(args.qa), "QA parquet")
    corpus_path = require_file(Path(args.corpus), "corpus parquet")
    project_dir = Path(args.project_dir) if args.project_dir else default_project_dir(config_path, Path(args.results_dir))
    project_dir.mkdir(parents=True, exist_ok=True)

    command = [
        "autorag",
        "validate" if args.validate else "evaluate",
        "--config",
        str(config_path),
        "--qa_data_path",
        str(qa_path),
        "--corpus_data_path",
        str(corpus_path),
    ]
    if not args.validate:
        command.extend(["--project_dir", str(project_dir), "--full_ingest", args.full_ingest])

    print("Running:", " ".join(command))
    print("Project dir:", project_dir)
    subprocess.run(command, check=True)


def require_file(path: Path, label: str) -> Path:
    if not path.exists():
        raise SystemExit(f"Missing {label}: {path}")
    return path


def default_project_dir(config_path: Path, results_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return results_dir / f"{timestamp}-{config_path.stem}"


if __name__ == "__main__":
    main()
