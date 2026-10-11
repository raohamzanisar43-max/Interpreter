import base64
import hashlib
import hmac
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from accounts.tokens import hash_token


class Assignment(models.Model):
    """One interpreter x one round. The secure-link token is reproducible only with SECRET_KEY + salt;
    the database holds the salt and a hash, never the usable token itself."""
    STATUSES = [("not_started", "Not started"), ("in_progress", "In progress"), ("submitted", "Submitted")]
    round = models.ForeignKey("rounds.Round", on_delete=models.CASCADE, related_name="assignments")
    interpreter = models.ForeignKey("organisations.Interpreter", on_delete=models.CASCADE, related_name="assignments")
    token_salt = models.CharField(max_length=64, blank=True)
    token_hash = models.CharField(max_length=64, blank=True, db_index=True)
    status = models.CharField(max_length=12, choices=STATUSES, default="not_started")
    submitted_at = models.DateTimeField(null=True, blank=True)
    deadline_override = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("round", "interpreter")]

    def save(self, *args, **kwargs):
        if not self.token_salt:
            self.rotate_token(save=False)
        super().save(*args, **kwargs)

    def rotate_token(self, save=True):
        self.token_salt = secrets.token_hex(16)
        self.token_hash = hash_token(self.token())
        if save:
            self.save(update_fields=["token_salt", "token_hash"])

    def token(self):
        mac = hmac.new(settings.SECRET_KEY.encode(), self.token_salt.encode(), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(mac).decode().rstrip("=")

    def link(self):
        return f"{settings.FRONTEND_URL}/i/{self.token()}"

    def effective_deadline(self):
        if self.deadline_override:
            return self.deadline_override
        part = self.round.participations.filter(company=self.interpreter.company).first()
        if part and part.deadline_override:
            return part.deadline_override
        return self.round.deadline

    def deadline_passed(self):
        return timezone.now() > self.effective_deadline()


class Interpretation(models.Model):
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name="interpretations")
    source_recording = models.ForeignKey("rounds.SourceRecording", on_delete=models.CASCADE,
                                         related_name="interpretations")
    audio_path = models.CharField(max_length=255, blank=True)
    mime_type = models.CharField(max_length=60, blank=True)
    duration_sec = models.FloatField(null=True, blank=True)
    is_final = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True)       # soft delete (re-record)
    audio_deleted_at = models.DateTimeField(null=True, blank=True)  # retention / erasure
