"""Exercise a running app with synthetic data; never print credentials.

Usage: python -m scripts.smoke_test --base-url http://127.0.0.1:8001
Creates a synthetic test account/order and leaves the audit trail intact.
"""

import argparse
import secrets
import uuid

import httpx


def run(base_url: str) -> None:
    email = f"smoke-{uuid.uuid4().hex}@example.com"
    password = secrets.token_urlsafe(24)
    with httpx.Client(base_url=base_url, timeout=120) as client:
        def request(method, path, expected=200, **kwargs):
            response = client.request(method, path, **kwargs)
            assert response.status_code == expected, f"{method} {path}: expected {expected}, got {response.status_code}"
            return response.json()

        assert request("GET", "/api/security/health")["status"] == "ok"
        print("PASS health")
        user = request("POST", "/api/auth/register", expected=201, json={
            "email": email, "password": password, "full_name": "Synthetic deployment verification"
        })
        login = request("POST", "/api/auth/login", json={"email": email, "password": password})
        headers = {"Authorization": f"Bearer {login['access_token']}"}
        assert request("GET", "/api/me", headers=headers)["id"] == user["user"]["id"]
        print("PASS registration, login, persisted profile")
        products = request("GET", "/api/products")["items"]
        product = next(p for p in products if p["stock"] > 0)
        address = request("POST", "/api/me/addresses", expected=201, headers=headers, json={
            "label": "Synthetic", "line1": "1 Test Street", "city": "Test City",
            "state": "Test State", "postal_code": "000000", "country": "Test", "is_default": True
        })
        cart = request("POST", "/api/cart/items", expected=201, headers=headers,
                       json={"product_id": product["id"], "quantity": 1})
        assert cart["total_cents"] == product["price_cents"]
        order = request("POST", "/api/cart/checkout", headers=headers, json={
            "shipping_address_id": address["id"], "payment_method_display": "Synthetic test payment"
        })["order"]
        assert request("GET", f"/api/orders/{order['id']}", headers=headers)["id"] == order["id"]
        assert request("GET", "/api/cart", headers=headers)["items"] == []
        print("PASS products, saved address, cart, checkout, persisted order")
        key = request("POST", "/api/api-keys", expected=201, headers=headers, json={
            "name": "Synthetic smoke test", "environment": "development", "scopes": ["security_events:read"]
        })
        key_headers = {"Authorization": f"Bearer {key['secret']}"}
        events = request("GET", "/api/security/events", headers=key_headers)
        assert events["items"]
        request("GET", "/api/security/users", expected=403, headers=key_headers)
        request("DELETE", f"/api/api-keys/{key['key']['id']}", headers=headers)
        request("GET", "/api/security/events", expected=401, headers=key_headers)
        request("POST", "/api/auth/logout", headers=headers)
        request("GET", "/api/me", expected=401, headers=headers)
        print("PASS security event feed, permission denial, key revocation, session revocation")
        print("PASS end-to-end application smoke test")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    run(parser.parse_args().base_url)
