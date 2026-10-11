"""Scoring, aggregation and ranking (spec section 4.6).

item score (one rater) = sum(w_k * s_k) / sum(w_k) * 100   with full=1, partial=0.5, lost=0
item score             = mean (or median) of the non-excluded raters; admin override wins
company score          = mean of the company's item scores
"""
import random
import statistics
from collections import defaultdict

from compliance.models import SiteSettings
from rating.models import VALUES, AnonymousItem, PairwiseTask


def task_score(task, key_points=None):
    kps = key_points if key_points is not None else list(
        task.anonymous_item.interpretation.source_recording.key_points.all())
    scored = {s.key_point_id: s.value for s in task.scores.all()}
    total_w = sum(k.weight for k in kps)
    if not total_w or any(k.id not in scored for k in kps):
        return None
    return sum(k.weight * VALUES[scored[k.id]] for k in kps) / total_w * 100


def item_stats(item, cfg=None):
    cfg = cfg or SiteSettings.get()
    kps = list(item.interpretation.source_recording.key_points.all())
    rows, vals = [], []
    for t in item.tasks.select_related("rater__user"):
        s = task_score(t, kps) if t.status == "done" else None
        rows.append({"task": t, "score": s})
        if s is not None and not t.excluded:
            vals.append(s)
    auto = None
    if vals:
        auto = statistics.median(vals) if cfg.aggregation == "median" else statistics.fmean(vals)
    spread = (max(vals) - min(vals)) if len(vals) > 1 else (0 if vals else None)
    final = item.override_score if item.override_score is not None else auto
    return {"item": item, "rows": rows, "auto": auto, "score": final, "spread": spread,
            "flagged": spread is not None and spread > cfg.disagreement_threshold, "n_scores": len(vals)}


def round_item_stats(round_):
    cfg = SiteSettings.get()
    items = (AnonymousItem.objects.filter(round=round_)
             .select_related("interpretation__assignment__interpreter__company", "interpretation__source_recording"))
    return [item_stats(i, cfg) for i in items]


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.fmean(xs) if xs else None


def pairwise_by_item(round_):
    """Win rate per item id (win=1, tie=0.5, loss=0) over completed comparisons."""
    out = defaultdict(list)
    for p in PairwiseTask.objects.filter(round=round_).exclude(winner=""):
        a, b = (1, 0) if p.winner == "a" else (0, 1) if p.winner == "b" else (0.5, 0.5)
        out[p.item_a_id].append(a)
        out[p.item_b_id].append(b)
    return {k: statistics.fmean(v) * 100 for k, v in out.items()}


def company_aggregates(round_):
    """{company_id: {name, score, per_recording, per_category, pairwise, items}} — admin-side data."""
    stats = round_item_stats(round_)
    pw = pairwise_by_item(round_)
    by_company = defaultdict(list)
    for s in stats:
        comp = s["item"].interpretation.assignment.interpreter.company
        by_company[comp].append(s)
    result = {}
    for comp, items in by_company.items():
        per_rec = defaultdict(list)
        cat_num, cat_den = defaultdict(float), defaultdict(float)
        for s in items:
            if s["score"] is not None:
                per_rec[s["item"].interpretation.source_recording].append(s["score"])
            for row in s["rows"]:
                t = row["task"]
                if row["score"] is None or t.excluded:
                    continue
                for sc in t.scores.select_related("key_point"):
                    cat_num[sc.key_point.category] += sc.key_point.weight * VALUES[sc.value]
                    cat_den[sc.key_point.category] += sc.key_point.weight
        result[comp.pk] = {
            "company": comp, "name": comp.name,
            "score": _mean([s["score"] for s in items]),
            "per_recording": [{"title": r.title, "order": r.order, "score": _mean(v)}
                              for r, v in sorted(per_rec.items(), key=lambda kv: (kv[0].order, kv[0].pk))],
            "per_category": [{"category": c, "score": cat_num[c] / cat_den[c] * 100}
                             for c in sorted(cat_den) if cat_den[c]],
            "pairwise": _mean([pw.get(s["item"].pk) for s in items]),
            "items": len(items)}
    return result


def rank_companies(aggs):
    """Competition ranking (1,2,2,4) of companies that have a score."""
    scored = sorted((a for a in aggs.values() if a["score"] is not None), key=lambda a: -a["score"])
    ranks, prev, rank = {}, None, 0
    for i, a in enumerate(scored, start=1):
        if prev is None or round(a["score"], 6) != round(prev, 6):
            rank = i
        ranks[a["company"].pk] = rank
        prev = a["score"]
    return ranks, len(scored)


def r1(x):
    return None if x is None else round(x, 1)


METHODOLOGY = ("Each interpretation is scored by independent raters against a checklist of key points "
               "(fully / partly / lost, weighted). The company score is the average of its interpretations. "
               "Peers are shown anonymously; individual interpreters are never identified.")


def build_report_data(round_, company, aggs, ranks, n_ranked, cfg=None, rng=None):
    """Snapshot for one company. Contains NO interpreter-level data and no peer names."""
    cfg = cfg or SiteSettings.get()
    rng = rng or random.SystemRandom()
    mine = aggs.get(company.pk)
    ranking_visible = n_ranked >= cfg.min_companies_for_ranking and mine and mine["score"] is not None
    data = {"round": {"name": round_.name, "language": round_.language, "deadline": round_.deadline.isoformat()},
            "overall_score": r1(mine["score"]) if mine else None,
            "per_recording": [{"title": x["title"], "score": r1(x["score"])} for x in (mine or {}).get("per_recording", [])],
            "per_category": [{"category": x["category"], "score": r1(x["score"])} for x in (mine or {}).get("per_category", [])],
            "ranking_visible": bool(ranking_visible), "companies_count": n_ranked,
            "rank": None, "percentile": None, "peer_distribution": [], "methodology": METHODOLOGY}
    if ranking_visible:
        rank = ranks[company.pk]
        data["rank"] = rank
        data["percentile"] = round((n_ranked - rank) / (n_ranked - 1) * 100) if n_ranked > 1 else 100
        peers = [a for pk, a in aggs.items() if pk != company.pk and a["score"] is not None]
        rng.shuffle(peers)   # labels are re-shuffled for every report: no cross-report identification
        letters = [chr(ord("A") + i) for i in range(len(peers))]
        dist = [{"label": f"Company {letters[i]}", "score": r1(p["score"]), "is_self": False}
                for i, p in enumerate(peers)]
        dist.append({"label": "Your company", "score": r1(mine["score"]), "is_self": True})
        data["peer_distribution"] = sorted(dist, key=lambda d: -d["score"])
    if round_.show_pairwise_in_report and mine and mine["pairwise"] is not None:
        data["pairwise_win_rate"] = r1(mine["pairwise"])
    return data
