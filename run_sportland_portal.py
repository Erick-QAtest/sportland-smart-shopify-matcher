from __future__ import annotations

import argparse
import hmac
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import webbrowser
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv

from smart_memory.config import MemoryConfig
from smart_memory.db import connect
from smart_portal.portal_v60 import (
    collect_status,
    render_customer_route,
    render_demand,
    render_memory,
    serve_artifact_page,
)
from smart_portal.centro_decisiones_v62 import (
    render_centro_hoy,
    render_recomendaciones,
)
from smart_commerce.amazon_v62 import render_amazon
from smart_commerce.marketing_v62 import render_calendario, render_whatsapp
from smart_portal.finanzas_proyeccion_v63 import render_finanzas_proyeccion
from smart_portal.auth_v70 import (
    AuthConfig,
    clear_session_cookie,
    issue_session,
    login_page,
    session_cookie,
    verify_password,
    verify_session,
)
from smart_portal.finanzas_captura_v73 import (
    SAVERS as FINANZAS_SAVERS,
    render_finanzas_captura,
)
from smart_portal.registro_v72 import (
    guardar_registro,
    parse_rows,
    render_registro,
)
from smart_portal.impacto_v71 import (
    make_csrf,
    registrar_estado,
    registrar_resultado,
    render_impacto,
    render_recomendacion_impacto,
    verify_csrf,
)


CUSTOMER_ROUTES = {
    "/customer-intelligence",
    "/customers",
    "/customer",
    "/sizes",
    "/brands",
    "/segments",
    "/opportunities",
}


