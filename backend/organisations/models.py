from django.conf import settings
from django.db import models


class Company(models.Model):
    name = models.CharField(max_length=200, unique=True)
    contact_email = models.EmailField()
    status = models.CharField(max_length=10, choices=[("active", "Active"), ("inactive", "Inactive")], default="active")
    terms_version_accepted = models.PositiveIntegerField(null=True, blank=True)
    terms_accepted_at = models.DateTimeField(null=True, blank=True)
    terms_accepted_ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "companies"
        ordering = ["name"]

    def __str__(self):
        return self.name


class CompanyMember(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="membership")
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="members")


class Interpreter(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="interpreters")
    full_name = models.CharField(max_length=200)
    email = models.EmailField()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    is_active = models.BooleanField(default=True)
    erased_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("company", "email")]
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name


class Rater(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="rater")
    languages = models.JSONField(default=list)
    is_calibrated = models.BooleanField(default=False)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.user.email
