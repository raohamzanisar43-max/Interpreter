from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAdmin, IsCompanyMember
from compliance.audit import audit
from config.storage import delete_file, process_audio, sign_media
from notifications.services import send_assignment_mail
from organisations.models import Company

from .models import KeyPoint, Round, RoundParticipation, SourceRecording

EDITABLE_FIELDS = ["name", "language", "deadline", "retention_days", "min_raters_per_item", "pairwise_per_item",
                   "instructions", "allow_replay", "show_pairwise_in_report"]


def keypoint_dict(k, admin=True):
    d = {"id": k.id, "order": k.order, "text": k.text, "category": k.category, "weight": k.weight}
    if admin:
        d["admin_notes"] = k.admin_notes
    return d


def recording_dict(r):
    return {"id": r.id, "title": r.title, "order": r.order, "duration_sec": r.duration_sec,
            "has_audio": bool(r.audio_path), "audio_url": sign_media(r.audio_path) if r.audio_path else None,
            "transcript": r.transcript, "key_points": [keypoint_dict(k) for k in r.key_points.all()]}


def round_dict(r, detail=False):
    assignments = r.assignments.all()
    d = {"id": r.id, "name": r.name, "language": r.language, "deadline": r.deadline, "status": r.status,
         "min_raters_per_item": r.min_raters_per_item, "pairwise_per_item": r.pairwise_per_item,
         "retention_days": r.retention_days, "instructions": r.instructions, "allow_replay": r.allow_replay,
         "show_pairwise_in_report": r.show_pairwise_in_report, "created_at": r.created_at,
         "released_at": r.released_at, "audio_deleted_at": r.audio_deleted_at,
         "recordings_count": r.recordings.count(), "companies_count": r.participations.count(),
         "submitted": assignments.filter(status="submitted").count(), "assignments_total": assignments.count()}
    from rating.models import RatingTask
    tasks = RatingTask.objects.filter(anonymous_item__round=r)
    d["rating_done"], d["rating_total"] = tasks.filter(status="done").count(), tasks.count()
    d["reports_pending"] = r.reports.exclude(status="released").count()
    if detail:
        d["companies"] = [{"id": p.company_id, "name": p.company.name, "deadline_override": p.deadline_override}
                          for p in r.participations.select_related("company")]
        d["recordings"] = [recording_dict(rec) for rec in r.recordings.prefetch_related("key_points")]
    return d


