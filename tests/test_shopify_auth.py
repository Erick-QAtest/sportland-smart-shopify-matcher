from pathlib import Path

from sportland_matcher.config import load_config, validate_config
from sportland_matcher.shopify_source import acquire_shopify_auth


def _base_env(monkeypatch):
    fixture = Path(__file__).parent / "fixtures" / "smart_events.csv"
    monkeypatch.setenv("SMART_SOURCE", "csv")
    monkeypatch.setenv("SMART_CSV_PATH", str(fixture))
    monkeypatch.setenv("SHOPIFY_SHOP", "sportland-sales.myshopify.com")
    monkeypatch.delenv("SHOPIFY_ADMIN_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("SHOPIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SHOPIFY_CLIENT_SECRET", raising=False)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.ok = 200 <= status_code < 300

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def test_config_accepts_client_credentials(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.setenv("SHOPIFY_CLIENT_ID", "client-id")
    monkeypatch.setenv("SHOPIFY_CLIENT_SECRET", "client-secret")

    cfg = load_config(env_file=None)

    assert validate_config(cfg) == []
    assert cfg.shopify_auth_mode == "client_credentials"


def test_config_accepts_existing_admin_token(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.setenv("SHOPIFY_ADMIN_ACCESS_TOKEN", "token-value")

    cfg = load_config(env_file=None)

    assert validate_config(cfg) == []
    assert cfg.shopify_auth_mode == "admin_access_token"


def test_auth_uses_existing_token_without_network(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.setenv("SHOPIFY_ADMIN_ACCESS_TOKEN", "token-value")
    cfg = load_config(env_file=None)

    auth = acquire_shopify_auth(cfg)

    assert auth.access_token == "token-value"
    assert auth.mode == "admin_access_token"


def test_auth_requests_token_from_shopify(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.setenv("SHOPIFY_CLIENT_ID", "client-id")
    monkeypatch.setenv("SHOPIFY_CLIENT_SECRET", "client-secret")
    cfg = load_config(env_file=None)
    fake = FakeSession(FakeResponse({
        "access_token": "runtime-token",
        "scope": "read_products,read_inventory,read_locations",
    }))

    auth = acquire_shopify_auth(cfg, session=fake)

    assert auth.access_token == "runtime-token"
    assert auth.mode == "client_credentials"
    assert "read_products" in auth.scope
    assert len(fake.calls) == 1
    url, kwargs = fake.calls[0]
    assert url == "https://sportland-sales.myshopify.com/admin/oauth/access_token"
    assert kwargs["data"]["grant_type"] == "client_credentials"
    assert kwargs["data"]["client_id"] == "client-id"
    assert kwargs["data"]["client_secret"] == "client-secret"
