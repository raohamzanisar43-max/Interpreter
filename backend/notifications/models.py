from django.db import models


class NotificationLog(models.Model):
    to_email = models.EmailField()
    template = models.CharField(max_length=40)
    subject = models.CharField(max_length=255)
    body = models.TextField()
    dedupe_key = models.CharField(max_length=120, blank=True, db_index=True)
    status = models.CharField(max_length=10, default="sent")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class EmailTemplate(models.Model):
    """Admin overrides for the built-in email texts (placeholders use {name} syntax)."""
    key = models.CharField(max_length=40, unique=True)
    subject = models.CharField(max_length=255)
    body = models.TextField()
