"""Create clearly identified synthetic shoppers with intentionally public demo credentials."""
from app.audit import log_event
from app.database import SessionLocal, init_db
from app.demo_data import DEMO_EMAILS, DEMO_PASSWORD
from app.models import DemoAccount, User
from app.security import hash_password


def main():
    init_db()
    created = 0
    with SessionLocal() as db:
        for number, email in enumerate(DEMO_EMAILS, 1):
            # Never relabel or reset an existing account to expose its credentials.
            if db.query(User).filter(User.email == email).first() is not None:
                continue
            user = User(email=email, full_name=f"Demo Shopper {number} (Synthetic)",
                        hashed_password=hash_password(DEMO_PASSWORD))
            db.add(user)
            db.flush()
            db.add(DemoAccount(user_id=user.id, expected_hash=user.hashed_password))
            db.commit()
            log_event(db, None, "demo_account_created", source="synthetic", pseudo_user=user.pseudo_id)
            created += 1
    print(f"Created {created} synthetic demo shoppers. Public sample credentials appear in Admin → Users.")


if __name__ == "__main__":
    main()