class AdminRoundViewSet(viewsets.ViewSet):
    permission_classes = [IsAdmin]

    def list(self, request):
        qs = Round.objects.all()
        if request.query_params.get("status"):
            qs = qs.filter(status=request.query_params["status"])
        return Response([round_dict(r) for r in qs])

    def retrieve(self, request, pk=None):
        r = get_object_or_404(Round, pk=pk)
        audit(request.user, "answer_key_view", r, request=request)
        return Response(round_dict(r, detail=True))

    @transaction.atomic
    def create(self, request):
        data = request.data
        errors = {}
        for f in ("name", "language", "deadline"):
            if not data.get(f):
                errors[f] = ["This field is required."]
        if errors:
            raise ValidationError(errors)
        from django.utils.dateparse import parse_datetime
        deadline = parse_datetime(str(data["deadline"]))
        if not deadline:
            raise ValidationError({"deadline": ["Invalid date."]})
        from compliance.models import SiteSettings
        r = Round.objects.create(
            name=data["name"], language=data["language"], deadline=deadline, created_by=request.user,
            retention_days=int(data.get("retention_days") or SiteSettings.get().default_retention_days),
            min_raters_per_item=int(data.get("min_raters_per_item") or 2),
            pairwise_per_item=int(data.get("pairwise_per_item") or 2),
            **({"instructions": data["instructions"]} if data.get("instructions") else {}))
        for cid in data.get("company_ids") or []:
            RoundParticipation.objects.get_or_create(round=r, company=get_object_or_404(Company, pk=cid))
        audit(request.user, "round_created", r, request=request)
        return Response(round_dict(r, detail=True), status=201)

    def partial_update(self, request, pk=None):
        r = get_object_or_404(Round, pk=pk)
        if r.status in ("released", "archived") and set(request.data) - {"retention_days"}:
            raise ValidationError({"detail": "Released rounds cannot be edited."})
        if "language" in request.data and r.status != "draft":
            raise ValidationError({"language": ["Language cannot change after the round has opened."]})
        for f in EDITABLE_FIELDS:
            if f in request.data:
                v = request.data[f]
                if f == "deadline":
                    from django.utils.dateparse import parse_datetime
                    v = parse_datetime(str(v))
                    if not v:
                        raise ValidationError({"deadline": ["Invalid date."]})
                setattr(r, f, v)
        r.save()
        if "company_ids" in request.data and r.status == "draft":
            ids = set(int(i) for i in request.data["company_ids"])
            r.participations.exclude(company_id__in=ids).delete()
            for cid in ids:
                RoundParticipation.objects.get_or_create(round=r, company=get_object_or_404(Company, pk=cid))
        audit(request.user, "round_updated", r, {"fields": list(request.data)}, request=request)
        return Response(round_dict(r, detail=True))

    def destroy(self, request, pk=None):
        r = get_object_or_404(Round, pk=pk)
        if r.status != "draft":
            raise ValidationError({"detail": "Only draft rounds can be deleted."})
        r.delete()
        return Response(status=204)

    # ---- lifecycle
    @action(detail=True, methods=["post"])
    def open(self, request, pk=None):
        from submissions.services import create_assignments_for_round
        r = get_object_or_404(Round, pk=pk)
        if not r.can_transition("open"):
            raise ValidationError({"detail": f"Cannot open a round that is {r.status}."})
        if r.status == "draft":
            recs = list(r.recordings.prefetch_related("key_points"))
            if not recs:
                raise ValidationError({"detail": "Add at least one source recording first."})
            if any(not rec.audio_path for rec in recs):
                raise ValidationError({"detail": "Every recording needs an audio file."})
            missing = [rec.title for rec in recs if not rec.key_points.exists()]
            if missing:
                raise ValidationError({"detail": "Every recording needs at least one key point: " + ", ".join(missing)})
            if not r.participations.exists():
                raise ValidationError({"detail": "Select at least one company."})
        else:  # closed -> open (deadline extension)
            from django.utils.dateparse import parse_datetime
            new_deadline = parse_datetime(str(request.data.get("deadline") or ""))
            if not new_deadline or new_deadline <= timezone.now():
                raise ValidationError({"deadline": ["Provide a new deadline in the future."]})
            r.deadline = new_deadline
        r.status = "open"
        r.save()
        created = create_assignments_for_round(r)
        for a in created:
            send_assignment_mail("interpreter_invite", a)
        audit(request.user, "round_opened", r, {"assignments_created": len(created)}, request=request)
        return Response(round_dict(r))

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        r = get_object_or_404(Round, pk=pk)
        if not r.can_transition("closed"):
            raise ValidationError({"detail": f"Cannot close a round that is {r.status}."})
        r.status = "closed"
        r.save()
        audit(request.user, "round_closed", r, request=request)
        return Response(round_dict(r))

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        r = get_object_or_404(Round, pk=pk)
        if not r.can_transition("archived"):
            raise ValidationError({"detail": "Only released rounds can be archived."})
        r.status = "archived"
        r.save()
        audit(request.user, "round_archived", r, request=request)
        return Response(round_dict(r))

    @action(detail=True, methods=["post"])
    def extend(self, request, pk=None):
        """Deadline extension for the whole round, one company, or one interpreter."""
        from django.utils.dateparse import parse_datetime
        from submissions.models import Assignment
        r = get_object_or_404(Round, pk=pk)
        new = parse_datetime(str(request.data.get("deadline") or ""))
        if not new or new <= timezone.now():
            raise ValidationError({"deadline": ["Provide a deadline in the future."]})
        if r.status in ("rating", "review", "released", "archived"):
            raise ValidationError({"detail": "Submissions are locked once rating has started."})
        if request.data.get("assignment_id"):
            a = get_object_or_404(Assignment, pk=request.data["assignment_id"], round=r)
            a.deadline_override = new
            a.save(update_fields=["deadline_override"])
            targets = [a]
        elif request.data.get("company_id"):
            part = get_object_or_404(RoundParticipation, round=r, company_id=request.data["company_id"])
            part.deadline_override = new
            part.save(update_fields=["deadline_override"])
            targets = list(r.assignments.filter(interpreter__company_id=part.company_id))
        else:
            r.deadline = new
            r.save(update_fields=["deadline"])
            targets = list(r.assignments.all())
        if r.status == "closed":
            r.status = "open"
            r.save(update_fields=["status"])
        for a in targets:
            if a.status != "submitted":
                send_assignment_mail("deadline_extended", a)
        audit(request.user, "deadline_extended", r, {"deadline": str(new), "scope": [k for k in ("assignment_id", "company_id") if request.data.get(k)] or ["round"]}, request=request)
        return Response(round_dict(r))

    # ---- recordings upload / ordering
    @action(detail=True, methods=["post"], url_path="recordings")
    def recordings(self, request, pk=None):
        r = get_object_or_404(Round, pk=pk)
        if r.status != "draft":
            raise ValidationError({"detail": "Recordings can only be added while the round is a draft."})
        f = request.FILES.get("file")
        title = (request.data.get("title") or (f.name.rsplit(".", 1)[0] if f else "")).strip()
        if not f:
            raise ValidationError({"file": ["Audio file is required."]})
        path, mime, dur = process_audio(f, "source")
        rec = SourceRecording.objects.create(
            round=r, title=title or f"Recording {r.recordings.count() + 1}", order=r.recordings.count(),
            audio_path=path, mime_type=mime, duration_sec=dur, transcript=request.data.get("transcript", ""))
        audit(request.user, "recording_uploaded", rec, request=request)
        return Response(recording_dict(rec), status=201)

    @action(detail=True, methods=["post"], url_path="recordings/reorder")
    def reorder_recordings(self, request, pk=None):
        r = get_object_or_404(Round, pk=pk)
        for i, rid in enumerate(request.data.get("ids") or []):
            r.recordings.filter(pk=rid).update(order=i)
        return Response({"ok": True})


