from django.urls import path
from . import views

app_name = "ai_assistant"

urlpatterns = [
    path("chat/", views.chat_api_view, name="chat"),
    path("jobs/", views.job_search_api_view, name="jobs_search"),
    path("models/", views.ai_models_api_view, name="models"),
    path("models/check/", views.ai_model_check_api_view, name="models_check"),
    path("status/", views.ai_status_api_view, name="status"),
]
