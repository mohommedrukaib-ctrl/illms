from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.ILIMSLoginView.as_view(), name="login"),
    path("logout/", views.LogoutConfirmView.as_view(), name="logout"),
    path("2fa/setup/", views.Setup2FAView.as_view(), name="setup_2fa"),
    path("2fa/verify/", views.Verify2FAView.as_view(), name="verify_2fa"),
    path("password/change/", views.PasswordChangeView.as_view(), name="password_change"),
    path("profile/", views.profile_view, name="profile"),
    path("locked-out/", views.locked_out_view, name="locked_out"),
]