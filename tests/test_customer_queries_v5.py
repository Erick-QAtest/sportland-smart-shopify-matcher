from smart_customer.shopify_customer import CUSTOMER_QUERY,ORDER_QUERY

def test_customer_query_is_read_only_and_requests_identity_fields():
    assert 'customers(' in CUSTOMER_QUERY; assert 'defaultEmailAddress' in CUSTOMER_QUERY; assert 'defaultPhoneNumber' in CUSTOMER_QUERY; assert 'mutation' not in CUSTOMER_QUERY.lower()
def test_order_query_requests_size_and_brand_sources():
    assert 'lineItems' in ORDER_QUERY; assert 'variant { id title }' in ORDER_QUERY; assert 'vendor' in ORDER_QUERY; assert 'currentQuantity' in ORDER_QUERY; assert 'mutation' not in ORDER_QUERY.lower()
