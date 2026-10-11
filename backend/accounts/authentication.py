from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .tokens import hash_token


class AssignmentUser:
    """Stand-in 'user' for an interpreter who entered through a secure link."""
    is_authenticated = True
    is_anonymous = False
    is_active = True
    role = "interpreter"

    def __init__(self, assignment):
        self.assignment = assignment
        self.pk = self.id = assignment.pk


class AssignmentTokenAuthentication(BaseAuthentication):
    """Interpreter secure link: header ``X-Assignment-Token`` -> exactly one Assignment."""

    def authenticate(self, request):
        raw = request.headers.get("X-Assignment-Token")
        if not raw:
            return None
        from submissions.models import Assignment
        a = (Assignment.objects.select_related("round", "interpreter")
             .filter(token_hash=hash_token(raw)).first())
        if (not a or not a.interpreter.is_active or a.interpreter.erased_at
                or a.round.status == "draft" or a.interpreter.company.status != "active"):
            raise AuthenticationFailed("This link is invalid or has expired.", code="invalid_token")
        return AssignmentUser(a), None

    def authenticate_header(self, request):
        return "Token"


class NoAuthentication(BaseAuthentication):
    """Public endpoints: never authenticates, but makes DRF answer 401 (not 403) to failures."""

    def authenticate(self, request):
        return None

    def authenticate_header(self, request):
        return "Bearer"
