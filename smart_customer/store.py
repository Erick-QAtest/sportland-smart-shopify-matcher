from __future__ import annotations
from datetime import datetime
from decimal import Decimal
import hashlib, uuid
from typing import Any, Iterable
from psycopg import Connection
from psycopg.types.json import Jsonb
from smart_customer.sizes import SizeProfile, build_size_profile, extract_size, normalize_brand

SOURCE='shopify_customer_sync_v5'
def _text(v): return str(v or '').strip()
def _email(v):
    x=_text(v).lower(); return x or None
def _phone(v):
    x=''.join(ch for ch in _text(v) if ch.isdigit() or ch=='+'); return x or None
def _money(v):
    try: return None if v in (None,'') else Decimal(str(v))
    except Exception: return None

def stable_client_uuid(gid:str)->str: return str(uuid.uuid5(uuid.NAMESPACE_URL,f'sportland:shopify-customer:{gid}'))
def stable_event_uuid(line_id:str)->str: return str(uuid.uuid5(uuid.NAMESPACE_URL,f'sportland:shopify-line-item:{line_id}'))

def _customer_values(node):
    spent=node.get('amountSpent') or {}; em=node.get('defaultEmailAddress') or {}; ph=node.get('defaultPhoneNumber') or {}
    try: orders=int(str(node.get('numberOfOrders'))) if node.get('numberOfOrders') not in (None,'') else 0
    except ValueError: orders=0
    return {'shopify_customer_id':_text(node.get('id')),'first_name':_text(node.get('firstName')) or None,'last_name':_text(node.get('lastName')) or None,
            'email':_email(em.get('emailAddress')),'phone_e164':_phone(ph.get('phoneNumber')),'orders_count':orders,'total_spent':_money(spent.get('amount')),
            'currency':_text(spent.get('currencyCode')) or None,'created_at':node.get('createdAt'),'updated_at':node.get('updatedAt')}

def _single_match(conn:Connection,column_sql:str,value:str|None)->int|None:
    if not value: return None
    rows=conn.execute(f'SELECT customer_id FROM customers WHERE {column_sql} ORDER BY customer_id LIMIT 2',(value,)).fetchall()
    return int(rows[0]['customer_id']) if len(rows)==1 else None

def _alias_customer(conn:Connection,alias_type:str,alias_value:str|None)->int|None:
    if not alias_value: return None
    r=conn.execute('SELECT customer_id FROM customer_identity_aliases WHERE alias_type=%s AND alias_value=%s',(alias_type,alias_value)).fetchone()
    return int(r['customer_id']) if r else None

def add_alias(conn:Connection,*,customer_id:int,alias_type:str,alias_value:str|None,source:str)->None:
    if not alias_value: return
    conn.execute('''INSERT INTO customer_identity_aliases(customer_id,alias_type,alias_value,source) VALUES(%s,%s,%s,%s)
                    ON CONFLICT(alias_type,alias_value) DO NOTHING''',(customer_id,alias_type,alias_value,source))

def resolve_or_create_customer(conn:Connection,node:dict[str,Any],*,synced_at:datetime)->tuple[int,bool]:
    v=_customer_values(node); gid=v['shopify_customer_id']
    if not gid: raise ValueError('Shopify customer node without id')
    cid=_alias_customer(conn,'SHOPIFY_CUSTOMER_ID',gid)
    if cid is None:
        r=conn.execute('SELECT customer_id FROM customers WHERE shopify_customer_id=%s',(gid,)).fetchone(); cid=int(r['customer_id']) if r else None
    if cid is None: cid=_single_match(conn,'phone_e164 = %s',v['phone_e164'])
    if cid is None and v['email']: cid=_single_match(conn,'lower(email) = %s',v['email'])
    inserted=False
    if cid is None:
        cu=stable_client_uuid(gid)
        r=conn.execute('''INSERT INTO customers(client_uuid,shopify_customer_id,first_name,last_name,email,phone_e164,first_seen_at,last_seen_at,first_channel,
                          shopify_orders_count,shopify_total_spent,shopify_currency,last_shopify_sync_at)
                          VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'SHOPIFY',%s,%s,%s,%s)
                          ON CONFLICT(client_uuid) DO UPDATE SET shopify_customer_id=COALESCE(customers.shopify_customer_id,EXCLUDED.shopify_customer_id),
                          first_name=COALESCE(EXCLUDED.first_name,customers.first_name),last_name=COALESCE(EXCLUDED.last_name,customers.last_name),
                          email=COALESCE(EXCLUDED.email,customers.email),phone_e164=COALESCE(EXCLUDED.phone_e164,customers.phone_e164),
                          shopify_orders_count=EXCLUDED.shopify_orders_count,shopify_total_spent=EXCLUDED.shopify_total_spent,
                          shopify_currency=COALESCE(EXCLUDED.shopify_currency,customers.shopify_currency),last_shopify_sync_at=EXCLUDED.last_shopify_sync_at,updated_at=now()
                          RETURNING customer_id''',(cu,gid,v['first_name'],v['last_name'],v['email'],v['phone_e164'],v['created_at'],v['updated_at'] or v['created_at'],v['orders_count'],v['total_spent'],v['currency'],synced_at)).fetchone()
        cid=int(r['customer_id']); inserted=True
    else:
        conn.execute('''UPDATE customers SET shopify_customer_id=COALESCE(shopify_customer_id,%s),first_name=COALESCE(%s,first_name),last_name=COALESCE(%s,last_name),
                       email=COALESCE(%s,email),phone_e164=COALESCE(%s,phone_e164),
                       first_seen_at=CASE WHEN first_seen_at IS NULL THEN %s WHEN %s::timestamptz IS NULL THEN first_seen_at ELSE LEAST(first_seen_at,%s::timestamptz) END,
                       last_seen_at=CASE WHEN last_seen_at IS NULL THEN %s WHEN %s::timestamptz IS NULL THEN last_seen_at ELSE GREATEST(last_seen_at,%s::timestamptz) END,
                       shopify_orders_count=%s,shopify_total_spent=%s,shopify_currency=COALESCE(%s,shopify_currency),last_shopify_sync_at=%s,updated_at=now()
                       WHERE customer_id=%s''',(gid,v['first_name'],v['last_name'],v['email'],v['phone_e164'],v['created_at'],v['created_at'],v['created_at'],v['updated_at'],v['updated_at'],v['updated_at'],v['orders_count'],v['total_spent'],v['currency'],synced_at,cid))
    canonical=conn.execute('SELECT client_uuid FROM customers WHERE customer_id=%s',(cid,)).fetchone()
    add_alias(conn,customer_id=cid,alias_type='SHOPIFY_CUSTOMER_ID',alias_value=gid,source=SOURCE)
    if canonical: add_alias(conn,customer_id=cid,alias_type='CLIENT_UUID',alias_value=canonical['client_uuid'],source='canonical')
    return cid,inserted

