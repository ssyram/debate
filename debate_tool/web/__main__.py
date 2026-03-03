"""Entry point: python -m debate_tool.web"""
from __future__ import annotations

import argparse
import sys
import threading
import time
import webbrowser


def main() -> None:
    parser = argparse.ArgumentParser(description="辩论议题向导 — Web 版")
    parser.add_argument("--port", "-p", type=int, default=5000, help="端口 (默认 5000)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="绑定地址")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--debug", action="store_true", help="Flask debug 模式")
    args = parser.parse_args()

    from debate_tool.web.app import create_app

    app = create_app()

    url = f"http://{args.host}:{args.port}"
    if not args.no_browser:
        def _open():
            time.sleep(1.0)
            webbrowser.open(url)
        threading.Thread(target=_open, daemon=True).start()

    print(f"\n  辩论议题向导 (Web)\n  {url}\n")
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
