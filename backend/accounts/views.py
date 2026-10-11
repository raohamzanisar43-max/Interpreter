import secrets
from datetime import timedelta

import pyotp
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from compliance.audit import audit, client_ip
from compliance.models import SiteSettings, Terms
from notifications.services import notify

from .authentication import NoAuthentication
from .models import BackupCode, User
from .tokens import consume_email_token, hash_token, issue_email_token


def _set_refresh_cookie(response, refresh):
    response.set_cookie(settings.REFRESH_COOKIE, refresh, httponly=True, secure=settings.REFRESH_COOKIE_SECURE,
                        samesite="Lax", max_age=24 * 3600, path="/api/auth/")


def user_payload(user):
    company = user.company
    data = {"id": user.pk, "email": user.email, "role": user.role, "mfa_enabled": user.mfa_enabled,
            "idle_timeout_minutes": SiteSettings.get().idle_timeout_minutes}
    if company:
        latest = Terms.latest_version()
        data["company"] = {"id": company.pk, "name": company.name, "terms_version": latest,
                           "terms_required": bool(latest and company.terms_version_accepted != latest)}
    return data


def issue_session(user, request):
    refresh = RefreshToken.for_user(user)
    refresh["role"] = user.role
    user.last_login = timezone.now()
    user.failed_logins = 0
    user.locked_until = None
    user.save(update_fields=["last_login", "failed_logins", "locked_until"])
    audit(user, "login", user, request=request)
    resp = Response({"access": str(refresh.access_token), "user": user_payload(user)})
    _set_refresh_cookie(resp, str(refresh))
    return resp


def _mfa_token(user):
    return signing.dumps({"uid": user.pk}, salt="mfa")


def _user_from_mfa_token(token):
    try:
        uid = signing.loads(token, salt="mfa", max_age=600)["uid"]
    except signing.BadSignature:
        raise AuthenticationFailed("2FA session expired. Please log in again.", code="mfa_expired")
    return User.objects.get(pk=uid, is_active=True)


def _register_failure(user, request):
    user.failed_logins += 1
    if user.failed_logins >= settings.LOCKOUT_ATTEMPTS:
        user.locked_until = timezone.now() + timedelta(minutes=settings.LOCKOUT_MINUTES)
        user.failed_logins = 0
    user.save(update_fields=["failed_logins", "locked_until"])


def _check_lock(user):
    if user.locked_until and user.locked_until > timezone.now():
        raise PermissionDenied(f"Account locked. Try again in {settings.LOCKOUT_MINUTES} minutes.", code="locked")


def mfa_required_for(user):
    if not settings.REQUIRE_2FA:
        return user.mfa_enabled
    return user.role in ("admin", "rater") or user.mfa_enabled


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = [NoAuthentication]
    throttle_scope = "auth"

    def post(self, request):
        email = (request.data.get("email") or "").strip().lower()
        password = request.data.get("password") or ""
        user = User.objects.filter(email=email).first()
        if user:
            _check_lock(user)
        if not user or not user.is_active or not user.has_usable_password() or not user.check_password(password):
            if user:
                _register_failure(user, request)
            audit(email or "unknown", "login_failed", request=request)
            raise AuthenticationFailed("Invalid email or password.", code="invalid_credentials")
        if user.role == "interpreter":
            raise PermissionDenied("Interpreters use their secure link.", code="forbidden")
        if mfa_required_for(user):
            return Response({"mfa_required": True, "mfa_setup_required": not user.mfa_enabled,
                             "mfa_token": _mfa_token(user)})
        return issue_session(user, request)


def _new_backup_codes(user):
    BackupCode.objects.filter(user=user).delete()
    codes = [secrets.token_hex(4) for _ in range(10)]
    BackupCode.objects.bulk_create([BackupCode(user=user, code_hash=hash_token(c)) for c in codes])
    return codes


class MfaSetupView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        token = request.data.get("mfa_token")
        if token:
            user = _user_from_mfa_token(token)
        elif request.user and request.user.is_authenticated:
            user = request.user
        else:
            raise AuthenticationFailed("Not authenticated.", code="not_authenticated")
        if user.mfa_enabled:
            raise PermissionDenied("2FA is already enabled. Ask an admin to reset it.", code="mfa_enabled")
        user.totp_secret = pyotp.random_base32()
        user.save(update_fields=["totp_secret"])
        uri = pyotp.TOTP(user.totp_secret).provisioning_uri(name=user.email, issuer_name="EQAL")
        return Response({"secret": user.totp_secret, "otpauth_uri": uri, "backup_codes": _new_backup_codes(user)})


class MfaVerifyView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        token = request.data.get("mfa_token")
        code = str(request.data.get("code") or "").strip().replace(" ", "")
        via_token = bool(token)
        if via_token:
            user = _user_from_mfa_token(token)
        elif request.user and request.user.is_authenticated:
            user = request.user
        else:
            raise AuthenticationFailed("Not authenticated.", code="not_authenticated")
        _check_lock(user)
        if not user.totp_secret:
            raise ValidationError({"code": ["Set up 2FA first."]})
        ok = bool(code) and pyotp.TOTP(user.totp_secret).verify(code, valid_window=1)
        if not ok and code:
            bc = BackupCode.objects.filter(user=user, code_hash=hash_token(code.lower()), used_at=None).first()
            if bc and user.mfa_enabled:
                bc.used_at = timezone.now()
                bc.save(update_fields=["used_at"])
                ok = True
        if not ok:
            _register_failure(user, request)
            audit(user, "mfa_failed", user, request=request)
            raise AuthenticationFailed("Invalid 2FA code.", code="invalid_mfa")
        if not user.mfa_enabled:
            user.mfa_enabled = True
            user.save(update_fields=["mfa_enabled"])
            audit(user, "mfa_enabled", user, request=request)
        if via_token:
            return issue_session(user, request)
        return Response({"mfa_enabled": True})


