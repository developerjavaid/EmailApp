"""One-off migration: add clinic_id to customer_test, create the clinic
mapping table (clinic_id -> name/template_name/from_email/source_table/
column mapping), seed the clinic table, then wipe and reload customer_test
with 3 testers x 5 clinics each (15 rows total).

source_table/email_column/first_name_column/last_name_column let the app
read each clinic's customers from a table and column names chosen per
clinic (and changed later just by updating this row) instead of a
hardcoded table/schema. All 5 clinics below point at customer_test's own
column names (email/fname/lname) - update the CLINICS table below if a
clinic's source table or column names change.

Run manually, with the project's env vars available (see local.settings.json
/ .env), e.g.:
    source .venv/bin/activate
    python setup_clinic_mapping.py

Uses the same Databricks connection helper as the rest of the app
(db_utils.get_connection).
"""

import json
import os


def _load_local_settings():
    """Populate os.environ from local.settings.json when running outside
    `func start` (e.g. plain `python setup_clinic_mapping.py`), without
    overriding any variables already set in the real environment."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local.settings.json")
    if not os.path.exists(path):
        return
    with open(path) as f:
        values = json.load(f).get("Values", {})
    for key, value in values.items():
        os.environ.setdefault(key, str(value))


_load_local_settings()

from db_utils import clinic_table_name, get_connection, test_customer_table_name  # noqa: E402

# (clinic_id, name, template_name, from_email, source_table, email_column,
# first_name_column, last_name_column). source_table is computed below
# (test_customer_table_name()) since all 5 clinics currently share
# customer_test; repoint an individual clinic at a different table by
# editing its source_table/column names here and re-running this script.
_CUSTOMER_TEST = test_customer_table_name()
CLINICS = [
    (1, "Georgia", "georgia_implants_and_dentures.html", "hello@georgiaimplantsanddentures.com",
     _CUSTOMER_TEST, "email", "fname", "lname"),
    (2, "Ohio", "ohio_implants_and_dentures.html", "hello@ohioimplantsanddentures.com",
     _CUSTOMER_TEST, "email", "fname", "lname"),
    (3, "Columbus", "viasmiles_columbus.html", "hello-columbus@viasmiles.com",
     _CUSTOMER_TEST, "email", "fname", "lname"),
    (4, "Pittsburgh", "viasmiles_pittsburgh.html", "hello-Pittsburgh@viasmiles.com",
     _CUSTOMER_TEST, "email", "fname", "lname"),
    (5, "Exton", "viasmiles_exton.html", "hello-exton@viasmiles.com",
     _CUSTOMER_TEST, "email", "fname", "lname"),
]

# Replaces all existing customer_test rows: 3 people x all 5 clinics,
# so each tester gets one row per clinic (15 rows total).
TEST_PEOPLE = [
    ("Javaid", "", "jvm@analyticsintellect.com"),
    ("Jahangir", "", "jm@analyticsintellect.com"),
    ("Abdur", "", "AM@analyticsintellect.com"),
]
CLINIC_IDS = [1, 2, 3, 4, 5]
CUSTOMERS = [
    (fname, lname, email, clinic_id)
    for fname, lname, email in TEST_PEOPLE
    for clinic_id in CLINIC_IDS
]


def create_and_seed_clinic_table(cursor):
    table = clinic_table_name()
    cursor.execute(
        f"CREATE TABLE IF NOT EXISTS {table} ("
        "  clinic_id INT,"
        "  name STRING,"
        "  template_name STRING,"
        "  from_email STRING,"
        "  source_table STRING,"
        "  email_column STRING,"
        "  first_name_column STRING,"
        "  last_name_column STRING"
        ")"
    )
    try:
        cursor.execute(
            f"ALTER TABLE {table} ADD COLUMNS ("
            "  source_table STRING, email_column STRING, first_name_column STRING,"
            "  last_name_column STRING"
            ")"
        )
        print(f"Added source_table/column-mapping columns to {table}")
    except Exception as e:
        print(f"Skipping ADD COLUMNS (likely already exists): {e}")

    try:
        cursor.execute(f"ALTER TABLE {table} DROP COLUMN customer_name_column")
        print(f"Dropped unused customer_name_column from {table}")
    except Exception as e:
        print(f"Skipping DROP COLUMN customer_name_column (likely already gone, or column "
              f"mapping isn't enabled on this table - harmless either way): {e}")

    for (clinic_id, name, template_name, from_email, source_table, email_column,
         first_name_column, last_name_column) in CLINICS:
        cursor.execute(
            f"MERGE INTO {table} AS target "
            "USING (SELECT ? AS clinic_id, ? AS name, ? AS template_name, ? AS from_email, "
            "  ? AS source_table, ? AS email_column, ? AS first_name_column, "
            "  ? AS last_name_column) AS src "
            "ON target.clinic_id = src.clinic_id "
            "WHEN MATCHED THEN UPDATE SET name = src.name, template_name = src.template_name, "
            "  from_email = src.from_email, source_table = src.source_table, "
            "  email_column = src.email_column, first_name_column = src.first_name_column, "
            "  last_name_column = src.last_name_column "
            "WHEN NOT MATCHED THEN INSERT (clinic_id, name, template_name, from_email, source_table, "
            "  email_column, first_name_column, last_name_column) "
            "VALUES (src.clinic_id, src.name, src.template_name, src.from_email, src.source_table, "
            "  src.email_column, src.first_name_column, src.last_name_column)",
            [clinic_id, name, template_name, from_email, source_table, email_column,
             first_name_column, last_name_column],
        )
    print(f"clinic table ready: {table} ({len(CLINICS)} rows)")


def add_clinic_id_to_customer_test(cursor):
    table = test_customer_table_name()
    try:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMNS (clinic_id INT)")
        print(f"Added clinic_id column to {table}")
    except Exception as e:
        print(f"Skipping ADD COLUMNS (likely already exists): {e}")


def reset_customers(cursor):
    """Wipe customer_test and reload it with CUSTOMERS (one row per
    person per clinic). Emails repeat across clinic_id on purpose, so this
    is a plain DELETE + INSERT rather than an email-keyed MERGE."""
    table = test_customer_table_name()
    cursor.execute(f"DELETE FROM {table}")
    print(f"Deleted all existing rows from {table}")

    insert_sql = f"INSERT INTO {table} (fname, lname, email, clinic_id) VALUES (?, ?, ?, ?)"
    cursor.executemany(insert_sql, [list(row) for row in CUSTOMERS])
    print(f"Inserted {len(CUSTOMERS)} rows into {table}")


def main():
    with get_connection() as conn:
        with conn.cursor() as cursor:
            create_and_seed_clinic_table(cursor)
            add_clinic_id_to_customer_test(cursor)
            reset_customers(cursor)


if __name__ == "__main__":
    main()
