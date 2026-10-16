from smart_customer.store import stable_client_uuid,stable_event_uuid

def test_shopify_customer_uuid_is_stable():
    gid='gid://shopify/Customer/123'; assert stable_client_uuid(gid)==stable_client_uuid(gid)
def test_different_customers_get_different_uuid(): assert stable_client_uuid('gid://shopify/Customer/1')!=stable_client_uuid('gid://shopify/Customer/2')
def test_line_item_event_uuid_is_stable():
    gid='gid://shopify/LineItem/99'; assert stable_event_uuid(gid)==stable_event_uuid(gid)
