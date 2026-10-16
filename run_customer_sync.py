from __future__ import annotations
import argparse
from pathlib import Path
from dotenv import load_dotenv
from smart_customer.output import write_customer_summary
from smart_customer.shopify_customer import ShopifyCustomerClient
from smart_customer.sync import sync_customer_intelligence
from smart_memory.config import MemoryConfig
from smart_memory.db import apply_migrations,connect

def main()->int:
    load_dotenv('.env'); p=argparse.ArgumentParser(description='Sportland Smart — Customer Intelligence v5.0')
    p.add_argument('--full',action='store_true'); p.add_argument('--history-days',type=int,default=None); p.add_argument('--overlap-days',type=int,default=2); p.add_argument('--artifacts-dir',default='artifacts'); args=p.parse_args()
    mcfg=MemoryConfig.from_env(); client=ShopifyCustomerClient(); errors=mcfg.validate()+client.validate()
    if errors:
        print('CONFIG ERROR'); [print(f'- {e}') for e in errors]; return 2
    scopes=client.validate_scopes(full_history=args.full)
    if scopes['missing']:
        print('SHOPIFY SCOPE ERROR'); print('Missing scopes:',', '.join(scopes['missing'])); print('Required:',', '.join(scopes['required'])); return 3
    for warning in scopes['warnings']: print('WARNING:',warning)
    with connect(mcfg) as conn:
        applied=apply_migrations(conn)
        if applied: print('Migrations:',', '.join(applied))
        stats=sync_customer_intelligence(conn,client,full=args.full,history_days=args.history_days,overlap_days=args.overlap_days)
        summary=write_customer_summary(conn,artifacts_dir=Path(args.artifacts_dir))
    print('\nSportland Smart — Customer Intelligence v5.0'); print(f"Sync mode: {stats['mode']}"); print(f"Customers read: {stats['customers_read']}"); print(f"Orders read: {stats['orders_read']}"); print(f"Purchase lines read: {stats['purchase_items_read']}"); print(f"Customers inserted: {stats['customers_inserted']}"); print(f"Customers updated: {stats['customers_updated']}"); print(f"Purchase items inserted: {stats['purchase_items_inserted']}"); print(f"Purchase items updated: {stats['purchase_items_updated']}"); print(f"Purchase events inserted: {stats['purchase_events_inserted']}"); print(f"Size profiles updated: {stats['size_profiles_updated']}"); print('Customers with size profile:',summary['customers']['customers_with_size_profile']); print('High-confidence size profiles:',summary['customers']['high_confidence_size_profiles']); print('\nGuardrails: Shopify read-only; no automatic customer contact.'); print('PII stays in PostgreSQL; generated artifacts are aggregate-only.'); return 0
if __name__=='__main__': raise SystemExit(main())
