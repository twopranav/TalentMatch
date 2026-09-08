"""
Seed script: creates 15 admin-track + 20 user/recruiter-track test accounts.

WHY IT'S SHAPED THIS WAY (updated for the recruiter-signup patch)
-------------------------------------------------------------------
Two backend fixes now applied (see backend_fixes/ if you're reading this
alongside them):
  - auth.py's register() now persists full_name/phone (was silently
    dropping them).
  - UserCreate now accepts role="user"|"recruiter" at signup. Signing up
    as "recruiter" doesn't grant the role immediately — it only sets
    requested_role, recorded on the User row. The account is a normal,
    functional USER until an admin activates it via PATCH /users/{id}/active;
    THAT action is what promotes requested_role="recruiter" accounts to
    role=RECRUITER. Never activated -> stays a USER, forever, by design.

So this script now:
  - Registers 15 accounts with default role (USER) -> admin track
  - Registers 10 accounts with default role (USER) -> user track
  - Registers 10 accounts with role="recruiter" -> recruiter track
    (they land as role=USER, requested_role=RECRUITER, is_active=False)
  - Activates all 35 via PATCH /users/{id}/active
    -> this alone promotes the 10 recruiter-track accounts to RECRUITER
  - Promotes the 15 admin-track accounts to ADMIN via admin-status

FILL THESE IN BEFORE RUNNING
-----------------------------
BASE_URL, SUPERUSER_EMAIL, and SUPERUSER_PASSWORD below — everything else
(paths, payload shapes, field names) is confirmed against your actual
auth.py / users.py / models/user.py / schemas/user.py.
"""

import random
import string
import uuid
import requests

# ---------------------------------------------------------------------------
# CONFIG — adjust to match your actual API
# ---------------------------------------------------------------------------
BASE_URL = "http://localhost:8000"

# Your existing superuser login (you're already logged in via the frontend,
# but this script talks to the API directly, so it needs its own token).
SUPERUSER_EMAIL = "twopranav@gmail.com"
SUPERUSER_PASSWORD = "emmveepk1234"

REGISTER_PATH = "/auth/register"          # confirmed from auth.py
LOGIN_PATH = "/auth/login"                # confirmed from auth.py
ACTIVATE_PATH_TEMPLATE = "/users/{id}/active"            # confirmed from users.py
ADMIN_STATUS_PATH_TEMPLATE = "/users/{id}/admin-status"  # confirmed from users.py

N_ADMIN = 15
N_USER = 10
N_RECRUITER_INTENDED = 10

# ---------------------------------------------------------------------------
# Random-but-unique account data
# ---------------------------------------------------------------------------
FIRST_NAMES = ["Aditi", "Rohan", "Kavya", "Arjun", "Meera", "Vikram", "Ananya",
               "Ishaan", "Priya", "Karan", "Sneha", "Nikhil", "Tara", "Dev", "Riya"]
LAST_NAMES = ["Sharma", "Patel", "Reddy", "Iyer", "Nair", "Gupta", "Rao",
              "Mehta", "Joshi", "Kapoor", "Verma", "Chatterjee", "Bose", "Menon"]


def random_person():
    """
    Builds one fake-but-plausible identity.

    Why uuid4().hex[:8] is in the email: first/last name combos will repeat
    once you generate 35 of them from a 15x14-name pool, but the email must
    be unique (it's almost certainly the DB's unique key / login identifier).
    The random hex suffix guarantees uniqueness without you having to track
    which names you've already used.
    """
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    unique_suffix = uuid.uuid4().hex[:8]
    email = f"{first.lower()}.{last.lower()}.{unique_suffix}@example.com"
    password = "".join(random.choices(string.ascii_letters + string.digits, k=12)) + "!1"
    return {
        "email": email,
        "password": password,
        "full_name": f"{first} {last}",
    }


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------
def register(person):
    """
    POST the new account. `person` may include "role": "recruiter" — the
    schema now accepts that at signup, but it only records a *request*
    (requested_role) rather than granting the role outright. Omit "role"
    entirely (or pass "user") for a plain account; UserCreate defaults to
    "user" either way.
    """
    resp = requests.post(f"{BASE_URL}{REGISTER_PATH}", json=person)
    resp.raise_for_status()
    return resp.json()  # includes the new user's id (UserRead)


