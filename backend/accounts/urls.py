from django.urls import path

from . import views

urlpatterns = [
    path("login/", views.LoginView.as_view()),
    path("mfa/setup/", views.MfaSetupView.as_view()),
    path("mfa/verify/", views.MfaVerifyView.as_view()),
    path("refresh/", views.RefreshView.as_view()),
    path("logout/", views.LogoutView.as_view()),
    path("me/", views.MeView.as_view()),
    path("magic-link/", views.MagicLinkView.as_view()),
    path("token/<str:token>/", views.TokenInfoView.as_view()),
    path("invite/accept/", views.InviteAcceptView.as_view()),
    path("invite/<str:token>/", views.InviteInfoView.as_view()),
    path("password-reset/", views.PasswordResetRequestView.as_view()),
    path("password-reset/confirm/", views.PasswordResetConfirmView.as_view()),
]
