"""One-command launcher for Career Context Studio v2.

Initializes the SQLite vault if needed (defaulting to ~/.career-context/career.sqlite
safely outside any git repository), detects `.semantic-model` automatically,
picks a free localhost port if 8765 is busy, and optionally opens the browser.
"""
from __future__ import annotations

import argparse
import tempfile
import threading
import time
import webbrowser
from pathlib import Path

from .db import CareerVault
from .server import create_server

DEFAULT_DB_PATH = Path.home() / ".career-context" / "career.sqlite"


def _is_inside_git_repo(path: Path) -> bool:
    for parent in [path.parent, *path.parent.parents]:
        if (parent / ".git").exists():
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Launch Career Context Studio v2 in your browser")
    p.add_argument(
        "db",
        nargs="?",
        default=None,
        help=f"Path to local SQLite career vault (default: {DEFAULT_DB_PATH})",
    )
    p.add_argument("--port", type=int, default=8765, help="Preferred localhost port (auto-falls back if busy)")
    p.add_argument("--name", default="", help="Initial name if creating a new vault")
    p.add_argument("--model-dir", default=None, help="Optional path to local .semantic-model directory")
    p.add_argument("--demo", action="store_true", help="Launch in a temporary fictional sample vault")
    p.add_argument("--open", dest="open_browser", action="store_true", help="Open browser automatically")
    args = p.parse_args(argv)

    tmp_ctx = None
    if args.demo:
        tmp_ctx = tempfile.TemporaryDirectory(prefix="career-context-demo-")
        db_path = Path(tmp_ctx.name) / "sample-vault.sqlite"
        with CareerVault(db_path) as v:
            v.seed_demo_vault(force=True)
        print("Loaded fictional sample vault (temporary session — nothing saved to your real vault).", flush=True)
    else:
        db_path = Path(args.db).expanduser().resolve() if args.db else DEFAULT_DB_PATH.resolve()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        if _is_inside_git_repo(db_path):
            print(
                f"Notice: {db_path} is inside a git repository. Keep private vaults outside git or verify *.sqlite* is gitignored.",
                flush=True,
            )
        if not db_path.exists():
            with CareerVault(db_path) as v:
                v.init(name=args.name)

    srv = None
    vault = None
    last_err: OSError | None = None
    for candidate_port in range(args.port, args.port + 20):
        try:
            srv, _token, vault = create_server(db_path, port=candidate_port, model_dir=args.model_dir)
            break
        except OSError as exc:
            last_err = exc
    if srv is None or vault is None:
        raise RuntimeError(f"Could not bind any localhost port in {args.port}..{args.port + 19}: {last_err}")

    host, port = srv.server_address
    url = f"http://{host}:{port}/"
    if port != args.port:
        print(f"Port {args.port} was busy; using {port} instead.", flush=True)
    print(f"Career Context Studio v2 ready at {url}", flush=True)
    print(f"Database: {db_path}", flush=True)

    if args.open_browser:
        threading.Thread(target=lambda: (time.sleep(0.4), webbrowser.open(url)), daemon=True).start()

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
        vault.close()
        if tmp_ctx is not None:
            tmp_ctx.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
