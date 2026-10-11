import hashlib
import secrets
from datetime import timedelta

from django.utils import timezone

from .models import EmailToken


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def issue_email_token(user, purpose, days=7):
    raw = secrets.token_urlsafe(32)
    EmailToken.objects.filter(user=user, purpose=purpose, used_at=None).delete()
    EmailToken.objects.create(user=user, purpose=purpose, token_hash=hash_token(raw),
                              expires_at=timezone.now() + timedelta(days=days))
    return raw


def consume_email_token(raw, purpose):
    t = EmailToken.objects.select_related("user").filter(token_hash=hash_token(raw), purpose=purpose,
                                                         used_at=None, expires_at__gt=timezone.now()).first()
    return t
