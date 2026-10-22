"""Every value of every native Postgres enum used by the models must exist in
the migrated database.

`alembic check` and `--autogenerate` cannot see a new enum value, so adding a
member to a Python enum without a migration passes review and then fails with
a 500 the first time that value is written.
"""
from sqlalchemy import Enum as SAEnum, text

from app import models  # noqa: F401  (registers every table on Base.metadata)
from app.db.session import Base


def _native_enums():
    seen = {}
    for table in Base.metadata.tables.values():
        for column in table.columns:
            kind = column.type
            if isinstance(kind, SAEnum) and kind.native_enum:
                seen.setdefault(kind.name, (table.name, column.name, list(kind.enums)))
    return seen


def test_every_native_enum_value_exists_in_the_database(db):
    rows = db.execute(
        text("SELECT t.typname, e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid")
    ).all()
    in_db: dict[str, set[str]] = {}
    for type_name, label in rows:
        in_db.setdefault(type_name, set()).add(label)

    missing = {
        f"{table}.{column} ({type_name})": [v for v in values if v not in in_db.get(type_name, set())]
        for type_name, (table, column, values) in _native_enums().items()
    }
    missing = {where: values for where, values in missing.items() if values}
    assert not missing, f"enum values in the models but not in the database: {missing}"
