from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.utils import timezone

from facilities.models import TARPCriterion, TARPCriterionApprovalLog


def _require_justification(value):
    if not value or not value.strip():
        raise ValidationError("A justificação é obrigatória.")


def _require_independent_reviewer(criterion, user):
    if criterion.created_by_id == user.pk:
        raise PermissionDenied(
            "Segregação de funções: o autor não pode aprovar o próprio critério."
        )


def _validate_criterion(criterion):
    if not criterion.created_by_id:
        raise ValidationError("O critério tem de identificar o seu autor.")

    if not criterion.effective_from:
        raise ValidationError("Defina a data de entrada em vigor.")

    if not criterion.source_document.strip():
        raise ValidationError("Indique o documento técnico de origem.")

    if not criterion.parameter_id:
        raise ValidationError("Seleccione a variável de monitorização.")

    criterion.full_clean()


@transaction.atomic
def submit_tarp_criterion(criterion_id, user, justification):
    criterion = TARPCriterion.objects.select_for_update().get(pk=criterion_id)

    if criterion.status != "DRAFT":
        raise ValidationError("Apenas critérios em rascunho podem ser submetidos.")

    _require_justification(justification)
    _validate_criterion(criterion)

    criterion.status = "REVIEW"
    criterion.save(update_fields=["status"])

    TARPCriterionApprovalLog.objects.create(
        criterion=criterion,
        action="SUBMITTED",
        performed_by=user,
        justification=justification.strip(),
    )
    return criterion


@transaction.atomic
def approve_tarp_criterion(criterion_id, user, justification, reference):
    if not user.has_perm("facilities.approve_tarpcriterion"):
        raise PermissionDenied("Não tem permissão para aprovar critérios TARP.")

    criterion = TARPCriterion.objects.select_for_update().get(pk=criterion_id)

    if criterion.status != "REVIEW":
        raise ValidationError("O critério não está em revisão.")

    _require_independent_reviewer(criterion, user)
    _require_justification(justification)

    if not reference or not reference.strip():
        raise ValidationError("A referência de aprovação é obrigatória.")

    _validate_criterion(criterion)

    criterion.status = "APPROVED"
    criterion.approved_by = user
    criterion.approved_at = timezone.now()
    criterion.approval_reference = reference.strip()
    criterion.save(update_fields=[
        "status", "approved_by", "approved_at", "approval_reference"
    ])

    TARPCriterionApprovalLog.objects.create(
        criterion=criterion,
        action="APPROVED",
        performed_by=user,
        justification=justification.strip(),
        reference=reference.strip(),
    )
    return criterion


@transaction.atomic
def reject_tarp_criterion(criterion_id, user, justification):
    if not user.has_perm("facilities.approve_tarpcriterion"):
        raise PermissionDenied("Não tem permissão para devolver critérios TARP.")

    criterion = TARPCriterion.objects.select_for_update().get(pk=criterion_id)

    if criterion.status != "REVIEW":
        raise ValidationError("O critério não está em revisão.")

    _require_independent_reviewer(criterion, user)
    _require_justification(justification)

    criterion.status = "DRAFT"
    criterion.save(update_fields=["status"])

    TARPCriterionApprovalLog.objects.create(
        criterion=criterion,
        action="REJECTED",
        performed_by=user,
        justification=justification.strip(),
    )
    return criterion


@transaction.atomic
def retire_tarp_criterion(criterion_id, user, justification):
    if not user.has_perm("facilities.retire_tarpcriterion"):
        raise PermissionDenied("Não tem permissão para retirar critérios TARP.")

    criterion = TARPCriterion.objects.select_for_update().get(pk=criterion_id)

    if criterion.status != "APPROVED":
        raise ValidationError("Apenas critérios aprovados podem ser retirados.")

    _require_independent_reviewer(criterion, user)
    _require_justification(justification)

    criterion.status = "RETIRED"
    criterion.save(update_fields=["status"])

    TARPCriterionApprovalLog.objects.create(
        criterion=criterion,
        action="RETIRED",
        performed_by=user,
        justification=justification.strip(),
    )
    return criterion
