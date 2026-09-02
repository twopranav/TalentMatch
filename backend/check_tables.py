from app.db.session import engine
from sqlalchemy import text

with engine.connect() as conn:
    result = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))
    print(result.fetchall())

from app.db.session import engine
from sqlalchemy import text

with engine.connect() as conn:
    result = conn.execute(text("SELECT version_num FROM alembic_version"))
    print(result.fetchall())