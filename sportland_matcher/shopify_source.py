from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any
import random
import time

import requests

from .config import Config
from .normalization import normalize_size, normalize_sku


@dataclass(frozen=True)
class ShopifyAuth:
    access_token: str
    mode: str
    scope: str = ""


@dataclass
class LocationInventory:
    location_id: str
    location_name: str
    available: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ShopifyVariant:
    variant_id: str
    variant_legacy_id: str
    product_id: str
    product_legacy_id: str
    product_handle: str
    product_title: str
    product_status: str
    variant_title: str
    sku: str
    size: str
    inventory_total: int
    price: str
    compare_at_price: str
    inventory_item_id: str
    locations: list[LocationInventory]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["locations"] = [x.to_dict() for x in self.locations]
        return data


QUERY = r'''
query SportlandVariants($first: Int!, $after: String) {
  productVariants(first: $first, after: $after, query: "status:active") {
    pageInfo { hasNextPage endCursor }
    nodes {
      id
      legacyResourceId
      sku
      title
      price
      compareAtPrice
      inventoryQuantity
      selectedOptions { name value }
      product {
        id
        legacyResourceId
        handle
        title
        status
      }
      inventoryItem {
        id
        legacyResourceId
        sku
        inventoryLevels(first: 10) {
          nodes {
            id
            location { id name }
            quantities(names: ["available"]) { name quantity }
          }
        }
      }
    }
  }
}
'''


