from django.urls import path
from . import views

urlpatterns = [
    path('tenants/', views.list_tenants, name='list_tenants'),
    path('ingest/', views.ingest_raw_payload, name='ingest_raw_payload'),
    path('activities/', views.list_activities, name='list_activities'),
    path('activities/<uuid:pk>/', views.activity_detail, name='activity_detail'),
    path('activities/<uuid:pk>/audit-logs/', views.activity_audit_logs, name='activity_audit_logs'),
    path('activities/bulk-action/', views.bulk_action, name='bulk_action'),
    
    # New Batch Ingestion & Records APIs
    path('batches/', views.list_batches, name='list_batches'),
    path('batches/upload/', views.batch_upload, name='batch_upload'),
    path('batches/<uuid:pk>/records/', views.batch_records, name='batch_records'),
    path('batches/<uuid:pk>/', views.batch_delete, name='batch_delete'),
    
    # Governance Records APIs
    path('records/', views.records_list, name='records_list'),
    path('records/<uuid:pk>/approve/', views.record_approve, name='record_approve'),
    path('records/<uuid:pk>/reject/', views.record_reject, name='record_reject'),
    path('records/summary/', views.dashboard_summary, name='dashboard_summary'),
    path('records/export/', views.records_export, name='records_export'),

    # Robust Authentication endpoints
    path('auth/token/', views.CustomObtainAuthToken.as_view(), name='obtain_token'),
    path('auth/register/', views.register_user, name='register_user'),
    path('auth/me/', views.user_profile, name='user_profile'),
]

