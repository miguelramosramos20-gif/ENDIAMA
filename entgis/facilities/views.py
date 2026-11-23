from django.contrib.admin.views.decorators import staff_member_required
import json
import unicodedata
from collections import Counter
from functools import lru_cache
from pathlib import Path

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST

from .models import MiningCompany, TailingsFacility


@lru_cache(maxsize=1)
def get_province_names():
    geojson_path = (
        Path(__file__).resolve().parent
        / "static"
        / "facilities"
        / "data"
        / "angola_provincias.geojson"
    )

    try:
        data = json.loads(geojson_path.read_text(encoding="utf-8"))
        return sorted({
            feature["properties"]["Nome_Prov"].strip()
            for feature in data.get("features", [])
            if feature.get("properties", {}).get("Nome_Prov")
        })
    except (OSError, ValueError, KeyError, TypeError):
        return list(
            TailingsFacility.objects.exclude(
                province=""
            ).values_list(
                "province", flat=True
            ).distinct().order_by("province")
        )


def normalize_name(value):
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(c for c in value if not unicodedata.combining(c))
    return " ".join(value.casefold().replace("-", " ").split())


def home(request):
    """Página institucional do portal nacional ENT-GIS."""
    return render(request, "facilities/home.html")


def _authorized_facilities_for_user(user):
    """
    Fonte comum de autorização para consulta de instalações.
    ENDIAMA: acesso nacional.
    Empresas: apenas instalações das empresas com vínculo activo.
    """
    from django.core.exceptions import PermissionDenied
    from facilities.models import MiningCompanyUser

    if user.is_staff:
        return TailingsFacility.objects.select_related("company").all()

    company_ids = MiningCompanyUser.objects.filter(
        user=user,
        is_active=True,
    ).values_list("company_id", flat=True)

    facilities = TailingsFacility.objects.filter(
        company_id__in=company_ids
    ).select_related("company")

    # Uma empresa com vínculo activo pode ainda não ter instalações.
    # Nesse caso, devolvemos uma lista vazia, sem bloquear o acesso
    # ao módulo de registo da primeira instalação.
    return facilities


@login_required(login_url="/accounts/login/")
def access_hub(request):
    if request.user.is_staff:
        links = [{
            "title": "Administração de utilizadores e acessos",
            "description": "Gerir contas, empresas, perfis e permissões.",
            "url": "/admin/",
        }]
    else:
        links = [{
            "title": "Portal da empresa",
            "description": "Consultar as instalações e os processos autorizados.",
            "url": "/portal/empresa/",
        }]

    return render(request, "facilities/section_hub.html", {
        "hub_title": "Administração de Utilizadores e Acessos",
        "hub_description": (
            "Gestão de contas, vínculos empresariais, perfis e permissões "
            "de acesso ao ENT-GIS."
        ),
        "hub_links": links,
        "hub_note": (
            "A gestão administrativa de contas é efectuada através do "
            "módulo de administração existente."
        ),
    })


@login_required(login_url="/accounts/login/")
def installations_hub(request):
    facilities = _authorized_facilities_for_user(request.user)

    links = [{
        "title": "Mapa geográfico",
        "description": "Consultar a localização das instalações autorizadas.",
        "url": "/mapa/",
    }]

    if request.user.is_staff:
        links.append({
            "title": "Processos submetidos pelas empresas",
            "description": "Analisar e validar os processos de ciclo de vida.",
            "url": "/endiama/processos/",
        })
    else:
        links.append({
            "title": "Portal da empresa",
            "description": "Registar e acompanhar os processos das instalações.",
            "url": "/portal/empresa/",
        })

    return render(request, "facilities/section_hub.html", {
        "hub_title": "Registo e Gestão de Instalações",
        "hub_description": (
            "Consulta das instalações autorizadas e acesso aos respectivos "
            "processos, fases do ciclo de vida e informação técnica."
        ),
        "hub_links": links,
        "facilities": facilities.order_by("province", "name"),
        "hub_note": (
            "Cada instalação mantém o seu próprio registo e histórico. "
            "Os dados técnicos devem ser consultados no contexto da "
            "instalação correspondente."
        ),
    })


@login_required(login_url="/accounts/login/")
def reports_hub(request):
    links = [
        {
            "title": "Monitorização",
            "description": "Consultar leituras, alertas e histórico.",
            "url": "/monitorizacao/",
        },
        {
            "title": "Eventos e alertas TARP",
            "description": "Consultar eventos, níveis de alerta e acções.",
            "url": "/tarp/eventos/",
        },
        {
            "title": "Indicadores GISTM",
            "description": "Consultar conformidade e cobertura da avaliação.",
            "url": "/compliance/",
        },
    ]

    if request.user.is_staff:
        links.append({
            "title": "Processos das empresas",
            "description": "Consultar processos submetidos e respectivas decisões.",
            "url": "/endiama/processos/",
        })

    return render(request, "facilities/section_hub.html", {
        "hub_title": "Relatórios",
        "hub_description": (
            "Acesso aos dados e indicadores existentes para acompanhamento "
            "individual das instalações e supervisão nacional."
        ),
        "hub_links": links,
        "hub_note": (
            "Os relatórios mensais, trimestrais, semestrais e anuais "
            "consolidados e o circuito de submissão mensal de dia 1 a 5 "
            "ainda necessitam de implementação própria. Esta página "
            "não representa a existência de um módulo de relatórios "
            "periódicos já concluído."
        ),
    })


