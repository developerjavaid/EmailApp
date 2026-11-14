import hashlib
import hmac

from config import get_secret


def _signing_key():
    return get_secret("unsubscribe-signing-key").encode("utf-8")


def generate_token(email):
    normalized = email.strip().lower()
    return hmac.new(_signing_key(), normalized.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_token(email, token):
    if not email or not token:
        return False
    expected = generate_token(email)
    return hmac.compare_digest(expected, token)
