"""
One-time manual bootstrap for the single SUPERUSER account.

Run once via:
    python scripts/create_superuser.py

This is NOT wired into main.py and should never become an HTTP endpoint.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend")) # Add backend/ to import path for `app.*`.
from app.db.session import SessionLocal         # IGNORE
from app.core.security import hash_password     # RED
from app.models.user import User, UserRole      # SQUIGGLES


def main():
    db = SessionLocal()

    try:
        existing_superuser = (
            db.query(User)
            .filter(User.role == UserRole.SUPERUSER)
            .first()
        )
        if existing_superuser:
            print(
                f"A superuser already exists: "
                f"{existing_superuser.email}. Aborting."
            )
            return
        email = input("Superuser email: ").strip()
        password = input("Superuser password: ").strip()
        superuser = User(
            email=email,
            hashed_password=hash_password(password),
            role=UserRole.SUPERUSER,
            is_active=True,
        )
        db.add(superuser)
        db.commit()
        print(f"Superuser created: {email}")
    finally:
        db.close()

if __name__ == "__main__":
    main()