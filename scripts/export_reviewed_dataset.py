"""Export caregiver-reviewed incidents as a JSONL retraining manifest.

Usage:
    python scripts/export_reviewed_dataset.py --database-url sqlite:///demo_data/eldercare_demo.db \
        --out datasets/derived/reviewed_incidents.jsonl

Keyframe paths in the manifest are relative to the evidence storage root.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from eldercare.db.session import create_db_engine, create_session_factory
from eldercare.incidents.export import build_reviewed_dataset, write_jsonl


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--database-url",
        default=None,
        help="SQLAlchemy URL (default: DATABASE_URL from settings)",
    )
    parser.add_argument("--out", type=Path, required=True, help="Output .jsonl path")
    parser.add_argument(
        "--include-uncertain",
        action="store_true",
        help="Also export incidents the reviewer labelled 'uncertain'",
    )
    args = parser.parse_args(argv)

    engine = create_db_engine(args.database_url)
    try:
        records = build_reviewed_dataset(
            create_session_factory(engine), include_uncertain=args.include_uncertain
        )
        count = write_jsonl(records, args.out)
    finally:
        engine.dispose()

    print(f"Wrote {count} reviewed incidents to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
