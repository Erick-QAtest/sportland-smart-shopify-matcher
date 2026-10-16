from smart_customer.sizes import build_size_profile, extract_size

def test_extract_direct_variant_size(): assert extract_size('27','2080-27')=='27'
def test_extract_half_size(): assert extract_size('27.5','ABC-27.5')=='27.5'
def test_extract_size_from_descriptive_variant(): assert extract_size('Negro / 26.5','ABC')=='26.5'
def test_extract_size_falls_back_to_sku(): assert extract_size('Negro','2080-27')=='27'
def test_rejects_non_mx_size(): assert extract_size('US 9','ABC') is None

def test_profile_uses_mode_and_quantity():
    rows=[{'size':'27','quantity':2,'purchased_at':'2026-01-01T00:00:00Z','cancelled':False},{'size':'27.5','quantity':1,'purchased_at':'2026-02-01T00:00:00Z','cancelled':False},{'size':'27','quantity':2,'purchased_at':'2026-03-01T00:00:00Z','cancelled':False}]
    p=build_size_profile(rows); assert p.preferred_size=='27'; assert p.observation_count==5; assert p.confidence==0.8; assert p.confidence_band=='HIGH'

def test_profile_tie_breaks_by_recency():
    rows=[{'size':'27','quantity':1,'purchased_at':'2026-01-01T00:00:00Z','cancelled':False},{'size':'27.5','quantity':1,'purchased_at':'2026-03-01T00:00:00Z','cancelled':False}]
    p=build_size_profile(rows); assert p.preferred_size=='27.5'; assert p.last_purchase_size=='27.5'

def test_cancelled_purchase_does_not_count():
    p=build_size_profile([{'size':'27','quantity':5,'purchased_at':'2026-01-01T00:00:00Z','cancelled':True},{'size':'28','quantity':1,'purchased_at':'2026-02-01T00:00:00Z','cancelled':False}])
    assert p.preferred_size=='28'; assert p.observation_count==1
