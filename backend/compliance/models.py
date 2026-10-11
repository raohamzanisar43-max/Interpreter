from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    actor = models.CharField(max_length=255, blank=True)   # email / "system" / "interpreter-link:<id>"
    action = models.CharField(max_length=60, db_index=True)
    object_type = models.CharField(max_length=60, blank=True)
    object_id = models.CharField(max_length=60, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-timestamp", "-id"]


class _Versioned(models.Model):
    version = models.PositiveIntegerField(unique=True)
    body = models.TextField()
    published_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ["-version"]

    @classmethod
    def latest(cls):
        return cls.objects.order_by("-version").first()

    @classmethod
    def latest_version(cls):
        obj = cls.latest()
        return obj.version if obj else None


class Terms(_Versioned):
    pass


class PrivacyNotice(_Versioned):
    pass


class SiteSettings(models.Model):
    """Single-row configuration editable from the admin Settings screen."""
    default_retention_days = models.PositiveIntegerField(default=90)
    reminder_days = models.CharField(max_length=40, default="7,3,1")
    idle_timeout_minutes = models.PositiveIntegerField(default=30)
    require_calibration = models.BooleanField(default=True)
    calibration_threshold = models.FloatField(default=80)
    disagreement_threshold = models.FloatField(default=25)   # score spread (points) that flags an item
    aggregation = models.CharField(max_length=6, default="mean", choices=[("mean", "mean"), ("median", "median")])
    min_companies_for_ranking = models.PositiveIntegerField(default=3)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
