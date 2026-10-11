import json
import statistics

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAdmin, IsRater
from compliance.audit import audit
from compliance.models import SiteSettings
from config.storage import delete_file, process_audio, sign_media
from reports.scoring import item_stats, pairwise_by_item, r1, round_item_stats, task_score
from rounds.models import Round

from . import distribution
from .models import (VALUES, AnonymousItem, ChecklistScore, PairwiseTask, PracticeAttempt, PracticeItem,
                     PracticeKeyPoint, RatingTask)


# =============================================================== rater portal
def calibration_locked(rater):
    cfg = SiteSettings.get()
    return bool(cfg.require_calibration and not rater.is_calibrated and PracticeItem.objects.filter(active=True).exists())


def _task_for(request, pk):
    task = get_object_or_404(RatingTask.objects.select_related("anonymous_item__round"), pk=pk,
                             rater=request.user.rater)
    if calibration_locked(request.user.rater):
        raise PermissionDenied("Complete the practice items first.", code="calibration_required")
    return task


def task_list_row(t):
    return {"id": t.pk, "code": t.anonymous_item.public_code, "status": t.status,
            "recording_title": t.anonymous_item.interpretation.source_recording.title, "due_at": t.due_at}


class RaterDashboardView(APIView):
    permission_classes = [IsRater]

    def get(self, request):
        rater = request.user.rater
        tasks = rater.tasks.filter(anonymous_item__round__status__in=["rating", "review"])
        pairs = rater.pairs.filter(round__status__in=["rating", "review"])
        due = tasks.exclude(due_at=None).order_by("due_at").values_list("due_at", flat=True).first()
        items = PracticeItem.objects.filter(active=True)
        return Response({
            "locked": calibration_locked(rater), "is_calibrated": rater.is_calibrated,
            "practice_total": items.count(),
            "practice_done": rater.practice_attempts.filter(item__in=items).values("item").distinct().count(),
            "todo": tasks.filter(status="todo").count(), "in_progress": tasks.filter(status="in_progress").count(),
            "done": tasks.filter(status="done").count(), "pairs_total": pairs.count(),
            "pairs_done": pairs.exclude(winner="").count(), "next_due": due})


class RaterTaskListView(APIView):
    permission_classes = [IsRater]

    def get(self, request):
        rater = request.user.rater
        if calibration_locked(rater):
            return Response({"locked": True, "tasks": []})
        qs = rater.tasks.filter(anonymous_item__round__status__in=["rating", "review"]).select_related(
            "anonymous_item__interpretation__source_recording").order_by("anonymous_item__order")
        if request.query_params.get("status"):
            qs = qs.filter(status=request.query_params["status"])
        return Response({"locked": False, "tasks": [task_list_row(t) for t in qs]})


class RaterTaskDetailView(APIView):
    permission_classes = [IsRater]

    def get(self, request, pk):
        t = _task_for(request, pk)
        rec = t.anonymous_item.interpretation.source_recording
        # Anonymisation: only the public code, recording title, audio URLs (random UUID paths) and key points.
        return Response({
            "id": t.pk, "code": t.anonymous_item.public_code, "status": t.status, "locked": t.locked,
            "recording_title": rec.title,
            "source_audio_url": sign_media(rec.audio_path), "interpretation_audio_url": sign_media(t.anonymous_item.audio_path),
            "key_points": [{"id": k.id, "text": k.text, "category": k.category} for k in rec.key_points.all()],
            "scores": {str(s.key_point_id): {"value": s.value, "comment": s.comment} for s in t.scores.all()},
            "overall_comment": t.overall_comment})

    @transaction.atomic
    def patch(self, request, pk):
        t = _task_for(request, pk)
        if t.locked or t.status == "done":
            raise PermissionDenied("This task is complete and locked.", code="task_locked")
        if t.anonymous_item.round.status != "rating":
            raise PermissionDenied("Rating is closed for this round.", code="rating_closed")
        valid_kps = {k.id for k in t.anonymous_item.interpretation.source_recording.key_points.all()}
        for entry in request.data.get("scores") or []:
            kp, val = entry.get("key_point"), entry.get("value")
            if kp not in valid_kps:
                raise ValidationError({"scores": ["Unknown key point."]})
            if val not in VALUES:
                raise ValidationError({"scores": ["Value must be full, partial or lost."]})
            ChecklistScore.objects.update_or_create(rating_task=t, key_point_id=kp,
                                                    defaults={"value": val, "comment": entry.get("comment", "")})
        if "overall_comment" in request.data:
            t.overall_comment = request.data["overall_comment"]
        if t.status == "todo":
            t.status, t.started_at = "in_progress", timezone.now()
        t.save()
        return Response({"saved": True, "scored": t.scores.count(), "total": len(valid_kps)})