@login_required(login_url="/accounts/login/")
def maturity_hub(request):
    return render(request, "facilities/section_hub.html", {
        "hub_title": "Maturidade GISTM",
        "hub_description": (
            "Acompanhamento da avaliação dos temas, princípios e requisitos "
            "GISTM por instalação."
        ),
        "hub_links": [{
            "title": "Avaliação GISTM por instalação",
            "description": (
                "Consultar avaliações, conformidade, cobertura, evidências "
                "e acções correctivas."
            ),
            "url": "/compliance/",
        }],
        "hub_note": (
            "O módulo existente apresenta indicadores de conformidade "
            "e cobertura dos requisitos avaliados. Estes indicadores não "
            "constituem, por si só, uma classificação formal de maturidade, "
            "uma avaliação de segurança física ou uma certificação GISTM."
        ),
    })



@login_required(login_url="/accounts/login/")
def national_map(request):
    province = request.GET.get("province", "").strip()
    municipality = request.GET.get("municipality", "").strip()
    company_id = request.GET.get("company", "").strip()

    authorized_facilities = _authorized_facilities_for_user(request.user)

    facilities = authorized_facilities.filter(
        latitude__isnull=False,
        longitude__isnull=False
    )

    if province:
        facilities = facilities.filter(province=province)

    if municipality:
        facilities = facilities.filter(municipality=municipality)

    if company_id.isdigit():
        facilities = facilities.filter(company_id=int(company_id))
    else:
        company_id = ""

    map_data = []

    for facility in facilities:
        latitude = float(facility.latitude)
        longitude = float(facility.longitude)

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

    municipalities_query = authorized_facilities.exclude(
        municipality=""
    ).exclude(
        municipality__isnull=True
    )

    if province:
        municipalities_query = municipalities_query.filter(
            province=province
        )

    municipalities = municipalities_query.values_list(
        "municipality", flat=True
    ).distinct().order_by("municipality")

    companies = MiningCompany.objects.filter(
        is_active=True,
        pk__in=authorized_facilities.values("company_id"),
    ).distinct().order_by("name")

    context = {
        "map_data": map_data,
        "facility_count": len(map_data),
        "provinces": get_province_names(),
        "municipalities": municipalities,
        "companies": companies,
        "selected_province": province,
        "selected_municipality": municipality,
        "selected_company": company_id,
    }

    return render(request, "facilities/map.html", context)


@login_required(login_url="/accounts/login/")
def module_page(request, section):
    """
    Páginas independentes de análise do ENT-GIS.
    Utiliza os modelos e dados já existentes.
    """
    facilities = _authorized_facilities_for_user(request.user)

    if section == "territorio":
        province_names = get_province_names()
        province_lookup = {
            normalize_name(name): name for name in province_names
        }

        raw_counts = Counter(
            normalize_name(name)
            for name in facilities.values_list("province", flat=True)
            if name
        )

        rows = []
        matched = 0

        for key, name in province_lookup.items():
            count = raw_counts.get(key, 0)
            matched += count
            rows.append({"name": name, "count": count})

        rows.sort(key=lambda item: (-item["count"], item["name"]))
        maximum = max([item["count"] for item in rows] or [0])

        for item in rows:
            item["percentage"] = (
                round(item["count"] / maximum * 100)
                if maximum else 0
            )

        context = {
            "section": section,
            "section_title": "Distribuição Territorial",
            "section_description": (
                "Análise da distribuição das instalações de rejeitados "
                "pelas províncias de Angola."
            ),
            "metric_title": "Províncias analisadas",
            "metric_count": len(province_names),
            "rows": rows,
            "unmapped_count": facilities.count() - matched,
            "total_facilities": facilities.count(),
        }

    elif section == "seguranca":
        rows = []

        for code, label in TailingsFacility.CONSEQUENCE_CHOICES:
            count = facilities.filter(consequence_class=code).count()
            rows.append({"name": label, "count": count})

        total = facilities.count()

        for item in rows:
            item["percentage"] = (
                round(item["count"] / total * 100)
                if total else 0
            )

        context = {
            "section": section,
            "section_title": "Segurança e Classificação GISTM",
            "section_description": (
                "Consulta da classificação de consequência registada "
                "para as instalações de rejeitados."
            ),
            "metric_title": "Instalações cadastradas",
            "metric_count": total,
            "rows": rows,
            "unmapped_count": 0,
            "total_facilities": total,
        }

    elif section == "operacoes":
        rows = []

        for code, label in TailingsFacility.STATUS_CHOICES:
            count = facilities.filter(operational_status=code).count()
            rows.append({"name": label, "count": count})

        total = facilities.count()

        for item in rows:
            item["percentage"] = (
                round(item["count"] / total * 100)
                if total else 0
            )

        context = {
            "section": section,
            "section_title": "Estado Operacional",
            "section_description": (
                "Visão das instalações segundo a sua fase no ciclo de vida."
            ),
            "metric_title": "Instalações cadastradas",
            "metric_count": total,
            "rows": rows,
            "unmapped_count": 0,
            "total_facilities": total,
        }

    else:
        from django.http import Http404
        raise Http404("Módulo não encontrado.")

    context["simulated_count"] = facilities.filter(
        is_simulated=True
    ).count()

    context["real_count"] = facilities.filter(
        is_simulated=False
    ).count()

    return render(request, "facilities/module.html", context)


