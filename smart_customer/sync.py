from __future__ import annotations
from datetime import datetime,timedelta,timezone
import uuid
from typing import Any
from psycopg import Connection
from psycopg.types.json import Jsonb
from smart_customer.shopify_customer import ShopifyCustomerClient
from smart_customer.store import insert_purchase_event,latest_successful_sync,refresh_size_profiles,resolve_or_create_customer,upsert_purchase_item

def make_sync_run_id(now:datetime|None=None)->str:
    now=now or datetime.now(timezone.utc)
    return f"customer-{now.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"

def sync_customer_intelligence(conn:Connection,client:ShopifyCustomerClient,*,full:bool=False,history_days:int|None=None,overlap_days:int=2)->dict[str,Any]:
    started=datetime.now(timezone.utc); run_id=make_sync_run_id(started)
    prev=None if full else latest_successful_sync(conn)
    since=prev-timedelta(days=max(0,overlap_days)) if prev else None
    mode='FULL' if full or since is None else 'INCREMENTAL'
    conn.execute("INSERT INTO customer_sync_runs(sync_run_id,started_at,status,mode,since_at,metadata) VALUES(%s,%s,'RUNNING',%s,%s,%s)",(run_id,started,mode,since,Jsonb({'source':'shopify','automatic_contact':False,'shopify_write':False}))); conn.commit()
    stats={'sync_run_id':run_id,'mode':mode,'since_at':since.isoformat() if since else None,'customers_read':0,'orders_read':0,'purchase_items_read':0,'customers_inserted':0,'customers_updated':0,'purchase_items_inserted':0,'purchase_items_updated':0,'purchase_events_inserted':0,'size_profiles_updated':0}
    try:
        customers=client.fetch_customers(updated_since=None if mode=='FULL' else since)
        orders=client.fetch_orders(history_days=history_days) if mode=='FULL' else client.fetch_orders(updated_since=since)
        stats['customers_read']=len(customers); stats['orders_read']=len(orders); affected=set(); mapping={}
        with conn.transaction():
            for node in customers:
                cid,ins=resolve_or_create_customer(conn,node,synced_at=started); mapping[str(node['id'])]=cid; affected.add(cid)
                stats['customers_inserted' if ins else 'customers_updated']+=1
            for order in orders:
                cnode=order.get('customer') or {}; gid=str(cnode.get('id') or '').strip()
                if not gid: continue
                cid=mapping.get(gid)
                if cid is None:
                    cid,ins=resolve_or_create_customer(conn,cnode,synced_at=started); mapping[gid]=cid; stats['customers_inserted' if ins else 'customers_updated']+=1
                affected.add(cid)
                for line in ((order.get('lineItems') or {}).get('nodes') or []):
                    stats['purchase_items_read']+=1
                    inserted,size=upsert_purchase_item(conn,customer_id=cid,order=order,line=line)
                    stats['purchase_items_inserted' if inserted else 'purchase_items_updated']+=1
                    if insert_purchase_event(conn,customer_id=cid,order=order,line=line,size=size,synced_at=started): stats['purchase_events_inserted']+=1
            stats['size_profiles_updated']=refresh_size_profiles(conn,affected)
        finished=datetime.now(timezone.utc)
        conn.execute('''UPDATE customer_sync_runs SET finished_at=%s,status='OK',customers_read=%s,orders_read=%s,purchase_items_read=%s,customers_inserted=%s,customers_updated=%s,purchase_items_inserted=%s,purchase_items_updated=%s,purchase_events_inserted=%s,size_profiles_updated=%s,metadata=metadata||%s WHERE sync_run_id=%s''',(finished,stats['customers_read'],stats['orders_read'],stats['purchase_items_read'],stats['customers_inserted'],stats['customers_updated'],stats['purchase_items_inserted'],stats['purchase_items_updated'],stats['purchase_events_inserted'],stats['size_profiles_updated'],Jsonb({'history_days':history_days,'overlap_days':overlap_days}),run_id)); conn.commit(); return stats
    except Exception as exc:
        conn.rollback(); conn.execute("UPDATE customer_sync_runs SET finished_at=now(),status='FAILED',error_message=%s WHERE sync_run_id=%s",(str(exc)[:2000],run_id)); conn.commit(); raise
