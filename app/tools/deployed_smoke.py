"""Run deployed-service smoke checks from explicit environment configuration."""

from __future__ import annotations

import argparse
import json

from app.services.deployed_smoke import run_deployed_smokes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=("all", "auth", "survey", "map", "recommendation", "chat"),
        default="all",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    results = run_deployed_smokes(mode=args.mode)
    if args.json:
        print(json.dumps([item.to_dict() for item in results], sort_keys=True))
    else:
        for item in results:
            print(
                "deployed smoke "
                f"name={item.name} status={item.status} detail={item.detail}",
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
