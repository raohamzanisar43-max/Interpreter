from django.conf import settings
from django.contrib import admin
from django.http import FileResponse, Http404
from django.urls import include, path, re_path
from rest_framework.routers import SimpleRouter

from accounts.permissions import IsAdmin  # noqa: F401
from compliance import views as comp
from organisations import views as org
from rating import views as rat
from reports import views as rep
from rounds import views as rnd
from submissions import views as sub

from . import storage

admin_router = SimpleRouter()
admin_router.register("companies", org.AdminCompanyViewSet, basename="admin-company")
admin_router.register("raters", org.AdminRaterViewSet, basename="admin-rater")
admin_router.register("rounds", rnd.AdminRoundViewSet, basename="admin-round")
admin_router.register("recordings", rnd.AdminRecordingViewSet, basename="admin-recording")
admin_router.register("keypoints", rnd.AdminKeyPointViewSet, basename="admin-keypoint")

company_router = SimpleRouter()
company_router.register("interpreters", org.CompanyInterpreterViewSet, basename="company-interpreter")
company_router.register("rounds", rnd.CompanyRoundViewSet, basename="company-round")

admin_extra = [
    path("dashboard/", comp.AdminDashboardView.as_view()),
    path("settings/", comp.AdminSettingsView.as_view()),
    path("terms/", comp.AdminTermsView.as_view()),
    path("privacy/", comp.AdminPrivacyView.as_view()),
    path("audit/", comp.AdminAuditView.as_view()),
    path("notifications/", comp.AdminNotificationLogView.as_view()),
    path("email-templates/", comp.AdminEmailTemplatesView.as_view()),
    path("email-templates/<str:key>/", comp.AdminEmailTemplatesView.as_view()),
    path("users/<int:user_id>/reset-mfa/", org.ResetMfaView.as_view()),
    path("interpreters/", comp.AdminInterpretersView.as_view()),
    path("interpreters/<int:pk>/<str:action>/", comp.AdminInterpreterActionView.as_view()),
    path("rounds/<int:round_id>/delete-audio/", comp.AdminRoundDeleteAudioView.as_view()),
    path("rounds/<int:round_id>/submission-status/", sub.AdminSubmissionStatusView.as_view()),
    path("rounds/<int:round_id>/reminders/", sub.AdminRemindersView.as_view()),
    path("rounds/<int:round_id>/distribute/", rat.AdminDistributeView.as_view()),
    path("rounds/<int:round_id>/review/", rat.AdminForceReviewView.as_view()),
    path("rounds/<int:round_id>/scores/", rat.AdminScoresView.as_view()),
    path("rounds/<int:round_id>/pairwise/", rat.AdminPairwiseResultsView.as_view()),
    path("rounds/<int:round_id>/reports/", rep.AdminReportListView.as_view()),
    path("rounds/<int:round_id>/reports/generate/", rep.AdminReportGenerateView.as_view()),
    path("rounds/<int:round_id>/reports/release-all/", rep.AdminReleaseAllView.as_view()),
    path("rounds/<int:round_id>/export.xlsx", rep.AdminRoundExportView.as_view()),
    path("export/all.xlsx", rep.AdminFullExportView.as_view()),
    path("reports/<int:pk>/", rep.AdminReportDetailView.as_view()),
    path("reports/<int:pk>/approve/", rep.AdminReportApproveView.as_view()),
    path("reports/<int:pk>/release/", rep.AdminReportReleaseView.as_view()),
    path("items/<int:item_id>/", rat.AdminItemDetailView.as_view()),
    path("items/<int:item_id>/override/", rat.AdminItemOverrideView.as_view()),
    path("tasks/<int:task_id>/<str:action>/", rat.AdminTaskActionView.as_view()),
    path("practice/", rat.AdminPracticeListView.as_view()),
    path("practice/<int:pk>/", rat.AdminPracticeDetailView.as_view()),
    path("practice/<int:pk>/keypoints/", rat.AdminPracticeKeyPointView.as_view()),
    path("practice-keypoints/<int:pk>/", rat.AdminPracticeKeyPointView.as_view()),
    path("rater-analytics/", rat.AdminRaterAnalyticsView.as_view()),
]

company_extra = [
    path("terms/", comp.CompanyTermsView.as_view()),
    path("terms/accept/", comp.CompanyTermsAcceptView.as_view()),
    path("reports/", rep.CompanyReportListView.as_view()),
    path("reports/<int:pk>/", rep.CompanyReportDetailView.as_view()),
    path("reports/<int:pk>/pdf/", rep.CompanyReportPdfView.as_view()),
    path("history/", rep.CompanyHistoryView.as_view()),
]

interpreter_urls = [
    path("assignment/", sub.InterpreterAssignmentView.as_view()),
    path("assignment/submit/", sub.InterpreterSubmitView.as_view()),
    path("recordings/<int:recording_id>/take/", sub.InterpreterTakeView.as_view()),
]

rater_urls = [
    path("dashboard/", rat.RaterDashboardView.as_view()),
    path("practice/", rat.RaterPracticeListView.as_view()),
    path("practice/<int:pk>/", rat.RaterPracticeDetailView.as_view()),
    path("practice/<int:pk>/score/", rat.RaterPracticeScoreView.as_view()),
    path("tasks/", rat.RaterTaskListView.as_view()),
    path("tasks/<int:pk>/", rat.RaterTaskDetailView.as_view()),
    path("tasks/<int:pk>/complete/", rat.RaterTaskCompleteView.as_view()),
    path("pairs/", rat.RaterPairListView.as_view()),
    path("pairs/<int:pk>/", rat.RaterPairDetailView.as_view()),
]

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/public/privacy/", comp.PublicPrivacyView.as_view()),
    path("api/public/terms/", comp.PublicTermsView.as_view()),
    path("api/media/<str:token>/", storage.serve_media),
    path("api/admin/", include(admin_extra)),
    path("api/admin/", include(admin_router.urls)),
    path("api/company/", include(company_extra)),
    path("api/company/", include(company_router.urls)),
    path("api/interpreter/", include(interpreter_urls)),
    path("api/rater/", include(rater_urls)),
]


def spa(request, path=""):
    """Serve the built React app (frontend/dist) with history-API fallback."""
    dist = settings.FRONTEND_DIST
    target = (dist / path).resolve()
    if path and target.is_file() and dist.resolve() in target.parents:
        return FileResponse(open(target, "rb"))
    index = dist / "index.html"
    if index.exists():
        return FileResponse(open(index, "rb"), content_type="text/html")
    raise Http404("Frontend not built. Run `npm run build` in /frontend, or use the Vite dev server on :5173.")


urlpatterns += [re_path(r"^(?!api/|django-admin/)(?P<path>.*)$", spa)]