def resolve_memory_customer(conn:Connection,*,client_uuid:str,phone_e164:str|None)->int|None:
    r=conn.execute('SELECT customer_id FROM customers WHERE client_uuid=%s',(client_uuid,)).fetchone()
    if r: return int(r['customer_id'])
    aid=_alias_customer(conn,'CLIENT_UUID',client_uuid)
    return aid if aid is not None else _single_match(conn,'phone_e164 = %s',_phone(phone_e164))

def _unit_price(line):
    money=((line.get('discountedUnitPriceAfterAllDiscountsSet') or {}).get('shopMoney') or {})
    return _money(money.get('amount')),_text(money.get('currencyCode')) or None

def upsert_purchase_item(conn:Connection,*,customer_id:int,order:dict[str,Any],line:dict[str,Any])->tuple[bool,str|None]:
    lid=_text(line.get('id'))
    if not lid: return False,None
    variant=line.get('variant') or {}; product=line.get('product') or {}; sku=_text(line.get('sku')) or None; vt=_text(variant.get('title')) or None
    size=extract_size(vt,sku); brand=normalize_brand(line.get('vendor') or product.get('vendor')); qty=int(line.get('currentQuantity') or 0)
    price,currency=_unit_price(line); cancelled=bool(order.get('cancelledAt')) or qty<=0
    existing=conn.execute('SELECT purchase_item_id FROM customer_purchase_items WHERE shopify_line_item_id=%s',(lid,)).fetchone()
    conn.execute('''INSERT INTO customer_purchase_items(shopify_line_item_id,shopify_order_id,shopify_order_name,customer_id,shopify_product_id,shopify_variant_id,sku,product_title,brand,variant_title,size,quantity,unit_price,currency,purchased_at,order_updated_at,cancelled,metadata)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(shopify_line_item_id) DO UPDATE SET shopify_order_id=EXCLUDED.shopify_order_id,shopify_order_name=EXCLUDED.shopify_order_name,customer_id=EXCLUDED.customer_id,
                    shopify_product_id=EXCLUDED.shopify_product_id,shopify_variant_id=EXCLUDED.shopify_variant_id,sku=EXCLUDED.sku,product_title=EXCLUDED.product_title,brand=EXCLUDED.brand,
                    variant_title=EXCLUDED.variant_title,size=EXCLUDED.size,quantity=EXCLUDED.quantity,unit_price=EXCLUDED.unit_price,currency=EXCLUDED.currency,purchased_at=EXCLUDED.purchased_at,
                    order_updated_at=EXCLUDED.order_updated_at,cancelled=EXCLUDED.cancelled,metadata=customer_purchase_items.metadata||EXCLUDED.metadata,updated_at=now()''',
                    (lid,_text(order.get('id')),_text(order.get('name')) or None,customer_id,_text(product.get('id')) or None,_text(variant.get('id')) or None,sku,_text(line.get('title') or product.get('title')) or None,brand,vt,size,qty,price,currency,order.get('createdAt'),order.get('updatedAt'),cancelled,Jsonb({'original_quantity':int(line.get('quantity') or 0),'source':SOURCE})))
    return existing is None,size

