from django.db import models

VALUES = {"full": 1.0, "partial": 0.5, "lost": 0.0}


class AnonymousItem(models.Model):
    round = models.ForeignKey("rounds.Round", on_delete=models.CASCADE, related_name="items")
    interpretation = models.OneToOneField("submissions.Interpretation", on_delete=models.CASCADE,
                                          related_name="anonymous_item")
    public_code = models.CharField(max_length=20, unique=True)
    order = models.PositiveIntegerField(default=0)
    audio_path = models.CharField(max_length=255, blank=True)  # anonymised copy, UUID name
    override_score = models.FloatField(null=True, blank=True)
    override_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["order"]


class RatingTask(models.Model):
    STATUSES = [("todo", "To do"), ("in_progress", "In progress"), ("done", "Done")]
    anonymous_item = models.ForeignKey(AnonymousItem, on_delete=models.CASCADE, related_name="tasks")
    rater = models.ForeignKey("organisations.Rater", on_delete=models.CASCADE, related_name="tasks")
    status = models.CharField(max_length=12, choices=STATUSES, default="todo")
    due_at = models.DateTimeField(null=True, blank=True)
    overall_comment = models.TextField(blank=True)
    locked = models.BooleanField(default=False)
    excluded = models.BooleanField(default=False)
    excluded_reason = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("anonymous_item", "rater")]


class ChecklistScore(models.Model):
    rating_task = models.ForeignKey(RatingTask, on_delete=models.CASCADE, related_name="scores")
    key_point = models.ForeignKey("rounds.KeyPoint", on_delete=models.CASCADE)
    value = models.CharField(max_length=8, choices=[(k, k) for k in VALUES])
    comment = models.TextField(blank=True)

    class Meta:
        unique_together = [("rating_task", "key_point")]


class PairwiseTask(models.Model):
    round = models.ForeignKey("rounds.Round", on_delete=models.CASCADE, related_name="pairs")
    rater = models.ForeignKey("organisations.Rater", on_delete=models.CASCADE, related_name="pairs")
    item_a = models.ForeignKey(AnonymousItem, on_delete=models.CASCADE, related_name="+")
    item_b = models.ForeignKey(AnonymousItem, on_delete=models.CASCADE, related_name="+")
    source_recording = models.ForeignKey("rounds.SourceRecording", on_delete=models.CASCADE, related_name="+")
    winner = models.CharField(max_length=4, blank=True, choices=[("a", "a"), ("b", "b"), ("tie", "tie")])
    comment = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)


class PracticeItem(models.Model):
    title = models.CharField(max_length=200)
    language = models.CharField(max_length=60, blank=True)
    source_audio_path = models.CharField(max_length=255, blank=True)
    interpretation_audio_path = models.CharField(max_length=255, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class PracticeKeyPoint(models.Model):
    item = models.ForeignKey(PracticeItem, on_delete=models.CASCADE, related_name="key_points")
    order = models.PositiveIntegerField(default=0)
    text = models.TextField()
    category = models.CharField(max_length=12, default="other")
    reference_value = models.CharField(max_length=8, choices=[(k, k) for k in VALUES], default="full")
    explanation = models.TextField(blank=True)

    class Meta:
        ordering = ["order", "id"]


class PracticeAttempt(models.Model):
    rater = models.ForeignKey("organisations.Rater", on_delete=models.CASCADE, related_name="practice_attempts")
    item = models.ForeignKey(PracticeItem, on_delete=models.CASCADE, related_name="attempts")
    answers = models.JSONField(default=dict)
    agreement = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
