"""One-off addition: insert more test customers into customer_test, one row
per clinic_id (1-5) for each person, without touching existing rows.

Run manually, with the project's env vars available (see local.settings.json
/ .env), e.g.:
    source .venv/bin/activate
    python add_customers.py

Uses the same Databricks connection helper as the rest of the app
(db_utils.get_connection). Upserts on (email, clinic_id) so no duplicate
rows are created, whether re-run or run after an email already exists from
an earlier seed (e.g. jvm@analyticsintellect.com from setup_clinic_mapping.py).
"""

import json
import os


def _load_local_settings():
    """Populate os.environ from local.settings.json when running outside
    `func start` (e.g. plain `python add_customers.py`), without overriding
    any variables already set in the real environment."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local.settings.json")
    if not os.path.exists(path):
        return
    with open(path) as f:
        values = json.load(f).get("Values", {})
    for key, value in values.items():
        os.environ.setdefault(key, str(value))


_load_local_settings()

from db_utils import get_connection, test_customer_table_name  # noqa: E402

# (full name, email) -> split into (fname, lname) on the first space.
PEOPLE = [
    ("Hamza Al-Saadi", "hamza@viasmiles.com"),
    ("Javaid Mir", "jvm@analyticsintellect.com"),
    ("Nick Rains", "nick@viasmiles.com"),
    ("Ahmet Mutlu Celikok", "ahmet@viasmiles.com"),
    ("Mahmoud Kounkourou", "mahmoud@viasmiles.com"),
    ("Abdurrehman Malekji", "abumalekji@gmail.com"),
    ("Mahmoud Kounkourou", "mk@analyticsintellect.com"),
    ("Abdurrehman Malekji", "am@viasmiles.com"),
    ("Mahmoud Kounkourou", "kounkour@gmail.com"),
    ("Abdurrehman Malekji", "am@analyticsintellect.com"),
    ("Anish Mansuri", "anm@analyticsintellect.com"),
    ("Alsaadihamza9", "Alsaadihamza9@gmail.com"),
    ("Hamza Al-Saadi", "Hamzaalsaadi5@gmail.com"),
    ("Jahangir Mukhdoomi", "Jahangirmukhdoomi@gmail.com"),
]
CLINIC_IDS = [1, 2, 3, 4, 5]


def _split_name(full_name):
    parts = full_name.split(" ", 1)
    return parts[0], parts[1] if len(parts) > 1 else ""


def _dedupe_by_email(people):
    seen = set()
    deduped = []
    for full_name, email in people:
        key = email.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append((full_name, email))
    return deduped


CUSTOMERS = [
    (*_split_name(full_name), email, clinic_id)
    for full_name, email in _dedupe_by_email(PEOPLE)
    for clinic_id in CLINIC_IDS
]


def add_customers(cursor):
    table = test_customer_table_name()
    for fname, lname, email, clinic_id in CUSTOMERS:
        cursor.execute(
            f"MERGE INTO {table} AS target "
            "USING (SELECT ? AS fname, ? AS lname, ? AS email, ? AS clinic_id) AS src "
            "ON lower(target.email) = lower(src.email) AND target.clinic_id = src.clinic_id "
            "WHEN MATCHED THEN UPDATE SET fname = src.fname, lname = src.lname "
            "WHEN NOT MATCHED THEN INSERT (fname, lname, email, clinic_id) "
            "VALUES (src.fname, src.lname, src.email, src.clinic_id)",
            [fname, lname, email, clinic_id],
        )
    print(f"Upserted {len(CUSTOMERS)} rows ({len(PEOPLE)} people x {len(CLINIC_IDS)} clinics) into {table}, no duplicates")


def main():
    with get_connection() as conn:
        with conn.cursor() as cursor:
            add_customers(cursor)


if __name__ == "__main__":
    main()