def build_handler(cfg: MemoryConfig, project_root: Path, auth_cfg: AuthConfig):
    class Handler(BaseHTTPRequestHandler):
        server_version = "SportlandSmartPortal/7.1"

        def send_html(
            self,
            body: str,
            status: int = 200,
            extra_headers: dict[str, str] | None = None,
        ) -> None:
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                "script-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                "font-src 'self' data:; connect-src 'self'; "
                "frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
            )
            if extra_headers:
                for key, value in extra_headers.items():
                    self.send_header(key, value)
            self.end_headers()
            self.wfile.write(payload)

        def redirect(
            self,
            location: str,
            *,
            cookie: str | None = None,
        ) -> None:
            self.send_response(303)
            self.send_header("Location", location)
            self.send_header("Cache-Control", "no-store")
            if cookie:
                self.send_header("Set-Cookie", cookie)
            self.end_headers()

        def _session_token(self) -> str:
            raw = self.headers.get("Cookie", "")
            if not raw:
                return ""
            try:
                cookie = SimpleCookie()
                cookie.load(raw)
                morsel = cookie.get("sportland_session")
                return morsel.value if morsel else ""
            except Exception:
                return ""

        def _authenticated(self) -> bool:
            if not auth_cfg.enabled:
                return True
            return verify_session(
                auth_cfg,
                self._session_token(),
            ) is not None

        def _csrf_token(self) -> str:
            return make_csrf(
                auth_cfg.session_secret,
                self._session_token(),
            )

        def _csrf_valid(self, token: str) -> bool:
            return verify_csrf(
                auth_cfg.session_secret,
                self._session_token(),
                token,
            )

        def _require_auth(self, route: str) -> bool:
            if not auth_cfg.enabled:
                return True
            if route in {"/login", "/salud"}:
                return True
            if self._authenticated():
                return True
            from urllib.parse import quote
            siguiente = self.path if self.path.startswith("/") else "/"
            self.redirect(
                "/login?siguiente=" + quote(siguiente, safe="/?=&")
            )
            return False

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            route = parsed.path.rstrip("/") or "/"
            query = parse_qs(parsed.query)

            if route == "/salud":
                self.send_html(
                    "<!doctype html><html><body>OK</body></html>"
                )
                return

            if route == "/login":
                if auth_cfg.enabled and self._authenticated():
                    self.redirect("/")
                    return
                siguiente = (query.get("siguiente") or ["/"])[0]
                self.send_html(login_page(siguiente=siguiente))
                return

            if route == "/salir":
                self.redirect(
                    "/login" if auth_cfg.enabled else "/",
                    cookie=clear_session_cookie(auth_cfg),
                )
                return

            if not self._require_auth(route):
                return

            try:
                if route in {"/", "/hoy", "/today"}:
                    with connect(cfg) as conn:
                        self.send_html(render_centro_hoy(conn, project_root))
                    return

                if route in {"/recomendaciones", "/recommendations"}:
                    with connect(cfg) as conn:
                        self.send_html(render_recomendaciones(conn, project_root))
                    return

                if route == "/impacto":
                    with connect(cfg) as conn:
                        self.send_html(render_impacto(conn))
                    return

                if route == "/finanzas/captura":
                    def _count(name: str) -> int:
                        raw = (query.get(name) or ["0"])[0]
                        return int(raw) if raw.isdigit() else 0
                    saved = {"nuevos": _count("nuevos"), "cambios": _count("cambios")} if query.get("guardado") else None
                    with connect(cfg) as conn:
                        self.send_html(render_finanzas_captura(conn, csrf_token=self._csrf_token(), saved=saved))
                    return

                if route == "/registro":
                    saved = (query.get("guardados") or [None])[0]
                    with connect(cfg) as conn:
                        self.send_html(
                            render_registro(
                                conn,
                                csrf_token=self._csrf_token(),
                                saved=int(saved) if saved and saved.isdigit() else None,
                                duplicates=int((query.get("duplicados") or ["0"])[0] or 0),
                                new_customers=int((query.get("nuevos") or ["0"])[0] or 0),
                            )
                        )
                    return

                if route == "/impacto/recomendacion":
                    raw_id = (query.get("id") or ["0"])[0]
                    try:
                        recommendation_id = int(raw_id)
                    except ValueError:
                        recommendation_id = 0
                    with connect(cfg) as conn:
                        self.send_html(
                            render_recomendacion_impacto(
                                conn,
                                recommendation_id,
                                csrf_token=self._csrf_token(),
                            )
                        )
                    return

                if route == "/amazon":
                    with connect(cfg) as conn:
                        self.send_html(render_amazon(conn))
                    return

                if route == "/marketing":
                    with connect(cfg) as conn:
                        self.send_html(render_calendario(conn))
                    return

                if route == "/whatsapp-borradores":
                    with connect(cfg) as conn:
                        self.send_html(render_whatsapp(conn))
                    return

                if route in CUSTOMER_ROUTES:
                    with connect(cfg) as conn:
                        self.send_html(render_customer_route(conn, route, query))
                    return

                if route == "/memory":
                    with connect(cfg) as conn:
                        self.send_html(render_memory(conn))
                    return

                if route == "/demand":
                    with connect(cfg) as conn:
                        self.send_html(render_demand(conn))
                    return

                if route == "/finance":
                    self.send_html(render_finanzas_proyeccion(project_root))
                    return

                if route == "/finance/reporte":
                    self.send_html(
                        serve_artifact_page(
                            project_root,
                            "artifacts/finance_dashboard.html",
                            "Finanzas",
                        )
                    )
                    return

                if route == "/growth":
                    self.send_html(
                        serve_artifact_page(
                            project_root,
                            "artifacts/growth_priority_dashboard_v41.html",
                            "Growth Priority",
                        )
                    )
                    return

                if route == "/growth/performance":
                    self.send_html(
                        serve_artifact_page(
                            project_root,
                            "artifacts/growth_performance_dashboard_v41.html",
                            "Growth Performance",
                        )
                    )
                    return

                if route in {"/ops", "/health"}:
                    self.send_html(
                        serve_artifact_page(
                            project_root,
                            "artifacts/ops_health_dashboard.html",
                            "Ops Health",
                        )
                    )
                    return

                self.send_html(
                    "<!doctype html><html><body style='font-family:system-ui;padding:30px'><h1>404</h1><p>Ruta no encontrada.</p><p><a href='/'>Volver al Portal</a></p></body></html>",
                    status=404,
                )

            except Exception as exc:
                print(f"[portal] request failed: {type(exc).__name__}: {exc}")
                self.send_html(
                    "<!doctype html><html><body style='font-family:system-ui;padding:30px'><h1>Sportland Smart</h1><p>No se pudo cargar este módulo.</p><p>Revisa la terminal del portal para ver el error.</p><p><a href='/'>Volver al Portal</a></p></body></html>",
                    status=500,
                )

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            route = parsed.path.rstrip("/") or "/"

            body_limit = 262144 if route == "/registro" or route.startswith("/finanzas/captura/") else 16384
            try:
                length = min(
                    int(self.headers.get("Content-Length", "0") or 0),
                    body_limit,
                )
            except ValueError:
                length = 0

            raw = self.rfile.read(length).decode("utf-8", errors="replace")
            form = parse_qs(raw)

            if route == "/login":
                if not auth_cfg.enabled:
                    self.redirect("/")
                    return

                usuario = (form.get("usuario") or [""])[0]
                contrasena = (form.get("contrasena") or [""])[0]
                siguiente = (form.get("siguiente") or ["/"])[0]

                if not siguiente.startswith("/") or siguiente.startswith("//"):
                    siguiente = "/"

                ok_user = (
                    hmac.compare_digest(usuario, auth_cfg.username)
                    if usuario and auth_cfg.username
                    else False
                )

                if ok_user and verify_password(
                    contrasena,
                    auth_cfg.password_hash,
                ):
                    token = issue_session(auth_cfg, auth_cfg.username)
                    self.redirect(
                        siguiente,
                        cookie=session_cookie(auth_cfg, token),
                    )
                    return

                self.send_html(
                    login_page(
                        error="Usuario o contraseña incorrectos.",
                        siguiente=siguiente,
                    ),
                    status=401,
                )
                return

            if not self._require_auth(route):
                return

            finanzas_section = route.removeprefix("/finanzas/captura/") if route.startswith("/finanzas/captura/") else None
            if route not in {"/impacto/estado", "/impacto/resultado", "/registro"} and finanzas_section not in FINANZAS_SAVERS:
                self.send_html(
                    "<!doctype html><html><body><h1>405</h1><p>Método no permitido.</p></body></html>",
                    status=405,
                )
                return

            csrf = (form.get("csrf") or [""])[0]
            if not self._csrf_valid(csrf):
                self.send_html(
                    "<!doctype html><html><body><h1>403</h1><p>Solicitud no válida.</p><p><a href='/impacto'>Volver a Impacto</a></p></body></html>",
                    status=403,
                )
                return

            if route == "/registro":
                self._handle_registro(form)
                return

            if finanzas_section in FINANZAS_SAVERS:
                self._handle_finanzas(finanzas_section, form)
                return

            try:
                recommendation_id = int((form.get("id") or ["0"])[0])
            except ValueError:
                recommendation_id = 0

            try:
                with connect(cfg) as conn:
                    if route == "/impacto/estado":
                        registrar_estado(
                            conn,
                            recommendation_id,
                            status=(form.get("status") or [""])[0],
                            notes=(form.get("notes") or [""])[0],
                        )
                    else:
                        registrar_resultado(
                            conn,
                            recommendation_id,
                            outcome=(form.get("outcome") or [""])[0],
                            attribution_method=(form.get("attribution_method") or [""])[0],
                            attribution_confidence=(form.get("attribution_confidence") or [""])[0],
                            attributed_revenue=(form.get("attributed_revenue") or ["0"])[0],
                            attributed_margin=(form.get("attributed_margin") or ["0"])[0],
                            avoided_cost=(form.get("avoided_cost") or ["0"])[0],
                            hours_saved=(form.get("hours_saved") or ["0"])[0],
                            hourly_value=(form.get("hourly_value") or ["0"])[0],
                            evidence_reference=(form.get("evidence_reference") or [""])[0],
                            notes=(form.get("notes") or [""])[0],
                        )
                self.redirect(f"/impacto/recomendacion?id={recommendation_id}")
            except Exception as exc:
                print(f"[portal] impact update failed: {type(exc).__name__}: {exc}")
                self.send_html(
                    "<!doctype html><html><body style='font-family:system-ui;padding:30px'><h1>Sportland Smart</h1><p>No se pudo guardar el seguimiento.</p><p>Revisa la terminal del portal para ver el error.</p><p><a href='/impacto'>Volver a Impacto</a></p></body></html>",
                    status=400,
                )

        def _handle_registro(self, form: dict[str, list[str]]) -> None:
            rows = parse_rows(form)
            actor = auth_cfg.username if auth_cfg.enabled and auth_cfg.username else "portal"
            try:
                with connect(cfg) as conn:
                    summary = guardar_registro(conn, rows, actor=actor)
                    if not any(result.errors for result in summary["results"]):
                        # Post/Redirect/Get: recargar la página no vuelve a enviar el lote.
                        self.redirect(
                            f"/registro?guardados={summary['saved']}"
                            f"&duplicados={summary['duplicates']}&nuevos={summary['new_customers']}"
                        )
                        return
                    self.send_html(
                        render_registro(
                            conn,
                            csrf_token=self._csrf_token(),
                            results=summary["results"],
                            rows=rows,
                        ),
                        status=400,
                    )
            except Exception as exc:
                print(f"[portal] registro failed: {type(exc).__name__}: {exc}")
                self.send_html(
                    "<!doctype html><html><body style='font-family:system-ui;padding:30px'><h1>Sportland Smart</h1><p>No se pudo guardar el registro. No se guardó ningún evento.</p><p>Revisa la terminal del portal para ver el error.</p><p><a href='/registro'>Volver al Registro del día</a></p></body></html>",
                    status=500,
                )

        def _handle_finanzas(self, section: str, form: dict[str, list[str]]) -> None:
            actor = auth_cfg.username if auth_cfg.enabled and auth_cfg.username else "portal"
            try:
                with connect(cfg) as conn:
                    result = FINANZAS_SAVERS[section](conn, form, actor=actor)
                    if result.ok:
                        self.redirect(
                            f"/finanzas/captura?guardado={section}&nuevos={result.inserted}&cambios={result.updated}#{section}"
                        )
                        return
                    self.send_html(
                        render_finanzas_captura(conn, csrf_token=self._csrf_token(), section=section, result=result, form=form),
                        status=400,
                    )
            except Exception as exc:
                print(f"[portal] finanzas {section} failed: {type(exc).__name__}: {exc}")
                self.send_html(
                    "<!doctype html><html><body style='font-family:system-ui;padding:30px'><h1>Sportland Smart</h1><p>No se pudo guardar. No se cambió nada.</p><p><a href='/finanzas/captura'>Volver a Captura de finanzas</a></p></body></html>",
                    status=500,
                )

        def log_message(self, fmt: str, *args) -> None:
            print("[portal]", fmt % args)

    return Handler