class RaterTaskCompleteView(APIView):
    permission_classes = [IsRater]

    @transaction.atomic
    def post(self, request, pk):
        t = _task_for(request, pk)
        if t.status == "done":
            return Response({"status": "done"})
        if t.anonymous_item.round.status != "rating":
            raise PermissionDenied("Rating is closed for this round.", code="rating_closed")
        total = t.anonymous_item.interpretation.source_recording.key_points.count()
        if t.scores.count() < total:
            raise ValidationError({"detail": "Score every key point before completing."})
        t.status, t.locked, t.completed_at = "done", True, timezone.now()
        t.save()
        r = t.anonymous_item.round
        if not RatingTask.objects.filter(anonymous_item__round=r).exclude(status="done").exists() and r.status == "rating":
            r.status = "review"
            r.save(update_fields=["status"])
            audit("system", "round_review_ready", r)
        return Response({"status": "done"})


# ---- practice
def _practice_dict(item, rater, detail=False):
    last = item.attempts.filter(rater=rater).order_by("-created_at").first()
    d = {"id": item.pk, "title": item.title, "language": item.language,
         "attempted": bool(last), "agreement": last.agreement if last else None}
    if detail:
        d.update({"source_audio_url": sign_media(item.source_audio_path) if item.source_audio_path else None,
                  "interpretation_audio_url": sign_media(item.interpretation_audio_path) if item.interpretation_audio_path else None,
                  "key_points": [{"id": k.id, "text": k.text, "category": k.category} for k in item.key_points.all()],
                  "last_answers": last.answers if last else {}})
    return d


class RaterPracticeListView(APIView):
    permission_classes = [IsRater]

    def get(self, request):
        rater = request.user.rater
        return Response([_practice_dict(i, rater) for i in PracticeItem.objects.filter(active=True)])


class RaterPracticeDetailView(APIView):
    permission_classes = [IsRater]

    def get(self, request, pk):
        return Response(_practice_dict(get_object_or_404(PracticeItem, pk=pk, active=True), request.user.rater, True))


class RaterPracticeScoreView(APIView):
    permission_classes = [IsRater]

    @transaction.atomic
    def post(self, request, pk):
        item = get_object_or_404(PracticeItem, pk=pk, active=True)
        rater = request.user.rater
        answers = request.data.get("answers") or {}
        kps = list(item.key_points.all())
        if not kps or any(str(k.id) not in answers or answers[str(k.id)] not in VALUES for k in kps):
            raise ValidationError({"detail": "Score every key point."})
        correct = sum(1 for k in kps if answers[str(k.id)] == k.reference_value)
        agreement = round(correct / len(kps) * 100, 1)
        PracticeAttempt.objects.create(rater=rater, item=item, answers=answers, agreement=agreement)
        # calibrated once every active item was attempted and the latest agreement averages >= threshold
        cfg = SiteSettings.get()
        active = list(PracticeItem.objects.filter(active=True))
        latest = []
        for i in active:
            a = i.attempts.filter(rater=rater).order_by("-created_at").first()
            if a:
                latest.append(a.agreement)
        if len(latest) == len(active) and statistics.fmean(latest) >= cfg.calibration_threshold and not rater.is_calibrated:
            rater.is_calibrated = True
            rater.save(update_fields=["is_calibrated"])
        return Response({"agreement": agreement, "is_calibrated": rater.is_calibrated,
                         "feedback": [{"key_point": k.id, "text": k.text, "yours": answers[str(k.id)],
                                       "reference": k.reference_value, "match": answers[str(k.id)] == k.reference_value,
                                       "explanation": k.explanation} for k in kps]})


