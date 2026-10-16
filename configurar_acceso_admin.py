from __future__ import annotations

import argparse
from getpass import getpass
from pathlib import Path
import secrets

from smart_portal.auth_v70 import hash_password


def dotenv_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Configurar acceso administrativo de Sportland Smart"
    )
    parser.add_argument("--archivo", default=".env.portal")
    parser.add_argument("--dominio", default="")
    parser.add_argument(
        "--cookie-segura",
        choices=["si", "no"],
        default="no",
    )
    args = parser.parse_args()

    print("")
    print("Sportland Smart — Acceso administrativo")
    print("La contraseña no se guardará en texto plano.")
    print("")

    usuario = input("Usuario administrador: ").strip()
    if not usuario:
        print("ERROR: el usuario no puede quedar vacío.")
        return 2

    password = getpass("Contraseña: ")
    confirm = getpass("Confirmar contraseña: ")
    if password != confirm:
        print("ERROR: las contraseñas no coinciden.")
        return 2

    try:
        password_hash = hash_password(password)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2

    session_secret = secrets.token_urlsafe(48)
    secure = "true" if args.cookie_segura == "si" else "false"

    lines = [
        "SPORTLAND_AUTH_ENABLED=true",
        f"SPORTLAND_ADMIN_USER={dotenv_quote(usuario)}",
        f"SPORTLAND_ADMIN_PASSWORD_HASH={dotenv_quote(password_hash)}",
        f"SPORTLAND_SESSION_SECRET={dotenv_quote(session_secret)}",
        "SPORTLAND_SESSION_HOURS=12",
        f"SPORTLAND_COOKIE_SECURE={secure}",
    ]
    if args.dominio:
        lines.append(
            f"SPORTLAND_PUBLIC_URL={dotenv_quote('https://' + args.dominio)}"
        )

    path = Path(args.archivo)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)

    print("")
    print(f"Acceso configurado en: {path}")
    print("La contraseña no quedó almacenada en texto plano.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
