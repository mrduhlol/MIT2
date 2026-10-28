"""End-to-end tests for the commerce-testbed FastAPI backend."""

import json
import uuid

from app.models import Order, OrderItem, Product, SecurityEvent, User
from tests.conftest import all_events

AGENT_KEY_HEADER = {"X-Agent-Key": "test-agent-key"}


def registered_user(client, password="S3cretpass!x", email=None):
    email = email or f"user-{uuid.uuid4().hex[:10]}@example.com"
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "full_name": "Test User"},
    )
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    user = response.json()["user"]
    return {"email": email, "password": password, "token": token, "user": user}


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def events_in_db(db):
    return [(
        e.event_type, e.severity, e.pseudo_user, e.details, e.ip
    ) for e in all_events(db)]


def find_events(db, event_type):
    return [e for e in all_events(db) if e.event_type == event_type]


# ---------------------------------------------------------------- auth

def test_health(client):
    response = client.get("/api/security/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "commerce-testbed"
    assert "time" in body
    assert client.get("/health").status_code == 200


def test_register_and_login_happy_path(client, db):
    creds = registered_user(client)
    assert creds["user"]["email"].endswith("@example.com")
    assert "hashed_password" not in creds["user"]
    assert "password" not in creds["user"]

    # duplicate email -> 409
    dup = client.post(
        "/api/auth/register",
        json={"email": creds["email"], "password": "AnotherPass1", "full_name": "Dup"},
    )
    assert dup.status_code == 409

    # login happy path
    login = client.post(
        "/api/auth/login",
        json={"email": creds["email"], "password": creds["password"]},
    )
    assert login.status_code == 200
    assert login.json()["access_token"]
    assert login.json()["user"]["email"] == creds["email"]

    events = events_in_db(db)
    account_created = [e for e in events if e[0] == "account_created"]
    assert account_created and account_created[-1][2] == creds["user"]["pseudo_id"]


def test_short_password_rejected(client):
    response = client.post(
        "/api/auth/register",
        json={"email": f"short-{uuid.uuid4().hex[:8]}@example.com", "password": "short", "full_name": "X"},
    )
    assert response.status_code == 422


def test_login_wrong_password_401_and_event(client, db):
    creds = registered_user(client)
    n_failures_before = len(find_events(db, "login_failure"))
    response = client.post(
        "/api/auth/login",
        json={"email": creds["email"], "password": "WrongPassword1"},
    )
    assert response.status_code == 401
    failures = find_events(db, "login_failure")
    assert len(failures) == n_failures_before + 1
    details = json.loads(failures[-1].details)
    assert details["reason"] == "invalid_credentials"
    assert "email_hash" in details

    # unknown email -> 401, reason unknown_email, hashed email (not raw)
    n_before = len(find_events(db, "login_failure"))
    response = client.post(
        "/api/auth/login",
        json={"email": f"ghost-{uuid.uuid4().hex[:6]}@example.com", "password": "Whatever123"},
    )
    assert response.status_code == 401
    failures = find_events(db, "login_failure")
    assert len(failures) == n_before + 1
    details = json.loads(failures[-1].details)
    assert details["reason"] == "unknown_email"
    assert "ghost-" not in details
    assert len(details["email_hash"]) == 12


def test_password_change(client, db):
    creds = registered_user(client)
    headers = auth_headers(creds["token"])

    # wrong current password
    bad = client.put(
        "/api/me/password",
        json={"current_password": "WrongOld1!", "new_password": "NewPassword1!"},
        headers=headers,
    )
    assert bad.status_code == 400
    assert find_events(db, "password_change_failed")

    # correct change
    ok = client.put(
        "/api/me/password",
        json={"current_password": creds["password"], "new_password": "NewPassword1!"},
        headers=headers,
    )
    assert ok.status_code == 200
    assert find_events(db, "password_changed")

    # token still valid; login with new password works
    login = client.post(
        "/api/auth/login",
        json={"email": creds["email"], "password": "NewPassword1!"},
    )
    assert login.status_code == 200


def test_logout_revokes_session(client, db):
    creds = registered_user(client)
    headers = auth_headers(creds["token"])
    assert client.get("/api/me", headers=headers).status_code == 200

    logout = client.post("/api/auth/logout", headers=headers)
    assert logout.status_code == 200
    assert client.get("/api/me", headers=headers).status_code == 401


# ---------------------------------------------------------------- users

def test_protected_endpoint_requires_token_and_logs_access_denied(client, db):
    n_before = len(find_events(db, "access_denied"))
    response = client.get("/api/me")
    assert response.status_code == 401

    # bogus token -> 401 as well
    assert client.get("/api/me", headers=auth_headers("not-a-token")).status_code == 401

    denied = find_events(db, "access_denied")
    assert len(denied) >= n_before + 2
    assert any(e.ip and e.details and json.loads(e.details).get("path") == "/api/me" for e in denied)


def test_profile_update(client, db):
    creds = registered_user(client)
    headers = auth_headers(creds["token"])
    response = client.put("/api/me", json={"full_name": "Updated Name", "phone": "+15551234567"}, headers=headers)
    assert response.status_code == 200
    assert response.json()["full_name"] == "Updated Name"
    assert response.json()["phone"] == "+15551234567"
    assert find_events(db, "profile_updated")

    # invalid: no fields
    assert client.put("/api/me", json={}, headers=headers).status_code == 400


def test_address_crud_and_ownership(client, db):
    user_a = registered_user(client)
    user_b = registered_user(client)
    headers_a = auth_headers(user_a["token"])
    headers_b = auth_headers(user_b["token"])

    created = client.post(
        "/api/me/addresses",
        json={
            "label": "Home", "line1": "1 Main St", "city": "Springfield",
            "state": "IL", "postal_code": "62704", "country": "USA",
        },
        headers=headers_a,
    )
    assert created.status_code == 201
    address_id = created.json()["id"]
    assert created.json()["is_default"] is True  # first address becomes default

    # ownership: user_b cannot see user_a's address list
    assert client.get("/api/me/addresses", headers=headers_b).json() == []

    updated = client.put(
        f"/api/me/addresses/{address_id}",
        json={
            "label": "Home", "line1": "2 Main St", "city": "Springfield",
            "state": "IL", "postal_code": "62704", "country": "USA", "is_default": True,
        },
        headers=headers_b,
    )
    assert updated.status_code == 404
    assert client.delete(f"/api/me/addresses/{address_id}", headers=headers_b).status_code == 404

    # owner updates and re-reads
    updated = client.put(
        f"/api/me/addresses/{address_id}",
        json={
            "label": "Office", "line1": "9 Work Blvd", "city": "Shelbyville",
            "state": "IL", "postal_code": "62565", "country": "USA", "is_default": True,
        },
        headers=headers_a,
    )
    assert updated.status_code == 200
    assert updated.json()["line1"] == "9 Work Blvd"

    add_second = client.post(
        "/api/me/addresses",
        json={
            "label": "Cabin", "line1": "7 Lake Rd", "city": "Ogdenville",
            "state": "IL", "postal_code": "62552", "country": "USA", "is_default": True,
        },
        headers=headers_a,
    )
    assert add_second.status_code == 201
    second_id = add_second.json()["id"]

    listing = client.get("/api/me/addresses", headers=headers_a)
    assert listing.status_code == 200
    defaults = [a for a in listing.json() if a["is_default"]]
    assert len(defaults) == 1
    assert defaults[0]["id"] == second_id  # new default unset the old one

    deleted = client.delete(f"/api/me/addresses/{address_id}", headers=headers_a)
    assert deleted.status_code == 200
    ids = [a["id"] for a in client.get("/api/me/addresses", headers=headers_a).json()]
    assert address_id not in ids
    assert find_events(db, "address_changed")


def test_sessions_listing_and_revocation(client, db):
    creds = registered_user(client)
    headers = auth_headers(creds["token"])
    # a second session
    second = client.post(
        "/api/auth/login", json={"email": creds["email"], "password": creds["password"]}
    )
    assert second.status_code == 200

    sessions = client.get("/api/me/sessions", headers=headers).json()
    assert len(sessions) >= 2
    assert all("revoked" in s and "expires_at" in s and "created_at" in s for s in sessions)

    other_id = next(s["id"] for s in sessions if not s["revoked"])
    response = client.delete(f"/api/me/sessions/{other_id}", headers=headers)
    assert response.status_code == 200
    assert find_events(db, "session_revoked")

    missing = client.delete("/api/me/sessions/999999999", headers=headers)
    assert missing.status_code == 404


# ---------------------------------------------------------------- products & cart

def test_products_list_categories_detail(client):
    response = client.get("/api/products")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 40
    assert len(body["items"]) == 20  # default page size
    assert body["page"] == 1

    cats = client.get("/api/products/categories").json()
    for expected in ("Electronics", "Home & Kitchen", "Books", "Sports", "Toys", "Beauty"):
        assert expected in cats

    single = client.get("/api/products/1")
    assert single.status_code == 200
    assert "picsum.photos" in single.json()["image_url"]
    assert client.get("/api/products/999999").status_code == 404

    search = client.get("/api/products", params={"q": "headphones", "page_size": 50})
    names = [item["name"] for item in search.json()["items"]]
    assert any("Headphones" in n for n in names)

    paged = client.get("/api/products", params={"category": "Books", "page_size": 3, "page": 2})
    assert paged.json()["page"] == 2
    assert all(i["category"] == "Books" for i in paged.json()["items"])


def test_cart_add_update_remove_and_merge(client):
    creds = registered_user(client)
    headers = auth_headers(creds["token"])

    products = client.get("/api/products", params={"page_size": 5}).json()["items"]
    pid1, pid2 = products[0]["id"], products[1]["id"]

    # add -> merge on second add of same product
    add = client.post("/api/cart/items", json={"product_id": pid1, "quantity": 2}, headers=headers)
    assert add.status_code == 201
    add_again = client.post("/api/cart/items", json={"product_id": pid1, "quantity": 1}, headers=headers)
    assert add_again.status_code == 201
    items = {i["product"]["id"]: i for i in add_again.json()["items"]}
    assert items[pid1]["quantity"] == 3

    update = client.patch(f"/api/cart/items/{items[pid1]['id']}", json={"quantity": 5}, headers=headers)
    assert update.status_code == 200
    items = {i["product"]["id"]: i for i in update.json()["items"]}
    assert items[pid1]["quantity"] == 5

    client.post("/api/cart/items", json={"product_id": pid2, "quantity": 1}, headers=headers)

    current = client.get("/api/cart", headers=headers).json()
    assert current["total_cents"] == sum(i["subtotal_cents"] for i in current["items"])

    remove = client.delete(f"/api/cart/items/{items[pid1]['id']}", headers=headers)
    assert remove.status_code == 200
    remaining = client.get("/api/cart", headers=headers).json()
    assert [i["product"]["id"] for i in remaining["items"]] == [pid2]

    # 404 on item owned by nobody else / nonexistent
    assert client.patch("/api/cart/items/999999", json={"quantity": 1}, headers=headers).status_code == 404


# ---------------------------------------------------------------- orders

def test_checkout_creates_order_clears_cart_and_stock(client, db):
    creds = registered_user(client)
    headers = auth_headers(creds["token"])

    client.post(
        "/api/me/addresses",
        json={"label": "Home", "line1": "1 Main St", "city": "Springfield",
              "state": "IL", "postal_code": "62704", "country": "USA"},
        headers=headers,
    )
    addresses = client.get("/api/me/addresses", headers=headers).json()
    address_id = addresses[0]["id"]

    # empty cart checkout rejected
    assert client.post(
        "/api/cart/checkout",
        json={"shipping_address_id": address_id, "payment_method_display": "card ending 4242"},
        headers=headers,
    ).status_code == 400

    # someone else's address -> 404
    other = registered_user(client)
    client.post(
        "/api/me/addresses",
        json={"label": "Home", "line1": "2 Oak St", "city": "X", "state": "Y",
              "postal_code": "1", "country": "USA"},
        headers=auth_headers(other["token"]),
    )
    other_addr = client.get("/api/me/addresses", headers=auth_headers(other["token"])).json()[0]
    assert client.post(
        "/api/cart/checkout",
        json={"shipping_address_id": other_addr["id"], "payment_method_display": "card"},
        headers=headers,
    ).status_code == 404

    product = db.query(Product).filter(Product.stock >= 5).first()
    assert product, "seed stock too low"
    before_stock = product.stock

    add = client.post("/api/cart/items", json={"product_id": product.id, "quantity": 3}, headers=headers)
    assert add.status_code == 201
    expected_total = 3 * product.price_cents

    checkout = client.post(
        "/api/cart/checkout",
        json={"shipping_address_id": address_id, "payment_method_display": "card ending 4242"},
        headers=headers,
    )
    assert checkout.status_code == 200, checkout.text
    order_id = checkout.json()["order"]["id"]
    assert checkout.json()["order"]["total_cents"] == expected_total

    # cart is cleared
    cart = client.get("/api/cart", headers=headers).json()
    assert cart["items"] == [] and cart["total_cents"] == 0

    # stock decremented
    db.expire_all()
    assert db.get(Product, product.id).stock == before_stock - 3

    # order details
    order = client.get(f"/api/orders/{order_id}", headers=headers).json()
    assert order["status"] == "placed"
    assert order["payment_method"] == "card ending 4242"
    assert len(order["items"]) == 1
    assert order["items"][0]["quantity"] == 3

    # order_placed event without PII
    placed = find_events(db, "order_placed")
    assert placed
    details = json.loads(placed[-1].details)
    assert details["order_id"] == order_id
    assert details["total_cents"] == expected_total


def test_orders_list_and_ownership(client, db):
    owner = registered_user(client)
    stranger = registered_user(client)
    owner_headers = auth_headers(owner["token"])
    stranger_headers = auth_headers(stranger["token"])

    product = db.query(Product).first()
    order = Order(
        user_id=db.query(User).filter(User.email == owner["email"]).first().id,
        status="placed", total_cents=product.price_cents, payment_method="card ending 1111",
        items=[OrderItem(
            product_id=product.id, name_snapshot=product.name,
            price_cents=product.price_cents, quantity=1,
        )],
    )
    db.add(order)
    db.commit()

    listed = client.get("/api/orders", headers=owner_headers)
    assert listed.status_code == 200
    assert order.id in [o["id"] for o in listed.json()]

    detail = client.get(f"/api/orders/{order.id}", headers=owner_headers)
    assert detail.status_code == 200
    assert detail.json()["items"][0]["name_snapshot"] == product.name

    # stranger gets 404 (ownership enforced), and stranger's list is empty
    assert client.get(f"/api/orders/{order.id}", headers=stranger_headers).status_code == 404
    assert client.get("/api/orders", headers=stranger_headers).json() == []


# ---------------------------------------------------------------- events feed

def test_events_feed_authentication(client, db):
    # missing key -> 401
    assert client.get("/api/events/feed").status_code == 401
    # wrong key -> 403
    wrong = client.get("/api/events/feed", headers={"X-Agent-Key": "nope"})
    assert wrong.status_code == 403
    # correct key -> 200
    ok = client.get("/api/events/feed", headers=AGENT_KEY_HEADER)
    assert ok.status_code == 200
    body = ok.json()
    assert isinstance(body["events"], list) and len(body["events"]) > 0

    event = body["events"][0]
    for field in ("ts", "request_id", "source", "event_type", "severity",
                  "pseudo_user", "ip", "user_agent", "details"):
        assert field in event

    # api_key query param also accepted
    ok2 = client.get("/api/events/feed", params={"api_key": "test-agent-key", "limit": 5})
    assert ok2.status_code == 200
    assert len(ok2.json()["events"]) <= 5

    # filters
    filtered = client.get(
        "/api/events/feed",
        headers=AGENT_KEY_HEADER,
        params={"source": "synthetic"},
    )
    assert all(e["source"] == "synthetic" for e in filtered.json()["events"])

    severe = client.get(
        "/api/events/feed",
        headers=AGENT_KEY_HEADER,
        params={"severity": "high", "limit": 10},
    )
    assert all(e["severity"] == "high" for e in severe.json()["events"])

    # 'since' filter excludes older events
    all_events_feed = client.get(
        "/api/events/feed", headers=AGENT_KEY_HEADER, params={"limit": 1000}
    ).json()["events"]
    middle = all_events_feed[len(all_events_feed) // 2]["ts"]
    since_feed = client.get(
        "/api/events/feed", headers=AGENT_KEY_HEADER, params={"since": middle, "limit": 1000}
    ).json()["events"]
    assert all(e["ts"] >= middle for e in since_feed)
    assert len(since_feed) < len(all_events_feed)


# ---------------------------------------------------------------- security invariants

def test_events_never_contain_raw_password_or_secret(client, db):
    password = "VeryUniqueSecretPassword42!"
    creds = registered_user(client, password=password)

    # failed logins with that password - details must hash, not leak
    client.post("/api/auth/login", json={"email": creds["email"], "password": password[::-1]})
    client.post("/api/auth/login", json={"email": creds["email"], "password": password})
    client.post("/api/auth/login", json={"email": f"fake-{uuid.uuid4().hex[:5]}@example.com", "password": password})
    client.put("/api/me/password", json={"current_password": password, "new_password": "NewPassw0rd9!"},
               headers=auth_headers(creds["token"]))

    # sweep every stored detail blob for the raw password
    for e in all_events(db):
        raw = e.details or ""
        assert password not in raw, f"raw password leaked in event {e.id} ({e.event_type}): {raw}"
        assert creds["token"] not in (e.details or "")
        assert creds["email"] not in (e.details or "")


def test_suspicious_login_activity_after_repeated_failures(client, db):
    email = f"victim-{uuid.uuid4().hex[:8]}@example.com"
    for _ in range(5):
        response = client.post(
            "/api/auth/login", json={"email": email, "password": "WrongPass99"}
        )
        assert response.status_code == 401
    suspicious = find_events(db, "suspicious_login_activity")
    assert suspicious
    last = suspicious[-1]
    details = json.loads(last.details)
    assert details["email_hash"]
    assert last.severity == "high"
    assert email not in (last.details or "")
    # de-duplicated within the window
    count_same_window = len([e for e in suspicious if json.loads(e.details or "{}").get("email_hash")])
    # only one suspicious event per email hash should exist for this test run
    hashes = [json.loads(e.details or "{}").get("email_hash") for e in suspicious]
    assert hashes.count(details["email_hash"]) == 1
