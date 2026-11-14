"""Per-clinic / per-campaign configuration.

Each campaign maps to its own Databricks table (so clinics' customer lists
stay isolated) and its own HTML template + merge-tag values (clinic city,
phone, booking link). Add a new clinic by adding an entry here plus a new
template file in templates/ and a new source table in Unity Catalog.
"""

import os

CATALOG = os.environ.get("DATABRICKS_CATALOG", "claraport_ws")

CAMPAIGNS = {
    "viasmiles_acquisition_v1": {
        "schema": os.environ.get("DATABRICKS_SCHEMA", "prd_viasmiles_email"),
        "table": os.environ.get("DATABRICKS_TABLE", "customer"),
        "template": "viasmiles_acquisition_email_v1.1.html",
        "subject": "Your free implant consultation, 3D CT scan included",
        "merge_tags": {
            "clinic_city": "Columbus",
            "clinic_phone": "(614) 999-1500",
            "booking_link": "https://viasmiles.com/book-consultation/",
        },
    },
    # Test/sandbox campaign — points at the isolated test table, used when
    # TEST_MODE=true.
    "viasmiles_test": {
        "schema": os.environ.get("DATABRICKS_CAMPAIGN_SCHEMA", "viasmiles_campaigns"),
        "table": os.environ.get("DATABRICKS_TEST_TABLE", "customer_test"),
        "template": "viasmiles_acquisition_email_v1.1.html",
        "subject": "Your free implant consultation, 3D CT scan included",
        "merge_tags": {
            "clinic_city": "Columbus",
            "clinic_phone": "(614) 999-1500",
            "booking_link": "https://viasmiles.com/book-consultation/",
        },
    },
}

DEFAULT_CAMPAIGN = os.environ.get("DEFAULT_CAMPAIGN", "viasmiles_acquisition_v1")


def get_campaign(campaign_id):
    if os.environ.get("TEST_MODE", "false").lower() == "true":
        campaign_id = "viasmiles_test"
    try:
        return campaign_id, CAMPAIGNS[campaign_id]
    except KeyError:
        raise ValueError(f"Unknown campaign '{campaign_id}'. Known: {list(CAMPAIGNS)}")


def qualified_table_name(campaign_config):
    return f"{CATALOG}.{campaign_config['schema']}.{campaign_config['table']}"
