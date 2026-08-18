#!/usr/bin/env python3
"""Overnight orchestrator: run envelope sensitivity study for all building types × cities.

Targets
-------
- small_office  × {denver, buffalo, atlanta, miami}   (new)
- large_office  × {denver, buffalo, atlanta, miami}   (new)
- medium_office × {denver, buffalo, atlanta, miami}   (re-run to add internal-gains variants)
  (medium_office × all 16 cities already done for envelope variants — only new variants run)

Results written to:
  data/envelope_study/results/multipliers_{type}_{city}.json

Usage
-----
    python scripts/run_sensitivity_all.py              # 4 workers
    python scripts/run_sensitivity_all.py --workers 2
    python scripts/run_sensitivity_all.py --dry-run
"""
import argparse
import multiprocessing
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))

ROOT        = pathlib.Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "data" / "envelope_study" / "results"
LOG_DIR     = ROOT / "data" / "wshp_validation"   # reuse for overnight logs
SUMMARY_LOG = ROOT / "data" / "overnight_summary.txt"

BUILDING_TYPES = [
    "small_office", "medium_office", "large_office",
    "retail_standalone", "retail_stripmall",
    "school_primary", "school_secondary",
    "outpatient", "hospital",
    "hotel_small", "hotel_large",
    "warehouse",
    "restaurant_fastfood", "restaurant_sitdown",
    "apartment_midrise", "apartment_highrise",
]
REPR_CITIES = ["denver", "buffalo", "atlanta", "miami"]


def _run_one(args: tuple) -> tuple[str, str, float]:
    building, city, dry_run = args
    import envelope_study as es

    tag = f"{building}_{city}"
    t0  = time.time()
    try:
        es.run_study(city=city, building_type=building, dry_run=dry_run)
        elapsed = time.time() - t0
        msg = f"ok ({elapsed/60:.1f} min)"
    except Exception as exc:
        elapsed = time.time() - t0
        msg = f"ERROR: {exc}"
    return tag, msg, elapsed


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run",  action="store_true")
    ap.add_argument("--workers",  type=int, default=4)
    args = ap.parse_args()

    tasks = [
        (bt, city, args.dry_run)
        for bt   in BUILDING_TYPES
        for city in REPR_CITIES
    ]

    print(f"[sensitivity] Tasks: {len(tasks)}  workers: {args.workers}")
    print(f"[sensitivity] Results → {RESULTS_DIR}")
    sys.stdout.flush()

    t_global = time.time()
    with multiprocessing.Pool(processes=args.workers) as pool:
        results = pool.map(_run_one, tasks)

    total_elapsed = time.time() - t_global

    # Write summary for morning review
    SUMMARY_LOG.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "=" * 60,
        "SENSITIVITY STUDY — OVERNIGHT SUMMARY",
        f"Wall time: {total_elapsed/60:.1f} min",
        "=" * 60,
    ]
    ok_count = err_count = skip_count = 0
    for tag, msg, elapsed in sorted(results):
        status = "✓" if msg.startswith("ok") else ("↷" if "SKIP" in msg else "✗")
        lines.append(f"  {status} {tag:<35} {msg}")
        if msg.startswith("ok"):      ok_count   += 1
        elif "SKIP" in msg:           skip_count += 1
        else:                         err_count  += 1
    lines += [
        "",
        f"  Completed: {ok_count}  Skipped: {skip_count}  Errors: {err_count}",
        "=" * 60,
    ]
    summary_text = "\n".join(lines)
    print("\n" + summary_text)

    # Append to master overnight log
    with open(SUMMARY_LOG, "a") as f:
        f.write("\n" + summary_text + "\n")
    print(f"\n[sensitivity] Summary appended → {SUMMARY_LOG}")


if __name__ == "__main__":
    main()
