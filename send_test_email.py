import time

from email_utils import send_email

TEST_EMAILS = [
    "jvm@analyticsintellect.com",
    "azk@analyticsintellect.com",
    "jm@analyticsintellect.com",
    "AM@analyticsintellect.com",
    "hamza@viasmiles.com",
    "developer.javaid@gmail.com"
]

if __name__ == "__main__":
    for to_address in TEST_EMAILS:
        send_email(
            to_address=to_address,
            subject="Test email from ViaSmiles EmailApp",
            body="This is a test email sent via ViaSmiles Azure Communication Service",
        )
        print(f"Test email sent to {to_address}")
        time.sleep(2)
