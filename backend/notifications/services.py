from django.conf import settings
from django.core.mail import send_mail

from .models import EmailTemplate, NotificationLog

DEFAULTS = {
    "invite": ("Your EQAL account invitation",
               "Hello,\n\nYou have been invited to EQAL ({role}).\nSet your password here:\n{link}\n\nThis link is valid for 7 days."),
    "interpreter_invite": ("EQAL: please record your interpretations for {round}",
                           "Hello {name},\n\n{company} has been invited to the EQAL round \"{round}\" ({language}).\n"
                           "Your personal secure link (do not share it):\n{link}\n\nDeadline: {deadline}\n"),
    "reminder": ("Reminder: EQAL round \"{round}\" closes {deadline}",
                 "Hello {name},\n\nYou have not submitted your recordings for \"{round}\" yet.\n"
                 "Deadline: {deadline}\nContinue here: {link}\n"),
    "submitted": ("EQAL: submission received for {round}",
                  "Hello {name},\n\nWe received your submission for \"{round}\" at {submitted_at}. Thank you.\n"),
    "deadline_extended": ("EQAL: deadline extended for {round}",
                          "Hello {name},\n\nThe deadline for \"{round}\" is now {deadline}.\nYour link: {link}\n"),
    "report_released": ("Your EQAL report for {round} is ready",
                        "Hello,\n\nYour company's report for \"{round}\" has been released.\nLog in to view it: {link}\n"),
    "rater_tasks": ("EQAL: new rating tasks for {round}",
                    "Hello,\n\nYou have {count} new tasks for \"{round}\".\nOpen your dashboard: {link}\n"),
    "password_reset": ("Reset your EQAL password",
                       "Hello,\n\nReset your password here:\n{link}\n\nIf you did not request this, ignore this email."),
    "magic_link": ("Your EQAL secure link",
                   "Hello {name},\n\nOpen your recording page for \"{round}\":\n{link}\n"),
}


class _Safe(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def render(key, ctx):
    subject, body = DEFAULTS[key]
    override = EmailTemplate.objects.filter(key=key).first()
    if override:
        subject, body = override.subject, override.body
    return subject.format_map(_Safe(ctx)), body.format_map(_Safe(ctx))


def notify(key, to_email, ctx, dedupe_key=""):
    if dedupe_key and NotificationLog.objects.filter(dedupe_key=dedupe_key).exists():
        return None
    subject, body = render(key, ctx)
    status = "sent"
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [to_email], fail_silently=False)
    except Exception:
        status = "failed"
    return NotificationLog.objects.create(to_email=to_email, template=key, subject=subject, body=body,
                                          dedupe_key=dedupe_key, status=status)


def fmt_dt(dt):
    from django.utils import timezone
    return timezone.localtime(dt).strftime("%d %b %Y %H:%M") if dt else ""


def assignment_ctx(a):
    return {"name": a.interpreter.full_name, "company": a.interpreter.company.name, "round": a.round.name,
            "language": a.round.language, "link": a.link(), "deadline": fmt_dt(a.effective_deadline())}


def send_assignment_mail(key, a, dedupe_key=""):
    return notify(key, a.interpreter.email, assignment_ctx(a), dedupe_key)