# ---- pairwise
def _pair_for(request, pk):
    p = get_object_or_404(PairwiseTask.objects.select_related("source_recording", "item_a", "item_b", "round"),
                          pk=pk, rater=request.user.rater)
    if calibration_locked(request.user.rater):
        raise PermissionDenied("Complete the practice items first.", code="calibration_required")
    return p


class RaterPairListView(APIView):
    permission_classes = [IsRater]

    def get(self, request):
        rater = request.user.rater
        if calibration_locked(rater):
            return Response({"locked": True, "pairs": []})
        qs = rater.pairs.filter(round__status="rating").select_related("source_recording")
        return Response({"locked": False, "pairs": [
            {"id": p.pk, "recording_title": p.source_recording.title, "done": bool(p.winner)} for p in qs]})


class RaterPairDetailView(APIView):
    permission_classes = [IsRater]

    def get(self, request, pk):
        p = _pair_for(request, pk)
        return Response({"id": p.pk, "recording_title": p.source_recording.title, "done": bool(p.winner),
                         "winner": p.winner, "comment": p.comment,
                         "source_audio_url": sign_media(p.source_recording.audio_path),
                         "a_audio_url": sign_media(p.item_a.audio_path), "b_audio_url": sign_media(p.item_b.audio_path)})

    def post(self, request, pk):
        p = _pair_for(request, pk)
        if p.round.status != "rating":
            raise PermissionDenied("Rating is closed for this round.", code="rating_closed")
        if request.data.get("winner") not in ("a", "b", "tie"):
            raise ValidationError({"winner": ["Choose A better, B better or About equal."]})
        p.winner, p.comment, p.completed_at = request.data["winner"], request.data.get("comment", ""), timezone.now()
        p.save()
        return Response({"saved": True})


# =============================================================== admin: distribution & score review
class AdminDistributeView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, round_id):
        r = get_object_or_404(Round, pk=round_id)
        k = int(request.data.get("raters_per_item") or r.min_raters_per_item)
        pw = request.data.get("pairwise_per_item")
        pw = r.pairwise_per_item if pw in (None, "") else int(pw)
        rater_ids = [int(x) for x in request.data.get("rater_ids") or []] or None
        if request.data.get("dry_run"):
            if r.status != "closed":
                raise ValidationError({"detail": "Distribution is only possible for a closed round."})
            return Response({"dry_run": True, **distribution.preview(distribution.make_plan(r, k, pw, rater_ids))})
        if k != r.min_raters_per_item or pw != r.pairwise_per_item:
            r.min_raters_per_item, r.pairwise_per_item = k, pw
            r.save(update_fields=["min_raters_per_item", "pairwise_per_item"])
        return Response(distribution.distribute(r, request.user, k, pw, rater_ids, request))


class AdminScoresView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request, round_id):
        r = get_object_or_404(Round, pk=round_id)
        stats = round_item_stats(r)
        items = []
        for s in stats:
            it = s["item"]
            interp = it.interpretation
            items.append({
                "id": it.pk, "code": it.public_code, "company": interp.assignment.interpreter.company.name,
                "company_id": interp.assignment.interpreter.company_id,
                "interpreter": interp.assignment.interpreter.full_name,      # admin only
                "recording": interp.source_recording.title,
                "score": r1(s["score"]), "auto_score": r1(s["auto"]), "override_score": it.override_score,
                "override_reason": it.override_reason, "spread": r1(s["spread"]), "flagged": s["flagged"],
                "raters": [{"task_id": row["task"].pk, "rater": row["task"].rater.user.email,
                            "status": row["task"].status, "score": r1(row["score"]),
                            "excluded": row["task"].excluded} for row in s["rows"]]})
        tasks = RatingTask.objects.filter(anonymous_item__round=r)
        raters = {}
        for t in tasks.select_related("rater__user"):
            x = raters.setdefault(t.rater_id, {"rater_id": t.rater_id, "email": t.rater.user.email, "assigned": 0, "done": 0})
            x["assigned"] += 1
            x["done"] += t.status == "done"
        spreads = [i["spread"] for i in items if i["spread"] is not None]
        return Response({
            "round": {"id": r.pk, "name": r.name, "status": r.status},
            "progress": {"done": tasks.filter(status="done").count(), "total": tasks.count()},
            "items": items, "raters": list(raters.values()),
            "agreement": {"flagged": sum(1 for i in items if i["flagged"]),
                          "mean_spread": r1(statistics.fmean(spreads)) if spreads else None,
                          "threshold": SiteSettings.get().disagreement_threshold}})


