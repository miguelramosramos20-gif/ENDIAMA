from django.db import transaction

from facilities.models import (
    MonitoringCriterion,
    MonitoringAlert,
    MonitoringAlertLog,
)


LEVELS = ("RED", "ORANGE", "YELLOW", "GREEN")


def _inside(value, lower, upper):
    if lower is None and upper is None:
        return False
    if lower is not None and value < lower:
        return False
    if upper is not None and value > upper:
        return False
    return True


def interpret_reading(reading):
    """
    Prepara a interpretação e o critério na própria instância,
    antes da primeira gravação. Não guarda nem altera registos existentes.
    """
    criterion = (
        MonitoringCriterion.objects
        .filter(
            facility_id=reading.facility_id,
            parameter_id=reading.parameter_id,
            status="APPROVED",
            effective_from__lte=reading.observed_at.date(),
        )
        .order_by("-version")
        .first()
    )

    if criterion is None:
        any_approved = MonitoringCriterion.objects.filter(
            facility_id=reading.facility_id,
            parameter_id=reading.parameter_id,
            status="APPROVED",
        ).exists()
        reading.criterion = None
        reading.interpretation = (
            "NOT_EFFECTIVE" if any_approved else "NOT_CONFIGURED"
        )
        return reading.interpretation

    reading.criterion = criterion

    if reading.unit.strip() != reading.parameter.unit.strip():
        reading.interpretation = "REVIEW"
        return reading.interpretation

    for level in LEVELS:
        lower = getattr(criterion, f"{level.lower()}_min")
        upper = getattr(criterion, f"{level.lower()}_max")
        if _inside(reading.value, lower, upper):
            reading.interpretation = level
            break
    else:
        reading.interpretation = "UNCLASSIFIED"

    return reading.interpretation


@transaction.atomic
def create_monitoring_alert(reading):
    """
    Cria o alerta depois de a leitura estar gravada.
    Regista a criação uma única vez e nunca altera a leitura original.
    """
    if reading.interpretation not in ("YELLOW", "ORANGE", "RED"):
        return None

    alert, created = MonitoringAlert.objects.get_or_create(
        reading=reading,
        defaults={"severity": reading.interpretation},
    )

    if created:
        MonitoringAlertLog.objects.create(
            alert=alert,
            action="CREATED",
            status_before="",
            status_after=alert.status,
            responsible_before="",
            responsible_after=alert.responsible,
            performed_by=reading.entered_by,
            details=(
                "Alerta criado automaticamente após a interpretação "
                f"da leitura. Nível: {alert.severity}."
            ),
        )

    return alert
