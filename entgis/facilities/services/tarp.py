import django.db
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from facilities.models import (
    TARPCriterion,
    TARPEvent,
    TARPEventLog,
)


def classify_tarp_value(value, criterion):
    """
    Classifica uma leitura nos níveis L1-L4.
    Em limites coincidentes, prevalece o nível de maior severidade.
    """
    levels = [
        ("L4", criterion.level_4),
        ("L3", criterion.level_3),
        ("L2", criterion.level_2),
        ("L1", criterion.level_1),
    ]

    for level, limit in levels:
        if criterion.direction == "HIGHER" and value >= limit:
            return level

        if criterion.direction == "LOWER" and value <= limit:
            return level

    return "L1"


def _get_effective_criterion(reading):
    criteria = TARPCriterion.objects.filter(
        facility_id=reading.facility_id,
        parameter_id=reading.parameter_id,
        associated_structure_id=reading.associated_structure_id,
        status="APPROVED",
        effective_from__lte=reading.observed_at.date(),
    ).order_by("-effective_from", "-version")

    return criteria.first()


@transaction.atomic
def interpret_tarp_reading(reading, actor=None):
    """
    Interpreta uma leitura usando exclusivamente o critério TARP
    aprovado e vigente para a instalação, estrutura e variável.
    Garante no máximo um evento por leitura.
    Não determina automaticamente S1-S4.
    Não encerra eventos anteriores.
    """
    reading = type(reading).objects.select_for_update().select_related(
        "facility", "parameter", "associated_structure", "entered_by"
    ).get(pk=reading.pk)

    # Verificar primeiro: a existência do evento prevalece sobre
    # alterações posteriores dos critérios ou da classificação.
    existing = TARPEvent.objects.filter(reading=reading).first()
    if existing:
        return {
            "status": "EVENT_EXISTS",
            "level": existing.trigger_level,
            "criterion": existing.criterion,
            "event": existing,
            "message": "Já existe um evento associado a esta leitura.",
        }

    criterion = _get_effective_criterion(reading)

    if criterion is None:
        return {
            "status": "NOT_CONFIGURED",
            "level": None,
            "criterion": None,
            "event": None,
            "message": "Não existe critério TARP aprovado e vigente para este activo.",
        }

    if reading.unit.strip() != criterion.parameter.unit.strip():
        return {
            "status": "UNIT_MISMATCH",
            "level": None,
            "criterion": criterion,
            "event": None,
            "message": "A unidade da leitura não corresponde à unidade da variável.",
        }

    level = classify_tarp_value(reading.value, criterion)

    if level == "L1":
        return {
            "status": "CLASSIFIED",
            "level": level,
            "criterion": criterion,
            "event": None,
            "message": "Leitura dentro do primeiro limite de referência TARP.",
        }

    responsible_user = (
        actor if getattr(actor, "is_authenticated", False)
        else reading.entered_by
    )

    if not responsible_user or not getattr(responsible_user, "is_authenticated", False):
        raise ValidationError(
            "Não é possível criar um evento TARP sem utilizador responsável "
            "para o respectivo registo de auditoria."
        )

    asset_name = (
        str(reading.associated_structure)
        if reading.associated_structure_id
        else str(reading.facility)
    )

    description = (
        f"Alerta TARP {level}: {reading.parameter.name}. "
        f"Valor observado: {reading.value} {reading.unit}. "
        f"Activo: {asset_name}. "
        f"Limites aplicados: L1={criterion.level_1}, "
        f"L2={criterion.level_2}, L3={criterion.level_3}, "
        f"L4={criterion.level_4}. "
        f"Critério versão {criterion.version}."
    )

    event = TARPEvent(
        facility=reading.facility,
        associated_structure=reading.associated_structure,
        reading=reading,
        criterion=criterion,
        trigger_level=level,
        response_level=None,
        status="OPEN",
        trigger_description=description,
    )
    event.full_clean()

    # Savepoint interno: permite recuperar de uma eventual corrida
    # entre dois processos que tentem criar o evento simultaneamente.
    try:
        with transaction.atomic():
            event.save()
            TARPEventLog.objects.create(
                event=event,
                action="AUTOMATIC_TRIGGER",
                performed_by=responsible_user,
                details=(
                    f"Evento criado automaticamente pelo motor TARP. "
                    f"Nível de alerta: {level}. "
                    f"Nível de resposta S1-S4 pendente de avaliação autorizada."
                ),
            )
    except django.db.IntegrityError:
        existing = TARPEvent.objects.filter(reading=reading).first()
        if existing:
            return {
                "status": "EVENT_EXISTS",
                "level": existing.trigger_level,
                "criterion": existing.criterion,
                "event": existing,
                "message": "Já existe um evento associado a esta leitura.",
            }
        raise

    return {
        "status": "EVENT_CREATED",
        "level": level,
        "criterion": criterion,
        "event": event,
        "message": f"Evento TARP {level} criado. Resposta operacional pendente.",
    }


