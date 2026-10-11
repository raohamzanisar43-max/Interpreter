from django.db import transaction

from organisations.models import Interpreter

from .models import Assignment


def ensure_assignments_for_interpreter(interp):
    """Create assignments for open rounds the interpreter's company takes part in. Returns new ones."""
    from rounds.models import Round
    if not interp.is_active or interp.erased_at:
        return []
    created = []
    for r in Round.objects.filter(status="open", participations__company=interp.company):
        a, new = Assignment.objects.get_or_create(round=r, interpreter=interp)
        if new:
            created.append(a)
    return created


@transaction.atomic
def create_assignments_for_round(round_):
    """Called when a round opens: one Assignment per active interpreter of every participating company."""
    created = []
    for part in round_.participations.select_related("company"):
        if part.company.status != "active":
            continue
        for interp in Interpreter.objects.filter(company=part.company, is_active=True, erased_at=None):
            a, new = Assignment.objects.get_or_create(round=round_, interpreter=interp)
            if new:
                created.append(a)
    return created


def assignment_progress(a):
    """Per-recording state for one assignment (never any score)."""
    taken = set(a.interpretations.filter(deleted_at=None).exclude(audio_path="").values_list("source_recording_id", flat=True))
    recs = list(a.round.recordings.all())
    return [{"recording_id": r.id, "title": r.title, "recorded": r.id in taken} for r in recs]
