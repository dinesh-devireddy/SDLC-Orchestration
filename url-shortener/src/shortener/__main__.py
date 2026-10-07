import argparse
import sys

from .config import Settings
from .database import check_ready, initialize, make_engine


def main():
    parser = argparse.ArgumentParser(description="Local SQLite URL shortener")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db", help="Create directories and apply migrations without deleting data")
    serve = sub.add_parser("serve", help="Serve an initialized database")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    try:
        settings = Settings.from_env()
        if args.command == "init-db":
            initialize(settings)
            print(f"Database ready: {settings.database_path}")
        else:
            engine = make_engine(settings)
            try:
                check_ready(engine, settings)
            finally:
                engine.dispose()
            import uvicorn
            from .api import create_app
            uvicorn.run(create_app(settings), host=args.host, port=args.port, access_log=False)
        return 0
    except Exception:
        print("Unable to initialize/start. Check configuration, database permissions and locks; run python -m shortener init-db before serve.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
