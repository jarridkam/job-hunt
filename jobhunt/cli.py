"""Command line entry: jobhunt serve | fetch | score | email | apply <app_id>."""
from __future__ import annotations

import argparse
import sys

from . import db


def _serve_dev(port: int) -> int:
    """Dev mode: run the server as a child process and restart it whenever jobhunt/ changes.

    uvicorn's own --reload sends Ctrl+C to its worker, which is unreliable on Windows; a plain
    terminate() + respawn always works. Open browser tabs notice the new boot id via /api/status
    and reload themselves.
    """
    import subprocess
    from pathlib import Path

    from watchfiles import watch

    src = Path(__file__).resolve().parent
    cmd = [sys.executable, "-m", "jobhunt.cli", "serve", "--no-browser", "--port", str(port)]
    print("jobhunt: dev mode - restarts on .py/.html/.css change under jobhunt/; open tabs reload themselves")

    def _wanted(_change, path: str) -> bool:
        return path.endswith((".py", ".html", ".css")) and "__pycache__" not in path

    proc = subprocess.Popen(cmd)
    try:
        for changes in watch(src, watch_filter=_wanted, debounce=400):
            names = sorted({Path(p).name for _, p in changes})
            print(f"jobhunt: changed {', '.join(names)} - restarting")
            proc.terminate()
            proc.wait()
            proc = subprocess.Popen(cmd)
    except KeyboardInterrupt:
        pass
    finally:
        if proc.poll() is None:
            proc.terminate()
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="jobhunt")
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("serve", help="run the local web UI")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--host", default="127.0.0.1", help="0.0.0.0 inside the server container; keep the default on a PC")
    s.add_argument("--no-browser", action="store_true")
    s.add_argument("--dev", action="store_true", help="auto-restart when code changes (open pages reload themselves)")
    sub.add_parser("fetch", help="fetch jobs from all sources")
    sub.add_parser("score", help="LLM-score unscored jobs")
    sub.add_parser("email", help="sync inbox for assessments / status")
    sub.add_parser("set-password", help="set the web login password (needed on the server, where the setup page is closed)")
    a = sub.add_parser("apply", help="auto-apply to a queued application")
    a.add_argument("app_id", type=int)
    args = p.parse_args(argv)
    db.init_db()

    if args.cmd == "serve" or args.cmd is None:
        import threading
        import time
        import webbrowser
        from urllib.request import urlopen

        import uvicorn
        port = getattr(args, "port", 8765)
        url = f"http://127.0.0.1:{port}/"

        def _open_when_ready():
            # Poll until the server answers, so the browser never lands on a connection error.
            for _ in range(120):
                try:
                    with urlopen(url, timeout=1) as r:
                        if r.status == 200:
                            break
                except Exception:  # noqa: BLE001
                    time.sleep(0.25)
            webbrowser.open(url)

        if not getattr(args, "no_browser", False):
            threading.Thread(target=_open_when_ready, daemon=True).start()
        print(f"jobhunt: starting on {url} (Ctrl+C to stop)")
        if getattr(args, "dev", False):
            return _serve_dev(port)
        uvicorn.run("jobhunt.web.app:app", host=args.host, port=port, log_level="warning",
                    proxy_headers=True, forwarded_allow_ips="*" if args.host != "127.0.0.1" else "127.0.0.1")
        return 0

    def _run(kind, fn):
        rid = db.start_run(kind)
        try:
            out = fn(rid)
            db.finish_run(rid, str(out))
            print(out)
        except Exception as e:  # noqa: BLE001
            db.finish_run(rid, f"failed: {e}", failed=True)
            print("FAILED:", e, file=sys.stderr)
            return 1
        finally:
            print((db.q1("SELECT log FROM runs WHERE id=?", (rid,)) or {}).get("log", ""))
        return 0

    if args.cmd == "set-password":
        from getpass import getpass

        from .web import auth
        pw = getpass("New password (10+ characters): ")
        if len(pw) < 10 or pw != getpass("Again: "):
            print("Too short or didn't match; nothing changed.", file=sys.stderr)
            return 1
        auth.set_password(pw)
        print("Password set. Every device is logged out.")
        return 0
    if args.cmd == "fetch":
        from .pipeline import fetch_all
        return _run("fetch", fetch_all)
    if args.cmd == "score":
        from .matcher import score_pending
        return _run("score", score_pending)
    if args.cmd == "email":
        from .email_tracker import sync
        return _run("email", sync)
    if args.cmd == "apply":
        from .apply import apply_to
        return _run(f"apply-{args.app_id}", lambda rid: apply_to(args.app_id, rid).submitted)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
