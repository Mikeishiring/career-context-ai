"""One-command launcher for Career Context Studio v2.

Initializes the SQLite vault if needed, detects `.semantic-model` automatically,
starts the localhost server, and optionally opens the default browser.
"""
from __future__ import annotations

import argparse
import threading
import time
import webbrowser
from pathlib import Path

from .db import CareerVault
from .server import create_server


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Launch Career Context Studio v2 in your browser")
    p.add_argument("db", help="Path to local SQLite career vault (created if missing)")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--name", default="", help="Initial name if creating a new vault")
    p.add_argument("--model-dir", default=None, help="Optional path to local .semantic-model directory")
    p.add_argument("--open", dest="open_browser", action="store_true", help="Open browser automatically")
    args = p.parse_args(argv)

    db_path = Path(args.db).expanduser().resolve()
    if not db_path.exists():
        with CareerVault(db_path) as v:
            v.init(name=args.name)

    srv, _token, vault = create_server(db_path, port=args.port, model_dir=args.model_dir)
    host, port = srv.server_address
    url = f"http://{host}:{port}/"
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
