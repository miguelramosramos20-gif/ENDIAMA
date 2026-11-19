from django.urls import path
from . import views, portal_views

app_name = "facilities"

urlpatterns = [
    path("portal/empresa/", portal_views.company_portal, name="company_portal"),
    path(
        "portal/empresa/processo/<int:submission_id>/documento/",
        portal_views.lifecycle_document_upload,
        name="lifecycle_document_upload",
    ),
    path(
        "documento/<int:document_id>/",
        portal_views.lifecycle_document_download,
        name="lifecycle_document_download",
    ),
    path("endiama/processos/", portal_views.lifecycle_review_queue, name="lifecycle_review_queue"),
    path("endiama/processos/<int:submission_id>/", portal_views.lifecycle_review_detail, name="lifecycle_review_detail"),
    path("endiama/instalacao/<int:facility_id>/transicao/", portal_views.lifecycle_stage_change_view, name="lifecycle_stage_change"),
    path(
        "portal/empresa/instalacao/<int:facility_id>/",
        portal_views.lifecycle_submission,
        name="lifecycle_submission",
    ),

    path("compliance/", views.compliance_dashboard, name="compliance_dashboard"),
    path("compliance/barragem/<int:facility_id>/", views.compliance_facility, name="compliance_facility"),

    path("monitorizacao/criterios/<int:criterion_id>/decidir/", views.monitoring_criterion_decide, name="monitoring_criterion_decide"),
    path("monitorizacao/criterios/<int:criterion_id>/editar/", views.monitoring_criterion_edit, name="monitoring_criterion_edit"),
    path("monitorizacao/criterios/<int:criterion_id>/retirar/", views.monitoring_criterion_retire, name="monitoring_criterion_retire"),
    path("monitorizacao/criterios/<int:criterion_id>/submeter/", views.monitoring_criterion_submit, name="monitoring_criterion_submit"),
    path("monitorizacao/criterios/", views.monitoring_criteria_list, name="monitoring_criteria_list"),
    path("monitorizacao/criterios/novo/", views.monitoring_criterion_entry, name="monitoring_criterion_entry"),

    path("mapa/", views.national_map, name="national_map"),
    path("territorio/", views.module_page, {"section": "territorio"}, name="territorio"),
    path("seguranca/", views.module_page, {"section": "seguranca"}, name="seguranca"),
    path("operacoes/", views.module_page, {"section": "operacoes"}, name="operacoes"),

    path("tarp/barragem/<int:facility_id>/relatorio/", views.tarp_facility_report, name="tarp_facility_report"),
    path("tarp/eventos/", views.tarp_events_dashboard, name="tarp_events_dashboard"),
    path("tarp/eventos/<int:event_id>/acao/", views.tarp_event_action, name="tarp_event_action"),

    path("monitorizacao/", views.monitoring_dashboard, name="monitoring_dashboard"),
    path("monitorizacao/registar/", views.monitoring_entry, name="monitoring_entry"),
    path("monitorizacao/historico/", views.monitoring_history, name="monitoring_history"),
]
