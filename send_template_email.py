import os
import time
import urllib.parse
from pathlib import Path

from email_utils import send_email
from unsubscribe_utils import generate_token

TEST_EMAILS = [
    "jvm@analyticsintellect.com",
    "azk@analyticsintellect.com",
    "jm@analyticsintellect.com",
    "AM@analyticsintellect.com",
    "hamza@viasmiles.com",
]

TEMPLATE_PATH = Path(__file__).parent / "templates" / "viasmiles_acquisition_email_v1.1.html"
SUBJECT = "Your free implant consultation, 3D CT scan included"
APP_BASE_URL = os.environ.get("APP_BASE_URL", "https://viasmiles-emailapp.azurewebsites.net")

# Merge tag defaults for this test send (no per-recipient CRM data used here).
MERGE_TAGS = {
    "first_name": "there",
    "clinic_city": "Columbus",
    "clinic_phone": "(614) 999-1500",
    "booking_link": "https://viasmiles.com/book-consultation/",
}


def unsubscribe_link(email):
    token = generate_token(email)
    return f"{APP_BASE_URL}/api/unsubscribe?email={urllib.parse.quote(email)}&token={token}"


def render_template(to_address):
    html = TEMPLATE_PATH.read_text(encoding="utf-8")
    for tag, value in MERGE_TAGS.items():
        html = html.replace("{{" + tag + "}}", value)
    html = html.replace("{{unsubscribe_link}}", unsubscribe_link(to_address))
    return html


if __name__ == "__main__":
    for to_address in TEST_EMAILS:
        send_email(
            to_address=to_address,
            subject=SUBJECT,
            html_body=render_template(to_address),
        )
        print(f"Template email sent to {to_address}")
        time.sleep(2)
