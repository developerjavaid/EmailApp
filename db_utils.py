import os
import re

from databricks import sql

from config import get_secret

# Fully-qualified table/column names used to build dynamic SQL (clinic
# source_table + its column mapping) come from the clinic_mapping table,
# not from request input - but they're still interpolated directly into
# SQL strings (the connector has no identifier-binding), so guard against
# a stray value turning into a SQL-injection foothold.
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_.]+$")


def _validate_identifier(name, what):
    if not name or not _IDENTIFIER_RE.match(name):
        raise ValueError(f"Invalid {what} from clinic mapping: {name!r}")
    return name


def get_connection():
    server_hostname = os.environ["DATABRICKS_SERVER_HOSTNAME"]
    http_path = os.environ["DATABRICKS_HTTP_PATH"]
    auth_type = os.environ.get("DATABRICKS_AUTH_TYPE", "service_principal")

    if auth_type == "token":
        return sql.connect(
            server_hostname=server_hostname,
            http_path=http_path,
            access_token=get_secret("databricks-token"),
        )

    # Entra ID service principal (same app registration used for ACS).
    # It must be added to the Databricks workspace and granted
    # USE CATALOG / USE SCHEMA / SELECT / MODIFY on the target table.
    return sql.connect(
        server_hostname=server_hostname,
        http_path=http_path,
        auth_type="azure-sp-m2m",
        azure_client_id=os.environ["AAD_CLIENT_ID"],
        azure_client_secret=get_secret("aad-client-secret-value"),
        azure_tenant_id=os.environ["AAD_TENANT_ID"],
    )


def _catalog():
    return os.environ.get("DATABRICKS_CATALOG", "claraport_ws")


def unsubscribe_table_name():
    schema = os.environ.get("DATABRICKS_CAMPAIGN_SCHEMA", "viasmiles_campaigns")
    table = os.environ.get("DATABRICKS_UNSUBSCRIBE_TABLE", "unsubscribe_list")
    return f"{_catalog()}.{schema}.{table}"


def clinic_table_name():
    schema = os.environ.get("DATABRICKS_CAMPAIGN_SCHEMA", "viasmiles_campaigns")
    table = os.environ.get("DATABRICKS_CLINIC_TABLE", "clinic")
    return f"{_catalog()}.{schema}.{table}"


def test_customer_table_name():
    schema = os.environ.get("DATABRICKS_CAMPAIGN_SCHEMA", "viasmiles_campaigns")
    table = os.environ.get("DATABRICKS_TEST_TABLE", "customer_test")
    return f"{_catalog()}.{schema}.{table}"


def threshold_table_name():
    schema = os.environ.get("DATABRICKS_CAMPAIGN_SCHEMA", "viasmiles_campaigns")
    table = os.environ.get("DATABRICKS_THRESHOLD_TABLE", "clinic_threshold")
    return f"{_catalog()}.{schema}.{table}"


def fetch_customers(table):
    """Fetch one (fname, lname, email, clinic_id) row per unique
    (email, clinic_id) pair for the given fully-qualified table, excluding
    anyone present in the unsubscribe_list table.

    `table` is a fully-qualified catalog.schema.table string, normally
    produced by campaigns.qualified_table_name() for the campaign being sent.
    `lname` is optional on the source table; missing values come back as "".
    If the same email appears under more than one clinic_id, one email is
    sent per clinic_id (each with that clinic's template/FROM address). If
    the same (email, clinic_id) pair appears more than once (duplicate
    rows), only one of them is picked so that pair is sent exactly once.
    The unsubscribe_list exclusion is by email only (not clinic_id), so once
    an address unsubscribes it is skipped for every clinic.
    """
    unsub_table = unsubscribe_table_name()
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "WITH deduped AS ("
                f"  SELECT c.fname, COALESCE(c.lname, '') AS lname, c.email, c.clinic_id, "
                "    ROW_NUMBER() OVER (PARTITION BY lower(c.email), c.clinic_id ORDER BY c.fname) AS rn "
                f"  FROM {table} c "
                f"  LEFT ANTI JOIN {unsub_table} u ON lower(c.email) = lower(u.email)"
                ") "
                "SELECT fname, lname, email, clinic_id FROM deduped WHERE rn = 1"
            )
            return cursor.fetchall()


