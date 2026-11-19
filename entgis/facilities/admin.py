from django.contrib import admin
from .models import MiningCompany, TailingsFacility, FacilityLifecycleHistory


@admin.register(MiningCompany)
class MiningCompanyAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "country",
        "province",
        "is_active",
        "is_simulated",
    )

    search_fields = ("name", "province")

    list_filter = (
        "country",
        "province",
        "is_active",
        "is_simulated",
    )


@admin.register(TailingsFacility)
class TailingsFacilityAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "company",
        "province",
        "municipality",
        "height_m",
        "capacity_m3",
        "consequence_class",
        "operational_status",
        "lifecycle_stage",
        "is_simulated",
    )

    search_fields = (
        "name",
        "company__name",
        "province",
        "municipality",
    )

    list_filter = (
        "company",
        "province",
        "consequence_class",
        "operational_status",
        "lifecycle_stage",
        "is_simulated",
    )

    autocomplete_fields = ("company",)


# ENT-GIS | Administração da monitorização
from django.contrib.admin.sites import AlreadyRegistered
from .models import (
    MonitoringParameter,
    MonitoringCriterion,
    MonitoringReading,
    MonitoringAlert,
)

for monitoring_model in (
    MonitoringParameter,
    MonitoringCriterion,
    MonitoringReading,
    MonitoringAlert,
):
    try:
        admin.site.register(monitoring_model)
    except AlreadyRegistered:
        pass


# ENT-GIS | Administração controlada da monitorização
from .models import CriterionApprovalLog


class ReadOnlyAuditAdmin(admin.ModelAdmin):
    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class MonitoringReadingAdmin(ReadOnlyAuditAdmin):
    list_display = (
        "facility", "parameter", "associated_structure",
        "observed_at", "value", "unit", "interpretation",
        "entered_by", "recorded_at",
    )
    list_filter = ("interpretation", "facility", "parameter")
    search_fields = (
        "facility__name", "parameter__name", "instrument_code",
    )
    ordering = ("-observed_at",)


admin.site.unregister(MonitoringReading)
admin.site.register(MonitoringReading, MonitoringReadingAdmin)


class MonitoringCriterionAdmin(ReadOnlyAuditAdmin):
    list_display = (
        "facility", "parameter", "version", "status",
        "created_by", "approved_by", "approved_at",
    )
    list_filter = ("status", "facility", "parameter")
    search_fields = ("facility__name", "parameter__name", "source_document")
    ordering = ("facility", "parameter", "-version")


class CriterionApprovalLogAdmin(ReadOnlyAuditAdmin):
    list_display = (
        "criterion", "action", "performed_by", "performed_at", "reference",
    )
    list_filter = ("action", "performed_at")
    search_fields = ("criterion__facility__name", "performed_by__username")
    date_hierarchy = "performed_at"


admin.site.unregister(MonitoringCriterion)
admin.site.register(MonitoringCriterion, MonitoringCriterionAdmin)
admin.site.register(CriterionApprovalLog, CriterionApprovalLogAdmin)


@admin.register(FacilityLifecycleHistory)
class FacilityLifecycleHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "facility", "previous_stage", "new_stage",
        "effective_date", "changed_by", "recorded_at",
    )
    list_filter = ("new_stage", "recorded_at")
    search_fields = ("facility__name", "facility__company__name")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ENT-GIS | Processos do ciclo de vida e auditoria institucional
from .models import (
    LifecycleSubmission,
    LifecycleDocument,
    LifecycleSubmissionLog,
)


class LifecycleSubmissionAdmin(ReadOnlyAuditAdmin):
    list_display = (
        "facility",
        "lifecycle_stage",
        "revision",
        "status",
        "submitted_by",
        "submitted_at",
        "reviewed_by",
        "reviewed_at",
    )
    list_filter = ("lifecycle_stage", "status", "facility__company")
    search_fields = ("facility__name", "facility__company__name")
    ordering = ("facility__name", "lifecycle_stage", "-revision")


class LifecycleDocumentAdmin(ReadOnlyAuditAdmin):
    list_display = (
        "title",
        "submission",
        "document_type",
        "reference",
        "uploaded_by",
        "uploaded_at",
        "is_simulated",
    )
    list_filter = ("document_type", "is_simulated", "uploaded_at")
    search_fields = (
        "title",
        "reference",
        "submission__facility__name",
    )


class LifecycleSubmissionLogAdmin(ReadOnlyAuditAdmin):
    list_display = (
        "submission",
        "action",
        "previous_status",
        "new_status",
        "performed_by",
        "performed_at",
    )
    list_filter = ("action", "performed_at")
    search_fields = (
        "submission__facility__name",
        "performed_by__username",
        "justification",
    )
    date_hierarchy = "performed_at"


for model, model_admin in (
    (LifecycleSubmission, LifecycleSubmissionAdmin),
    (LifecycleDocument, LifecycleDocumentAdmin),
    (LifecycleSubmissionLog, LifecycleSubmissionLogAdmin),
):
    try:
        admin.site.register(model, model_admin)
    except AlreadyRegistered:
        pass