def acquire_shopify_auth(cfg: Config, *, session: requests.Session | None = None) -> ShopifyAuth:
    """Return a usable Admin API token without writing it to disk.

    Backwards-compatible behavior:
    - If SHOPIFY_ADMIN_ACCESS_TOKEN exists, use it directly.
    - Otherwise request a short-lived token from Shopify using
      SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET.
    """
    if cfg.shopify_token:
        return ShopifyAuth(
            access_token=cfg.shopify_token,
            mode="admin_access_token",
        )

    if not cfg.shopify_client_id or not cfg.shopify_client_secret:
        raise RuntimeError(
            "Shopify credentials are incomplete. Configure SHOPIFY_CLIENT_ID and "
            "SHOPIFY_CLIENT_SECRET, or provide SHOPIFY_ADMIN_ACCESS_TOKEN."
        )

    auth_url = f"https://{cfg.shopify_shop}/admin/oauth/access_token"
    http = session or requests.Session()
    try:
        response = http.post(
            auth_url,
            data={
                "grant_type": "client_credentials",
                "client_id": cfg.shopify_client_id,
                "client_secret": cfg.shopify_client_secret,
            },
            headers={"Accept": "application/json"},
            timeout=cfg.shopify_timeout_seconds,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Shopify authentication request failed: {exc}") from exc

    if not response.ok:
        # Do not include submitted credentials in the error message.
        detail = ""
        try:
            payload = response.json()
            detail = str(payload.get("error_description") or payload.get("error") or "").strip()
        except ValueError:
            detail = ""
        suffix = f" ({detail})" if detail else ""
        raise RuntimeError(f"Shopify authentication failed with HTTP {response.status_code}{suffix}.")

    payload = response.json()
    access_token = str(payload.get("access_token") or "").strip()
    if not access_token:
        raise RuntimeError("Shopify authentication succeeded but returned no access_token.")

    scope_value = payload.get("scope") or ""
    if isinstance(scope_value, list):
        scope = ",".join(str(x) for x in scope_value)
    else:
        scope = str(scope_value)

    return ShopifyAuth(
        access_token=access_token,
        mode="client_credentials",
        scope=scope,
    )


class ShopifyReadOnlyClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.url = f"https://{cfg.shopify_shop}/admin/api/{cfg.shopify_api_version}/graphql.json"
        self.session = requests.Session()
        self.auth = acquire_shopify_auth(cfg, session=self.session)
        self.session.headers.update({
            "X-Shopify-Access-Token": self.auth.access_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Sportland-Smart-Shopify-Matcher/1.1",
        })

    def _post(self, variables: dict[str, Any]) -> dict[str, Any]:
        delay = 1.0
        for attempt in range(1, self.cfg.shopify_max_retries + 1):
            try:
                response = self.session.post(
                    self.url,
                    json={"query": QUERY, "variables": variables},
                    timeout=self.cfg.shopify_timeout_seconds,
                )
            except requests.RequestException:
                if attempt >= self.cfg.shopify_max_retries:
                    raise
                time.sleep(delay + random.random() * 0.35)
                delay = min(delay * 2, 20)
                continue

            if response.status_code == 429:
                if attempt >= self.cfg.shopify_max_retries:
                    response.raise_for_status()
                retry_after = response.headers.get("Retry-After")
                sleep_for = float(retry_after) if retry_after else delay
                time.sleep(sleep_for + random.random() * 0.35)
                delay = min(delay * 2, 20)
                continue

            if 500 <= response.status_code < 600:
                if attempt >= self.cfg.shopify_max_retries:
                    response.raise_for_status()
                time.sleep(delay + random.random() * 0.35)
                delay = min(delay * 2, 20)
                continue

            response.raise_for_status()
            payload = response.json()
            errors = payload.get("errors") or []
            throttled = any(
                (e.get("extensions") or {}).get("code") == "THROTTLED"
                for e in errors if isinstance(e, dict)
            )
            if throttled:
                if attempt >= self.cfg.shopify_max_retries:
                    raise RuntimeError(f"Shopify GraphQL THROTTLED after {attempt} attempts.")
                time.sleep(delay + random.random() * 0.35)
                delay = min(delay * 2, 20)
                continue
            if errors:
                raise RuntimeError(f"Shopify GraphQL errors: {errors}")
            return payload
        raise RuntimeError("Shopify request failed unexpectedly.")

    def fetch_all_variants(self) -> list[ShopifyVariant]:
        variants: list[ShopifyVariant] = []
        after: str | None = None
        while True:
            payload = self._post({"first": self.cfg.shopify_variant_page_size, "after": after})
            connection = payload["data"]["productVariants"]
            for node in connection.get("nodes", []):
                product = node.get("product") or {}
                inv_item = node.get("inventoryItem") or {}
                size = ""
                for option in node.get("selectedOptions") or []:
                    if str(option.get("name", "")).casefold() in self.cfg.shopify_size_option_names:
                        size = normalize_size(option.get("value"))
                        break
                locations: list[LocationInventory] = []
                for level in (inv_item.get("inventoryLevels") or {}).get("nodes") or []:
                    available = 0
                    for q in level.get("quantities") or []:
                        if q.get("name") == "available":
                            available = int(q.get("quantity") or 0)
                            break
                    loc = level.get("location") or {}
                    locations.append(LocationInventory(
                        location_id=str(loc.get("id") or ""),
                        location_name=str(loc.get("name") or ""),
                        available=available,
                    ))
                variants.append(ShopifyVariant(
                    variant_id=str(node.get("id") or ""),
                    variant_legacy_id=str(node.get("legacyResourceId") or ""),
                    product_id=str(product.get("id") or ""),
                    product_legacy_id=str(product.get("legacyResourceId") or ""),
                    product_handle=str(product.get("handle") or ""),
                    product_title=str(product.get("title") or ""),
                    product_status=str(product.get("status") or ""),
                    variant_title=str(node.get("title") or ""),
                    sku=normalize_sku(node.get("sku") or inv_item.get("sku")),
                    size=size,
                    inventory_total=int(node.get("inventoryQuantity") or 0),
                    price=str(node.get("price") or ""),
                    compare_at_price=str(node.get("compareAtPrice") or ""),
                    inventory_item_id=str(inv_item.get("id") or ""),
                    locations=locations,
                ))
            page_info = connection.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                break
            after = page_info.get("endCursor")
            if not after:
                break
        return variants
