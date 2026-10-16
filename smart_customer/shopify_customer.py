from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any
from smart_finance.shopify_finance import ShopifyFinanceClient, ShopifyFinanceConfig

CUSTOMER_QUERY = '''
query CustomerIntelligenceCustomers($first:Int!, $after:String, $query:String) {
  customers(first:$first, after:$after, query:$query, sortKey:UPDATED_AT) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id firstName lastName createdAt updatedAt numberOfOrders
      amountSpent { amount currencyCode }
      defaultEmailAddress { emailAddress }
      defaultPhoneNumber { phoneNumber }
    }
  }
}
'''

ORDER_QUERY = '''
query CustomerIntelligenceOrders($first:Int!, $after:String, $query:String) {
  orders(first:$first, after:$after, query:$query, sortKey:UPDATED_AT) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id name createdAt updatedAt cancelledAt
      customer {
        id firstName lastName createdAt updatedAt numberOfOrders
        amountSpent { amount currencyCode }
        defaultEmailAddress { emailAddress }
        defaultPhoneNumber { phoneNumber }
      }
      lineItems(first:100) {
        nodes {
          id title sku vendor quantity currentQuantity
          discountedUnitPriceAfterAllDiscountsSet { shopMoney { amount currencyCode } }
          variant { id title }
          product { id title vendor }
        }
      }
    }
  }
}
'''

def _iso(v: datetime) -> str:
    return v.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

class ShopifyCustomerClient:
    REQUIRED_SCOPES={'read_customers','read_orders'}
    def __init__(self,cfg:ShopifyFinanceConfig|None=None):
        self.cfg=cfg or ShopifyFinanceConfig.from_env(); self.client=ShopifyFinanceClient(self.cfg)
    def validate(self)->list[str]: return self.cfg.validate()
    def validate_scopes(self,*,full_history:bool=False)->dict[str,Any]:
        granted=self.client.access_scopes(); missing=sorted(self.REQUIRED_SCOPES-granted); warnings=[]
        if full_history and 'read_all_orders' not in granted:
            warnings.append('read_all_orders no está concedido; Shopify puede limitar pedidos anteriores a 60 días.')
        return {'granted':sorted(granted),'required':sorted(self.REQUIRED_SCOPES),'missing':missing,'warnings':warnings,'ok':not missing}
    def fetch_customers(self,*,updated_since:datetime|None=None)->list[dict[str,Any]]:
        q=f'updated_at:>={_iso(updated_since)}' if updated_since else None; after=None; out=[]
        while True:
            data=self.client.graphql(CUSTOMER_QUERY,{'first':100,'after':after,'query':q}); conn=data.get('customers') or {}
            out.extend(conn.get('nodes') or []); page=conn.get('pageInfo') or {}
            if not page.get('hasNextPage'): break
            after=page.get('endCursor')
            if not after: break
        return out
    def fetch_orders(self,*,updated_since:datetime|None=None,history_days:int|None=None)->list[dict[str,Any]]:
        if updated_since: q=f'updated_at:>={_iso(updated_since)}'
        elif history_days: q=f'created_at:>={_iso(datetime.now(timezone.utc)-timedelta(days=history_days))}'
        else: q=None
        after=None; out=[]
        while True:
            data=self.client.graphql(ORDER_QUERY,{'first':100,'after':after,'query':q}); conn=data.get('orders') or {}
            out.extend(conn.get('nodes') or []); page=conn.get('pageInfo') or {}
            if not page.get('hasNextPage'): break
            after=page.get('endCursor')
            if not after: break
        return out