# ==========================================================
# ENT-GIS | MÓDULO DE MONITORIZAÇÃO OPERACIONAL
# ==========================================================

from django.contrib.auth.decorators import login_required

def _monitoring_facilities_for_user(user):
    from django.core.exceptions import PermissionDenied
    from facilities.models import MiningCompanyUser, TailingsFacility

    if user.is_staff:
        return TailingsFacility.objects.all()

    company_ids = MiningCompanyUser.objects.filter(
        user=user,
        is_active=True,
        role__in=[
            "COMPANY_ADMIN",
            "COMPANY_EDITOR",
            "COMPANY_VIEWER",
        ],
    ).values_list("company_id", flat=True)

    facilities = TailingsFacility.objects.filter(
        company_id__in=company_ids
    )

    if not facilities.exists():
        raise PermissionDenied(
            "Não tem autorização para consultar a monitorização."
        )

    return facilities


@login_required
@require_POST
def monitoring_alert_action(request, alert_id):
    from django.core.exceptions import PermissionDenied, ValidationError
    from django.shortcuts import get_object_or_404, redirect
    from django.contrib import messages
    from facilities.models import MonitoringAlert, MiningCompanyUser
    from facilities.services.monitoring_alerts import (
        acknowledge_monitoring_alert,
        assign_monitoring_alert,
        record_monitoring_alert_action,
        close_monitoring_alert,
    )

    user = request.user

    if user.is_staff:
        allowed_alerts = MonitoringAlert.objects.all()
    else:
        memberships = MiningCompanyUser.objects.filter(
            user=user,
            is_active=True,
            role__in=["COMPANY_ADMIN", "COMPANY_EDITOR"],
        )
        company_ids = memberships.values_list("company_id", flat=True)

        if not company_ids.exists():
            raise PermissionDenied(
                "Não tem autorização para gerir alertas."
            )

        allowed_alerts = MonitoringAlert.objects.filter(
            reading__facility__company_id__in=company_ids
        )

    alert = get_object_or_404(allowed_alerts, pk=alert_id)

    action = request.POST.get("action", "").strip()
    details = request.POST.get("details", "").strip()
    responsible = request.POST.get("responsible", "").strip()

    try:
        if action == "acknowledge":
            acknowledge_monitoring_alert(alert, user, details)

        elif action == "assign":
            assign_monitoring_alert(
                alert, user, responsible, details
            )

        elif action == "record_action":
            record_monitoring_alert_action(alert, user, details)

        elif action == "close":
            close_monitoring_alert(alert, user, details)

        else:
            messages.error(request, "Acção de alerta inválida.")
            return redirect("facilities:monitoring_dashboard")

    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        return redirect("facilities:monitoring_dashboard")

    messages.success(
        request,
        "Acção registada no histórico auditável do alerta.",
    )
    return redirect("facilities:monitoring_dashboard")


@login_required
def monitoring_dashboard(request):
    from facilities.models import (
        MonitoringReading, MonitoringAlert, MiningCompanyUser
    )

    allowed_facilities = _monitoring_facilities_for_user(request.user)

    readings = MonitoringReading.objects.filter(
        facility__in=allowed_facilities
    ).select_related(
        "facility", "parameter"
    ).order_by("-observed_at")

    alerts = MonitoringAlert.objects.filter(
        reading__facility__in=allowed_facilities,
        status__in=["OPEN", "ACKNOWLEDGED"],
    ).select_related(
        "reading", "reading__facility", "reading__parameter"
    ).prefetch_related(
        "audit_history__performed_by"
    ).order_by("-created_at")

    if request.user.is_staff:
        can_manage_alerts = True
    else:
        can_manage_alerts = MiningCompanyUser.objects.filter(
            user=request.user,
            is_active=True,
            role__in=["COMPANY_ADMIN", "COMPANY_EDITOR"],
        ).exists()

    context = {
        "total_readings": readings.count(),
        "open_alerts": alerts.filter(status="OPEN").count(),
        "acknowledged_alerts": alerts.filter(
            status="ACKNOWLEDGED"
        ).count(),
        "total_pending_alerts": alerts.count(),
        "can_manage_alerts": can_manage_alerts,
        "unconfigured": readings.filter(
            interpretation__in=["NOT_CONFIGURED", "NOT_EFFECTIVE"]
        ).count(),
        "red_count": readings.filter(interpretation="RED").count(),
        "orange_count": readings.filter(interpretation="ORANGE").count(),
        "yellow_count": readings.filter(interpretation="YELLOW").count(),
        "latest_readings": readings[:15],
        "open_alert_list": alerts[:20],
    }

    return render(
        request,
        "facilities/monitoring_dashboard.html",
        context,
    )



