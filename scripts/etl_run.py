"""Local ETL entrypoint — runs one incremental ETL pass over FedReg + eCFR.
Run:  python -m scripts.etl_run
Single-pass only (D7): no scheduler loop, no cron wiring, no CI workflow.
ETL_SCHEDULE is read into config for completeness but unused by this script."""
from __future__ import annotations

from src.etl.pipeline import run_once
from src.rag.config import CONFIG


def main() -> None:
    print(f"Running ETL pass (fedreg since={CONFIG.etl_fedreg_since}, "
          f"ecfr since={CONFIG.etl_ecfr_since}, parts={CONFIG.parts}) ...")
    summary = run_once(CONFIG)
    for source, counts in summary.items():
        print(f"  {source}: {counts}")
    print("Done.")


if __name__ == "__main__":
    main()
