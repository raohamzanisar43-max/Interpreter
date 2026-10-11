from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission


class RolePermission(BasePermission):
    role = None

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and getattr(u, "role", None) == self.role
                    and getattr(u, "is_active", True))


class IsAdmin(RolePermission):
    role = "admin"


class IsRater(RolePermission):
    role = "rater"


class IsInterpreter(RolePermission):
    role = "interpreter"


class IsCompanyMember(RolePermission):
    """Company user whose company is active and has accepted the latest terms.

    Views that must work before acceptance set ``allow_without_terms = True``.
    """
    role = "company"

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        company = request.user.company
        if company is None or company.status != "active":
            return False
        if getattr(view, "allow_without_terms", False):
            return True
        from compliance.models import Terms
        latest = Terms.latest_version()
        if latest and company.terms_version_accepted != latest:
            raise PermissionDenied("You must accept the latest terms first.", code="terms_required")
        return True


class CompanyScopedQuerysetMixin:
    """Restrict every queryset to the requesting user's own company."""
    company_field = "company"

    def get_queryset(self):
        return super().get_queryset().filter(**{self.company_field: self.request.user.company})
