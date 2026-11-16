from django.urls import path
from . import views

app_name = "facilities"

urlpatterns = [
    path("mapa/", views.national_map, name="national_map"),
]