from django.contrib.auth.decorators import login_required

@login_required
def monitoring_entry(request):
    from django.shortcuts import redirect
    from django.contrib import messages
    from django.core.exceptions import PermissionDenied
    from facilities.forms import MonitoringReadingForm
    from facilities.models import MiningCompanyUser, TailingsFacility
    from facilities.services.monitoring import (
        interpret_reading,
        create_monitoring_alert,
    )
    from facilities.services.tarp import interpret_tarp_reading

    # ENDIAMA pode registar em qualquer instalação.
    if request.user.is_staff:
        allowed_facilities = TailingsFacility.objects.all()
    else:
        memberships = MiningCompanyUser.objects.filter(
            user=request.user,
            is_active=True,
            role__in=["COMPANY_ADMIN", "COMPANY_EDITOR"],
        )

        company_ids = memberships.values_list("company_id", flat=True)

        allowed_facilities = TailingsFacility.objects.filter(
            company_id__in=company_ids
        )

        if not allowed_facilities.exists():
            raise PermissionDenied(
                "Não tem autorização para registar leituras de monitorização."
            )

    if request.method == "POST":
        form = MonitoringReadingForm(
            request.POST,
            allowed_facilities=allowed_facilities,
        )

        if form.is_valid():
            reading = form.save(commit=False)
            reading.unit = reading.parameter.unit
            reading.entered_by = request.user

            # Classificação e critério são definidos antes da gravação.
            interpret_reading(reading)
            reading.save()

            # O alerta é criado sem modificar a leitura original.
            create_monitoring_alert(reading)

            # Motor TARP independente e sem alteração da leitura.
            tarp_result = interpret_tarp_reading(
                reading,
                actor=request.user,
            )

            messages.success(
                request,
                "Leitura registada. Interpretação de monitorização: "
                f"{reading.get_interpretation_display()}."
            )

            if tarp_result["status"] == "EVENT_CREATED":
                messages.warning(
                    request,
                    f"EVENTO TARP {tarp_result['level']} CRIADO. "
                    "A atribuição da resposta S1-S4 aguarda avaliação "
                    "autorizada."
                )
            elif tarp_result["status"] == "CLASSIFIED":
                messages.info(
                    request,
                    f"Classificação TARP: {tarp_result['level']}. "
                    "Não foi necessário criar evento."
                )
            elif tarp_result["status"] == "NOT_CONFIGURED":
                messages.info(
                    request,
                    "Motor TARP: não existe critério aprovado e vigente "
                    "para este activo e variável."
                )
            elif tarp_result["status"] == "UNIT_MISMATCH":
                messages.error(
                    request,
                    "Motor TARP: unidade incompatível. "
                    "A leitura requer verificação."
                )
            elif tarp_result["status"] == "EVENT_EXISTS":
                messages.info(
                    request,
                    "Já existe um evento TARP associado a esta leitura."
                )

            return redirect("facilities:monitoring_history")

    else:
        form = MonitoringReadingForm(
            allowed_facilities=allowed_facilities,
        )

    return render(
        request,
        "facilities/monitoring_entry.html",
        {"form": form},
    )


from django.contrib.auth.decorators import login_required

@login_required
def monitoring_history(request):
    from facilities.models import MonitoringReading
    from facilities.models import TailingsFacility, MonitoringParameter

    allowed_facilities = _monitoring_facilities_for_user(request.user)

    readings = MonitoringReading.objects.filter(
        facility__in=allowed_facilities
    ).select_related(
        "facility", "parameter", "entered_by", "criterion"
    ).order_by("-observed_at")

    facility_id = request.GET.get("facility")
    parameter_id = request.GET.get("parameter")
    interpretation = request.GET.get("interpretation")

    if facility_id:
        readings = readings.filter(facility_id=facility_id)

    if parameter_id:
        readings = readings.filter(parameter_id=parameter_id)

    if interpretation:
        readings = readings.filter(interpretation=interpretation)

    context = {
        "readings": readings[:500],
        "facilities": allowed_facilities.order_by("name"),
        "parameters": MonitoringParameter.objects.filter(
            is_active=True
        ).order_by("name"),
        "selected_facility": facility_id or "",
        "selected_parameter": parameter_id or "",
        "selected_interpretation": interpretation or "",
        "interpretation_choices": MonitoringReading.INTERPRETATION_CHOICES,
    }

    return render(
        request,
        "facilities/monitoring_history.html",
        context,
    )



