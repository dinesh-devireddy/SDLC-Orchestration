"""Local commands; demo is the default and never constructs a provider client."""

import argparse
import json
from pathlib import Path

from .runner import DEFAULT_ROOT, RunManager


def main():
    parser = argparse.ArgumentParser(description="Governed SDLC lifecycle")
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_ROOT)
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start")
    start.add_argument("requirement")
    start.add_argument("--mode", choices=["demo", "live"], default="demo")
    start.add_argument("--scenario", choices=["greenfield", "brownfield", "ambiguous", "repair", "failure", "retry"], default="greenfield")
    start.add_argument("--source", type=Path)
    start.add_argument("--test-python", type=Path, help="Trusted Python environment with service test dependencies installed")
    for name in ("show", "stop"):
        commands.add_parser(name).add_argument("run_id")
    commands.add_parser("list")
    commands.add_parser("metrics")
    resume = commands.add_parser("resume")
    resume.add_argument("run_id")
    resume.add_argument("--action", choices=["approve", "reject", "revise", "clarify", "stop"], required=True)
    resume.add_argument("--actor", required=True)
    resume.add_argument("--note", required=True)
    resume.add_argument("--digest", default="")
    resume.add_argument("--requirement", default="")
    resume.add_argument("--execute-tests", action="store_true", help="Authorize execution of repository Python on this machine; not an OS sandbox")
    args = parser.parse_args()
    manager = RunManager(args.runs_dir)
    try:
        if args.command == "start":
            result = manager.start(args.requirement, mode=args.mode, scenario=args.scenario, source=args.source,
                                   test_python=args.test_python)
        elif args.command == "resume":
            result = manager.resume(args.run_id, {"action": args.action, "actor": args.actor,
                                    "note": args.note, "expected_digest": args.digest,
                                    "requirement": args.requirement, "execute_tests": args.execute_tests})
        elif args.command == "show":
            result = manager.view(args.run_id)
        elif args.command == "stop":
            result = manager.stop(args.run_id)
        elif args.command == "list":
            result = [{"run_id": r["run_id"], "status": r["status"]} for r in manager.list_runs()]
        else:
            result = manager.metrics()
        print(json.dumps(result, indent=2))
        return 0
    except Exception as error:
        print(f"Command failed ({type(error).__name__}). Check arguments, configuration, or the run's RUNNING lock.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
