from django.contrib.auth import views as auth_views
from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from helpdesk.admin import admin_site
from helpdesk import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("health/", views.health, name="health"),
    path("admin/", admin_site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    path("accounts/login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("webhooks/helpdesk", views.HelpdeskWebhook.as_view(), name="helpdesk-webhook"),
    path("api/v1/tickets/", views.TicketList.as_view(), name="tickets"),
    path("api/v1/tickets/<str:ticket_id>/approve/", views.ApproveTicket.as_view(), name="approve"),
    path("api/v1/tickets/<str:ticket_id>/reject/", views.RejectTicket.as_view(), name="reject"),
]