class RefreshView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = [NoAuthentication]

    def post(self, request):
        raw = request.COOKIES.get(settings.REFRESH_COOKIE)
        if not raw:
            raise AuthenticationFailed("No session.", code="no_session")
        ser = TokenRefreshSerializer(data={"refresh": raw})
        try:
            ser.is_valid(raise_exception=True)
        except TokenError:
            raise AuthenticationFailed("Session expired.", code="session_expired")
        except Exception:
            raise AuthenticationFailed("Session expired.", code="session_expired")
        data = ser.validated_data
        from rest_framework_simplejwt.tokens import AccessToken
        user = User.objects.filter(pk=AccessToken(data["access"])["user_id"], is_active=True).first()
        if not user:
            raise AuthenticationFailed("Session expired.", code="session_expired")
        resp = Response({"access": data["access"], "user": user_payload(user)})
        if data.get("refresh"):
            _set_refresh_cookie(resp, data["refresh"])
        return resp


class LogoutView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = [NoAuthentication]

    def post(self, request):
        raw = request.COOKIES.get(settings.REFRESH_COOKIE)
        if raw:
            try:
                RefreshToken(raw).blacklist()
            except TokenError:
                pass
        resp = Response({"ok": True})
        resp.delete_cookie(settings.REFRESH_COOKIE, path="/api/auth/")
        return resp


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not hasattr(request.user, "email"):
            raise PermissionDenied("Not a user session.", code="forbidden")
        return Response(user_payload(request.user))


def _validate_password(password, user=None):
    try:
        validate_password(password, user)
    except DjangoValidationError as e:
        raise ValidationError({"password": list(e.messages)})


class InviteInfoView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = [NoAuthentication]

    def get(self, request, token):
        for purpose in ("invite", "reset"):
            t = consume_email_token(token, purpose)
            if t:
                return Response({"email": t.user.email, "role": t.user.role, "purpose": purpose,
                                 "terms_version": Terms.latest_version()})
        raise ValidationError({"token": ["This link is invalid or has expired."]})


class InviteAcceptView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = [NoAuthentication]
    throttle_scope = "auth"

    def post(self, request):
        t = consume_email_token(request.data.get("token") or "", "invite")
        if not t:
            raise ValidationError({"token": ["This invitation is invalid or has expired."]})
        if not request.data.get("accept_terms"):
            raise ValidationError({"accept_terms": ["You must accept the terms."]})
        user = t.user
        _validate_password(request.data.get("password") or "", user)
        user.set_password(request.data["password"])
        user.save(update_fields=["password"])
        t.used_at = timezone.now()
        t.save(update_fields=["used_at"])
        company = user.company
        latest = Terms.latest_version()
        if company and latest:
            company.terms_version_accepted = latest
            company.terms_accepted_at = timezone.now()
            company.terms_accepted_ip = client_ip(request)
            company.save()
            audit(user, "terms_accepted", company, {"version": latest}, request=request)
        audit(user, "invite_accepted", user, request=request)
        return Response({"email": user.email, "role": user.role})


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = [NoAuthentication]
    throttle_scope = "auth"

    def post(self, request):
        email = (request.data.get("email") or "").strip().lower()
        user = User.objects.filter(email=email, is_active=True).exclude(role="interpreter").first()
        if user:
            raw = issue_email_token(user, "reset", days=1)
            notify("password_reset", user.email, {"link": f"{settings.FRONTEND_URL}/reset/{raw}"})
        return Response({"ok": True})


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = [NoAuthentication]
    throttle_scope = "auth"

    def post(self, request):
        t = consume_email_token(request.data.get("token") or "", "reset")
        if not t:
            raise ValidationError({"token": ["This reset link is invalid or has expired."]})
        _validate_password(request.data.get("password") or "", t.user)
        t.user.set_password(request.data["password"])
        t.user.failed_logins = 0
        t.user.locked_until = None
        t.user.save()
        t.used_at = timezone.now()
        t.save(update_fields=["used_at"])
        audit(t.user, "password_reset", t.user, request=request)
        return Response({"ok": True})


class MagicLinkView(APIView):
    """Interpreter enters their email; if they have open assignments we email the secure links."""
    permission_classes = [AllowAny]
    authentication_classes = [NoAuthentication]
    throttle_scope = "auth"

    def post(self, request):
        from notifications.services import send_assignment_mail
        from submissions.models import Assignment
        email = (request.data.get("email") or "").strip().lower()
        qs = Assignment.objects.select_related("round", "interpreter__company").filter(
            interpreter__email__iexact=email, interpreter__is_active=True, interpreter__erased_at=None,
            round__status__in=["open", "closed"]).exclude(status="submitted")
        for a in qs:
            if not a.deadline_passed():
                send_assignment_mail("magic_link", a)
        return Response({"ok": True, "message": "If we found an open round for this email, a link has been sent."})


class TokenInfoView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = [NoAuthentication]
    throttle_scope = "auth"

    def get(self, request, token):
        from submissions.models import Assignment
        a = (Assignment.objects.select_related("round", "interpreter")
             .filter(token_hash=hash_token(token)).first())
        if not a or not a.interpreter.is_active or a.interpreter.erased_at or a.round.status == "draft":
            raise AuthenticationFailed("This link is invalid or has expired.", code="invalid_token")
        return Response({"valid": True, "round_name": a.round.name, "language": a.round.language,
                         "deadline": a.effective_deadline(), "deadline_passed": a.deadline_passed(),
                         "status": a.status, "interpreter_name": a.interpreter.full_name})