class AdminItemDetailView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request, item_id):
        it = get_object_or_404(AnonymousItem, pk=item_id)
        s = item_stats(it)
        rec = it.interpretation.source_recording
        kps = list(rec.key_points.all())
        raters = []
        for row in s["rows"]:
            t = row["task"]
            scored = {sc.key_point_id: sc for sc in t.scores.all()}
            raters.append({"task_id": t.pk, "rater": t.rater.user.email, "status": t.status, "excluded": t.excluded,
                           "excluded_reason": t.excluded_reason, "locked": t.locked, "score": r1(row["score"]),
                           "overall_comment": t.overall_comment,
                           "checklist": [{"key_point": k.id, "text": k.text, "category": k.category,
                                          "value": scored[k.id].value if k.id in scored else None,
                                          "comment": scored[k.id].comment if k.id in scored else ""} for k in kps]})
        interp = it.interpretation
        return Response({
            "id": it.pk, "code": it.public_code, "recording": rec.title,
            "company": interp.assignment.interpreter.company.name, "interpreter": interp.assignment.interpreter.full_name,
            "score": r1(s["score"]), "auto_score": r1(s["auto"]), "spread": r1(s["spread"]), "flagged": s["flagged"],
            "override_score": it.override_score, "override_reason": it.override_reason,
            "source_audio_url": sign_media(rec.audio_path),
            "interpretation_audio_url": sign_media(it.audio_path) if it.audio_path else None, "raters": raters})


class AdminItemOverrideView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, item_id):
        it = get_object_or_404(AnonymousItem, pk=item_id)
        if it.round.status in ("released", "archived"):
            raise ValidationError({"detail": "Released rounds are frozen."})
        score = request.data.get("score")
        if score in (None, ""):
            old = it.override_score
            it.override_score, it.override_reason = None, ""
            it.save()
            audit(request.user, "score_override_cleared", it, {"old": old}, request=request)
            return Response({"override_score": None})
        reason = (request.data.get("reason") or "").strip()
        try:
            score = float(score)
        except (TypeError, ValueError):
            raise ValidationError({"score": ["Must be a number."]})
        if not 0 <= score <= 100:
            raise ValidationError({"score": ["Must be between 0 and 100."]})
        if not reason:
            raise ValidationError({"reason": ["A reason is required."]})
        old = it.override_score
        it.override_score, it.override_reason = score, reason
        it.save()
        audit(request.user, "score_override", it, {"old": old, "new": score, "reason": reason}, request=request)
        return Response({"override_score": score})


class AdminTaskActionView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, task_id, action):
        t = get_object_or_404(RatingTask.objects.select_related("anonymous_item__round"), pk=task_id)
        if t.anonymous_item.round.status in ("released", "archived"):
            raise ValidationError({"detail": "Released rounds are frozen."})
        if action == "exclude":
            excluded = bool(request.data.get("excluded", True))
            reason = (request.data.get("reason") or "").strip()
            if excluded and not reason:
                raise ValidationError({"reason": ["A reason is required."]})
            t.excluded, t.excluded_reason = excluded, reason if excluded else ""
            t.save()
            audit(request.user, "rater_excluded" if excluded else "rater_included", t, {"reason": reason}, request=request)
        elif action == "unlock":
            t.locked, t.status = False, "in_progress"
            t.save()
            r = t.anonymous_item.round
            if r.status == "review":
                r.status = "rating"
                r.save(update_fields=["status"])
            audit(request.user, "task_unlocked", t, request=request)
        elif action == "reassign":
            from organisations.models import Rater
            if t.status == "done":
                raise ValidationError({"detail": "Completed tasks cannot be reassigned. Unlock it instead."})
            new = get_object_or_404(Rater, pk=request.data.get("rater_id"), active=True)
            r = t.anonymous_item.round
            if new.pk not in [x.pk for x in distribution.eligible_raters(r)]:
                raise ValidationError({"rater_id": ["Rater is not eligible for this round (language / calibration)."]})
            if RatingTask.objects.filter(anonymous_item=t.anonymous_item, rater=new).exists():
                raise ValidationError({"rater_id": ["This rater already has this item."]})
            old = t.rater_id
            t.rater, t.status, t.started_at = new, "todo", None
            t.scores.all().delete()
            t.save()
            audit(request.user, "task_reassigned", t, {"from": old, "to": new.pk}, request=request)
        else:
            raise ValidationError({"detail": "Unknown action."})
        return Response({"ok": True})


