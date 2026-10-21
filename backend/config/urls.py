from django.urls import include, path, re_path
from django.views.generic import TemplateView

urlpatterns = [
    path("api/", include("routing.urls")),
    # Everything else is the React single-page app (built into frontend/dist).
    re_path(r"^(?!api/).*$", TemplateView.as_view(template_name="index.html")),
]
