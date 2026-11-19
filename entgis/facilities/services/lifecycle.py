from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from facilities.models import (
    TailingsFacility,
    FacilityLifecycleHistory,
    LifecycleSubmission,
)


@transaction.atomic
def change_lifecycle_stage(
    facility_id,
    new_stage,
    actor,
    effective_date=None,
    notes="",
):
    if not actor or not actor.is_authenticated:
        raise PermissionDenied("É necessário autenticar o utilizador.")

    if not (
        actor.is_staff
        or actor.has_perm("facilities.change_tailingsfacility")
    ):
        raise PermissionDenied(
            "Só um utilizador autorizado da ENDIAMA pode alterar a fase."
        )

    stages = [key for key, label in TailingsFacility.LIFECYCLE_CHOICES]

    if new_stage not in stages:
        raise ValidationError("Fase do ciclo de vida inválida.")

    if not notes or not notes.strip():
        raise ValidationError(
            "A justificação da mudança de fase é obrigatória."
        )

    facility = TailingsFacility.objects.select_for_update().get(
        pk=facility_id
    )
    previous_stage = facility.lifecycle_stage

    if previous_stage == new_stage:
        raise ValidationError("A instalação já se encontra nessa fase.")

    current_index = stages.index(previous_stage)

    if current_index >= len(stages) - 1:
        raise ValidationError(
            "A instalação já se encontra na última fase do ciclo de vida."
        )

    expected_stage = stages[current_index + 1]

    if new_stage != expected_stage:
        raise ValidationError(
            f"A transição permitida é para a fase seguinte: "
            f"{dict(TailingsFacility.LIFECYCLE_CHOICES)[expected_stage]}."
        )

    latest_submission = (
        LifecycleSubmission.objects.select_for_update()
        .filter(
            facility=facility,
            lifecycle_stage=previous_stage,
        )
        .order_by("-revision")
        .first()
    )

    if not latest_submission or latest_submission.status != "APPROVED":
        raise ValidationError(
            "A revisão mais recente do processo da fase actual "
            "tem de estar aprovada pela ENDIAMA antes da transição."
        )

    facility.lifecycle_stage = new_stage
    facility.save(update_fields=["lifecycle_stage", "updated_at"])

    history = FacilityLifecycleHistory.objects.create(
        facility=facility,
        previous_stage=previous_stage,
        new_stage=new_stage,
        effective_date=effective_date or timezone.localdate(),
        changed_by=actor,
        notes=notes.strip(),
    )

    return facility, history