class AdminRecordingViewSet(viewsets.ViewSet):
    permission_classes = [IsAdmin]

    def partial_update(self, request, pk=None):
        rec = get_object_or_404(SourceRecording, pk=pk)
        for f in ("title", "transcript", "order"):
            if f in request.data:
                setattr(rec, f, request.data[f])
        rec.save()
        audit(request.user, "answer_key_edit", rec, {"fields": list(request.data)}, request=request)
        return Response(recording_dict(rec))

    def destroy(self, request, pk=None):
        rec = get_object_or_404(SourceRecording, pk=pk)
        if rec.round.status != "draft":
            raise ValidationError({"detail": "Recordings can only be removed while the round is a draft."})
        delete_file(rec.audio_path)
        rec.delete()
        return Response(status=204)

    @action(detail=True, methods=["get", "post"], url_path="keypoints")
    def keypoints(self, request, pk=None):
        rec = get_object_or_404(SourceRecording, pk=pk)
        if request.method == "GET":
            return Response([keypoint_dict(k) for k in rec.key_points.all()])
        _guard_key_edit(rec.round)
        k = KeyPoint(source_recording=rec, order=rec.key_points.count())
        _fill_keypoint(k, request.data)
        k.save()
        audit(request.user, "answer_key_edit", k, {"action": "create"}, request=request)
        return Response(keypoint_dict(k), status=201)

    @action(detail=True, methods=["post"], url_path="keypoints/reorder")
    def reorder(self, request, pk=None):
        rec = get_object_or_404(SourceRecording, pk=pk)
        _guard_key_edit(rec.round)
        for i, kid in enumerate(request.data.get("ids") or []):
            rec.key_points.filter(pk=kid).update(order=i)
        return Response({"ok": True})


def _guard_key_edit(r):
    if r.status in ("rating", "review", "released", "archived"):
        raise ValidationError({"detail": "The answer key is locked once rating has started."})


def _fill_keypoint(k, data):
    if "text" in data:
        if not str(data["text"]).strip():
            raise ValidationError({"text": ["Text is required."]})
        k.text = data["text"]
    elif not k.pk:
        raise ValidationError({"text": ["Text is required."]})
    if "category" in data:
        if data["category"] not in KeyPoint.CATEGORIES:
            raise ValidationError({"category": ["Invalid category."]})
        k.category = data["category"]
    if "weight" in data:
        try:
            k.weight = float(data["weight"])
        except (TypeError, ValueError):
            raise ValidationError({"weight": ["Must be a number."]})
        if k.weight <= 0:
            raise ValidationError({"weight": ["Must be greater than 0."]})
    if "admin_notes" in data:
        k.admin_notes = data["admin_notes"]
    if "order" in data:
        k.order = int(data["order"])


class AdminKeyPointViewSet(viewsets.ViewSet):
    permission_classes = [IsAdmin]

    def partial_update(self, request, pk=None):
        k = get_object_or_404(KeyPoint, pk=pk)
        _guard_key_edit(k.source_recording.round)
        _fill_keypoint(k, request.data)
        k.save()
        audit(request.user, "answer_key_edit", k, {"action": "update"}, request=request)
        return Response(keypoint_dict(k))

    def destroy(self, request, pk=None):
        k = get_object_or_404(KeyPoint, pk=pk)
        _guard_key_edit(k.source_recording.round)
        audit(request.user, "answer_key_edit", k, {"action": "delete"}, request=request)
        k.delete()
        return Response(status=204)


# ---------------------------------------------------------------- company portal (no answer key, no scores)
def _company_round_dict(r, company):
    part = r.participations.get(company=company)
    interps = r.assignments.filter(interpreter__company=company)
    return {"id": r.id, "name": r.name, "language": r.language, "status": r.status,
            "deadline": part.deadline_override or r.deadline, "instructions": r.instructions,
            "interpreters_total": interps.count(), "interpreters_submitted": interps.filter(status="submitted").count()}


class CompanyRoundViewSet(viewsets.ViewSet):
    permission_classes = [IsCompanyMember]

    def list(self, request):
        company = request.user.company
        rounds = Round.objects.filter(participations__company=company).exclude(status="draft")
        return Response([_company_round_dict(r, company) for r in rounds])

    @action(detail=True, methods=["get"])
    def progress(self, request, pk=None):
        company = request.user.company
        r = get_object_or_404(Round.objects.exclude(status="draft"), pk=pk, participations__company=company)
        d = _company_round_dict(r, company)
        d["interpreters"] = [{"name": a.interpreter.full_name, "submitted": a.status == "submitted",
                              "submitted_at": a.submitted_at}
                             for a in r.assignments.filter(interpreter__company=company).select_related("interpreter")]
        return Response(d)
