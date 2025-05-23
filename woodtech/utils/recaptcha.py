# utils/recaptcha.py

import requests
from django.conf import settings

def verify_recaptcha(token: str) -> bool:
    """Verify Google Invisible reCAPTCHA token with Google's API."""
    if not token:
        return False

    resp = requests.post(
        'https://www.google.com/recaptcha/api/siteverify',
        data={
            'secret': settings.RECAPTCHA_SECRET_KEY,
            'response': token,
        },
        timeout=5,
    )
    result = resp.json()
    return result.get('success', False)
