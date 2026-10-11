import csv

from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.authentication import NoAuthentication
from accounts.permissions import IsAdmin, IsCompanyMember
from notifications.models import EmailTemplate, NotificationLog
from notifications.services import DEFAULTS
from organisations.models import Interpreter
from rounds.models import Round
from rounds.views import round_dict

from . import services
from .audit import audit, client_ip
from .models import AuditLog, PrivacyNotice, SiteSettings, Terms


# ---------------------------------------------------------------- dashboard + settings
class AdminDashboardView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        rounds = Round.objects.exclude(status__in=["draft", "archived"])
        return Response({"rounds": [round_dict(r) for r in rounds],
                         "drafts": Round.objects.filter(status="draft").count()})


SETTING_FIELDS = {"default_retention_days": int, "reminder_days": str, "idle_timeout_minutes": int,
                  "require_calibration": bool, "calibration_threshold": float, "disagreement_threshold": float,
                  "aggregation": str, "min_companies_for_ranking": int}


def settings_dict():
    s = SiteSettings.get()
    return {f: getattr(s, f) for f in SETTING_FIELDS}


class AdminSettingsView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        return Response(settings_dict())

    def patch(self, request):
        s = SiteSettings.get()
        for f, typ in SETTING_FIELDS.items():
            if f in request.data:
                v = request.data[f]
                try:
                    v = (str(v).lower() in ("1", "true", "yes")) if typ is bool else typ(v)
                except (TypeError, ValueError):
                    raise ValidationError({f: ["Invalid value."]})
                setattr(s, f, v)
        if s.aggregation not in ("mean", "median"):
            raise ValidationError({"aggregation": ["Must be mean or median."]})
        if s.min_companies_for_ranking < 3:
            raise ValidationError({"min_companies_for_ranking": ["Cannot be lower than 3 (anonymity)."]})
        s.save()
        audit(request.user, "settings_change", s, {"fields": [f for f in SETTING_FIELDS if f in request.data]}, request=request)
        return Response(settings_dict())


# ---------------------------------------------------------------- terms + privacy
def _versioned(model, obj):
    return {"version": obj.version, "body": obj.body, "published_at": obj.published_at} if obj else None


class PublicPrivacyView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = [NoAuthentication]

    def get(self, request):
        return Response(_versioned(PrivacyNotice, PrivacyNotice.latest()) or {"version": 0, "body": "", "published_at": None})


class PublicTermsView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = [NoAuthentication]

    def get(self, request):
        return Response(_versioned(Terms, Terms.latest()) or {"version": 0, "body": "", "published_at": None})


class AdminVersionedView(APIView):
    permission_classes = [IsAdmin]
    model = None
    action_name = ""

    def get(self, request):
        return Response([{"version": o.version, "body": o.body, "published_at": o.published_at} for o in self.model.objects.all()])

    def post(self, request):
        body = (request.data.get("body") or "").strip()
        if not body:
            raise ValidationError({"body": ["Text is required."]})
        latest = self.model.latest_version() or 0
        obj = self.model.objects.create(version=latest + 1, body=body)
        audit(request.user, self.action_name, obj, {"version": obj.version}, request=request)
        return Response(_versioned(self.model, obj), status=201)


class AdminTermsView(AdminVersionedView):
    model, action_name = Terms, "terms_published"


class AdminPrivacyView(AdminVersionedView):
    model, action_name = PrivacyNotice, "privacy_published"


class CompanyTermsView(APIView):
    permission_classes = [IsCompanyMember]
    allow_without_terms = True

    def get(self, request):
        c = request.user.company
        t = Terms.latest()
        return Response({**(_versioned(Terms, t) or {"version": 0, "body": ""}),
                         "accepted_version": c.terms_version_accepted, "accepted_at": c.terms_accepted_at})


class CompanyTermsAcceptView(APIView):
    permission_classes = [IsCompanyMember]
    allow_without_terms = True

    def post(self, request):
        latest = Terms.latest_version()
        if not latest:
            raise ValidationError({"detail": "No terms have been published."})
        if int(request.data.get("version") or 0) != latest:
            raise ValidationError({"version": ["Please accept the latest version."]})
        c = request.user.company
        c.terms_version_accepted, c.terms_accepted_at, c.terms_accepted_ip = latest, timezone.now(), client_ip(request)
        c.save()
        audit(request.user, "terms_accepted", c, {"version": latest}, request=request)
        return Response({"accepted_version": latest})