def fetch_clinics():
    """Fetch the clinic_id -> {name, template_name, from_email, source_table,
    email_column, first_name_column, last_name_column} mapping used to pick
    the per-recipient email template/FROM address and to locate + read that
    clinic's own customer source table.

    `source_table` is a fully-qualified catalog.schema.table string that can
    be repointed at a different table per clinic just by updating this row -
    the app always reads column names from here rather than hardcoding them,
    so it stays correct even if a clinic's source table uses different
    column names for first/last name. All four columns are required.
    """
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT clinic_id, name, template_name, from_email, source_table, "
                "email_column, first_name_column, last_name_column "
                f"FROM {clinic_table_name()}"
            )
            return {
                row[0]: {
                    "name": row[1],
                    "template_name": row[2],
                    "from_email": row[3],
                    "source_table": row[4],
                    "email_column": row[5],
                    "first_name_column": row[6],
                    "last_name_column": row[7],
                }
                for row in cursor.fetchall()
            }


def fetch_thresholds():
    """Fetch the clinic_id -> {daily_limit, hourly_limit, per_minute_limit}
    send-throttling mapping. A clinic with daily_limit <= 0 should not be
    sent to at all; hourly_limit caps how many of that daily budget go out
    in one run; per_minute_limit caps that clinic's own send rate within a
    run (0 means that clinic doesn't send at all this way)."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT clinic_id, daily_limit, hourly_limit, per_minute_limit "
                f"FROM {threshold_table_name()}"
            )
            return {
                clinic_id: {
                    "daily_limit": daily_limit,
                    "hourly_limit": hourly_limit,
                    "per_minute_limit": per_minute_limit or 0,
                }
                for clinic_id, daily_limit, hourly_limit, per_minute_limit in cursor.fetchall()
            }


def ensure_delivery_columns(source_table):
    """Add delivery_status (STRING) / delivery_sent_at (TIMESTAMP) to a
    clinic's source table if they don't already exist. Safe to call every
    run: the ADD COLUMNS simply fails (and is ignored) once they're there."""
    table = _validate_identifier(source_table, "source_table")
    with get_connection() as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    f"ALTER TABLE {table} ADD COLUMNS "
                    "(delivery_status STRING, delivery_sent_at TIMESTAMP)"
                )
            except Exception:
                pass  # columns already exist


def count_sent_today(source_table, clinic_id):
    """How many emails this clinic's source table already shows as sent
    (delivery_status = 'sent') with a delivery_sent_at timestamp from today,
    used to compute the remaining daily budget for this clinic."""
    table = _validate_identifier(source_table, "source_table")
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT COUNT(*) FROM {table} "
                "WHERE delivery_status = 'sent' "
                "AND delivery_sent_at >= current_date()"
            )
            return cursor.fetchone()[0]


def fetch_unsent_customers(clinic, clinic_id, limit):
    """Fetch up to `limit` (email, fname, lname) rows for one clinic from its
    own source_table/column mapping, skipping anyone already marked
    delivery_status = 'sent' (checked once, forever - not scoped to today)
    and anyone in the unsubscribe_list.

    `clinic` is one value from fetch_clinics(): its source_table and column
    mapping decide the query.
    """
    table = _validate_identifier(clinic["source_table"], "source_table")
    email_column = _validate_identifier(clinic["email_column"], "email_column")
    fname_column = _validate_identifier(clinic["first_name_column"], "first_name_column")
    lname_column = _validate_identifier(clinic["last_name_column"], "last_name_column")
    unsub_table = unsubscribe_table_name()

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT c.{email_column} AS email, c.{fname_column} AS fname, "
                f"c.{lname_column} AS lname "
                f"FROM {table} c "
                f"LEFT ANTI JOIN {unsub_table} u ON lower(c.{email_column}) = lower(u.email) "
                "WHERE (c.delivery_status IS NULL OR c.delivery_status <> 'sent') "
                f"LIMIT {int(limit)}"
            )
            return cursor.fetchall()


def mark_delivered(clinic, clinic_id, email):
    """Mark one email as delivered (delivery_status = 'sent',
    delivery_sent_at = now) on that clinic's source table, so it is never
    picked up again by fetch_unsent_customers regardless of date."""
    table = _validate_identifier(clinic["source_table"], "source_table")
    email_column = _validate_identifier(clinic["email_column"], "email_column")
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"UPDATE {table} SET delivery_status = 'sent', delivery_sent_at = current_timestamp() "
                f"WHERE lower({email_column}) = lower(?)",
                [email],
            )


def mark_unsubscribed(email, campaign=None, source="web_click"):
    """Record an unsubscribe in the dedicated unsubscribe_list table.

    Uses MERGE so clicking the link twice doesn't create duplicate rows.
    """
    unsub_table = unsubscribe_table_name()
    normalized = email.strip().lower()
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"MERGE INTO {unsub_table} AS target "
                "USING (SELECT ? AS email, ? AS campaign, ? AS source) AS src "
                "ON lower(target.email) = lower(src.email) "
                "WHEN NOT MATCHED THEN INSERT (email, campaign, source, unsubscribed_at) "
                "VALUES (src.email, src.campaign, src.source, current_timestamp())",
                [normalized, campaign, source],
            )
