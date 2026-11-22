"""Create and evaluate forward-only Phase 5D research forecasts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.research.forecast_tracking import (
    create_forward_predictions,
    evaluate_forward_outcomes,
    register_snapshot,
)


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STORE = BACKEND_ROOT / "data" / "forecast_tracking"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    for name in ("register-snapshot", "forecast", "evaluate"):
        command = commands.add_parser(name)
        command.add_argument("--input-dir", required=True, type=Path, help="Validated Yahoo market snapshot directory")
        command.add_argument("--store-root", type=Path, default=DEFAULT_STORE)
        command.add_argument("--registry", type=Path, default=DEFAULT_STORE / "forecast_registry.sqlite3")
        if name == "forecast":
            command.add_argument("--phase5c-reference", required=True, type=Path, help="Existing Phase 5C result JSON; read and hash only")

    args = parser.parse_args()
    if args.command == "register-snapshot":
        result = register_snapshot(args.input_dir, args.registry, args.store_root)
    elif args.command == "forecast":
        result = create_forward_predictions(
            args.input_dir, args.registry, args.store_root, args.phase5c_reference,
        )
    else:
        result = evaluate_forward_outcomes(args.input_dir, args.registry, args.store_root)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