def login_superuser():
    """
    Gets a bearer token for the account you're already logged in as in the
    browser. The script needs its own token because it's a separate,
    stateless HTTP client — it doesn't share your browser's session/cookies.

    IMPORTANT: /auth/login uses FastAPI's OAuth2PasswordRequestForm, which
    reads from a form body (application/x-www-form-urlencoded), not JSON —
    that's why this uses `data=` instead of `json=`. The form field is
    literally called "username" even though we're passing an email into it;
    that's OAuth2PasswordRequestForm's fixed field name, not a choice this
    backend made.
    """
    resp = requests.post(
        f"{BASE_URL}{LOGIN_PATH}",
        data={"username": SUPERUSER_EMAIL, "password": SUPERUSER_PASSWORD},
    )
    resp.raise_for_status()
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def activate(user_id, headers):
    """
    UserActiveUpdate expects {"is_active": bool} — confirmed from schemas/user.py.
    """
    resp = requests.patch(
        f"{BASE_URL}{ACTIVATE_PATH_TEMPLATE.format(id=user_id)}",
        json={"is_active": True},
        headers=headers,
    )
    resp.raise_for_status()


def set_role(user_id, role, headers):
    """
    role must be the enum's *value* string, not its name — UserRole is a
    str-Enum defined as ADMIN = "admin", USER = "user", etc. Pydantic
    matches incoming JSON against the value ("admin"), not the Python
    identifier (ADMIN). Sending "ADMIN" here would fail validation.
    The endpoint itself only accepts "admin" or "user" — anything else 400s.
    """
    resp = requests.patch(
        f"{BASE_URL}{ADMIN_STATUS_PATH_TEMPLATE.format(id=user_id)}",
        json={"role": role},
        headers=headers,
    )
    resp.raise_for_status()


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def main():
    headers = login_superuser()

    admin_track, user_track, recruiter_track = [], [], []

    # Register all 35 up front. Each registered account is tagged locally
    # with what it's *meant* to become — the API has no concept of this yet,
    # so we track it ourselves in these three lists.
    for _ in range(N_ADMIN):
        p = random_person()
        created = register(p)
        admin_track.append({**p, "id": created["id"]})

    for _ in range(N_USER):
        p = random_person()
        created = register(p)
        user_track.append({**p, "id": created["id"]})

    for _ in range(N_RECRUITER_INTENDED):
        p = random_person()
        p["role"] = "recruiter"  # enum VALUE — records a pending request, doesn't grant it yet
        created = register(p)
        recruiter_track.append({**p, "id": created["id"]})

    # Activate everyone — all 35 need is_active flipped regardless of
    # eventual role, since registration leaves them inactive. For the
    # recruiter_track accounts, this single call is also what promotes
    # them to role=RECRUITER server-side (see update_user_active in users.py).
    for account in admin_track + user_track + recruiter_track:
        activate(account["id"], headers)

    # Promote only the admin-track accounts to ADMIN. recruiter_track
    # accounts were already promoted to RECRUITER by activate() above —
    # nothing further to do for them here.
    for account in admin_track:
        set_role(account["id"], "admin", headers)  # enum VALUE, not name

    # Report what actually happened, not what was intended.
    print(f"Created & activated {len(admin_track)} accounts, promoted to ADMIN.")
    print(f"Created & activated {len(user_track)} accounts, left as USER (as intended).")
    print(f"Created, activated & promoted {len(recruiter_track)} accounts to RECRUITER:")
    for account in recruiter_track:
        print(f"  id={account['id']}  email={account['email']}")


if __name__ == "__main__":
    main()