"""
One-time manual bootstrap for the single ADMIN account.
Run once via `python -m scripts.create_admin`, then never again — this is
NOT wired into main.py and should never become an HTTP endpoint.
"""
from backend.app.db.session import SessionLocal
from backend.app.core.security import hash_password
from backend.app.models.user import User, UserRole

def main():
    db = SessionLocal()
    try:
        existing_admin = db.query(User).filter(User.role == UserRole.ADMIN).first()
        if existing_admin:
            print(f"An admin already exists: {existing_admin.email}. Aborting.")
            return
        email = input("Admin email: ").strip()
        password = input("Admin password: ").strip()
        admin = User(email=email, hashed_password=hash_password(password), role=UserRole.ADMIN)
        db.add(admin)
        db.commit()
        print(f"Admin created: {email}")
    finally:
        db.close()

if __name__ == "__main__":
    main()