# ---------------------------------------------------------------- audit log
def _audit_qs(request):
    q = request.query_params
    qs = AuditLog.objects.all()
    if q.get("actor"):
        qs = qs.filter(actor__icontains=q["actor"])
    if q.get("action"):
        qs = qs.filter(action=q["action"])
    if q.get("object_type"):
        qs = qs.filter(object_type=q["object_type"])
    if q.get("object_id"):
        qs = qs.filter(object_id=q["object_id"])
    if q.get("date_from") and parse_date(q["date_from"]):
        qs = qs.filter(timestamp__date__gte=parse_date(q["date_from"]))
    if q.get("date_to") and parse_date(q["date_to"]):
        qs = qs.filter(timestamp__date__lte=parse_date(q["date_to"]))
    return qs


class AdminAuditView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        qs = _audit_qs(request)
        if request.query_params.get("export") == "csv":
            resp = HttpResponse(content_type="text/csv")
            resp["Content-Disposition"] = 'attachment; filename="audit-log.csv"'
            w = csv.writer(resp)
            w.writerow(["timestamp", "actor", "action", "object_type", "object_id", "ip", "metadata"])
            for a in qs[:20000]:
                w.writerow([a.timestamp.isoformat(), a.actor, a.action, a.object_type, a.object_id, a.ip, a.metadata])
            audit(request.user, "export", None, {"scope": "audit_csv"}, request=request, object_type="AuditLog")
            return resp
        limit = min(int(request.query_params.get("limit") or 100), 500)
        offset = int(request.query_params.get("offset") or 0)
        return Response({"total": qs.count(), "actions": sorted(set(AuditLog.objects.values_list("action", flat=True))),
                         "results": [{"id": a.pk, "timestamp": a.timestamp, "actor": a.actor, "action": a.action,
                                      "object_type": a.object_type, "object_id": a.object_id, "ip": a.ip,
                                      "metadata": a.metadata} for a in qs[offset:offset + limit]]})


# ---------------------------------------------------------------- notifications
class AdminNotificationLogView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        return Response([{"id": n.pk, "to": n.to_email, "template": n.template, "subject": n.subject, "body": n.body,
                          "status": n.status, "created_at": n.created_at} for n in NotificationLog.objects.all()[:200]])


class AdminEmailTemplatesView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        over = {t.key: t for t in EmailTemplate.objects.all()}
        return Response([{"key": k, "subject": over[k].subject if k in over else v[0],
                          "body": over[k].body if k in over else v[1], "customised": k in over,
                          "default_subject": v[0], "default_body": v[1]} for k, v in DEFAULTS.items()])

    def put(self, request, key):
        if key not in DEFAULTS:
            raise ValidationError({"key": ["Unknown template."]})
        subject, body = request.data.get("subject"), request.data.get("body")
        if not subject or not body:
            raise ValidationError({"detail": "Subject and body are required."})
        EmailTemplate.objects.update_or_create(key=key, defaults={"subject": subject, "body": body})
        audit(request.user, "settings_change", None, {"email_template": key}, request=request, object_type="EmailTemplate")
        return Response({"ok": True})

    def delete(self, request, key):
        EmailTemplate.objects.filter(key=key).delete()
        return Response(status=204)


# ---------------------------------------------------------------- retention / erasure / data access
class AdminInterpretersView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        qs = Interpreter.objects.select_related("company")
        q = request.query_params.get("q")
        if q:
            qs = qs.filter(Q(full_name__icontains=q) | Q(email__icontains=q) | Q(company__name__icontains=q))
        return Response([{"id": i.pk, "full_name": i.full_name, "email": i.email, "company": i.company.name,
                          "is_active": i.is_active, "erased": bool(i.erased_at)} for i in qs[:300]])


class AdminInterpreterActionView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk, action):
        interp = get_object_or_404(Interpreter, pk=pk)
        if not request.data.get("confirm"):
            raise ValidationError({"detail": "Confirmation required."})
        if action == "erase":
            services.erase_interpreter(interp, request.user, request)
            return Response({"erased": True})
        if action == "delete-audio":
            return Response({"files_deleted": services.delete_interpreter_audio(interp, request.user, request)})
        raise ValidationError({"detail": "Unknown action."})

    def get(self, request, pk, action):
        if action != "export":
            raise ValidationError({"detail": "Unknown action."})
        interp = get_object_or_404(Interpreter, pk=pk)
        audit(request.user, "data_export", interp, {"scope": "subject_access_request"}, request=request)
        resp = Response(services.export_interpreter(interp))
        return resp


class AdminRoundDeleteAudioView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, round_id):
        r = get_object_or_404(Round, pk=round_id)
        if not request.data.get("confirm"):
            raise ValidationError({"detail": "Confirmation required."})
        if r.status in ("open", "closed", "rating"):
            raise ValidationError({"detail": "Audio can't be deleted while the round is still being processed."})
        return Response({"files_deleted": services.delete_round_audio(r, request.user, "manual", request)})