def insert_purchase_event(conn:Connection,*,customer_id:int,order:dict[str,Any],line:dict[str,Any],size:str|None,synced_at:datetime)->bool:
    qty=int(line.get('currentQuantity') or 0)
    if bool(order.get('cancelledAt')) or qty<=0: return False
    lid=_text(line.get('id'))
    if not lid: return False
    customer=conn.execute('SELECT client_uuid FROM customers WHERE customer_id=%s',(customer_id,)).fetchone()
    if not customer: return False
    variant=line.get('variant') or {}; product=line.get('product') or {}; price,currency=_unit_price(line); amount=price*qty if price is not None else None
    brand=normalize_brand(line.get('vendor') or product.get('vendor')); sku=_text(line.get('sku')) or None
    row_hash=hashlib.sha256(f'shopify-line:{lid}'.encode()).hexdigest()
    r=conn.execute('''INSERT INTO customer_events(event_uuid,event_hash,source,source_row_hash,customer_id,client_uuid,event_type_id,event_type_name,detail,occurred_at,logged_at,sku,size,amount,channel,currency,actor,origin,metadata,raw_status)
                      VALUES(%s,%s,%s,%s,%s,%s,41,'COMPRA_ECOMMERCE',%s,%s,%s,%s,%s,%s,'SHOPIFY',%s,'system','shopify',%s,'LOGGED')
                      ON CONFLICT DO NOTHING RETURNING event_id''',(stable_event_uuid(lid),row_hash,SOURCE,row_hash,customer_id,customer['client_uuid'],_text(line.get('title') or product.get('title')) or None,order.get('createdAt'),synced_at,sku,size,amount,currency or 'MXN',Jsonb({'shopify_order_id':_text(order.get('id')),'shopify_order_name':_text(order.get('name')),'shopify_line_item_id':lid,'shopify_variant_id':_text(variant.get('id')) or None,'shopify_product_id':_text(product.get('id')) or None,'variant_title':_text(variant.get('title')) or None,'brand':brand,'quantity':qty}))).fetchone()
    return bool(r)

def _write_profile(conn,customer_id:int,p:SizeProfile):
    conn.execute('''INSERT INTO customer_size_profiles(customer_id,preferred_size,last_purchase_size,observation_count,unique_sizes,confidence,confidence_band,first_observed_at,last_observed_at,size_counts,updated_at)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now()) ON CONFLICT(customer_id) DO UPDATE SET preferred_size=EXCLUDED.preferred_size,last_purchase_size=EXCLUDED.last_purchase_size,
                    observation_count=EXCLUDED.observation_count,unique_sizes=EXCLUDED.unique_sizes,confidence=EXCLUDED.confidence,confidence_band=EXCLUDED.confidence_band,
                    first_observed_at=EXCLUDED.first_observed_at,last_observed_at=EXCLUDED.last_observed_at,size_counts=EXCLUDED.size_counts,updated_at=now()''',(customer_id,p.preferred_size,p.last_purchase_size,p.observation_count,p.unique_sizes,p.confidence,p.confidence_band,p.first_observed_at,p.last_observed_at,Jsonb(p.size_counts)))
    conn.execute('''UPDATE customers SET preferred_size=%s,last_purchase_size=%s,size_confidence=%s,size_confidence_band=%s,size_observation_count=%s,updated_at=now() WHERE customer_id=%s''',(p.preferred_size,p.last_purchase_size,p.confidence,p.confidence_band,p.observation_count,customer_id))

def refresh_size_profiles(conn:Connection,customer_ids:Iterable[int])->int:
    updated=0
    for cid in sorted(set(int(x) for x in customer_ids)):
        rows=conn.execute('SELECT size,quantity,purchased_at,cancelled,brand FROM customer_purchase_items WHERE customer_id=%s ORDER BY purchased_at,purchase_item_id',(cid,)).fetchall()
        p=build_size_profile([dict(r) for r in rows]); _write_profile(conn,cid,p)
        conn.execute('DELETE FROM customer_brand_size_profiles WHERE customer_id=%s',(cid,)); by_brand={}
        for raw in rows:
            row=dict(raw); brand=normalize_brand(row.get('brand'))
            if brand: by_brand.setdefault(brand,[]).append(row)
        for brand,items in by_brand.items():
            bp=build_size_profile(items)
            if bp.observation_count<=0: continue
            conn.execute('''INSERT INTO customer_brand_size_profiles(customer_id,brand,preferred_size,last_purchase_size,observation_count,unique_sizes,confidence,confidence_band,size_counts,first_observed_at,last_observed_at,updated_at)
                            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())''',(cid,brand,bp.preferred_size,bp.last_purchase_size,bp.observation_count,bp.unique_sizes,bp.confidence,bp.confidence_band,Jsonb(bp.size_counts),bp.first_observed_at,bp.last_observed_at))
        updated+=1
    return updated

def latest_successful_sync(conn:Connection):
    r=conn.execute("SELECT finished_at FROM customer_sync_runs WHERE status='OK' ORDER BY finished_at DESC NULLS LAST LIMIT 1").fetchone()
    return r['finished_at'] if r and r['finished_at'] else None
