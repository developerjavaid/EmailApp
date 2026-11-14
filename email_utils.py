import os
import smtplib
from email.message import EmailMessage

from config import get_secret


def send_email(to_address, subject, body=None, html_body=None, from_address=None):
    smtp_host = os.environ.get("ACS_SMTP_HOST", "smtp.azurecomm.net")
    smtp_port = int(os.environ.get("ACS_SMTP_PORT", "587"))
    smtp_username = os.environ["ACS_SMTP_USERNAME"]
    sender_address = from_address or os.environ["ACS_SENDER_ADDRESS"]

    # ACS SMTP AUTH with Microsoft Entra ID: the password is the linked
    # Entra application's client secret itself. ACS exchanges it for a
    # token on its own backend using the app info tied to the SMTP
    # username - the client never does the OAuth exchange directly.
    client_secret = get_secret("aad-client-secret-value")

    message = EmailMessage()
    message["From"] = sender_address
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(body or "This email requires an HTML-capable email client to view.")
    if html_body:
        message.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_username, client_secret)
        server.send_message(message)
