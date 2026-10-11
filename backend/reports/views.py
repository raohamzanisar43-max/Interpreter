from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAdmin, IsCompanyMember
from compliance.audit import audit
from notifications.services import notify
from rating.models import ChecklistScore
from rounds.models import Round

from .export import build_workbook
from .models import CompanyReport
from .pdf import render_report_pdf
from .scoring import build_report_data, company_aggregates, rank_companies


def _admin_row(rep):
    d = rep.data or {}
    return {"id": rep.pk, "company_id": rep.company_id, "company": rep.company.name, "status": rep.status,
            "overall_score": d.get("overall_score"), "rank": d.get("rank"), "released_at": rep.released_at}


class AdminReportGenerateView(APIView):
    permission_classes = [IsAdmin]

    @transaction.atomic
    def post(self, request, round_id):
        r = get_object_or_404(Round, pk=round_id)
        if r.status != "review":
            raise ValidationError({"detail": "Reports can be generated once the round is in the Review stage."})
        aggs = company_aggregates(r)
        ranks, n = rank_companies(aggs)
        made = 0
        for part in r.participations.select_related("company"):
            mine = aggs.get(part.company.pk)
            if not mine or mine["score"] is None:      # nothing submitted / scored: no report to release
                CompanyReport.objects.filter(round=r, company=part.company).exclude(status="released").delete()
                continue
            rep, _ = CompanyReport.objects.get_or_create(round=r, company=part.company)
            if rep.status == "released":
                continue
            rep.data = build_report_data(r, part.company, aggs, ranks, n)
            rep.status = "draft"
            rep.approved_at = None
            rep.save()
            made += 1
        audit(request.user, "reports_generated", r, {"count": made}, request=request)
        return Response({"generated": made})


class AdminReportListView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request, round_id):
        r = get_object_or_404(Round, pk=round_id)
        return Response([_admin_row(x) for x in r.reports.select_related("company")])


def _comment_digest(rep):
    """Anonymous rater comments for this company's items, to help the admin write the summary."""
    out = []
    qs = ChecklistScore.objects.filter(
        rating_task__anonymous_item__round=rep.round,
        rating_task__anonymous_item__interpretation__assignment__interpreter__company=rep.company,
        rating_task__excluded=False).exclude(comment="").select_related(
        "key_point", "rating_task__anonymous_item__interpretation__source_recording")
    for s in qs:
        out.append({"recording": s.rating_task.anonymous_item.interpretation.source_recording.title,
                    "key_point": s.key_point.text, "value": s.value, "comment": s.comment})
    for t in rep.round.items.filter(interpretation__assignment__interpreter__company=rep.company):
        for task in t.tasks.filter(excluded=False).exclude(overall_comment=""):
            out.append({"recording": t.interpretation.source_recording.title, "key_point": "(overall)",
                        "value": "", "comment": task.overall_comment})
    return out


class AdminReportDetailView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request, pk):
        rep = get_object_or_404(CompanyReport.objects.select_related("company", "round"), pk=pk)
        return Response({**_admin_row(rep), "round": {"id": rep.round_id, "name": rep.round.name},
                         "summary": rep.summary, "data": rep.data, "comments": _comment_digest(rep)})

    def patch(self, request, pk):
        rep = get_object_or_404(CompanyReport, pk=pk)
        if rep.status == "released":
            raise ValidationError({"detail": "Released reports are immutable."})
        if "summary" in request.data:
            rep.summary = request.data["summary"]
            if rep.status == "approved":
                rep.status, rep.approved_at = "draft", None
            rep.save()
            audit(request.user, "report_edited", rep, request=request)
        return Response({"ok": True, "status": rep.status})


class AdminReportApproveView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        rep = get_object_or_404(CompanyReport, pk=pk)
        if rep.status != "draft":
            raise ValidationError({"detail": f"Report is already {rep.status}."})
        if rep.data.get("overall_score") is None:
            raise ValidationError({"detail": "This company has no scored items; nothing to approve."})
        rep.status, rep.approved_at = "approved", timezone.now()
        rep.save()
        audit(request.user, "report_approved", rep, request=request)
        return Response({"status": "approved"})


