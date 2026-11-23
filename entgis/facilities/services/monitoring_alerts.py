from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from facilities.models import MonitoringAlert, MonitoringAlertLog


def _validate_action(actor, details):
    if not getattr(actor, "is_authenticated", False):
        raise ValidationError("É necessário um utilizador autenticado.")

    if not details or not details.strip():
        raise ValidationError("A justificação da acção é obrigatória.")


def _write_log(alert, actor, action, status_before, responsible_before, details):
    MonitoringAlertLog.objects.create(
        alert=alert,
        action=action,
        status_before=status_before,
        status_after=alert.status,
        responsible_before=responsible_before,
        responsible_after=alert.responsible,
        performed_by=actor,
        details=details.strip(),
    )


@transaction.atomic
def acknowledge_monitoring_alert(alert, actor, details):
    _validate_action(actor, details)
    locked = MonitoringAlert.objects.select_for_update().get(pk=alert.pk)

    if locked.status != "OPEN":
        raise ValidationError("Só é possível reconhecer alertas abertos.")

    previous_status = locked.status
    previous_responsible = locked.responsible

    locked.status = "ACKNOWLEDGED"
    locked.acknowledged_at = timezone.now()
    locked.save(update_fields=["status", "acknowledged_at"])

    _write_log(
        locked, actor, "ACKNOWLEDGED",
        previous_status, previous_responsible,
        f"Alerta reconhecido. {details.strip()}",
    )
    return locked


@transaction.atomic
def assign_monitoring_alert(alert, actor, responsible, details):
    _validate_action(actor, details)
    locked = MonitoringAlert.objects.select_for_update().get(pk=alert.pk)

    if locked.status not in ("OPEN", "ACKNOWLEDGED"):
        raise ValidationError(
            "Não é possível atribuir um responsável a um alerta encerrado."
        )

    responsible = (responsible or "").strip()
    if not responsible or len(responsible) > 180:
        raise ValidationError(
            "Indique um responsável válido (máximo de 180 caracteres)."
        )

    previous_status = locked.status
    previous_responsible = locked.responsible

    locked.responsible = responsible
    locked.save(update_fields=["responsible"])

    _write_log(
        locked, actor, "ASSIGNED",
        previous_status, previous_responsible,
        f"Responsável atribuído/alterado para {responsible}. "
        f"Justificação: {details.strip()}",
    )
    return locked


@transaction.atomic
def record_monitoring_alert_action(alert, actor, details):
    _validate_action(actor, details)
    locked = MonitoringAlert.objects.select_for_update().get(pk=alert.pk)

    if locked.status != "ACKNOWLEDGED":
        raise ValidationError(
            "Reconheça o alerta antes de registar uma intervenção."
        )

    previous_status = locked.status
    previous_responsible = locked.responsible

    locked.action_taken = (
        f"{locked.action_taken}\n\n{details.strip()}"
    ).strip()
    locked.save(update_fields=["action_taken"])

    _write_log(
        locked, actor, "ACTION_RECORDED",
        previous_status, previous_responsible,
        f"Intervenção registada: {details.strip()}",
    )
    return locked


@transaction.atomic
def close_monitoring_alert(alert, actor, details):
    _validate_action(actor, details)
    locked = MonitoringAlert.objects.select_for_update().get(pk=alert.pk)

    if locked.status != "ACKNOWLEDGED":
        raise ValidationError(
            "Reconheça o alerta antes de o encerrar."
        )

    if not locked.responsible:
        raise ValidationError(
            "Atribua um responsável antes de encerrar o alerta."
        )

    previous_status = locked.status
    previous_responsible = locked.responsible

    locked.status = "CLOSED"
    locked.closed_at = timezone.now()
    locked.action_taken = (
        f"{locked.action_taken}\n\n"
        f"Justificação de encerramento: {details.strip()}"
    ).strip()
    locked.save(
        update_fields=["status", "closed_at", "action_taken"]
    )

    _write_log(
        locked, actor, "CLOSED",
        previous_status, previous_responsible,
        f"Alerta encerrado. Responsável: {locked.responsible}. "
        f"Justificação: {details.strip()}",
    )
    return locked
