"""
Historical (pre-v1.1.0) permanent-image audit and explicit backfill.

Read-only by default. Never runs automatically.

    python scripts/historical_dataset_audit.py                      # audit only (read-only)
    python scripts/historical_dataset_audit.py --backfill           # dry-run: what would be repaired
    python scripts/historical_dataset_audit.py --backfill --apply   # repair + make eligible

Backfill regenerates labels from existing DB annotations (never fabricated),
keeps the previous label as <label>.pre_a1.bak, appends new training sequences
after all existing ones, and never touches existing snapshots.
"""
import argparse
import json
import os
import sys

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from app.database import SessionLocal  # noqa: E402
import app.models  # noqa: E402,F401
from app.services.training_dataset_service import (  # noqa: E402
    audit_historical_images,
    backfill_historical_images,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--backfill", action="store_true", help="plan (or with --apply, run) the backfill")
    parser.add_argument("--apply", action="store_true", help="actually write changes (requires --backfill)")
    parser.add_argument("--include-mismatched", action="store_true",
                        help="also repair images whose TXT disagrees with their DB annotations")
    parser.add_argument("--details", action="store_true", help="print per-image records")
    args = parser.parse_args()
    if args.apply and not args.backfill:
        parser.error("--apply requires --backfill")

    db = SessionLocal()
    try:
        if args.backfill:
            result = backfill_historical_images(db, apply=args.apply, include_mismatched=args.include_mismatched)
        else:
            result = audit_historical_images(db)
            if not args.details:
                result = {k: v for k, v in result.items() if k != "images"}
        print(json.dumps(result, indent=2, default=str))
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
