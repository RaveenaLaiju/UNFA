from django.urls import path, include
from django.conf.urls.static import static
from django.conf import settings
from . import views


urlpatterns = [
    path("", views.visitor_home, name="visitor_home"),
    path("visitor_sign", views.visitor_sign, name="visitor_sign"),
    path("user_login", views.user_login, name="user_login"),
    path("user_registration", views.user_registration, name="user_registration"),  # FIXED: was "user_registraion"
    path("matches", views.matches, name="matches"),

    # Include user_app URLs
    path("user_app/", include("user_app.urls")),
]
