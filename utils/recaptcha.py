import requests
from django.conf import settings

def verify_recaptcha(token: str, remote_ip: str = None) -> bool:
    """
    Verify a reCAPTCHA token with Google's API.

    Args:
        token: The reCAPTCHA token from the client.
        remote_ip: Optional remote IP of the user.

    Returns:
        True if verification succeeded and hostname matches (if configured), False otherwise.
    """
    secret_key = getattr(settings, "RECAPTCHA_SECRET_KEY", None)
    if not secret_key:
        print("RECAPTCHA_SECRET_KEY not configured in settings.")
        return False

    data = {
        'secret': secret_key,
        'response': token,
    }
    if remote_ip:
        data['remoteip'] = remote_ip

    try:
        response = requests.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data=data,
            timeout=5
        )
        result = response.json()
        print("reCAPTCHA response:", result)
    except requests.RequestException as e:
        print("Error verifying reCAPTCHA:", e)
        return False

    if not result.get('success', False):
        print("reCAPTCHA verification failed:", result)
        return False

    expected_host = getattr(settings, "RECAPTCHA_EXPECTED_HOSTNAME", None)
    if expected_host and result.get('hostname') != expected_host:
        print(f"reCAPTCHA hostname mismatch: expected '{expected_host}', got '{result.get('hostname')}'")
        return False

    print("reCAPTCHA verification succeeded.")
    return True
