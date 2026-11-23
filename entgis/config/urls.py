from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import path, include
from facilities.views import home

urlpatterns = [
    path("accounts/login/", LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("accounts/logout/", LogoutView.as_view(), name="logout"),

    path("admin/", admin.site.urls),
    path("", home, name="home"),
    path("", include("facilities.urls")),
]


urlpatterns += staticfiles_urlpatterns()
