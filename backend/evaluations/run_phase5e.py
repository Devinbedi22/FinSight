"""Operate the research-only Phase 5D forward forecast registry."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from app.research.forecast_operations import (
    DownloadWorkflowError,
    SnapshotValidationError,
    audit_registry,
    backup_registry,
    registry_status,
    update_registry,
)


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STORE = BACKEND_ROOT / "data" / "forecast_tracking"
DEFAULT_PHASE5C = BACKEND_ROOT / "data" / "market_cache" / "phase5b" / "snapshot_20261121T093632Z" / "phase5c_output" / "phase5c_evaluation.json"


def _common(command):
    command.add_argument("--registry", type=Path, default=DEFAULT_STORE / "forecast_registry.sqlite3")
    command.add_argument("--store-root", type=Path, default=DEFAULT_STORE)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    update = commands.add_parser("update", help="Download, validate, evaluate, and conditionally create forward forecasts")
    _common(update)
    update.add_argument("--phase5c-reference", type=Path, default=DEFAULT_PHASE5C)

    status = commands.add_parser("status", help="Show current registry counts and descriptive mature-outcome metrics")
    _common(status)

    backup = commands.add_parser("backup", help="Create and verify a consistent SQLite registry backup")
    _common(backup)

    audit = commands.add_parser("audit", help="Verify append-only controls, training cutoffs, and snapshot/artifact hashes")
    _common(audit)
    audit.add_argument("--phase5c-reference", type=Path, default=DEFAULT_PHASE5C)

    args = parser.parse_args(argv)
    try:
        if args.command == "update":
            result = update_registry(
                args.registry, args.store_root, args.phase5c_reference,
            )
        elif args.command == "status":
            result = registry_status(args.registry)
        elif args.command == "backup":
            result = backup_registry(args.registry, args.store_root / "backups")
        else:
            result = audit_registry(args.registry, args.phase5c_reference)
        print(json.dumps(result, indent=2, sort_keys=True))
        if args.command == "audit" and not result["valid"]:
            return 4
        return 0
    except SnapshotValidationError as exc:
        print(f"snapshot_rejected: {exc}", file=sys.stderr)
        return 2
    except DownloadWorkflowError as exc:
        print(f"download_failed: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"phase5e_failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
