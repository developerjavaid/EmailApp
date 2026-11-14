"""One-off loader: create marketing.leads and bulk-load a prospects CSV into it.

Run manually, e.g.:
    python load_leads_csv.py "/home/javaid/Downloads/OneDrive_2026-10-10/Leads File by Clinic/U6637830 Prospects List.csv"

Uses the same Databricks connection helper as the rest of the app
(db_utils.get_connection), so it must be run with the project's env vars
available (DATABRICKS_SERVER_HOSTNAME, DATABRICKS_HTTP_PATH, AAD_CLIENT_ID,
AAD_TENANT_ID, KEY_VAULT_URL, etc. -- see local.settings.json / .env).
"""

import csv
import json
import os
import sys


def _load_local_settings():
    """Populate os.environ from local.settings.json when running outside
    `func start` (e.g. plain `python load_leads_csv.py ...`), without
    overriding any variables already set in the real environment."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local.settings.json")
    if not os.path.exists(path):
        return
    with open(path) as f:
        values = json.load(f).get("Values", {})
    for key, value in values.items():
        os.environ.setdefault(key, str(value))


_load_local_settings()

from db_utils import get_connection, _catalog

SCHEMA = "viasmiles_campaigns"
TABLE = "lead"

# Source CSV header -> standardized (snake_case) column name, in file order.
COLUMN_MAP = [
    ("PREFIXTTL", "prefix_ttl"),
    ("INDIVIDUALNAME", "individual_name"),
    ("FIRSTNAME", "first_name"),
    ("MIDDLENAME", "middle_name"),
    ("LASTNAME", "last_name"),
    ("ADDRESS", "address"),
    ("ADDRESS2LINE", "address2_line"),
    ("CITY", "city"),
    ("STATE", "state"),
    ("ZIP", "zip"),
    ("ZIP4", "zip4"),
    ("DPBC", "dpbc"),
    ("KEYCODE", "keycode"),
    ("UKEYCODE1", "ukeycode1"),
    ("CONFIDENCECODE", "confidence_code"),
    ("FIPS_COUNTY_NAME", "fips_county_name"),
    ("ITACOMB", "itacomb"),
    ("GENDER", "gender"),
    ("AGEOFINDIVIDUAL", "age_of_individual"),
    ("ESTIMATEDINCOMEHIGHERRANGES", "estimated_income_higher_ranges"),
    ("BUSINESSOWNER", "business_owner"),
    ("EMAIL", "email"),
    ("IBE2359", "ibe2359"),
    ("IBE2359_DESCRIPTION", "ibe2359_description"),
    ("AUTOWORK", "autowork"),
    ("BOATING", "boating"),
    ("FASH", "fash"),
    ("FISHING", "fishing"),
    ("GOLF", "golf"),
    ("GRCHLD", "grchld"),
    ("OWNDOG", "owndog"),
    ("PHOTOGR", "photogr"),
    ("RLESTINV", "rlestinv"),
    ("SELFIMPR", "selfimpr"),
    ("SNOWSKIING", "snowskiing"),
    ("STOCKSBOND", "stocksbond"),
    ("SWPCONT", "swpcont"),
    ("VACATIONTRAVEL_RV", "vacationtravel_rv"),
    ("AVIATION", "aviation"),
    ("BEAUTYANDCOSMETICS", "beautyandcosmetics"),
    ("HEALTH_MEDICAL", "health_medical"),
    ("HISTORY_MILITARY", "history_military"),
    ("INVESTING_FINANCEGROUPING", "investing_financegrouping"),
    ("NASCAR", "nascar"),
    ("EQUESTRIAN", "equestrian"),
    ("TENNIS", "tennis"),
    ("SPECTATORSPORTS_HOCKEY", "spectatorsports_hockey"),
    ("THEATER_PERFORMINGARTS", "theater_performingarts"),
    ("TRAVELGROUPING", "travelgrouping"),
    ("HOMEOWNREN", "homeownren"),
    ("HOWNRENFL", "hownrenfl"),
]

BATCH_SIZE = 2000


def qualified_table_name():
    return f"{_catalog()}.{SCHEMA}.{TABLE}"


def create_table(cursor):
    cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {_catalog()}.{SCHEMA}")
    columns_sql = ",\n    ".join(f"{col} STRING" for _, col in COLUMN_MAP)
    cursor.execute(
        f"CREATE TABLE IF NOT EXISTS {qualified_table_name()} (\n    {columns_sql}\n)"
    )


def load_csv(cursor, csv_path):
    dest_columns = ", ".join(col for _, col in COLUMN_MAP)
    placeholders = ", ".join(["?"] * len(COLUMN_MAP))
    insert_sql = (
        f"INSERT INTO {qualified_table_name()} ({dest_columns}) VALUES ({placeholders})"
    )

    with open(csv_path, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        source_headers = [h for h, _ in COLUMN_MAP]
        missing = set(source_headers) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV is missing expected columns: {sorted(missing)}")

        batch = []
        total = 0
        for row in reader:
            batch.append([row.get(h) or None for h in source_headers])
            if len(batch) >= BATCH_SIZE:
                cursor.executemany(insert_sql, batch)
                total += len(batch)
                print(f"Inserted {total} rows...")
                batch = []
        if batch:
            cursor.executemany(insert_sql, batch)
            total += len(batch)
        print(f"Done. Inserted {total} rows into {qualified_table_name()}.")


def main():
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <path-to-csv>")
        sys.exit(1)
    csv_path = sys.argv[1]

    with get_connection() as conn:
        with conn.cursor() as cursor:
            create_table(cursor)
        with conn.cursor() as cursor:
            load_csv(cursor, csv_path)


if __name__ == "__main__":
    main()
