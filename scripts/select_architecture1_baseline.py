"""Select an Architecture 1 Cypher baseline from a sweep report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.config.models import CypherModelCandidate, DEFAULT_CYPHER_CANDIDATES
from common.evaluation import ModelRunResult, select_baseline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", help="JSON report produced by run_architecture1_sweep.py")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    rows = json.loads(Path(args.report).read_text(encoding="utf-8"))
    candidates = {item.name: item for item in DEFAULT_CYPHER_CANDIDATES}
    results = []
    for row in rows:
        summary = row["summary"]
        candidate = candidates.get(row["model"], CypherModelCandidate(row["model"], "configured"))
        results.append(
            ModelRunResult(
                candidate=candidate,
                raw_score=int(summary["raw_score"]),
                accuracy_count=int(summary["accuracy_count"]),
                false_positive_count=int(summary["false_positive_count"]),
                no_answer_count=int(summary["no_answer_count"]),
                run_id=row.get("run_id"),
            )
        )
    selected = select_baseline(results)
    print(json.dumps({
        "model": selected.candidate.name,
        "provider": selected.candidate.provider,
        "raw_score": selected.raw_score,
        "accuracy_count": selected.accuracy_count,
        "false_positive_count": selected.false_positive_count,
        "no_answer_count": selected.no_answer_count,
        "run_id": selected.run_id,
        "review_required": True,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
