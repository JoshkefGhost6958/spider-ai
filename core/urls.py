from django.urls import path
from . import views

urlpatterns = [
    path("", views.landing_page, name="landing_page"),
    path("chat/<str:session_id>/", views.chat_thread_page, name="chat_thread_page"),
    path("chats/<str:session_id>/", views.chat_thread_page, name="chats_thread_page"),
    path("api/upload/", views.api_upload_file, name="api_upload_file"),
    path("api/transcribe/", views.api_transcribe_audio, name="api_transcribe_audio"),
    path("api/analyze/stream/", views.analyze_intent_stream, name="analyze_intent_stream"),
    path("api/analyze/", views.analyze_intent_json, name="analyze_intent_json"),
    # History Tracking & Chat Organization
    path("api/threads/", views.api_threads_list, name="api_threads_list"),
    path("api/threads/save/", views.api_thread_save, name="api_thread_save"),
    path("api/threads/<str:session_id>/", views.api_thread_detail, name="api_thread_detail"),
    path("api/threads/<str:session_id>/delete/", views.api_thread_delete, name="api_thread_delete"),
    path("api/session/clear-guest/", views.api_clear_guest_session, name="api_clear_guest_session"),
    # Auth Endpoints
    path("api/auth/login/", views.api_auth_login, name="api_auth_login"),
    path("api/auth/register/", views.api_auth_register, name="api_auth_register"),
    path("api/auth/logout/", views.api_auth_logout, name="api_auth_logout"),
    path("api/auth/status/", views.api_auth_status, name="api_auth_status"),
    # Site Monitoring & Notification Endpoints
    path("api/monitors/", views.api_monitors_list, name="api_monitors_list"),
    path("api/monitors/create/", views.api_monitor_create, name="api_monitor_create"),
    path("api/monitors/poll/", views.api_monitors_poll, name="api_monitors_poll"),
    path("api/notifications/", views.api_notifications_list, name="api_notifications_list"),
    path("api/notifications/read/", views.api_notifications_mark_read, name="api_notifications_mark_read"),
]