def release_report(rep, actor, request=None):
    if rep.status != "approved":
        raise ValidationError({"detail": "Only approved reports can be released."})
    if rep.round.status not in ("review", "released"):
        raise ValidationError({"detail": "Round is not in the Review stage."})
    pdf = render_report_pdf(rep.company.name, rep.round.name, rep.data, rep.summary)
    rep.pdf_path = default_storage.save(f"reports/{rep.round_id}-{rep.company_id}-{timezone.now():%Y%m%d%H%M%S}.pdf",
                                        ContentFile(pdf))
    rep.status, rep.released_at = "released", timezone.now()
    rep.save()
    r = rep.round
    if not r.reports.exclude(status="released").exists():
        r.status, r.released_at = "released", timezone.now()
        r.save(update_fields=["status", "released_at"])
    for m in rep.company.members.select_related("user"):
        notify("report_released", m.user.email, {"round": r.name, "link": f"{settings.FRONTEND_URL}/company/reports"})
    audit(actor, "report_released", rep, {"company": rep.company.name}, request=request)


class AdminReportReleaseView(APIView):
    permission_classes = [IsAdmin]

    @transaction.atomic
    def post(self, request, pk):
        rep = get_object_or_404(CompanyReport.objects.select_related("round", "company"), pk=pk)
        release_report(rep, request.user, request)
        return Response({"status": "released"})


class AdminReleaseAllView(APIView):
    permission_classes = [IsAdmin]

    @transaction.atomic
    def post(self, request, round_id):
        r = get_object_or_404(Round, pk=round_id)
        n = 0
        for rep in r.reports.filter(status="approved").select_related("round", "company"):
            release_report(rep, request.user, request)
            n += 1
        return Response({"released": n})


# ---------------------------------------------------------------- company side (released only)
def _company_row(rep):
    d = rep.data
    return {"id": rep.pk, "round_name": rep.round.name, "language": rep.round.language, "released_at": rep.released_at,
            "overall_score": d.get("overall_score"), "rank": d.get("rank"), "companies_count": d.get("companies_count"),
            "ranking_visible": d.get("ranking_visible")}


class CompanyReportListView(APIView):
    permission_classes = [IsCompanyMember]

    def get(self, request):
        qs = CompanyReport.objects.filter(company=request.user.company, status="released").select_related("round") \
            .order_by("-released_at")
        return Response([_company_row(x) for x in qs])


class CompanyReportDetailView(APIView):
    permission_classes = [IsCompanyMember]

    def get(self, request, pk):
        rep = get_object_or_404(CompanyReport.objects.select_related("round"), pk=pk,
                                company=request.user.company, status="released")
        return Response({**_company_row(rep), "summary": rep.summary, "data": rep.data})


class CompanyReportPdfView(APIView):
    permission_classes = [IsCompanyMember]

    def get(self, request, pk):
        rep = get_object_or_404(CompanyReport, pk=pk, company=request.user.company, status="released")
        if not rep.pdf_path or not default_storage.exists(rep.pdf_path):
            raise ValidationError({"detail": "PDF not available."})
        resp = FileResponse(default_storage.open(rep.pdf_path, "rb"), content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="eqal-report-{rep.round_id}.pdf"'
        return resp


class CompanyHistoryView(APIView):
    permission_classes = [IsCompanyMember]

    def get(self, request):
        qs = CompanyReport.objects.filter(company=request.user.company, status="released").select_related("round") \
            .order_by("released_at")
        return Response([{"round": x.round.name, "released_at": x.released_at, "score": x.data.get("overall_score"),
                          "rank": x.data.get("rank"), "companies_count": x.data.get("companies_count")} for x in qs])


# ---------------------------------------------------------------- exports
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class AdminRoundExportView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request, round_id):
        r = get_object_or_404(Round, pk=round_id)
        audit(request.user, "export", r, {"scope": "round"}, request=request)
        resp = HttpResponse(build_workbook([r]), content_type=XLSX)
        resp["Content-Disposition"] = f'attachment; filename="eqal-round-{r.pk}.xlsx"'
        return resp


class AdminFullExportView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        audit(request.user, "export", None, {"scope": "all"}, request=request, object_type="Round")
        resp = HttpResponse(build_workbook(Round.objects.all()), content_type=XLSX)
        resp["Content-Disposition"] = 'attachment; filename="eqal-full-export.xlsx"'
        return resp