class AdminForceReviewView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, round_id):
        r = get_object_or_404(Round, pk=round_id)
        if r.status != "rating":
            raise ValidationError({"detail": "Round is not in the rating stage."})
        open_tasks = RatingTask.objects.filter(anonymous_item__round=r).exclude(status="done").count()
        if open_tasks and not request.data.get("force"):
            raise ValidationError({"detail": f"{open_tasks} tasks are not complete yet. Use force to continue."})
        r.status = "review"
        r.save(update_fields=["status"])
        audit(request.user, "round_review_started", r, {"forced": bool(open_tasks), "open_tasks": open_tasks}, request=request)
        return Response({"status": "review"})


class AdminPairwiseResultsView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request, round_id):
        r = get_object_or_404(Round, pk=round_id)
        pw = pairwise_by_item(r)
        pairs = PairwiseTask.objects.filter(round=r).select_related(
            "rater__user", "source_recording", "item_a__interpretation__assignment__interpreter__company",
            "item_b__interpretation__assignment__interpreter__company")
        company_scores = {}
        for it in AnonymousItem.objects.filter(round=r).select_related("interpretation__assignment__interpreter__company"):
            if it.pk in pw:
                company_scores.setdefault(it.interpretation.assignment.interpreter.company.name, []).append(pw[it.pk])
        return Response({
            "pairs": [{"id": p.pk, "recording": p.source_recording.title, "rater": p.rater.user.email,
                       "a": p.item_a.public_code, "a_company": p.item_a.interpretation.assignment.interpreter.company.name,
                       "b": p.item_b.public_code, "b_company": p.item_b.interpretation.assignment.interpreter.company.name,
                       "winner": p.winner, "comment": p.comment} for p in pairs],
            "company_win_rate": [{"company": k, "win_rate": r1(statistics.fmean(v))} for k, v in company_scores.items()]})


# =============================================================== admin: practice items + analytics
def _practice_admin(item):
    return {"id": item.pk, "title": item.title, "language": item.language, "active": item.active,
            "source_audio_url": sign_media(item.source_audio_path) if item.source_audio_path else None,
            "interpretation_audio_url": sign_media(item.interpretation_audio_path) if item.interpretation_audio_path else None,
            "key_points": [{"id": k.id, "order": k.order, "text": k.text, "category": k.category,
                            "reference_value": k.reference_value, "explanation": k.explanation}
                           for k in item.key_points.all()]}


class AdminPracticeListView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        return Response([_practice_admin(i) for i in PracticeItem.objects.all()])

    def post(self, request):
        title = (request.data.get("title") or "").strip()
        if not title:
            raise ValidationError({"title": ["Title is required."]})
        item = PracticeItem(title=title, language=request.data.get("language", ""))
        for field, attr in (("source_file", "source_audio_path"), ("interpretation_file", "interpretation_audio_path")):
            f = request.FILES.get(field)
            if f:
                setattr(item, attr, process_audio(f, "practice")[0])
        item.save()
        kps = request.data.get("key_points")
        if kps:
            for i, k in enumerate(json.loads(kps) if isinstance(kps, str) else kps):
                PracticeKeyPoint.objects.create(item=item, order=i, text=k["text"], category=k.get("category", "other"),
                                                reference_value=k.get("reference_value", "full"),
                                                explanation=k.get("explanation", ""))
        return Response(_practice_admin(item), status=201)


