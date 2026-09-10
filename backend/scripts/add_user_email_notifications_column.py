"""
One-off migration: add User.email_notifications (Module 9).

The app creates tables with Base.metadata.create_all, which builds missing
tables but never alters existing ones. A database created before Module 9
existed therefore needs this column added by hand — this script does that,
and is safe to run more than once.

The column is NOT NULL with a default of true. Both matter: the model declares
it non-nullable, and existing rows need a value at the moment the column
appears. True is the right default because everything the platform sends is
transactional — a candidate's own report, a recruiter's own work queue — not
marketing. It remains a real switch; users can turn it off in the app.

    python -m scripts.add_user_email_notifications_column
"""

from sqlalchemy import inspect, text

from app.db.session import engine

TABLE = "users"
COLUMN = "email_notifications"

# SQLite has no boolean literal, so its default is written as 1. The column
# definition is kept whole rather than split into type and default, because the
# two have to agree per dialect.
COLUMN_SPEC = {
    "postgresql": "BOOLEAN NOT NULL DEFAULT true",
    "sqlite": "BOOLEAN NOT NULL DEFAULT 1",
}


def main() -> None:
    dialect = engine.dialect.name
    inspector = inspect(engine)

    if TABLE not in inspector.get_table_names():
        print(f"{TABLE} does not exist yet — start the app once to create it.")
        return

    existing = {column["name"] for column in inspector.get_columns(TABLE)}
    if COLUMN in existing:
        print(f"{TABLE}.{COLUMN}: already present")
        return

    spec = COLUMN_SPEC.get(dialect, COLUMN_SPEC["sqlite"])
    with engine.begin() as connection:
        connection.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} {spec}"))
    print(f"{TABLE}.{COLUMN}: added ({spec})")


if __name__ == "__main__":
    main()
