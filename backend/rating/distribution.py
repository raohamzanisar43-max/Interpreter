"""Anonymise submitted interpretations and hand them out to raters (spec section 4.5)."""
import random
import secrets
from collections import defaultdict
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from compliance.audit import audit
from compliance.models import SiteSettings
from config.storage import anonymised_copy
from notifications.services import notify
from organisations.models import Rater
from submissions.models import Interpretation

from .models import AnonymousItem, PairwiseTask, RatingTask

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def eligible_raters(round_, rater_ids=None):
    cfg = SiteSettings.get()
    from .models import PracticeItem
    needs_cal = cfg.require_calibration and PracticeItem.objects.filter(active=True).exists()
    out = []
    for r in Rater.objects.select_related("user").filter(active=True, user__is_active=True):
        if rater_ids and r.pk not in rater_ids:
            continue
        if round_.language.lower() not in [x.lower() for x in r.languages]:
            continue
        if needs_cal and not r.is_calibrated:
            continue
        out.append(r)
    return out


def final_interpretations(round_):
    return list(Interpretation.objects.filter(
        assignment__round=round_, assignment__status="submitted", deleted_at=None, is_final=True)
        .exclude(audio_path="").select_related("assignment__interpreter", "source_recording"))


def _company_of(interp):
    return interp.assignment.interpreter.company_id


def make_plan(round_, k, pairwise_n, rater_ids=None, rng=None):
    """Pure planning step (used for dry-run preview and real distribution)."""
    rng = rng or random.SystemRandom()
    raters = eligible_raters(round_, rater_ids)
    interps = final_interpretations(round_)
    if not interps:
        raise ValidationError({"detail": "There are no submitted interpretations to distribute."})
    if len(raters) < k:
        raise ValidationError({"detail": f"Need at least {k} eligible raters for {round_.language}; found {len(raters)}."})
    load = {r.pk: 0 for r in raters}
    per_company = {r.pk: defaultdict(int) for r in raters}
    task_plan = {}
    shuffled = interps[:]
    rng.shuffle(shuffled)
    for it in shuffled:
        comp = _company_of(it)
        ranked = sorted(raters, key=lambda r: (load[r.pk], per_company[r.pk][comp], rng.random()))
        chosen = ranked[:k]
        task_plan[it.pk] = [r.pk for r in chosen]
        for r in chosen:
            load[r.pk] += 1
            per_company[r.pk][comp] += 1
    # pairwise: same source recording, different companies, each item in >= pairwise_n comparisons
    pair_plan, pair_load = [], {r.pk: 0 for r in raters}
    by_rec = defaultdict(list)
    for it in interps:
        by_rec[it.source_recording_id].append(it)
    for rec_id, group in by_rec.items():
        if len({_company_of(i) for i in group}) < 2:
            continue
        seen, count = set(), defaultdict(int)
        for _ in range(pairwise_n * 4):
            if all(count[i.pk] >= pairwise_n for i in group):
                break
            pool = sorted(group, key=lambda i: (count[i.pk], rng.random()))
            for a in pool:
                if count[a.pk] >= pairwise_n:
                    continue
                partners = [b for b in pool if _company_of(b) != _company_of(a) and
                            frozenset((a.pk, b.pk)) not in seen]
                if not partners:
                    continue
                b = min(partners, key=lambda x: (count[x.pk], rng.random()))
                seen.add(frozenset((a.pk, b.pk)))
                count[a.pk] += 1
                count[b.pk] += 1
                x, y = (a, b) if rng.random() < 0.5 else (b, a)     # random A/B position
                rater = min(raters, key=lambda r: (pair_load[r.pk], rng.random()))
                pair_load[rater.pk] += 1
                pair_plan.append((rater.pk, x.pk, y.pk, rec_id))
    return {"raters": raters, "interps": interps, "task_plan": task_plan, "pair_plan": pair_plan,
            "load": load, "pair_load": pair_load}


def preview(plan):
    return {"items": len(plan["interps"]), "pairs": len(plan["pair_plan"]),
            "raters": [{"rater_id": r.pk, "email": r.user.email, "tasks": plan["load"][r.pk],
                        "pairs": plan["pair_load"][r.pk]} for r in plan["raters"]]}


@transaction.atomic
def distribute(round_, actor, k=None, pairwise_n=None, rater_ids=None, request=None):
    if round_.status != "closed":
        raise ValidationError({"detail": "Distribution is only possible for a closed round."})
    k = k or round_.min_raters_per_item
    pairwise_n = round_.pairwise_per_item if pairwise_n is None else pairwise_n
    plan = make_plan(round_, k, pairwise_n, rater_ids)
    rng = random.SystemRandom()
    order = list(range(len(plan["interps"])))
    rng.shuffle(order)
    raters = {r.pk: r for r in plan["raters"]}
    items, due = {}, timezone.now() + timedelta(days=14)
    for idx, interp in zip(order, plan["interps"]):
        while True:
            code = f"R{round_.pk}-" + "".join(secrets.choice(CODE_ALPHABET) for _ in range(4))
            if not AnonymousItem.objects.filter(public_code=code).exists():
                break
        items[interp.pk] = AnonymousItem.objects.create(
            round=round_, interpretation=interp, public_code=code, order=idx,
            audio_path=anonymised_copy(interp.audio_path))
    tasks = 0
    for interp_id, rater_ids_ in plan["task_plan"].items():
        for rid in rater_ids_:
            RatingTask.objects.create(anonymous_item=items[interp_id], rater=raters[rid], due_at=due)
            tasks += 1
    for rid, a, b, rec_id in plan["pair_plan"]:
        PairwiseTask.objects.create(round=round_, rater=raters[rid], item_a=items[a], item_b=items[b],
                                    source_recording_id=rec_id)
    round_.status = "rating"
    round_.save(update_fields=["status"])
    from django.conf import settings
    for r in plan["raters"]:
        n = plan["load"][r.pk]
        if n:
            notify("rater_tasks", r.user.email, {"round": round_.name, "count": n,
                                                 "link": f"{settings.FRONTEND_URL}/rater"})
    audit(actor, "distribute", round_, {"items": len(items), "tasks": tasks, "pairs": len(plan["pair_plan"])},
          request=request)
    return {"items": len(items), "tasks": tasks, "pairs": len(plan["pair_plan"])}