class AdminPracticeDetailView(APIView):
    permission_classes = [IsAdmin]

    def patch(self, request, pk):
        item = get_object_or_404(PracticeItem, pk=pk)
        for f in ("title", "language"):
            if f in request.data:
                setattr(item, f, request.data[f])
        if "active" in request.data:
            item.active = str(request.data["active"]).lower() in ("1", "true", "yes")
        for field, attr in (("source_file", "source_audio_path"), ("interpretation_file", "interpretation_audio_path")):
            f = request.FILES.get(field)
            if f:
                delete_file(getattr(item, attr))
                setattr(item, attr, process_audio(f, "practice")[0])
        item.save()
        return Response(_practice_admin(item))

    def delete(self, request, pk):
        item = get_object_or_404(PracticeItem, pk=pk)
        delete_file(item.source_audio_path)
        delete_file(item.interpretation_audio_path)
        item.delete()
        return Response(status=204)


class AdminPracticeKeyPointView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        item = get_object_or_404(PracticeItem, pk=pk)
        if not (request.data.get("text") or "").strip():
            raise ValidationError({"text": ["Text is required."]})
        ref = request.data.get("reference_value", "full")
        if ref not in VALUES:
            raise ValidationError({"reference_value": ["Invalid value."]})
        PracticeKeyPoint.objects.create(item=item, order=item.key_points.count(), text=request.data["text"],
                                        category=request.data.get("category", "other"), reference_value=ref,
                                        explanation=request.data.get("explanation", ""))
        return Response(_practice_admin(item), status=201)

    def patch(self, request, pk):          # pk = key point id
        k = get_object_or_404(PracticeKeyPoint, pk=pk)
        for f in ("text", "category", "reference_value", "explanation"):
            if f in request.data:
                setattr(k, f, request.data[f])
        k.save()
        return Response(_practice_admin(k.item))

    def delete(self, request, pk):
        k = get_object_or_404(PracticeKeyPoint, pk=pk)
        k.delete()
        return Response(status=204)


class AdminRaterAnalyticsView(APIView):
    """Rater quality: agreement with the panel, speed, practice accuracy."""
    permission_classes = [IsAdmin]

    def get(self, request):
        from organisations.models import Rater
        out = []
        for rater in Rater.objects.select_related("user"):
            done = list(rater.tasks.filter(status="done").select_related("anonymous_item"))
            same = total = 0
            diffs, minutes = [], []
            for t in done:
                others = RatingTask.objects.filter(anonymous_item=t.anonymous_item, status="done", excluded=False).exclude(pk=t.pk)
                if not others.exists():
                    continue
                s_mine = task_score(t)
                other_scores = [task_score(o) for o in others]
                other_scores = [x for x in other_scores if x is not None]
                if s_mine is not None and other_scores:
                    diffs.append(abs(s_mine - statistics.fmean(other_scores)))
                mine = {s.key_point_id: s.value for s in t.scores.all()}
                for kp_id, val in mine.items():
                    vals = [x.value for o in others for x in o.scores.all() if x.key_point_id == kp_id]
                    if vals:
                        total += 1
                        same += val == statistics.mode(vals)
                if t.started_at and t.completed_at:
                    minutes.append((t.completed_at - t.started_at).total_seconds() / 60)
            attempts = rater.practice_attempts.all()
            out.append({"rater_id": rater.pk, "email": rater.user.email, "tasks_done": len(done),
                        "tasks_total": rater.tasks.count(),
                        "pct_same_as_panel": r1(same / total * 100) if total else None,
                        "mean_abs_diff": r1(statistics.fmean(diffs)) if diffs else None,
                        "avg_minutes": r1(statistics.fmean(minutes)) if minutes else None,
                        "practice_accuracy": r1(statistics.fmean(a.agreement for a in attempts)) if attempts else None,
                        "is_calibrated": rater.is_calibrated, "excluded_tasks": rater.tasks.filter(excluded=True).count()})
        return Response(out)
