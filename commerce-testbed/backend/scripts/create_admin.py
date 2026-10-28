"""Provision an administrator explicitly; passwords are never saved or printed.

python -m scripts.create_admin --email owner@example.com
Use --password-stdin for private automation input.
"""
import argparse
import getpass
import sys

from app.audit import log_event
from app.database import SessionLocal, init_db
from app.models import AdminRole, SessionRecord, User, utcnow
from app.security import hash_password


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password-stdin", action="store_true")
    args = parser.parse_args()
    password = sys.stdin.readline().rstrip("\r\n") if args.password_stdin else getpass.getpass("Administrator password: ")
    if len(password) < 8:
        parser.error("Password must contain at least 8 characters")
    init_db()
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == args.email.strip().lower()).first()
        if user is None:
            user = User(email=args.email.strip().lower(), full_name="Amezon Administrator", hashed_password=hash_password(password))
            db.add(user)
            db.flush()
        else:
            user.hashed_password = hash_password(password)
            user.is_active = True
            db.query(SessionRecord).filter(SessionRecord.user_id == user.id, SessionRecord.revoked_at.is_(None)).update({"revoked_at": utcnow()})
        if db.get(AdminRole, user.id) is None:
            db.add(AdminRole(user_id=user.id))
        db.commit()
        log_event(db, None, "admin_account_provisioned", pseudo_user=user.pseudo_id, details={"role": "admin"})
    print("Administrator provisioned; password stored only as a bcrypt hash.")


if __name__ == "__main__":
    main()
