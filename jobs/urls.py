from django.urls import path
from . import views

app_name = "jobs"

urlpatterns = [
    path("", views.job_list, name="list"),
    path("check-eligibility/", views.eligibility_check, name="eligibility_check"),
    path("details/<int:pk>/", views.job_detail, name="detail"),
    path("<int:pk>/", views.job_detail_json, name="job_detail"),
]
