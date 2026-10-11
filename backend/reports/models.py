from django.db import models


class CompanyReport(models.Model):
    STATUSES = [("draft", "Draft"), ("approved", "Approved"), ("released", "Released")]
    round = models.ForeignKey("rounds.Round", on_delete=models.CASCADE, related_name="reports")
    company = models.ForeignKey("organisations.Company", on_delete=models.CASCADE, related_name="reports")
    status = models.CharField(max_length=10, choices=STATUSES, default="draft")
    data = models.JSONField(default=dict)       # frozen snapshot once released
    summary = models.TextField(blank=True)
    pdf_path = models.CharField(max_length=255, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("round", "company")]
