from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAdmin, IsInterpreter
from compliance.audit import audit
from config.storage import delete_file, process_audio, sign_media
from notifications.services import fmt_dt, notify, send_assignment_mail
from rounds.models import Round, SourceRecording

from .models import Assignment, Interpretation
from .services import assignment_progress


def _current_takes(a):
    return {i.source_recording_id: i for i in a.interpretations.filter(deleted_at=None).exclude(audio_path="")}


def _assignment(request):
    return Assignment.objects.select_related("round", "interpreter__company").get(pk=request.user.assignment.pk)


def _guard_writable(a):
    if a.status == "submitted":
        raise PermissionDenied("You have already submitted. Changes are not possible.", code="already_submitted")
    if a.round.status != "open" or a.deadline_passed():
        raise PermissionDenied("The deadline for this round has passed.", code="deadline_passed")


class InterpreterAssignmentView(APIView):
    permission_classes = [IsInterpreter]

    def get(self, request):
        a = _assignment(request)
        takes = _current_takes(a)
        recs = []
        for r in a.round.recordings.all():
            t = takes.get(r.id)
            recs.append({"id": r.id, "title": r.title, "order": r.order, "duration_sec": r.duration_sec,
                         "source_audio_url": sign_media(r.audio_path) if r.audio_path else None,
                         "recorded": bool(t), "take_url": sign_media(t.audio_path) if t else None,
                         "take_duration": t.duration_sec if t else None})
        return Response({
            "round_name": a.round.name, "language": a.round.language, "instructions": a.round.instructions,
            "allow_replay": a.round.allow_replay, "deadline": a.effective_deadline(),
            "deadline_passed": a.deadline_passed() or a.round.status != "open", "status": a.status,
            "submitted_at": a.submitted_at, "interpreter_name": a.interpreter.full_name, "recordings": recs})


class InterpreterTakeView(APIView):
    permission_classes = [IsInterpreter]

    def _recording(self, a, rec_id):
        return get_object_or_404(SourceRecording, pk=rec_id, round=a.round)   # round-scoped: no IDOR

    @transaction.atomic
    def post(self, request, recording_id):
        a = _assignment(request)
        rec = self._recording(a, recording_id)
        _guard_writable(a)
        f = request.FILES.get("file")
        if not f:
            raise ValidationError({"file": ["No audio file received."]})
        path, mime, dur = process_audio(f, "takes")
        if not dur and request.data.get("duration_sec"):
            try:
                dur = float(request.data["duration_sec"])
            except ValueError:
                dur = None
        for old in a.interpretations.filter(source_recording=rec, deleted_at=None):
            delete_file(old.audio_path)
            old.is_final, old.deleted_at, old.audio_path = False, timezone.now(), ""
            old.save()
        take = Interpretation.objects.create(assignment=a, source_recording=rec, audio_path=path, mime_type=mime,
                                             duration_sec=dur)
        if a.status == "not_started":
            a.status = "in_progress"
            a.save(update_fields=["status"])
        return Response({"recording_id": rec.id, "recorded": True, "take_url": sign_media(take.audio_path),
                         "take_duration": take.duration_sec}, status=201)

    @transaction.atomic
    def delete(self, request, recording_id):
        a = _assignment(request)
        rec = self._recording(a, recording_id)
        _guard_writable(a)
        for old in a.interpretations.filter(source_recording=rec, deleted_at=None):
            delete_file(old.audio_path)
            old.is_final, old.deleted_at, old.audio_path = False, timezone.now(), ""
            old.save()
        if not _current_takes(a):
            a.status = "not_started"
            a.save(update_fields=["status"])
        return Response(status=204)


class InterpreterSubmitView(APIView):
    permission_classes = [IsInterpreter]

    @transaction.atomic
    def post(self, request):
        a = _assignment(request)
        _guard_writable(a)
        takes = _current_takes(a)
        missing = [r.title for r in a.round.recordings.all() if r.id not in takes]
        if missing:
            raise ValidationError({"detail": "Record every item before submitting: " + ", ".join(missing)})
        a.status = "submitted"
        a.submitted_at = timezone.now()
        a.save(update_fields=["status", "submitted_at"])
        audit(f"interpreter-link:{a.pk}", "submission", a, request=request)
        notify("submitted", a.interpreter.email, {"name": a.interpreter.full_name, "round": a.round.name,
                                                  "submitted_at": fmt_dt(a.submitted_at)})
        return Response({"status": "submitted", "submitted_at": a.submitted_at})


# ---------------------------------------------------------------- admin tracker
class AdminSubmissionStatusView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request, round_id):
        r = get_object_or_404(Round, pk=round_id)
        recs = [{"id": x.id, "title": x.title} for x in r.recordings.all()]
        companies = []
        for part in r.participations.select_related("company"):
            rows = []
            for a in r.assignments.filter(interpreter__company=part.company).select_related("interpreter"):
                takes = _current_takes(a)
                rows.append({"assignment_id": a.id, "interpreter": a.interpreter.full_name,
                             "email": a.interpreter.email, "status": a.status, "submitted_at": a.submitted_at,
                             "deadline": a.effective_deadline(),
                             "per_recording": {str(x["id"]): x["id"] in takes for x in recs}})
            companies.append({"company_id": part.company_id, "company": part.company.name,
                              "deadline_override": part.deadline_override, "interpreters": rows,
                              "submitted": sum(1 for x in rows if x["status"] == "submitted"), "total": len(rows)})
        return Response({"round": {"id": r.id, "name": r.name, "status": r.status, "deadline": r.deadline},
                         "recordings": recs, "companies": companies})


class AdminRemindersView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, round_id):
        r = get_object_or_404(Round, pk=round_id)
        if r.status != "open":
            raise ValidationError({"detail": "Reminders can only be sent while the round is open."})
        qs = r.assignments.select_related("interpreter__company").exclude(status="submitted")
        ids = request.data.get("assignment_ids")
        if ids:
            qs = qs.filter(pk__in=ids)
        elif not request.data.get("all"):
            raise ValidationError({"detail": "Select interpreters or choose 'all'."})
        n = 0
        for a in qs:
            if a.interpreter.is_active and not a.interpreter.erased_at:
                send_assignment_mail("reminder", a)
                n += 1
        audit(request.user, "reminders_sent", r, {"count": n}, request=request)
        return Response({"sent": n})
