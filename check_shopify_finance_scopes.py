from __future__ import annotations

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = lambda *_a, **_k: None

from smart_finance.shopify_finance import ShopifyFinanceClient, ShopifyFinanceConfig

load_dotenv(".env")
cfg = ShopifyFinanceConfig.from_env()
errors = cfg.validate()
if errors:
    for e in errors:
        print("ERROR:", e)
    raise SystemExit(2)

client = ShopifyFinanceClient(cfg)
result = client.validate_scopes()
print("Shopify:", cfg.shop)
print("Granted:", ", ".join(result["granted"]))
print("Required:", ", ".join(result["required"]))
if result["missing"]:
    print("Missing:", ", ".join(result["missing"]))
    raise SystemExit(3)
print("OK — Shopify Finance can read orders + products")
