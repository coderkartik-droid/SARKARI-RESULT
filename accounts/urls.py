from django.urls import path

from . import views


urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("signup/", views.signup_view, name="signup"),
    path("logout/", views.logout_view, name="logout"),
    path("google/login/", views.google_login_view, name="google_login"),
    path("google/verify/", views.google_auth_verify, name="google_verify"),
    path("password-reset/", views.CustomPasswordResetView.as_view(), name="password_reset"),
    path("password-reset/done/", views.CustomPasswordResetDoneView.as_view(), name="password_reset_done"),
    path(
        "password-reset/confirm/<uidb64>/<token>/",
        views.CustomPasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "password-reset/complete/",
        views.CustomPasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("exams/", views.exams_list, name="exams"),
    path("exams/upcoming/", views.upcoming_exams_list, name="upcoming_exams"),
    path("exams/recent/", views.recent_exams_list, name="recent_exams"),
    path("exams/<int:pk>/", views.exam_detail, name="exam_detail"),
    path(
        "latest-jobs/",
        views.resource_section_list,
        {"section": "latest-jobs"},
        name="latest_jobs",
    ),
    path(
        "latest-jobs/<int:pk>/",
        views.resource_section_detail,
        {"section": "latest-jobs"},
        name="latest_job_detail",
    ),
    path(
        "answer-sheets/",
        views.resource_section_list,
        {"section": "answer-sheets"},
        name="answer_sheets",
    ),
    path(
        "answer-sheets/<int:pk>/",
        views.resource_section_detail,
        {"section": "answer-sheets"},
        name="answer_sheet_detail",
    ),
    path(
        "registration-forms/",
        views.resource_section_list,
        {"section": "registration-forms"},
        name="registration_forms",
    ),
    path(
        "registration-forms/<int:pk>/",
        views.resource_section_detail,
        {"section": "registration-forms"},
        name="registration_form_detail",
    ),
    path(
        "previous-papers/",
        views.resource_section_list,
        {"section": "previous-papers"},
        name="previous_papers",
    ),
    path(
        "previous-papers/<int:pk>/",
        views.resource_section_detail,
        {"section": "previous-papers"},
        name="previous_paper_detail",
    ),
    path(
        "results/",
        views.resource_section_list,
        {"section": "results"},
        name="results",
    ),
    path(
        "results/<int:pk>/",
        views.resource_section_detail,
        {"section": "results"},
        name="result_detail",
    ),
    path("sections/<slug:slug>/", views.section_list, name="section_list"),
    path(
        "sections/<slug:slug>/items/<int:item_id>/",
        views.section_item_detail,
        name="section_item_detail",
    ),
]
