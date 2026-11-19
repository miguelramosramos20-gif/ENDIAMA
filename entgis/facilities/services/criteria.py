from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.utils import timezone

from facilities.models import MonitoringCriterion, CriterionApprovalLog


def _require_justification(value):
    if not value or not value.strip():
        raise ValidationError("A justificação é obrigatória.")


def _validate_criterion_for_review(criterion):
    if not criterion.created_by_id:
        raise ValidationError("O critério tem de identificar o seu autor.")

    if not criterion.effective_from:
        raise ValidationError("Defina a data de entrada em vigor.")

    if not criterion.source_document.strip():
        raise ValidationError("Indique o documento técnico de origem.")

    for level in ("green", "yellow", "orange", "red"):
        lower = getattr(criterion, f"{level}_min")
        upper = getattr(criterion, f"{level}_max")

        if lower is None and upper is None:
            raise ValidationError(
                f"Configure pelo menos um limite para o nível {level.upper()}."
            )

        if lower is not None and upper is not None and lower > upper:
            raise ValidationError(
                f"Limite mínimo superior ao máximo no nível {level.upper()}."
            )


def _require_independent_reviewer(criterion, user):
    if criterion.created_by_id and criterion.created_by_id == user.pk:
        raise PermissionDenied(
            "Segregação de funções: o autor não pode decidir o próprio critério."
        )


@transaction.atomic
def submit_criterion(criterion_id, user, justification):
    criterion = MonitoringCriterion.objects.select_for_update().get(
        pk=criterion_id
    )

    if criterion.status != "DRAFT":
        raise ValidationError("Apenas critérios em rascunho podem ser submetidos.")

    _require_justification(justification)
    _validate_criterion_for_review(criterion)

    criterion.status = "REVIEW"
    criterion.save(update_fields=["status"])

    CriterionApprovalLog.objects.create(
        criterion=criterion,
        action="SUBMITTED",
        performed_by=user,
        justification=justification.strip(),
    )
    return criterion


@transaction.atomic
def approve_criterion(criterion_id, user, justification, reference):
    if not user.has_perm("facilities.approve_monitoringcriterion"):
        raise PermissionDenied("Apenas utilizadores autorizados podem aprovar.")

    criterion = MonitoringCriterion.objects.select_for_update().get(
        pk=criterion_id
    )

    if criterion.status != "REVIEW":
        raise ValidationError("O critério não está em revisão.")

    _require_independent_reviewer(criterion, user)
    _require_justification(justification)

    if not reference or not reference.strip():
        raise ValidationError("A referência da aprovação é obrigatória.")

    _validate_criterion_for_review(criterion)

    criterion.status = "APPROVED"
    criterion.approved_by = user.get_username()
    criterion.approved_at = timezone.now()
    criterion.approval_reference = reference.strip()
    criterion.save(update_fields=[
        "status", "approved_by", "approved_at", "approval_reference"
    ])

    CriterionApprovalLog.objects.create(
        criterion=criterion,
        action="APPROVED",
        performed_by=user,
        justification=justification.strip(),
        reference=reference.strip(),
    )
    return criterion


@transaction.atomic
def reject_criterion(criterion_id, user, justification):
    if not user.has_perm("facilities.approve_monitoringcriterion"):
        raise PermissionDenied("Apenas utilizadores autorizados podem devolver.")

    criterion = MonitoringCriterion.objects.select_for_update().get(
        pk=criterion_id
    )

    if criterion.status != "REVIEW":
        raise ValidationError("O critério não está em revisão.")

    _require_independent_reviewer(criterion, user)
    _require_justification(justification)

    criterion.status = "DRAFT"
    criterion.save(update_fields=["status"])

    CriterionApprovalLog.objects.create(
        criterion=criterion,
        action="REJECTED",
        performed_by=user,
        justification=justification.strip(),
    )
    return criterion


@transaction.atomic
def update_criterion(criterion_id, user, cleaned_data, justification):
    from facilities.models import MiningCompanyUser

    criterion = MonitoringCriterion.objects.select_for_update().get(
        pk=criterion_id
    )

    if criterion.status != "DRAFT":
        raise ValidationError(
            "Apenas critérios em rascunho podem ser editados."
        )

    if not user.is_staff:
        allowed = MiningCompanyUser.objects.filter(
            user=user,
            company_id=criterion.facility.company_id,
            is_active=True,
            role__in=["COMPANY_ADMIN", "COMPANY_EDITOR"],
        ).exists()
        if not allowed:
            raise PermissionDenied(
                "Não tem autorização para editar este critério."
            )

    _require_justification(justification)

    editable_fields = [
        "facility", "parameter", "version", "effective_from",
        "green_min", "green_max",
        "yellow_min", "yellow_max",
        "orange_min", "orange_max",
        "red_min", "red_max",
        "source_document", "notes",
    ]

    for field in editable_fields:
        if field in cleaned_data:
            setattr(criterion, field, cleaned_data[field])

    criterion.save()

    CriterionApprovalLog.objects.create(
        criterion=criterion,
        action="UPDATED",
        performed_by=user,
        justification=justification.strip(),
    )
    return criterion


@transaction.atomic
def retire_criterion(criterion_id, user, justification):
    if not user.is_staff or not user.has_perm(
        "facilities.approve_monitoringcriterion"
    ):
        raise PermissionDenied(
            "Apenas revisores institucionais autorizados podem retirar critérios."
        )

    criterion = MonitoringCriterion.objects.select_for_update().get(
        pk=criterion_id
    )

    if criterion.status != "APPROVED":
        raise ValidationError(
            "Apenas critérios aprovados podem ser retirados."
        )

    _require_justification(justification)

    criterion.status = "RETIRED"
    criterion.save(update_fields=["status"])

    CriterionApprovalLog.objects.create(
        criterion=criterion,
        action="RETIRED",
        performed_by=user,
        justification=justification.strip(),
        reference=criterion.approval_reference or "",
    )
    return criterion