def _validate_tarp_action(actor, details):
    if not getattr(actor, "is_authenticated", False):
        raise ValidationError("É necessário um utilizador autenticado.")

    if not details or not details.strip():
        raise ValidationError(
            "É obrigatório registar a justificação ou descrição da acção."
        )


@transaction.atomic
def acknowledge_tarp_event(event, actor, details):
    """Reconhece um evento TARP aberto e regista a operação na auditoria."""
    _validate_tarp_action(actor, details)

    locked_event = TARPEvent.objects.select_for_update().get(pk=event.pk)

    if locked_event.status != "OPEN":
        raise ValidationError(
            "Só é possível reconhecer eventos ainda abertos."
        )

    locked_event.status = "ACKNOWLEDGED"
    locked_event.acknowledged_at = timezone.now()
    locked_event.save(update_fields=["status", "acknowledged_at"])

    TARPEventLog.objects.create(
        event=locked_event,
        action="ACKNOWLEDGED",
        performed_by=actor,
        details=f"Evento reconhecido. {details.strip()}",
    )

    return locked_event


@transaction.atomic
def assign_tarp_response(event, actor, response_level, responsible, details):
    """Atribui a resposta S1-S4 e o responsável a um evento reconhecido."""
    _validate_tarp_action(actor, details)

    locked_event = TARPEvent.objects.select_for_update().get(pk=event.pk)

    if locked_event.status != "ACKNOWLEDGED":
        raise ValidationError(
            "Reconheça o evento antes de atribuir uma resposta."
        )

    valid_levels = dict(TARPEvent.RESPONSE_CHOICES)

    if response_level not in valid_levels:
        raise ValidationError(
            "Seleccione um nível de resposta S1, S2, S3 ou S4."
        )

    responsible = (responsible or "").strip()

    if not responsible or len(responsible) > 180:
        raise ValidationError(
            "Indique um responsável válido (máximo de 180 caracteres)."
        )

    previous_response = locked_event.response_level
    previous_responsible = locked_event.responsible
    reassignment = bool(previous_response or previous_responsible)

    locked_event.response_level = response_level
    locked_event.responsible = responsible
    locked_event.save(update_fields=["response_level", "responsible"])

    previous_details = ""
    if reassignment:
        previous_label = valid_levels.get(
            previous_response, previous_response or "Não atribuída"
        )
        previous_details = (
            f"Resposta anterior: {previous_response or 'Não atribuída'} "
            f"— {previous_label}. "
            f"Responsável anterior: {previous_responsible or 'Não atribuído'}. "
        )

    TARPEventLog.objects.create(
        event=locked_event,
        action="RESPONSE_REASSIGNED" if reassignment else "RESPONSE_ASSIGNED",
        performed_by=actor,
        details=(
            f"{previous_details}"
            f"Nova resposta: {response_level} — "
            f"{valid_levels[response_level]}. "
            f"Novo responsável: {responsible}. "
            f"Justificação: {details.strip()}"
        ),
    )

    return locked_event


@transaction.atomic
def close_tarp_event(event, actor, details):
    """Encerra um evento com resposta atribuída e mantém o histórico."""
    _validate_tarp_action(actor, details)

    locked_event = TARPEvent.objects.select_for_update().get(pk=event.pk)

    if locked_event.status != "ACKNOWLEDGED":
        raise ValidationError(
            "Reconheça o evento antes de o encerrar."
        )

    if not locked_event.response_level or not locked_event.responsible:
        raise ValidationError(
            "Atribua primeiro o nível de resposta e o responsável."
        )

    details = details.strip()

    locked_event.status = "CLOSED"
    locked_event.closed_at = timezone.now()
    locked_event.action_taken = (
        f"{locked_event.action_taken}\n\n"
        f"Justificação de encerramento: {details}"
    ).strip()

    locked_event.save(
        update_fields=["status", "closed_at", "action_taken"]
    )

    TARPEventLog.objects.create(
        event=locked_event,
        action="CLOSED",
        performed_by=actor,
        details=(
            f"Evento encerrado. Resposta: {locked_event.response_level}. "
            f"Responsável: {locked_event.responsible}. "
            f"Justificação: {details}"
        ),
    )

    return locked_event