@login_required(login_url="/accounts/login/")
@staff_member_required(login_url="/admin/login/")
def monitoring_criterion_entry(request):
    from django.contrib import messages
    from django.shortcuts import redirect
    from facilities.forms import MonitoringCriterionForm

    if request.method == "POST":
        form = MonitoringCriterionForm(request.POST)

        if form.is_valid():
            criterion = form.save(commit=False)
            criterion.created_by = request.user
            criterion.save()
            messages.success(
                request,
                f"Critério {criterion} criado como RASCUNHO. "
                "Ainda não pode ser utilizado na interpretação TARP."
            )
            return redirect("facilities:monitoring_criteria_list")
    else:
        form = MonitoringCriterionForm()

    return render(
        request,
        "facilities/monitoring_criterion_entry.html",
        {"form": form}
    )


def _criterion_editable_facilities(user):
    from facilities.models import MiningCompanyUser, TailingsFacility

    if user.is_staff:
        return TailingsFacility.objects.all()

    company_ids = MiningCompanyUser.objects.filter(
        user=user,
        is_active=True,
        role__in=["COMPANY_ADMIN", "COMPANY_EDITOR"],
    ).values_list("company_id", flat=True)

    return TailingsFacility.objects.filter(company_id__in=company_ids)


@login_required(login_url="/accounts/login/")
def monitoring_criterion_edit(request, criterion_id):
    from django.contrib import messages
    from django.core.exceptions import PermissionDenied, ValidationError
    from django.http import HttpResponseNotAllowed
    from django.shortcuts import get_object_or_404, redirect, render
    from facilities.forms import MonitoringCriterionForm
    from facilities.models import MonitoringCriterion
    from facilities.services.criteria import update_criterion

    if request.method not in ("GET", "POST"):
        return HttpResponseNotAllowed(["GET", "POST"])

    allowed_facilities = _criterion_editable_facilities(request.user)
    if not allowed_facilities.exists():
        raise PermissionDenied(
            "Não tem autorização para editar critérios de monitorização."
        )

    criterion = get_object_or_404(
        MonitoringCriterion,
        pk=criterion_id,
        facility__in=allowed_facilities,
        status="DRAFT",
    )

    form = MonitoringCriterionForm(
        request.POST or None,
        instance=criterion,
    )
    form.fields["facility"].queryset = allowed_facilities

    if request.method == "POST" and form.is_valid():
        try:
            update_criterion(
                criterion.pk,
                request.user,
                form.cleaned_data,
                request.POST.get("justification", ""),
            )
            messages.success(
                request,
                "Critério actualizado. A alteração ficou registada na auditoria."
            )
            return redirect("facilities:monitoring_criteria_list")
        except ValidationError as exc:
            form.add_error(None, str(exc))

    return render(
        request,
        "facilities/monitoring_criterion_entry.html",
        {"form": form, "editing": True},
    )


@login_required(login_url="/accounts/login/")
def monitoring_criterion_retire(request, criterion_id):
    from django.contrib import messages
    from django.core.exceptions import PermissionDenied, ValidationError
    from django.http import HttpResponseNotAllowed
    from django.shortcuts import get_object_or_404, redirect
    from facilities.models import MonitoringCriterion
    from facilities.services.criteria import retire_criterion

    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    if not request.user.is_staff or not request.user.has_perm(
        "facilities.approve_monitoringcriterion"
    ):
        raise PermissionDenied(
            "Não tem autorização para retirar critérios aprovados."
        )

    criterion = get_object_or_404(
        MonitoringCriterion,
        pk=criterion_id,
        status="APPROVED",
    )

    try:
        retire_criterion(
            criterion.pk,
            request.user,
            request.POST.get("justification", ""),
        )
        messages.success(
            request,
            "Critério retirado. A operação ficou registada na auditoria."
        )
    except ValidationError as exc:
        messages.error(request, str(exc))

    return redirect("facilities:monitoring_criteria_list")


@login_required(login_url="/accounts/login/")
def monitoring_criteria_list(request):
    from facilities.models import (
        MonitoringCriterion,
        CriterionApprovalLog,
        MiningCompanyUser,
    )

    allowed_facilities = _monitoring_facilities_for_user(request.user)

    can_submit = request.user.is_staff or MiningCompanyUser.objects.filter(
        user=request.user,
        is_active=True,
        role__in=["COMPANY_ADMIN", "COMPANY_EDITOR"],
        company_id__in=allowed_facilities.values_list(
            "company_id", flat=True
        ),
    ).exists()

    can_decide = (
        request.user.is_staff
        and request.user.has_perm(
            "facilities.approve_monitoringcriterion"
        )
    )

    criteria = MonitoringCriterion.objects.select_related(
        "facility", "parameter"
    ).filter(
        facility__in=allowed_facilities
    )

    editable_facilities = _criterion_editable_facilities(request.user)
    editable_criterion_ids = set(
        criteria.filter(
            status="DRAFT",
            facility__in=editable_facilities,
        ).values_list("pk", flat=True)
    )
    submittable_criterion_ids = editable_criterion_ids

    logs = CriterionApprovalLog.objects.select_related(
        "criterion", "performed_by"
    ).filter(
        criterion__facility__in=allowed_facilities
    )[:30]

    return render(
        request,
        "facilities/monitoring_criteria_list.html",
        {
            "criteria": criteria,
            "logs": logs,
            "can_submit": can_submit,
            "can_decide": can_decide,
            "editable_criterion_ids": editable_criterion_ids,
            "submittable_criterion_ids": submittable_criterion_ids,
        }
    )


