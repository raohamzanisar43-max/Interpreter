from django.conf import settings
from django.db import models

STATUSES = ["draft", "open", "closed", "rating", "review", "released", "archived"]
TRANSITIONS = {
    "draft": ["open"],
    "open": ["closed"],
    "closed": ["open", "rating"],     # closed -> open = deadline extension (only before rating starts)
    "rating": ["review"],
    "review": ["released", "rating"],
    "released": ["archived"],
    "archived": [],
}


class Round(models.Model):
    name = models.CharField(max_length=200)
    language = models.CharField(max_length=60)
    deadline = models.DateTimeField()
    status = models.CharField(max_length=10, choices=[(s, s) for s in STATUSES], default="draft")
    min_raters_per_item = models.PositiveIntegerField(default=2)
    pairwise_per_item = models.PositiveIntegerField(default=2)
    retention_days = models.PositiveIntegerField(default=90)
    instructions = models.TextField(blank=True, default="Listen to each recording, then interpret it aloud as you "
                                    "would in a real consultation. Find a quiet place.")
    allow_replay = models.BooleanField(default=True)
    show_pairwise_in_report = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    released_at = models.DateTimeField(null=True, blank=True)
    audio_deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def can_transition(self, to):
        return to in TRANSITIONS[self.status]


class RoundParticipation(models.Model):
    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name="participations")
    company = models.ForeignKey("organisations.Company", on_delete=models.CASCADE, related_name="participations")
    invited_at = models.DateTimeField(auto_now_add=True)
    terms_accepted_at = models.DateTimeField(null=True, blank=True)
    deadline_override = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [("round", "company")]


class SourceRecording(models.Model):
    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name="recordings")
    title = models.CharField(max_length=200)
    order = models.PositiveIntegerField(default=0)
    audio_path = models.CharField(max_length=255, blank=True)
    mime_type = models.CharField(max_length=60, blank=True)
    duration_sec = models.FloatField(null=True, blank=True)
    transcript = models.TextField(blank=True)  # admin only

    class Meta:
        ordering = ["order", "id"]


class KeyPoint(models.Model):
    CATEGORIES = ["warning", "doubt", "dosage", "instruction", "other"]
    source_recording = models.ForeignKey(SourceRecording, on_delete=models.CASCADE, related_name="key_points")
    order = models.PositiveIntegerField(default=0)
    text = models.TextField()
    category = models.CharField(max_length=12, choices=[(c, c) for c in CATEGORIES], default="other")
    weight = models.FloatField(default=1.0)
    admin_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["order", "id"]
