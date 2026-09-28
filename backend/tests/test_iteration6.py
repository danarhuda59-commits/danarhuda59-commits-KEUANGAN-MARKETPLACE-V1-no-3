"""Iteration 6 - regression + marketplace JSON sanity checks."""
import os, math, json, re
import requests, pytest

BASE = os.environ.get('REACT_APP_BACKEND_URL', 'http://localhost:3000').rstrip('/')
# Frontend .env has it
try:
    with open('/app/frontend/.env') as f:
        for line in f:
            if line.startswith('REACT_APP_BACKEND_URL='):
                BASE = line.split('=', 1)[1].strip().rstrip('/')
except Exception:
    pass

EMAIL = 'owner@keuangan-v1.app'
PWD = '3kpgWW63mV8onkZN'

@pytest.fixture(scope='module')
def token():
    r = requests.post(f'{BASE}/api/auth/login', json={'email': EMAIL, 'password': PWD}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()['token']

@pytest.fixture(scope='module')
def h(token):
    return {'Authorization': f'Bearer {token}'}

def _no_nan(obj, path='root'):
    """Assert no NaN/Infinity in nested json-like structure."""
    if isinstance(obj, float):
        assert not math.isnan(obj), f'NaN at {path}'
        assert not math.isinf(obj), f'Inf at {path}'
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _no_nan(v, f'{path}.{k}')
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _no_nan(v, f'{path}[{i}]')

def _raw_no_nan_tokens(text):
    # Python json.loads will already reject bare NaN unless allow_nan; requests uses standard json.
    # Also check raw text for JavaScript NaN/Infinity literals.
    assert not re.search(r'\bNaN\b', text), 'Raw NaN literal in response'
    assert not re.search(r'\bInfinity\b', text), 'Raw Infinity literal in response'

def test_regression_dashboard(h):
    r = requests.get(f'{BASE}/api/dashboard', headers=h, timeout=30)
    assert r.status_code == 200, r.text
    _raw_no_nan_tokens(r.text)
    _no_nan(r.json())

def test_regression_profit_loss(h):
    r = requests.get(f'{BASE}/api/reports/profit-loss', headers=h, timeout=30)
    assert r.status_code == 200, r.text
    _no_nan(r.json())

def test_regression_legacy_sale(h):
    # Need a product with stock
    prods = requests.get(f'{BASE}/api/products', headers=h, timeout=30).json()
    prod = None
    for p in prods:
        if (p.get('stock') or 0) >= 1:
            prod = p; break
    if not prod:
        # adjust stock on any product
        if not prods:
            pytest.skip('no products')
        pid = prods[0]['id']
        requests.post(f'{BASE}/api/inventory/adjust', headers=h, timeout=30, json={
            'item_type': 'product', 'item_id': pid, 'direction': 'in', 'quantity': 5, 'note': 'TEST_it6'
        })
        prod = requests.get(f'{BASE}/api/products/{pid}', headers=h, timeout=30).json()
    payload = {
        'items': [{'product_id': prod['id'], 'qty': 1, 'price': 15000}],
        'channel': 'offline', 'note': 'TEST_it6_legacy'
    }
    r = requests.post(f'{BASE}/api/sales', headers=h, timeout=30, json=payload)
    assert r.status_code in (200, 201), r.text
    data = r.json()
    assert 'net_total' in data or 'total' in data

def test_marketplace_dashboard_no_nan(h):
    r = requests.get(f'{BASE}/api/marketplace/dashboard', headers=h, params={'period': 'all'}, timeout=30)
    assert r.status_code == 200, r.text
    _raw_no_nan_tokens(r.text)
    _no_nan(r.json())

def test_marketplace_orders_no_nan_and_refund_margin(h):
    r = requests.get(f'{BASE}/api/marketplace/orders', headers=h, timeout=30)
    assert r.status_code == 200, r.text
    _raw_no_nan_tokens(r.text)
    data = r.json()
    _no_nan(data)
    orders = data if isinstance(data, list) else data.get('items') or data.get('orders') or []
    # Check margin_pct=0 when net_revenue=0 for refund/cancelled orders
    for o in orders:
        net = o.get('net_revenue')
        margin = o.get('margin_pct')
        if net == 0 and margin is not None:
            assert margin == 0, f'Order {o.get("order_id")} has net=0 but margin={margin}'