@login_required(login_url="/accounts/login/")
def monitoring_criterion_submit(request, criterion_id):
    from django.contrib import messages
    from django.core.exceptions import PermissionDenied, ValidationError
    from django.shortcuts import redirect, get_object_or_404
    from facilities.models import MiningCompanyUser, MonitoringCriterion, TailingsFacility
    from facilities.services.criteria import submit_criterion

    if request.method != "POST":
        return redirect("facilities:monitoring_criteria_list")

    if request.user.is_staff:
        allowed_facilities = TailingsFacility.objects.all()
    else:
        company_ids = MiningCompanyUser.objects.filter(
            user=request.user,
            is_active=True,
            role__in=["COMPANY_ADMIN", "COMPANY_EDITOR"],
        ).values_list("company_id", flat=True)

        allowed_facilities = TailingsFacility.objects.filter(
            company_id__in=company_ids
        )

        if not allowed_facilities.exists():
            raise PermissionDenied(
                "Não tem autorização para submeter critérios de monitorização."
            )

    criterion = get_object_or_404(
        MonitoringCriterion,
        pk=criterion_id,
        facility__in=allowed_facilities,
    )

    try:
        submit_criterion(
            criterion.pk,
            request.user,
            request.POST.get("justification", "")
        )
        messages.success(request, "Critério submetido para revisão.")
    except ValidationError as exc:
        messages.error(request, str(exc))

    return redirect("facilities:monitoring_criteria_list")


@login_required(login_url="/accounts/login/")
def monitoring_criterion_decide(request, criterion_id):
    from django.contrib import messages
    from django.core.exceptions import PermissionDenied, ValidationError
    from django.shortcuts import redirect, get_object_or_404
    from facilities.models import MonitoringCriterion
    from facilities.services.criteria import approve_criterion, reject_criterion

    if request.method != "POST":
        return redirect("facilities:monitoring_criteria_list")

    if (
        not request.user.is_staff
        or not request.user.has_perm(
            "facilities.approve_monitoringcriterion"
        )
    ):
        raise PermissionDenied(
            "A decisão de critérios está reservada aos revisores "
            "institucionais autorizados da ENDIAMA."
        )

    criterion = get_object_or_404(MonitoringCriterion, pk=criterion_id)
    action = request.POST.get("action")
    justification = request.POST.get("justification", "")
    reference = request.POST.get("reference", "")

    try:
        if action == "APPROVE":
            approve_criterion(
                criterion.pk, request.user, justification, reference
            )
            messages.success(request, "Critério aprovado.")
        elif action == "REJECT":
            reject_criterion(
                criterion.pk, request.user, justification
            )
            messages.warning(request, "Critério devolvido para correcção.")
        else:
            messages.error(request, "Decisão inválida.")
    except PermissionDenied:
        raise
    except ValidationError as exc:
        messages.error(request, str(exc))

    return redirect("facilities:monitoring_criteria_list")


# ==========================================================
# ENT-GIS | PAINEL NACIONAL E INDIVIDUAL DE COMPLIANCE GISTM
# ==========================================================

@login_required(login_url="/accounts/login/")
def compliance_dashboard(request):
    from django.db.models import Count
    from facilities.models import TailingsFacility, GISTMAssessment, GISTMRequirement

    total_req = GISTMRequirement.objects.filter(is_active=True).count()
    rows = []
    totals = {k: 0 for k in (
        "conformant", "partial", "non_conformant",
        "under_review", "not_assessed", "not_applicable"
    )}
    evaluated_total = applicable_total = 0

    authorized_facilities = _authorized_facilities_for_user(request.user)

    for facility in authorized_facilities.order_by("province", "name"):
        assessment = GISTMAssessment.objects.filter(
            facility=facility
        ).order_by("-version").first()

        counts = {k: 0 for k in totals}
        if assessment:
            data = assessment.requirement_results.values("status").annotate(total=Count("id"))
            mapping = {
                "CONFORMANT": "conformant", "PARTIAL": "partial",
                "NON_CONFORMANT": "non_conformant",
                "UNDER_REVIEW": "under_review",
                "NOT_ASSESSED": "not_assessed",
                "NOT_APPLICABLE": "not_applicable",
            }
            for item in data:
                key = mapping.get(item["status"])
                if key:
                    counts[key] = item["total"]

        evaluated = counts["conformant"] + counts["partial"] + counts["non_conformant"]
        applicable = max(total_req - counts["not_applicable"], 0)
        compliance = round(100 * counts["conformant"] / evaluated, 1) if evaluated else None
        coverage = round(100 * evaluated / applicable, 1) if applicable else None

        for key in totals:
            totals[key] += counts[key]
        evaluated_total += evaluated
        applicable_total += applicable

        rows.append({
            "facility": facility, "assessment": assessment,
            "counts": counts, "compliance": compliance, "coverage": coverage,
            "simulated": facility.is_simulated or facility.company.is_simulated,
        })

    national_compliance = round(
        100 * totals["conformant"] / evaluated_total, 1
    ) if evaluated_total else None
    national_coverage = round(
        100 * evaluated_total / applicable_total, 1
    ) if applicable_total else None

    return render(request, "facilities/compliance_dashboard.html", {
        "rows": rows, "totals": totals, "facility_count": len(rows),
        "active_requirements": total_req,
        "evaluated_total": evaluated_total,
        "national_compliance": national_compliance,
        "national_coverage": national_coverage,
    })


