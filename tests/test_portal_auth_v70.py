from smart_portal.auth_v70 import (
    AuthConfig,
    hash_password,
    issue_session,
    login_page,
    verify_password,
    verify_session,
)


def cfg():
    return AuthConfig(
        enabled=True,
        username="admin",
        password_hash=hash_password("una-clave-segura-123"),
        session_secret="x" * 64,
        session_hours=12,
        cookie_secure=True,
    )


def test_hash_de_password_no_guarda_texto_plano():
    encoded = hash_password("una-clave-segura-123")
    assert "una-clave-segura-123" not in encoded
    assert verify_password("una-clave-segura-123", encoded)
    assert not verify_password("incorrecta", encoded)


def test_sesion_valida_y_firmada():
    c = cfg()
    token = issue_session(c, "admin", now=1000)
    assert verify_session(c, token, now=1100) == "admin"


def test_sesion_manipulada_falla():
    c = cfg()
    token = issue_session(c, "admin", now=1000)
    body, sig = token.split(".", 1)
    altered = body[:-1] + ("A" if body[-1] != "A" else "B") + "." + sig
    assert verify_session(c, altered, now=1100) is None


def test_sesion_expirada_falla():
    c = cfg()
    token = issue_session(c, "admin", now=1000)
    assert verify_session(c, token, now=1000 + 13 * 3600) is None


def test_login_esta_en_espanol():
    html = login_page(error="Error")
    assert "Portal administrativo" in html
    assert "Usuario" in html
    assert "Contraseña" in html
    assert "Entrar al portal" in html
