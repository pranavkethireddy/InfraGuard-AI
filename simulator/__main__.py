"""Run from repository root: python3 -m simulator --help."""

import argparse
from datetime import datetime
import json
import sys

from . import SCENARIOS, readings_payload
from .client import SimulationAPIError, SimulationClient


def main(argv=None):
    parser = argparse.ArgumentParser(description="Preview seeded readings or control backend-managed demo simulations.")
    parser.add_argument("--base-url", default="http://localhost:8000/api/v1", help="Backend API base URL (no credentials)")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("preview", "start"):
        p = commands.add_parser(name)
        p.add_argument("--scenario", choices=SCENARIOS, default="normal")
        p.add_argument("--seed", type=int, default=42)
        p.add_argument("--asset-id", default="cooling-01")
        if name == "preview":
            p.add_argument("--simulation-id", default="sim-preview")
            p.add_argument("--start-at", required=True, help="Timezone-aware ISO timestamp; preview only, never sent")
            p.add_argument("--tick-seconds", type=float, default=2.0)
    for name in ("status", "reset"):
        p = commands.add_parser(name)
        p.add_argument("simulation_id")
    p = commands.add_parser("list", help="Find backend runs, including recovery after restarting the CLI")
    p.add_argument("--status", choices=("running", "completed", "reset"))
    p.add_argument("--asset-id")
    args = parser.parse_args(argv)
    try:
        if args.command == "preview":
            result = readings_payload(
                args.scenario, args.seed, args.asset_id, args.simulation_id,
                datetime.fromisoformat(args.start_at.replace("Z", "+00:00")), args.tick_seconds,
            )
        else:
            client = SimulationClient(args.base_url)
            if args.command == "start":
                result = client.start(args.scenario, args.seed, args.asset_id)
            elif args.command == "list":
                result = client.list_runs(status=args.status, asset_id=args.asset_id)
            else:
                result = getattr(client, args.command)(args.simulation_id)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except (ValueError, SimulationAPIError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
