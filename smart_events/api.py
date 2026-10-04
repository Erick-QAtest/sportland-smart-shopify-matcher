from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .capture import capture_event
from .resolver import CatalogResolver
from .sheet_store import GoogleSheetEventStore, SheetConfig


def create_app():
    from fastapi import FastAPI, HTTPException, Request
    from pydantic import BaseModel, Field

    cfg = SheetConfig.from_env()
    errors = cfg.validate()
    if errors:
        raise RuntimeError("; ".join(errors))
    store = GoogleSheetEventStore(cfg)
    resolver = CatalogResolver.from_csv(os.getenv("EVENT_CAPTURE_CATALOG_CSV", "artifacts/shopify_inventory_finance.csv"))

    app = FastAPI(title="Sportland Smart Event Capture", version="2.2.0")

    class WebEvent(BaseModel):
        occurred_at: str
        action: str
        text: str = ""
        sku: str = ""
        product_title: str = ""
        size: str = ""
        source_event_id: str = ""
        device: str = "web"
        metadata: dict[str, Any] = Field(default_factory=dict)

    @app.get("/health")
    def health():
        return {"ok": True, "version": "2.2.0"}

    @app.post("/v1/events/web")
    def web_event(payload: WebEvent):
        try:
            return capture_event(
                store=store, resolver=resolver, text=payload.text,
                occurred_at=payload.occurred_at, channel="ecommerce", sku=payload.sku,
                product_title=payload.product_title, size=payload.size, action=payload.action,
                source_event_id=payload.source_event_id, device=payload.device,
                origin="shopify_web_v22", metadata=payload.metadata,
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/webhooks/whatsapp")
    def whatsapp_verify(request: Request):
        q = request.query_params
        token = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
        if q.get("hub.mode") == "subscribe" and token and hmac.compare_digest(q.get("hub.verify_token", ""), token):
            return int(q.get("hub.challenge") or 0)
        raise HTTPException(status_code=403, detail="verification failed")

    @app.post("/webhooks/whatsapp")
    async def whatsapp_webhook(request: Request):
        raw = await request.body()
        app_secret = os.getenv("WHATSAPP_APP_SECRET", "")
        sig = request.headers.get("x-hub-signature-256", "")
        if app_secret:
            expected = "sha256=" + hmac.new(app_secret.encode(), raw, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig, expected):
                raise HTTPException(status_code=401, detail="invalid signature")
        payload = json.loads(raw.decode("utf-8"))
        results = []
        for entry in payload.get("entry") or []:
            for change in entry.get("changes") or []:
                value = change.get("value") or {}
                for msg in value.get("messages") or []:
                    if msg.get("type") != "text":
                        continue
                    body = ((msg.get("text") or {}).get("body") or "").strip()
                    ts = msg.get("timestamp")
                    dt = datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat() if ts else ""
                    phone = str(msg.get("from") or "")
                    sid = "wa-cloud:" + str(msg.get("id") or "")
                    try:
                        results.append(capture_event(
                            store=store, resolver=resolver, text=body, occurred_at=dt,
                            channel="whatsapp", phone_e164=phone, source_event_id=sid,
                            device="mobile", origin="whatsapp_cloud_v22",
                            metadata={"whatsapp_message_id": msg.get("id")},
                        ))
                    except Exception as e:
                        results.append({"status": "ERROR", "error": str(e), "source_event_id": sid})
        return {"ok": True, "processed": len(results), "results": results}

    return app
