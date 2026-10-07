"""CLI: load configuration, invoke the graph once, print the final shared state."""

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from .errors import describe_error
from .llm import llm_from_environment
from .workflow import run_workflow


def main() -> int:
    parser = argparse.ArgumentParser(description="Produce a draft engineering plan")
    parser.add_argument("requirement", nargs="?", default="Add expiration support to shortened URLs.")
    args = parser.parse_args()
    # Only read .env in the current directory; existing environment values win.
    load_dotenv(Path.cwd() / ".env", override=False)
    try:
        if not args.requirement.strip():
            raise ValueError("Requirement must not be blank")
        llm = llm_from_environment()
    except ValueError as error:
        print(f"Configuration/input error: {error}", file=sys.stderr)
        return 2
    try:
        state = run_workflow(args.requirement, llm)
    except Exception as error:
        # Provider errors may contain request data. Do not echo raw responses/keys.
        print(
            describe_error(error) + " No automatic retry was attempted.",
            file=sys.stderr,
        )
        return 1
    print(state.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
