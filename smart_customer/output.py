from __future__ import annotations
import csv,json
from pathlib import Path
from typing import Any
from psycopg import Connection

def write_customer_summary(conn:Connection,*,artifacts_dir:str|Path='artifacts')->dict[str,Any]:
    art=Path(artifacts_dir); art.mkdir(parents=True,exist_ok=True)
    totals=conn.execute('''SELECT COUNT(*) AS customers,COUNT(*) FILTER(WHERE shopify_customer_id IS NOT NULL) AS shopify_customers,
        COUNT(*) FILTER(WHERE phone_e164 IS NOT NULL) AS customers_with_phone,COUNT(*) FILTER(WHERE email IS NOT NULL) AS customers_with_email,
        COUNT(*) FILTER(WHERE preferred_size IS NOT NULL) AS customers_with_size_profile,COUNT(*) FILTER(WHERE size_confidence_band='HIGH') AS high_confidence_size_profiles,
        COUNT(*) FILTER(WHERE size_confidence_band='MEDIUM') AS medium_confidence_size_profiles,COUNT(*) FILTER(WHERE size_confidence_band='LOW') AS low_confidence_size_profiles FROM customers''').fetchone()
    purchases=conn.execute("SELECT COUNT(*) AS purchase_items,COALESCE(SUM(quantity),0) AS units,COUNT(*) FILTER(WHERE size IS NOT NULL) AS purchase_lines_with_size FROM customer_purchase_items WHERE cancelled=FALSE AND quantity>0").fetchone()
    dist=conn.execute("SELECT preferred_size AS size,COUNT(*) AS customers FROM customer_size_profiles WHERE preferred_size IS NOT NULL GROUP BY preferred_size ORDER BY preferred_size::numeric").fetchall()
    brands=conn.execute("SELECT brand,preferred_size AS size,COUNT(*) AS customers FROM customer_brand_size_profiles WHERE preferred_size IS NOT NULL GROUP BY brand,preferred_size ORDER BY brand,preferred_size::numeric").fetchall()
    payload={'customers':dict(totals),'purchases':dict(purchases),'size_distribution':[dict(x) for x in dist],'guardrails':{'contains_pii':False,'shopify_write':False,'automatic_contact':False}}
    (art/'customer_intelligence_summary.json').write_text(json.dumps(payload,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
    with (art/'customer_size_distribution.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['size','customers']); w.writeheader(); w.writerows([dict(x) for x in dist])
    with (art/'customer_brand_size_distribution.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['brand','size','customers']); w.writeheader(); w.writerows([dict(x) for x in brands])
    return payload
