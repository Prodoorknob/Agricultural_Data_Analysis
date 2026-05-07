"""Weight-calibration CLI for the SignalBoard.

Spec: §4.2 + §13 step 2 of analyst-agent-tech-spec.md.

Workflow:

    # 1. Generate candidate signals over the last 26 weeks (Sundays).
    python -m backend.agent.calibrate seed --weeks 26 \\
        --out backend/agent/data/calibration_unlabelled.csv

    # 2. Open the CSV in Excel/Sheets and add a `label` column:
    #      0 = "would not have been a story"
    #      1 = "would have been a story"
    #    Save as calibration_labelled.csv.

    # 3. Fit weights via grid search over (mag, reach, novelty, calendar)
    #    that sum to 1.0, optimising AUC against the labels.
    python -m backend.agent.calibrate fit \\
        --labels backend/agent/data/calibration_labelled.csv \\
        --out backend/agent/data/weights.json

    # 4. The runner loads weights.json at startup. If the file is missing,
    #    it falls back to DEFAULT_WEIGHTS in _common.py.

The labelling step is intentionally manual (Raj reviews ~600 rows over
~1 day per the spec budget). The fit step is fast (<1 min) once labels
are in.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )


# ---------------------------------------------------------------------------
# Seed: dump unlabelled candidate signals across N historical Sundays.
# ---------------------------------------------------------------------------


def cmd_seed(args: argparse.Namespace) -> int:
    from backend.agent.signal_board import build_candidates
    from backend.agent.signals._fips_label import county_label, state_label

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    sundays = _last_sundays(args.weeks)
    rows: list[dict] = []

    def _scope_label(scope: str) -> str:
        if scope == "national":
            return "U.S."
        if scope.startswith("state:"):
            return state_label(scope.split(":", 1)[1])
        if scope.startswith("county:"):
            return county_label(scope.split(":", 1)[1])
        return scope

    for sunday in sundays:
        try:
            cands = build_candidates(sunday, top_n=args.top_n)
        except Exception as exc:  # noqa: BLE001
            logger.warning("seed: as_of=%s failed: %s", sunday, exc)
            continue
        for sig in cands:
            sp = sig.evidence.get("score_parts", {}) if isinstance(sig.evidence, dict) else {}
            rows.append(
                {
                    "as_of_date": sunday.isoformat(),
                    "signal_id": sig.id,
                    "domain": sig.domain,
                    "scope": sig.scope,
                    "scope_label": _scope_label(sig.scope),
                    "headline": sig.headline,
                    "score": round(sig.score, 2),
                    "magnitude": round(sp.get("magnitude", 0), 2),
                    "reach": round(sp.get("reach", 0), 2),
                    "novelty": round(sp.get("novelty", 0), 2),
                    "calendar": round(sp.get("calendar", 0), 2),
                    "direction": sig.direction,
                    "label": "",  # operator fills in 0 or 1
                }
            )

    if not rows:
        logger.error("seed: no candidates produced. Check that signal sources work.")
        return 1

    fieldnames = list(rows[0].keys())
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    logger.info("seed: wrote %d rows to %s", len(rows), out_path)
    return 0


def _last_sundays(n: int) -> list[date]:
    today = date.today()
    days_to_sunday = (today.weekday() + 1) % 7  # Mon=0 -> 1, Sun=6 -> 0
    last_sunday = today - timedelta(days=days_to_sunday)
    return [last_sunday - timedelta(weeks=i) for i in range(n)]


# ---------------------------------------------------------------------------
# Fit: grid search weights to maximize AUC over labels.
# ---------------------------------------------------------------------------


def cmd_fit(args: argparse.Namespace) -> int:
    labels_path = Path(args.labels)
    if not labels_path.exists():
        logger.error("fit: labels file not found: %s", labels_path)
        return 1

    rows = list(csv.DictReader(labels_path.open(encoding="utf-8")))
    rows = [r for r in rows if r.get("label", "").strip() in {"0", "1"}]
    if len(rows) < 50:
        logger.error("fit: need at least 50 labelled rows, got %d", len(rows))
        return 1

    labels = [int(r["label"]) for r in rows]
    parts = [
        (
            float(r["magnitude"]),
            float(r["reach"]),
            float(r["novelty"]),
            float(r["calendar"]),
        )
        for r in rows
    ]

    best = {"auc": 0.0, "weights": None}
    # Grid over weights summing to 1.0 in steps of 0.05.
    step = 0.05
    grid = [round(x * step, 2) for x in range(int(1 / step) + 1)]

    for w_mag, w_reach, w_nov, w_cal in itertools.product(grid, repeat=4):
        s = w_mag + w_reach + w_nov + w_cal
        if abs(s - 1.0) > 1e-6:
            continue
        scores = [w_mag * m + w_reach * r + w_nov * n + w_cal * c for m, r, n, c in parts]
        auc = _auc(scores, labels)
        if auc > best["auc"]:
            best = {
                "auc": auc,
                "weights": {
                    "magnitude": w_mag,
                    "reach": w_reach,
                    "novelty": w_nov,
                    "calendar": w_cal,
                },
            }

    if best["weights"] is None:
        logger.error("fit: grid search produced no result (degenerate input?)")
        return 1

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({**best, "n_labels": len(rows)}, indent=2))
    logger.info(
        "fit: AUC=%.3f, weights=%s, wrote %s",
        best["auc"], best["weights"], out_path,
    )
    return 0


def _auc(scores: list[float], labels: list[int]) -> float:
    """ROC AUC via Mann-Whitney U statistic. Returns 0.5 on degenerate input."""
    pos = [s for s, lab in zip(scores, labels) if lab == 1]
    neg = [s for s, lab in zip(scores, labels) if lab == 0]
    if not pos or not neg:
        return 0.5
    n_correct = 0.0
    for p in pos:
        for n in neg:
            if p > n:
                n_correct += 1
            elif p == n:
                n_correct += 0.5
    return n_correct / (len(pos) * len(neg))


def main() -> int:
    _setup_logging()
    parser = argparse.ArgumentParser(description="SignalBoard weight calibrator.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    seed = sub.add_parser("seed", help="Dump unlabelled candidate signals.")
    seed.add_argument("--weeks", type=int, default=26, help="Number of historical Sundays to seed.")
    seed.add_argument("--top-n", type=int, default=40, help="Top candidates per Sunday.")
    seed.add_argument(
        "--out", default="backend/agent/data/calibration_unlabelled.csv",
        help="Output CSV path.",
    )

    fit = sub.add_parser("fit", help="Fit weights from a labelled CSV.")
    fit.add_argument("--labels", required=True, help="Labelled CSV (with label column).")
    fit.add_argument(
        "--out", default="backend/agent/data/weights.json",
        help="Output weights JSON.",
    )

    args = parser.parse_args()
    if args.cmd == "seed":
        return cmd_seed(args)
    if args.cmd == "fit":
        return cmd_fit(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
