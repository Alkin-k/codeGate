"""Phase 2 A/B Batch Runner — runs all 3 cases and produces summary."""
from __future__ import annotations
import json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def run_all():
    from test_ab_case1 import run_case1
    from test_ab_case2 import run_case2
    from test_ab_case3 import run_case3

    results = []
    start = time.time()

    for name, fn in [("Case 1", run_case1), ("Case 2", run_case2), ("Case 3", run_case3)]:
        print(f"\n{'#' * 70}")
        print(f"# Running {name}")
        print(f"{'#' * 70}")
        try:
            r = fn()
            results.append(r)
        except Exception as e:
            print(f"❌ {name} FAILED: {e}")
            results.append({"case": name, "verdict": "ERROR", "error": str(e)})

    total = time.time() - start

    print("\n" + "=" * 70)
    print("📊 PHASE 2 SUMMARY")
    print("=" * 70)
    print(f"{'Case':<40} {'Verdict':<8} {'Findings':<10} {'Blocking':<10} {'Time'}")
    print("-" * 80)
    for r in results:
        print(f"{r.get('case','?'):<40} {r.get('verdict','?'):<8} "
              f"{r.get('findings_count','?'):<10} {r.get('blocking_findings','?'):<10} "
              f"{r.get('elapsed_seconds','?')}s")

    passed = sum(1 for r in results if r.get("verdict") == "PASS")
    print(f"\nTotal: {passed}/{len(results)} PASS, {total:.0f}s elapsed")

    out = Path(__file__).parent.parent / "real_project_results" / "phase2_summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"results": results, "total_seconds": round(total, 1)}, indent=2, ensure_ascii=False))
    print(f"Summary saved: {out}")
    return results


if __name__ == "__main__":
    run_all()