def main() -> int:
    project_root = Path(__file__).resolve().parent
    load_dotenv(project_root / ".env")
    load_dotenv(project_root / ".env.portal", override=True)

    parser = argparse.ArgumentParser(
        description="Sportland Smart Portal Administrativo v7.1"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8700)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()

    if args.host not in {"127.0.0.1", "localhost"}:
        print("SECURITY ERROR: Sportland Smart Portal only binds to localhost.")
        return 2

    cfg = MemoryConfig.from_env(str(project_root / ".env"))
    errors = cfg.validate()
    if errors:
        print("ERROR DE CONFIGURACIÓN:", "; ".join(errors))
        return 2

    auth_cfg = AuthConfig.from_env()
    auth_errors = auth_cfg.validate()
    if auth_errors:
        print("ERROR DE ACCESO:", "; ".join(auth_errors))
        return 2

    with connect(cfg) as conn:
        conn.execute("SELECT 1").fetchone()
        conn.execute("SELECT COUNT(*) FROM customers").fetchone()

    server = ThreadingHTTPServer(
        (args.host, args.port),
        build_handler(cfg, project_root, auth_cfg),
    )

    url = f"http://127.0.0.1:{args.port}/"
    print("")
    print("Sportland Smart Portal Administrativo v7.1")
    print(f"Portal: {url}")
    print("Red: aplicación enlazada solo a localhost; acceso externo únicamente mediante proxy HTTPS")
    print("Datos personales: protegidos por autenticación cuando SPORTLAND_AUTH_ENABLED=true")
    print("Escrituras en Shopify: ninguna")
    print("Contacto automático con clientes: desactivado")
    print(f"Autenticación: {'ACTIVA' if auth_cfg.enabled else 'DESACTIVADA'}")
    print("Detener: Ctrl+C")
    print("")

    if not args.no_open:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nPortal Sportland Smart detenido.")
    finally:
        server.server_close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
