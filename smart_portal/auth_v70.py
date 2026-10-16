from __future__ import annotations

from dataclasses import dataclass
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any


HASH_NAME = "pbkdf2_sha256"
HASH_ITERATIONS = 390_000


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64d(value: str) -> bytes:
    raw = value.encode("ascii")
    raw += b"=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(raw)


def hash_password(password: str, *, iterations: int = HASH_ITERATIONS) -> str:
    if len(password) < 10:
        raise ValueError("La contraseña debe tener al menos 10 caracteres.")
    salt = secrets.token_bytes(18)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return f"{HASH_NAME}${iterations}${_b64e(salt)}${_b64e(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        name, iterations_raw, salt_raw, digest_raw = encoded.split("$", 3)
        if name != HASH_NAME:
            return False
        iterations = int(iterations_raw)
        salt = _b64d(salt_raw)
        expected = _b64d(digest_raw)
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
        )
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


@dataclass(frozen=True)
class AuthConfig:
    enabled: bool
    username: str
    password_hash: str
    session_secret: str
    session_hours: int = 12
    cookie_secure: bool = True

    @classmethod
    def from_env(cls) -> "AuthConfig":
        enabled = str(
            os.getenv("SPORTLAND_AUTH_ENABLED", "false")
        ).strip().lower() in {"1", "true", "yes", "si", "sí", "on"}

        secure = str(
            os.getenv("SPORTLAND_COOKIE_SECURE", "true")
        ).strip().lower() in {"1", "true", "yes", "si", "sí", "on"}

        try:
            hours = int(os.getenv("SPORTLAND_SESSION_HOURS", "12"))
        except ValueError:
            hours = 12

        return cls(
            enabled=enabled,
            username=os.getenv("SPORTLAND_ADMIN_USER", "").strip(),
            password_hash=os.getenv(
                "SPORTLAND_ADMIN_PASSWORD_HASH", ""
            ).strip(),
            session_secret=os.getenv(
                "SPORTLAND_SESSION_SECRET", ""
            ).strip(),
            session_hours=max(1, min(hours, 72)),
            cookie_secure=secure,
        )

    def validate(self) -> list[str]:
        if not self.enabled:
            return []
        errors = []
        if not self.username:
            errors.append("falta SPORTLAND_ADMIN_USER")
        if not self.password_hash:
            errors.append("falta SPORTLAND_ADMIN_PASSWORD_HASH")
        if not self.session_secret or len(self.session_secret) < 32:
            errors.append("SPORTLAND_SESSION_SECRET no es válido")
        return errors


def issue_session(
    cfg: AuthConfig,
    username: str,
    *,
    now: int | None = None,
) -> str:
    now = int(time.time() if now is None else now)
    payload = {
        "u": username,
        "iat": now,
        "exp": now + cfg.session_hours * 3600,
    }
    body = _b64e(
        json.dumps(
            payload,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    )
    sig = _b64e(
        hmac.new(
            cfg.session_secret.encode("utf-8"),
            body.encode("ascii"),
            hashlib.sha256,
        ).digest()
    )
    return f"{body}.{sig}"


def verify_session(
    cfg: AuthConfig,
    token: str,
    *,
    now: int | None = None,
) -> str | None:
    try:
        body, sig = token.split(".", 1)
        expected = _b64e(
            hmac.new(
                cfg.session_secret.encode("utf-8"),
                body.encode("ascii"),
                hashlib.sha256,
            ).digest()
        )
        if not hmac.compare_digest(sig, expected):
            return None

        payload: dict[str, Any] = json.loads(
            _b64d(body).decode("utf-8")
        )
        current = int(time.time() if now is None else now)
        if int(payload.get("exp", 0)) < current:
            return None

        username = str(payload.get("u", ""))
        if not hmac.compare_digest(username, cfg.username):
            return None
        return username
    except Exception:
        return None


def session_cookie(cfg: AuthConfig, token: str) -> str:
    parts = [
        f"sportland_session={token}",
        "Path=/",
        "HttpOnly",
        "SameSite=Lax",
        f"Max-Age={cfg.session_hours * 3600}",
    ]
    if cfg.cookie_secure:
        parts.append("Secure")
    return "; ".join(parts)


def clear_session_cookie(cfg: AuthConfig) -> str:
    parts = [
        "sportland_session=",
        "Path=/",
        "HttpOnly",
        "SameSite=Lax",
        "Max-Age=0",
    ]
    if cfg.cookie_secure:
        parts.append("Secure")
    return "; ".join(parts)


def login_page(*, error: str = "", siguiente: str = "/") -> str:
    error_html = (
        f'<div class="error">{_escape(error)}</div>'
        if error else ""
    )
    safe_next = siguiente if siguiente.startswith("/") else "/"

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Acceso · Sportland Smart</title>
<style>
:root{{--navy:#071b33;--line:#e4e7ec;--muted:#667085}}
*{{box-sizing:border-box}}
body{{margin:0;min-height:100vh;display:grid;place-items:center;background:linear-gradient(145deg,#eef4fb,#f8fafc);font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#101828;padding:20px}}
.card{{width:min(430px,100%);background:#fff;border:1px solid var(--line);border-radius:24px;padding:28px;box-shadow:0 24px 70px rgba(7,27,51,.12)}}
.brand{{display:flex;gap:13px;align-items:center;margin-bottom:24px}}
.mark{{width:48px;height:48px;border-radius:15px;background:var(--navy);color:white;display:grid;place-items:center;font-size:22px;font-weight:950}}
h1{{font-size:23px;margin:0}} .sub{{font-size:12px;color:var(--muted);margin-top:4px}}
label{{display:block;font-size:12px;font-weight:800;margin:15px 0 6px}}
input{{width:100%;padding:12px 13px;border:1px solid #d0d5dd;border-radius:11px;font-size:14px;outline:none}}
input:focus{{border-color:#84adff;box-shadow:0 0 0 3px #eff4ff}}
button{{width:100%;border:0;background:var(--navy);color:white;padding:12px 14px;border-radius:11px;margin-top:19px;font-size:13px;font-weight:850;cursor:pointer}}
.error{{background:#fff1f0;color:#b42318;border:1px solid #fecdca;padding:10px 12px;border-radius:10px;font-size:12px;margin-bottom:13px}}
.note{{font-size:11px;color:#98a2b3;text-align:center;margin-top:17px;line-height:1.45}}
</style>
</head>
<body>
<form class="card" method="post" action="/login">
  <div class="brand">
    <div class="mark">S</div>
    <div>
      <h1>Sportland Smart</h1>
      <div class="sub">Portal administrativo</div>
    </div>
  </div>
  {error_html}
  <input type="hidden" name="siguiente" value="{_escape(safe_next)}">
  <label for="usuario">Usuario</label>
  <input id="usuario" name="usuario" autocomplete="username" required autofocus>
  <label for="contrasena">Contraseña</label>
  <input id="contrasena" type="password" name="contrasena" autocomplete="current-password" required>
  <button type="submit">Entrar al portal</button>
  <div class="note">Acceso protegido. Las acciones comerciales sensibles continúan requiriendo revisión humana.</div>
</form>
</body>
</html>"""


def _escape(value: Any) -> str:
    import html
    return html.escape(str(value if value is not None else ""), quote=True)
