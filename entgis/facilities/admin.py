from django.contrib import admin
from .models import MiningCompany, TailingsFacility


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
        "is_simulated",
    )

    autocomplete_fields = ("company",)
