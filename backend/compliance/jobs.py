"""Scheduled jobs (run with `python manage.py run_jobs`, one-shot or --loop). Celery-ready: each is a plain function."""
from datetime import timedelta

from django.core.management import call_command
from django.utils import timezone

from .audit import audit
from .models import SiteSettings


def send_deadline_reminders():
    from notifications.services import send_assignment_mail
    from rounds.models import Round
    from submissions.models import Assignment
    thresholds = sorted(int(x) for x in SiteSettings.get().reminder_days.split(",") if x.strip().isdigit())
    sent, now = 0, timezone.now()
    for r in Round.objects.filter(status="open"):
        for a in Assignment.objects.filter(round=r).exclude(status="submitted").select_related("interpreter__company", "round"):
            if not a.interpreter.is_active or a.interpreter.erased_at:
                continue
            deadline = a.effective_deadline()
            left = (deadline - now).total_seconds() / 86400
            if left <= 0:
                continue
            due = [d for d in thresholds if left <= d]
            if due:
                key = f"reminder:{a.pk}:{min(due)}:{deadline:%Y%m%d%H%M}"
                if send_assignment_mail("reminder", a, dedupe_key=key):
                    sent += 1
    return sent


def auto_close_rounds():
    from rounds.models import Round
    from submissions.models import Assignment
    closed = 0
    now = timezone.now()
    for r in Round.objects.filter(status="open"):
        latest = max([a.effective_deadline() for a in Assignment.objects.filter(round=r)] + [r.deadline])
        if latest < now:
            r.status = "closed"
            r.save(update_fields=["status"])
            audit("system", "round_auto_closed", r)
            closed += 1
    return closed


def retention_cleanup():
    from rounds.models import Round
    from .services import delete_round_audio
    n = 0
    for r in Round.objects.filter(status__in=["released", "archived"], audio_deleted_at=None):
        if timezone.now() > r.deadline + timedelta(days=r.retention_days):
            delete_round_audio(r, "system", reason="retention_expired")
            n += 1
    return n


def cleanup_tokens():
    from accounts.models import EmailToken
    EmailToken.objects.filter(expires_at__lt=timezone.now() - timedelta(days=1)).delete()
    EmailToken.objects.filter(used_at__lt=timezone.now() - timedelta(days=1)).delete()
    try:
        call_command("flushexpiredtokens")
    except Exception:
        pass


def run_all():
    return {"closed": auto_close_rounds(), "reminders": send_deadline_reminders(), "retention": retention_cleanup()}
