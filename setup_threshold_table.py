"""One-off migration: create clinic_threshold (clinic_id -> daily_limit,
hourly_limit) and seed it with one row per clinic in the clinic table.

daily_limit is the total number of *new* emails that clinic may ever send
in a calendar day; a clinic is only sent to at all while daily_limit > 0.
hourly_limit caps how many of that daily budget go out in a single run -
with TIMER_SCHEDULE firing hourly, a clinic with daily_limit=3000 and
hourly_limit=1000 sends roughly 1000/run until that day's 3000 is used up.

Initial values per the rollout plan: Columbus (3) and Pittsburgh (4) get
daily_limit=3000, hourly_limit=1000; Georgia (1), Ohio (2) and Exton (5)
start at daily_limit=0 (no sends) until they're ready to go live.

Run manually, with the project's env vars available (see local.settings.json
/ .env), e.g.:
    source .venv/bin/activate
    python setup_threshold_table.py
"""

import json
import os


def _load_local_settings():
    """Populate os.environ from local.settings.json when running outside
    `func start` (e.g. plain `python setup_threshold_table.py`), without
    overriding any variables already set in the real environment."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local.settings.json")
    if not os.path.exists(path):
        return
    with open(path) as f:
        values = json.load(f).get("Values", {})
    for key, value in values.items():
        os.environ.setdefault(key, str(value))


_load_local_settings()

from db_utils import get_connection, threshold_table_name  # noqa: E402

# (clinic_id, daily_limit, hourly_limit, per_minute_limit). clinic_id must
# match the clinic table's clinic_id (see setup_clinic_mapping.py's CLINICS).
# per_minute_limit paces that clinic's own sends within a run (ACS allows
# 100/minute and 1000/hour account-wide - see rate_limiter.py for the actual
# account-wide enforcement); 0 means that clinic sends none, same as the
# other columns.
THRESHOLDS = [
    (1, 0, 1000, 0),      # Georgia - off until ready
    (2, 0, 1000, 0),      # Ohio - off until ready
    (3, 3000, 1000, 100), # Columbus
    (4, 3000, 1000, 100), # Pittsburgh
    (5, 0, 1000, 0),      # Exton - off until ready
]


def create_and_seed_threshold_table(cursor):
    table = threshold_table_name()
    cursor.execute(
        f"CREATE TABLE IF NOT EXISTS {table} ("
        "  clinic_id INT,"
        "  daily_limit INT,"
        "  hourly_limit INT,"
        "  per_minute_limit INT"
        ")"
    )
    try:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMNS (per_minute_limit INT)")
    except Exception:
        pass  # column already exists
    for clinic_id, daily_limit, hourly_limit, per_minute_limit in THRESHOLDS:
        cursor.execute(
            f"MERGE INTO {table} AS target "
            "USING (SELECT ? AS clinic_id, ? AS daily_limit, ? AS hourly_limit, "
            "? AS per_minute_limit) AS src "
            "ON target.clinic_id = src.clinic_id "
            "WHEN MATCHED THEN UPDATE SET daily_limit = src.daily_limit, "
            "hourly_limit = src.hourly_limit, per_minute_limit = src.per_minute_limit "
            "WHEN NOT MATCHED THEN INSERT (clinic_id, daily_limit, hourly_limit, per_minute_limit) "
            "VALUES (src.clinic_id, src.daily_limit, src.hourly_limit, src.per_minute_limit)",
            [clinic_id, daily_limit, hourly_limit, per_minute_limit],
        )
    print(f"clinic_threshold table ready: {table} ({len(THRESHOLDS)} rows)")


def main():
    with get_connection() as conn:
        with conn.cursor() as cursor:
            create_and_seed_threshold_table(cursor)


if __name__ == "__main__":
    main()
