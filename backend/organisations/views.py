from django.conf import settings
from django.db import transaction
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from accounts.permissions import CompanyScopedQuerysetMixin, IsAdmin, IsCompanyMember
from accounts.tokens import issue_email_token
from compliance.audit import audit
from notifications.services import notify, send_assignment_mail

from .models import Company, CompanyMember, Interpreter, Rater


def send_invite(user):
    raw = issue_email_token(user, "invite")
    link = f"{settings.FRONTEND_URL}/invite/{raw}"
    notify("invite", user.email, {"role": user.role, "link": link})
    return link


# ---------------------------------------------------------------- admin: companies
class CompanySerializer(serializers.ModelSerializer):
    member_email = serializers.SerializerMethodField()
    member_mfa = serializers.SerializerMethodField()
    interpreters_count = serializers.SerializerMethodField()
    terms_current = serializers.SerializerMethodField()

    class Meta:
        model = Company
        fields = ["id", "name", "contact_email", "status", "terms_version_accepted", "terms_accepted_at",
                  "member_email", "member_mfa", "interpreters_count", "terms_current", "created_at"]
        read_only_fields = ["terms_version_accepted", "terms_accepted_at", "created_at"]

    def get_member_email(self, obj):
        m = obj.members.select_related("user").first()
        return m.user.email if m else None

    def get_member_mfa(self, obj):
        m = obj.members.select_related("user").first()
        return bool(m and m.user.mfa_enabled)

    def get_interpreters_count(self, obj):
        return obj.interpreters.filter(erased_at=None).count()

    def get_terms_current(self, obj):
        from compliance.models import Terms
        latest = Terms.latest_version()
        return (not latest) or obj.terms_version_accepted == latest


class AdminCompanyViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdmin]
    serializer_class = CompanySerializer
    queryset = Company.objects.all()

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        member_email = (request.data.get("member_email") or ser.validated_data["contact_email"]).strip().lower()
        if User.objects.filter(email=member_email).exists():
            raise ValidationError({"member_email": ["A user with this email already exists."]})
        company = ser.save()
        user = User.objects.create_user(member_email, role="company")
        CompanyMember.objects.create(user=user, company=company)
        link = send_invite(user)
        audit(request.user, "company_created", company, request=request)
        data = self.get_serializer(company).data
        if settings.DEBUG:
            data["invite_url"] = link
        return Response(data, status=201)

    def perform_update(self, serializer):
        company = serializer.save()
        for m in company.members.select_related("user"):
            m.user.is_active = company.status == "active"
            m.user.save(update_fields=["is_active"])
        audit(self.request.user, "company_updated", company, request=self.request)

    def destroy(self, request, *args, **kwargs):   # soft: deactivate
        company = self.get_object()
        company.status = "inactive"
        company.save(update_fields=["status"])
        for m in company.members.select_related("user"):
            m.user.is_active = False
            m.user.save(update_fields=["is_active"])
        audit(request.user, "company_deactivated", company, request=request)
        return Response(self.get_serializer(company).data)

    @action(detail=True, methods=["post"], url_path="resend-invite")
    def resend_invite(self, request, pk=None):
        company = self.get_object()
        m = company.members.select_related("user").first()
        if not m:
            raise ValidationError({"detail": "Company has no login user."})
        link = send_invite(m.user)
        return Response({"ok": True, "invite_url": link if settings.DEBUG else None})


# ---------------------------------------------------------------- admin: raters
class RaterSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    mfa_enabled = serializers.BooleanField(source="user.mfa_enabled", read_only=True)
    workload = serializers.SerializerMethodField()
    practice_done = serializers.SerializerMethodField()

    class Meta:
        model = Rater
        fields = ["id", "user_id", "email", "languages", "is_calibrated", "active", "mfa_enabled", "workload", "practice_done"]

    def get_workload(self, obj):
        tasks = obj.tasks.all()
        return {"total": tasks.count(), "done": tasks.filter(status="done").count()}

    def get_practice_done(self, obj):
        return obj.practice_attempts.values("item").distinct().count()


class AdminRaterViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdmin]
    serializer_class = RaterSerializer
    queryset = Rater.objects.select_related("user").all()

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        email = (request.data.get("email") or "").strip().lower()
        langs = request.data.get("languages") or []
        if isinstance(langs, str):
            langs = [x.strip() for x in langs.split(",") if x.strip()]
        if not email:
            raise ValidationError({"email": ["Email is required."]})
        if User.objects.filter(email=email).exists():
            raise ValidationError({"email": ["A user with this email already exists."]})
        user = User.objects.create_user(email, role="rater")
        rater = Rater.objects.create(user=user, languages=langs)
        link = send_invite(user)
        audit(request.user, "rater_created", rater, request=request)
        data = self.get_serializer(rater).data
        if settings.DEBUG:
            data["invite_url"] = link
        return Response(data, status=201)

    def update(self, request, *args, **kwargs):
        rater = self.get_object()
        langs = request.data.get("languages", rater.languages)
        if isinstance(langs, str):
            langs = [x.strip() for x in langs.split(",") if x.strip()]
        rater.languages = langs
        for f in ("is_calibrated", "active"):
            if f in request.data:
                setattr(rater, f, bool(request.data[f]))
        rater.save()
        rater.user.is_active = rater.active
        rater.user.save(update_fields=["is_active"])
        return Response(self.get_serializer(rater).data)

    partial_update = update

    def destroy(self, request, *args, **kwargs):
        rater = self.get_object()
        rater.active = False
        rater.save(update_fields=["active"])
        rater.user.is_active = False
        rater.user.save(update_fields=["is_active"])
        return Response(self.get_serializer(rater).data)

    @action(detail=True, methods=["post"], url_path="resend-invite")
    def resend_invite(self, request, pk=None):
        link = send_invite(self.get_object().user)
        return Response({"ok": True, "invite_url": link if settings.DEBUG else None})


class ResetMfaView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, user_id):
        user = User.objects.filter(pk=user_id).exclude(role="interpreter").first()
        if not user:
            raise ValidationError({"detail": "User not found."})
        user.mfa_enabled = False
        user.totp_secret = ""
        user.save(update_fields=["mfa_enabled", "totp_secret"])
        user.backup_codes.all().delete()
        audit(request.user, "mfa_reset", user, request=request)
        return Response({"ok": True})


# ---------------------------------------------------------------- company: interpreters
class InterpreterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Interpreter
        fields = ["id", "full_name", "email", "is_active"]


class CompanyInterpreterViewSet(CompanyScopedQuerysetMixin, viewsets.ModelViewSet):
    permission_classes = [IsCompanyMember]
    serializer_class = InterpreterSerializer
    queryset = Interpreter.objects.filter(erased_at=None)

    def _check_unique(self, email, exclude=None):
        qs = Interpreter.objects.filter(company=self.request.user.company, email__iexact=email)
        if exclude:
            qs = qs.exclude(pk=exclude.pk)
        if qs.exists():
            raise ValidationError({"email": ["An interpreter with this email already exists."]})

    def perform_create(self, serializer):
        email = serializer.validated_data["email"].lower()
        self._check_unique(email)
        interp = serializer.save(company=self.request.user.company, email=email)
        from submissions.services import ensure_assignments_for_interpreter
        for a in ensure_assignments_for_interpreter(interp):
            send_assignment_mail("interpreter_invite", a)

    def perform_update(self, serializer):
        if "email" in serializer.validated_data:
            self._check_unique(serializer.validated_data["email"], serializer.instance)
        serializer.save()

    def destroy(self, request, *args, **kwargs):  # deactivate only
        obj = self.get_object()
        obj.is_active = False
        obj.save(update_fields=["is_active"])
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"])
    def resend(self, request, pk=None):
        from submissions.models import Assignment
        interp = self.get_object()
        sent = 0
        for a in Assignment.objects.filter(interpreter=interp, round__status="open").exclude(status="submitted"):
            send_assignment_mail("interpreter_invite", a)
            sent += 1
        return Response({"sent": sent})
