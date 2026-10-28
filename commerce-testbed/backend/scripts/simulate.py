"""Synthetic data generator for the commerce-testbed.

Writes DIRECTLY to the database (users, orders, cart events) and to
SecurityEvent rows with source="synthetic". It creates ~8 synthetic fake
users, normal browsing/order activity over the past 7 days, and two
simulated incidents:

  1. Credential stuffing: one IP, hundreds of login_failure events across
     many different attempted email hashes within a 10-minute window
     (severity medium).
  2. Account takeover attempt: many login_failures for one account from an
     unusual IP, followed by a login_success / session_created /
     password_changed / address_changed chain (chain severity high).

Usage:
    python -m scripts.simulate               # (from the backend/ directory)
    python scripts/simulate.py               # also works
    python scripts/simulate.py --db /path/to/app.db
"""

import argparse
import json
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Make "app" importable whether run as a module or a plain script.
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic e-commerce activity and security incidents.")
    parser.add_argument(
        "--db",
        default=None,
        help="Path to the SQLite database file to write to (default: app DATABASE_URL).",
    )
    args = parser.parse_args()

    if args.db:
        abs_path = Path(args.db).resolve()
        os.environ["DATABASE_URL"] = f"sqlite:///{abs_path}"

    from app import seed_data
    from app.audit import email_hash
    from app.database import SessionLocal, init_db
    from app.models import (
        Address,
        CartItem,
        Order,
        OrderItem,
        Product,
        SecurityEvent,
        User,
    )
    from app.security import hash_password

    init_db()

    random.seed(1337)  # deterministic, reproducible runs
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    db = SessionLocal()
    events_created: list[SecurityEvent] = []

    def iso(dt: datetime) -> str:
        return dt.isoformat()

    def rand_ts(start: datetime, end: datetime) -> datetime:
        delta = (end - start).total_seconds()
        offset = random.uniform(0, max(delta, 1))
        # Trim microseconds a bit for tidier output.
        return (start + timedelta(seconds=offset)).replace(microsecond=random.randint(0, 999999))

    def add_event(
        ts: datetime,
        event_type: str,
        severity: str = "low",
        pseudo_user: str | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
        details: dict | None = None,
    ) -> SecurityEvent:
        event = SecurityEvent(
            ts=iso(ts),
            request_id=uuid.uuid4().hex,
            source="synthetic",
            event_type=event_type,
            severity=severity,
            pseudo_user=pseudo_user,
            ip=ip,
            user_agent=user_agent,
            details=json.dumps(details) if details else None,
        )
        db.add(event)
        events_created.append(event)
        return event

    usernames = ["Alex", "Bailey", "Casey", "Drew", "Emery", "Fran", "Gale", "Harper"]

    users = []
    products = db.query(Product).all()
    product_by_name = {p.name: p for p in products}

    # ---------- synthetic users ----------
    for i, uname in enumerate(usernames, start=1):
        email = f"synthetic.user{i}.{uname.lower()}@example.test"
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            users.append(existing)
            continue
        user = User(
            email=email,
            hashed_password=hash_password(f"Synthetic!Pass{i}"),
            full_name=f"{uname} Synthetica",
            phone=f"+15550001{i:03d}",
            pseudo_id=uuid.uuid4().hex,
        )
        db.add(user)
        db.flush()
        addr = Address(
            user_id=user.id,
            label="Home",
            line1=f"{100 + i} Mockingbird Lane",
            city="Testville",
            state="TS",
            postal_code=f"1000{i}",
            country="USA",
            is_default=True,
        )
        db.add(addr)
        users.append(user)
    db.commit()

    ua = "commerce-simulator/1.0 (synthetic)"

    # ---------- normal activity over the past 7 days ----------
    orders_created = 0
    for user in users:
        pseudo = user.pseudo_id
        synthetic_flag = {"synthetic": True, "user": user.full_name}
        # a few logins spread over the week
        for _ in range(random.randint(2, 4)):
            ts = rand_ts(week_ago, now - timedelta(hours=2))
            add_event(ts, "login_success", "low", pseudo, ip="198.51.100.7",
                      details={"email_hash": email_hash(user.email), **synthetic_flag})
            add_event(ts + timedelta(seconds=1), "session_created", "low", pseudo,
                      ip="198.51.100.7", details={"reason": "login", **synthetic_flag})
        # an order or two from the seed products
        for _ in range(random.randint(1, 2)):
            ts = rand_ts(week_ago, now - timedelta(hours=1))
            chosen = random.sample(products, k=random.randint(1, 3))
            total = 0
            order = Order(
                user_id=user.id, created_at=ts.replace(tzinfo=None), status="placed",
                total_cents=0, payment_method="card ending 4242",
            )
            db.add(order)
            db.flush()
            for product in chosen:
                qty = random.randint(1, 2)
                total += product.price_cents * qty
                db.add(OrderItem(
                    order_id=order.id, product_id=product.id,
                    name_snapshot=product.name, price_cents=product.price_cents,
                    quantity=qty,
                ))
                product.stock = max(0, product.stock - qty)
            order.total_cents = total
            orders_created += 1
            add_event(ts, "order_placed", "low", pseudo, ip="198.51.100.7",
                      details={"order_id": order.id, "total_cents": total, **synthetic_flag})
        # occasional cart churn
        for _ in range(random.randint(1, 3)):
            ts = rand_ts(week_ago, now)
            product = random.choice(products)
            if random.random() < 0.5:
                db.add(CartItem(
                    user_id=user.id, product_id=product.id,
                    quantity=random.randint(1, 3),
                    created_at=ts.replace(tzinfo=None),
                ))
                db.commit()
            add_event(ts, "cart_updated", "low", pseudo, ip="198.51.100.7",
                      details={"product_id": product.id, "action": "add", **synthetic_flag})
    db.commit()

    # ---------- incident 1: credential stuffing ----------
    stuffing_ip = "203.0.113.66"
    t_end = now - timedelta(days=2, hours=5)
    t_start = t_end - timedelta(minutes=10)
    stuffing_count = 150
    for i in range(stuffing_count):
        ts = rand_ts(t_start, t_end)
        victim_email = f"victim{i}@example.test"
        add_event(
            ts,
            "login_failure",
            "medium",
            pseudo_user=None,
            ip=stuffing_ip,
            user_agent="python-requests/2.31 (stuffing-bot)",
            details={
                "reason": "invalid_credentials",
                "email_hash": email_hash(victim_email),
                "attempt": i + 1,
                "incident": "credential_stuffing",
                "synthetic": True,
            },
        )
    db.commit()

    # ---------- incident 2: account takeover attempt ----------
    ato_ip = "198.51.100.23"
    target_user = users[0]
    target_ehash = email_hash(target_user.email)
    base = now - timedelta(days=1, hours=6)
    failure_count = 12
    t = base
    for i in range(failure_count):
        t += timedelta(minutes=random.randint(2, 10))
        add_event(
            t,
            "login_failure",
            "medium",
            pseudo_user=target_user.pseudo_id,
            ip=ato_ip,
            user_agent="curl/8.4.0",
            details={
                "reason": "invalid_credentials",
                "email_hash": target_ehash,
                "attempt": i + 1,
                "incident": "account_takeover_attempt",
                "synthetic": True,
            },
        )
    # the takeover chain
    t_success = t + timedelta(minutes=3)
    add_event(t_success, "login_success", "high", target_user.pseudo_id, ip=ato_ip,
              user_agent="curl/8.4.0",
              details={"email_hash": target_ehash, "incident": "account_takeover_attempt",
                       "synthetic": True})
    add_event(t_success + timedelta(seconds=2), "session_created", "high",
              target_user.pseudo_id, ip=ato_ip, user_agent="curl/8.4.0",
              details={"reason": "login", "incident": "account_takeover_attempt",
                       "synthetic": True})
    add_event(t_success + timedelta(minutes=4), "password_changed", "high",
              target_user.pseudo_id, ip=ato_ip, user_agent="curl/8.4.0",
              details={"incident": "account_takeover_attempt", "synthetic": True})
    add_event(t_success + timedelta(minutes=6), "address_changed", "high",
              target_user.pseudo_id, ip=ato_ip, user_agent="curl/8.4.0",
              details={"action": "created", "incident": "account_takeover_attempt",
                       "synthetic": True})
    db.commit()

    # ---------- summary ----------
    counts: dict[str, int] = {}
    for ev in events_created:
        counts[ev.event_type] = counts.get(ev.event_type, 0) + 1
    total_events = db.query(SecurityEvent).count()
    total_users = db.query(User).count()
    total_orders = db.query(Order).count()
    products_seeded = db.query(Product).count()

    print("=== commerce-testbed simulation summary ===")
    print(f"Database:                 {_BACKEND_DIR / 'data' if not args.db else args.db}")
    print(f"Synthetic users ensured:  {len(users)}")
    print(f"Products in DB:           {products_seeded}")
    print(f"Synthetic orders placed:  {orders_created}")
    print(f"Synthetic events written: {len(events_created)}")
    print("Simulated incidents:")
    print(f"  - credential stuffing:       {stuffing_count} login_failure events "
          f"from {stuffing_ip} over a 10-minute window (severity medium)")
    print(f"  - account takeover attempt:  {failure_count} login_failure events "
          f"from {ato_ip}, then login_success/session_created/password_changed/"
          f"address_changed chain (severity high)")
    print(f"Event counts by type:")
    for event_type in sorted(counts):
        print(f"  {event_type:<28} {counts[event_type]}")
    print(f"Total security events in DB: {total_events}")
    print(f"Total users in DB:           {total_users}")
    print(f"Total orders in DB:          {total_orders}")

    db.close()


if __name__ == "__main__":
    main()
