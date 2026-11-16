
from django.shortcuts import render
from .models import MiningCompany, TailingsFacility


def home(request):
    context = {
        "company_count": MiningCompany.objects.count(),
        "facility_count": TailingsFacility.objects.count(),
        "simulated_count": TailingsFacility.objects.filter(
            is_simulated=True
        ).count(),
    }

    return render(request, "facilities/home.html", context)

def national_map(request):
    facilities = TailingsFacility.objects.select_related(
        "company"
    ).filter(
        latitude__isnull=False,
        longitude__isnull=False
    )

    province = request.GET.get("province", "").strip()
    company_id = request.GET.get("company", "").strip()

    if province:
        facilities = facilities.filter(province=province)

    if company_id:
        facilities = facilities.filter(company_id=company_id)

    map_data = []

    for facility in facilities:
        latitude = float(facility.latitude)
        longitude = float(facility.longitude)

        # Validar coordenadas geográficas
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            continue

        map_data.append({
            "id": facility.id,
            "name": facility.name,
            "company": facility.company.name,
            "province": facility.province,
            "municipality": facility.municipality,
            "latitude": latitude,
            "longitude": longitude,
            "height_m": (
                float(facility.height_m)
                if facility.height_m is not None else None
            ),
            "capacity_m3": (
                float(facility.capacity_m3)
                if facility.capacity_m3 is not None else None
            ),
            "consequence_class": facility.get_consequence_class_display(),
            "operational_status": facility.get_operational_status_display(),
            "is_simulated": facility.is_simulated,
        })

    provinces = TailingsFacility.objects.exclude(
        province=""
    ).values_list(
        "province", flat=True
    ).distinct().order_by("province")

    companies = MiningCompany.objects.filter(
        is_active=True
    ).order_by("name")

    context = {
        "map_data": map_data,
        "facility_count": len(map_data),
        "provinces": provinces,
        "companies": companies,
        "selected_province": province,
        "selected_company": company_id,
    }

    return render(request, "facilities/map.html", context)