@login_required(login_url="/accounts/login/")
def compliance_facility(request, facility_id):
    from django.shortcuts import get_object_or_404
    from facilities.models import (
        TailingsFacility, GISTMAssessment, GISTMTopic,
        GISTMRequirementAssessment,
    )

    authorized_facilities = _authorized_facilities_for_user(request.user)
    facility = get_object_or_404(
        authorized_facilities, pk=facility_id
    )
    assessment = GISTMAssessment.objects.filter(
        facility=facility
    ).order_by("-version").first()

    results = {}
    if assessment:
        results = {
            r.requirement_id: r
            for r in assessment.requirement_results.select_related("requirement")
        }

    topics = []
    for topic in GISTMTopic.objects.order_by("order"):
        principles = []
        for principle in topic.principles.order_by("number"):
            requirements = []
            for req in principle.requirements.filter(is_active=True).order_by("code"):
                result = results.get(req.pk)
                requirements.append({"requirement": req, "result": result})
            principles.append({
                "principle": principle, "requirements": requirements
            })
        topics.append({"topic": topic, "principles": principles})

    counts = {
        "conformant": 0, "partial": 0, "non_conformant": 0,
        "under_review": 0, "not_assessed": 0, "not_applicable": 0,
    }
    for result in results.values():
        if result.status in counts:
            counts[result.status.lower()] += 1

    evaluated = counts["conformant"] + counts["partial"] + counts["non_conformant"]
    total_req = sum(
        len(p["requirements"]) for t in topics for p in t["principles"]
    )
    applicable = max(total_req - counts["not_applicable"], 0)
    compliance = round(100 * counts["conformant"] / evaluated, 1) if evaluated else None
    coverage = round(100 * evaluated / applicable, 1) if applicable else None

    return render(request, "facilities/compliance_facility.html", {
        "facility": facility, "assessment": assessment, "topics": topics,
        "counts": counts, "evaluated": evaluated, "total_req": total_req,
        "compliance": compliance, "coverage": coverage,
        "simulated": facility.is_simulated or facility.company.is_simulated,
    })


# ==========================================================
# ENT-GIS | PAINEL NACIONAL E GESTÃO DE EVENTOS TARP
# ==========================================================

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST


@login_required
def tarp_events_dashboard(request):
    from facilities.models import (
        TARPEvent, MiningCompanyUser, MiningCompany, TailingsFacility,
    )

    user = request.user

    if user.is_staff:
        authorized_events = TARPEvent.objects.all()
        companies = MiningCompany.objects.all()
        facilities = TailingsFacility.objects.all()
        can_manage_tarp = True
    else:
        memberships = MiningCompanyUser.objects.filter(
            user=user, is_active=True
        )
        company_ids = list(
            memberships.values_list("company_id", flat=True)
        )
        if not company_ids:
            raise PermissionDenied

        authorized_events = TARPEvent.objects.filter(
            facility__company_id__in=company_ids
        )
        companies = MiningCompany.objects.filter(pk__in=company_ids)
        facilities = TailingsFacility.objects.filter(
            company_id__in=company_ids
        )
        can_manage_tarp = memberships.filter(
            role__in=["COMPANY_ADMIN", "COMPANY_EDITOR"]
        ).exists()

    events = authorized_events.select_related(
        "facility", "facility__company", "associated_structure",
        "reading", "reading__parameter", "criterion",
    ).prefetch_related("history__performed_by")

    company_id = request.GET.get("company", "")
    facility_id = request.GET.get("facility", "")
    trigger_level = request.GET.get("trigger_level", "")
    response_level = request.GET.get("response_level", "")
    status = request.GET.get("status", "")

    if company_id.isdigit():
        events = events.filter(facility__company_id=int(company_id))
    if facility_id.isdigit():
        events = events.filter(facility_id=int(facility_id))
    if trigger_level in ("L1", "L2", "L3", "L4"):
        events = events.filter(trigger_level=trigger_level)
    if response_level in ("S1", "S2", "S3", "S4"):
        events = events.filter(response_level=response_level)
    if status in ("OPEN", "ACKNOWLEDGED", "CLOSED"):
        events = events.filter(status=status)

    # Os indicadores acompanham os filtros seleccionados.
    # A queryset continua limitada às empresas autorizadas.
    now = timezone.now()

    context = {
        "events": events[:200],
        "displayed_events_count": min(events.count(), 200),
        "now": now,
        "total_events": events.count(),
        "open_events": events.filter(status="OPEN").count(),
        "acknowledged_events": events.filter(
            status="ACKNOWLEDGED"
        ).count(),
        "closed_events": events.filter(status="CLOSED").count(),
        "awaiting_response": events.filter(
            response_level__isnull=True
        ).exclude(status="CLOSED").count(),
        "critical_events": events.filter(
            trigger_level="L4"
        ).exclude(status="CLOSED").count(),
        "overdue_events": events.filter(
            due_at__lt=now
        ).exclude(status="CLOSED").count(),
        "companies": companies.order_by("name"),
        "facilities": facilities.select_related(
            "company"
        ).order_by("name"),
        "can_manage_tarp": can_manage_tarp,
        "filters": {
            "company": company_id,
            "facility": facility_id,
            "trigger_level": trigger_level,
            "response_level": response_level,
            "status": status,
        },
    }

    return render(
        request, "facilities/tarp_events_dashboard.html", context
    )


