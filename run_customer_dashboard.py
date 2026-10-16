from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import webbrowser
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv

from smart_customer.dashboard_v51 import (
    fetch_brand_distribution,
    fetch_customer_360,
    fetch_opportunities,
    fetch_overview,
    fetch_segments,
    fetch_size_distribution,
    render_brands,
    render_customer_360,
    render_customers,
    render_opportunities,
    render_overview,
    render_segments,
    render_sizes,
    search_customers,
)
from smart_memory.config import MemoryConfig
from smart_memory.db import connect


def build_handler(cfg: MemoryConfig):
    class Handler(BaseHTTPRequestHandler):
        server_version = "SportlandCustomerDashboard/5.1"

        def _html(self, body: str, status: int = 200) -> None:
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)

            try:
                with connect(cfg) as conn:
                    if parsed.path == "/":
                        self._html(render_overview(fetch_overview(conn)))
                        return

                    if parsed.path == "/sizes":
                        self._html(render_sizes(fetch_size_distribution(conn)))
                        return

                    if parsed.path == "/brands":
                        self._html(render_brands(fetch_brand_distribution(conn)))
                        return

                    if parsed.path == "/segments":
                        self._html(render_segments(fetch_segments(conn)))
                        return

                    if parsed.path == "/customers":
                        q = (qs.get("q") or [""])[0]
                        size = (qs.get("size") or [""])[0]
                        segment = (qs.get("segment") or [""])[0]
                        rows = search_customers(
                            conn,
                            q=q,
                            size=size,
                            segment=segment,
                            limit=100,
                        )
                        self._html(
                            render_customers(
                                rows,
                                q=q,
                                size=size,
                                segment=segment,
                            )
                        )
                        return

                    if parsed.path == "/customer":
                        raw = (qs.get("customer_id") or [""])[0]
                        try:
                            customer_id = int(raw)
                        except ValueError:
                            self._html(
                                "<h1>customer_id inválido</h1>",
                                status=400,
                            )
                            return
                        self._html(render_customer_360(fetch_customer_360(conn, customer_id)))
                        return

                    if parsed.path == "/opportunities":
                        priority = (qs.get("priority") or [""])[0].upper()
                        self._html(
                            render_opportunities(
                                fetch_opportunities(conn, priority=priority),
                                priority=priority,
                            )
                        )
                        return

                self._html("<h1>404</h1>", status=404)

            except Exception as exc:
                # Error is shown locally, but never emit environment variables or credentials.
                self._html(
                    f"""<!doctype html><html><body style="font-family:system-ui;padding:30px">
                    <h1>Customer Intelligence Dashboard</h1>
                    <p>No se pudo leer la base local.</p>
                    <pre>{str(exc)[:1000]}</pre>
                    </body></html>""",
                    status=500,
                )

        def log_message(self, fmt: str, *args) -> None:
            print("[dashboard]", fmt % args)

    return Handler


def main() -> int:
    load_dotenv(".env")

    parser = argparse.ArgumentParser(
        description="Sportland Smart — Customer Intelligence Dashboard v5.1"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()

    # Safety: do not expose CRM PII to the LAN by accident.
    if args.host not in {"127.0.0.1", "localhost"}:
        print("SECURITY ERROR: Customer dashboard only binds to localhost.")
        return 2

    cfg = MemoryConfig.from_env()
    errors = cfg.validate()
    if errors:
        print("CONFIG ERROR:", "; ".join(errors))
        return 2

    # Fail fast before starting the server.
    with connect(cfg) as conn:
        conn.execute("SELECT 1").fetchone()
        conn.execute("SELECT COUNT(*) FROM customer_sync_runs").fetchone()

    server = ThreadingHTTPServer((args.host, args.port), build_handler(cfg))
    url = f"http://127.0.0.1:{args.port}/"

    print("")
    print("Sportland Smart — Customer Intelligence Dashboard v5.1")
    print(f"Local URL: {url}")
    print("PII policy: local browser only; no PII artifact generated.")
    print("Shopify: no writes. Customer contact: disabled.")
    print("Stop: Ctrl+C")
    print("")

    if not args.no_open:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
