"""UK GDPR operations: retention deletion, erasure, data-subject export."""
from django.db import transaction
from django.utils import timezone

from config.storage import delete_file

from .audit import audit


def _purge_interpretation(interp):
    n = 0
    if interp.audio_path:
        delete_file(interp.audio_path)
        interp.audio_path = ""
        n += 1
    interp.audio_deleted_at = timezone.now()
    interp.save(update_fields=["audio_path", "audio_deleted_at"])
    item = getattr(interp, "anonymous_item", None)
    if item is not None and item.audio_path:
        delete_file(item.audio_path)
        item.audio_path = ""
        item.save(update_fields=["audio_path"])
        n += 1
    return n


@transaction.atomic
def delete_round_audio(round_, actor, reason="manual", request=None):
    from submissions.models import Interpretation
    files = sum(_purge_interpretation(i) for i in
                Interpretation.objects.filter(assignment__round=round_).select_related("anonymous_item"))
    round_.audio_deleted_at = timezone.now()
    round_.save(update_fields=["audio_deleted_at"])
    audit(actor, "deletion", round_, {"scope": "round_audio", "files_deleted": files, "reason": reason,
                                      "certificate": f"DEL-R{round_.pk}-{timezone.now():%Y%m%d%H%M%S}"}, request=request)
    return files


@transaction.atomic
def delete_interpreter_audio(interp, actor, request=None):
    from submissions.models import Interpretation
    files = sum(_purge_interpretation(i) for i in
                Interpretation.objects.filter(assignment__interpreter=interp).select_related("anonymous_item"))
    audit(actor, "deletion", interp, {"scope": "interpreter_audio", "files_deleted": files}, request=request)
    return files


@transaction.atomic
def erase_interpreter(interp, actor, request=None):
    """Right to erasure: audio deleted, name + email anonymised, secure links revoked. Scores remain, unattributed."""
    files = delete_interpreter_audio(interp, actor, request)
    interp.full_name = "Erased interpreter"
    interp.email = f"erased-{interp.pk}@erased.invalid"
    interp.is_active = False
    interp.user = None
    interp.erased_at = timezone.now()
    interp.save()
    interp.assignments.update(token_hash="", token_salt="x")
    audit(actor, "erasure", interp, {"files_deleted": files, "certificate": f"ERA-I{interp.pk}-{timezone.now():%Y%m%d%H%M%S}"},
          request=request)


def export_interpreter(interp):
    """Data-subject access request: everything we hold about one interpreter."""
    return {
        "interpreter": {"id": interp.pk, "name": interp.full_name, "email": interp.email, "company": interp.company.name,
                        "active": interp.is_active, "created_at": interp.created_at.isoformat()},
        "assignments": [{
            "round": a.round.name, "status": a.status, "submitted_at": a.submitted_at.isoformat() if a.submitted_at else None,
            "recordings": [{"title": i.source_recording.title, "recorded_at": i.created_at.isoformat(),
                            "duration_sec": i.duration_sec, "audio_held": bool(i.audio_path)}
                           for i in a.interpretations.filter(deleted_at=None).select_related("source_recording")]}
            for a in interp.assignments.select_related("round")]}