@login_required
def tarp_facility_report(request, facility_id):
    """
    Relatório individual TARP de uma instalação.
    A autorização é limitada à empresa do utilizador.
    """
    from facilities.models import (
        TailingsFacility,
        TARPEvent,
        MiningCompanyUser,
    )

    user = request.user

    if user.is_staff:
        authorized_facilities = TailingsFacility.objects.select_related(
            "company"
        )
    else:
        memberships = MiningCompanyUser.objects.filter(
            user=user,
            is_active=True,
        )
        company_ids = memberships.values_list("company_id", flat=True)

        if not company_ids.exists():
            raise PermissionDenied

        authorized_facilities = TailingsFacility.objects.filter(
            company_id__in=company_ids
        ).select_related("company")

    facility = get_object_or_404(
        authorized_facilities,
        pk=facility_id,
    )

    events = TARPEvent.objects.filter(
        facility=facility
    ).select_related(
        "associated_structure",
        "reading",
        "reading__parameter",
        "criterion",
    ).prefetch_related(
        "history__performed_by"
    ).order_by("-opened_at")

    now = timezone.now()

    total_events = events.count()
    open_events = events.filter(status="OPEN").count()
    acknowledged_events = events.filter(status="ACKNOWLEDGED").count()
    closed_events = events.filter(status="CLOSED").count()

    overdue_events = events.filter(
        due_at__lt=now
    ).exclude(status="CLOSED").count()

    awaiting_response = events.filter(
        response_level__isnull=True
    ).exclude(status="CLOSED").count()

    trigger_counts = {
        level: events.filter(trigger_level=level).count()
        for level in ("L1", "L2", "L3", "L4")
    }

    response_counts = {
        level: events.filter(response_level=level).count()
        for level in ("S1", "S2", "S3", "S4")
    }

    context = {
        "facility": facility,
        "events": events[:200],
        "total_events": total_events,
        "displayed_events_count": min(total_events, 200),
        "open_events": open_events,
        "acknowledged_events": acknowledged_events,
        "closed_events": closed_events,
        "overdue_events": overdue_events,
        "awaiting_response": awaiting_response,
        "critical_events": events.filter(
            trigger_level="L4"
        ).exclude(status="CLOSED").count(),
        "trigger_counts": trigger_counts,
        "response_counts": response_counts,
        "now": now,
    }

    return render(
        request,
        "facilities/tarp_facility_report.html",
        context,
    )

@login_required
@require_POST
def tarp_event_action(request, event_id):
    from django.core.exceptions import ValidationError
    from facilities.models import TARPEvent, MiningCompanyUser
    from facilities.services.tarp import (
        acknowledge_tarp_event,
        assign_tarp_response,
        close_tarp_event,
    )

    user = request.user

    # Mantém o isolamento dos eventos por empresa.
    if user.is_staff:
        allowed_events = TARPEvent.objects.all()
    else:
        memberships = MiningCompanyUser.objects.filter(
            user=user,
            is_active=True,
            role__in=["COMPANY_ADMIN", "COMPANY_EDITOR"],
        )
        company_ids = memberships.values_list("company_id", flat=True)

        if not company_ids.exists():
            raise PermissionDenied

        allowed_events = TARPEvent.objects.filter(
            facility__company_id__in=company_ids
        )

    action = request.POST.get("action", "").strip()
    details = request.POST.get("details", "").strip()
    response_level = request.POST.get("response_level", "").strip()
    responsible = request.POST.get("responsible", "").strip()

    if action not in ("acknowledge", "assign_response", "close"):
        messages.error(request, "Acção TARP inválida.")
        return redirect("facilities:tarp_events_dashboard")

    event = get_object_or_404(allowed_events, pk=event_id)

    try:
        if action == "acknowledge":
            acknowledge_tarp_event(event, user, details)

        elif action == "assign_response":
            assign_tarp_response(
                event,
                user,
                response_level,
                responsible,
                details,
            )

        else:
            close_tarp_event(event, user, details)

    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        return redirect("facilities:tarp_events_dashboard")

    messages.success(
        request,
        "Acção TARP registada no histórico auditável.",
    )
    return redirect("facilities:tarp_events_dashboard")
