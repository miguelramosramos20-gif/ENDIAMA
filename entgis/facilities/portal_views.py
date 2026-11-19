from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.http import FileResponse, Http404
import os
from django.utils import timezone

from .forms import get_lifecycle_phase_form, LifecycleDocumentForm
from .models import (
    MiningCompanyUser,
    TailingsFacility,
    LifecycleSubmission,
    LifecycleSubmissionLog,
    LifecycleDocument,
)


def company_facilities(user):
    company_ids = MiningCompanyUser.objects.filter(
        user=user, is_active=True
    ).values_list("company_id", flat=True)

    return TailingsFacility.objects.filter(
        company_id__in=company_ids
    ).select_related("company")


def require_endiama_user(user):
    if not user.is_staff:
        raise PermissionDenied(
            "Esta área é reservada aos utilizadores autorizados da ENDIAMA."
        )


@login_required
def company_portal(request):
    facilities = company_facilities(request.user)
    return render(
        request,
        "facilities/company_portal.html",
        {"facilities": facilities},
    )


@login_required
def lifecycle_submission(request, facility_id):
    with transaction.atomic():
        facility = get_object_or_404(
            company_facilities(request.user).select_for_update(),
            pk=facility_id,
        )
        membership = get_object_or_404(
            MiningCompanyUser,
            user=request.user,
            company=facility.company,
            is_active=True,
        )

        latest = LifecycleSubmission.objects.filter(
            facility=facility,
            lifecycle_stage=facility.lifecycle_stage,
        ).order_by("-revision").first()

        editable_statuses = ("DRAFT", "REJECTED", "CHANGES_REQUESTED")
        can_edit = (
            membership.role != "COMPANY_VIEWER"
            and (latest is None or latest.status in editable_statuses)
        )

        if request.method == "POST":
            if not can_edit:
                raise PermissionDenied(
                    "Este processo não pode ser alterado no estado actual."
                )

            form_class = get_lifecycle_phase_form(facility.lifecycle_stage)
            form = form_class(request.POST)

            if form.is_valid():
                action = request.POST.get("action", "draft")
                if action not in ("draft", "submit"):
                    raise PermissionDenied("Acção inválida.")

                if latest and latest.status == "DRAFT":
                    submission = latest
                else:
                    revision = (
                        LifecycleSubmission.objects.filter(
                            facility=facility,
                            lifecycle_stage=facility.lifecycle_stage,
                        ).order_by("-revision").values_list(
                            "revision", flat=True
                        ).first() or 0
                    ) + 1

                    submission = LifecycleSubmission(
                        facility=facility,
                        lifecycle_stage=facility.lifecycle_stage,
                        revision=revision,
                    )

                previous_status = submission.status
                phase_data = {}
                for key, value in form.cleaned_data.items():
                    if hasattr(value, "isoformat"):
                        value = value.isoformat()
                    phase_data[key] = value

                submission.phase_data = phase_data

                if action == "submit":
                    submission.status = "SUBMITTED"
                    submission.submitted_by = request.user
                    submission.submitted_at = timezone.now()
                    log_action = "SUBMITTED"
                else:
                    submission.status = "DRAFT"
                    log_action = "DRAFT_SAVED"

                submission.save()

                LifecycleSubmissionLog.objects.create(
                    submission=submission,
                    action=log_action,
                    previous_status=previous_status,
                    new_status=submission.status,
                    performed_by=request.user,
                    justification=(
                        "Submissão efectuada pela empresa."
                        if action == "submit"
                        else "Gravação de rascunho pela empresa."
                    ),
                )

                messages.success(
                    request,
                    "Processo submetido à ENDIAMA."
                    if action == "submit"
                    else "Rascunho guardado com sucesso.",
                )
                return redirect(
                    "facilities:lifecycle_submission",
                    facility_id=facility.pk,
                )

        display_submission = latest
        form_class = get_lifecycle_phase_form(facility.lifecycle_stage)
        initial = display_submission.phase_data if display_submission else {}

        if request.method != "POST":
            form = form_class(initial=initial)

    documents = (
        display_submission.documents.select_related("uploaded_by").all()
        if display_submission else []
    )

    return render(
        request,
        "facilities/lifecycle_submission.html",
        {
            "facility": facility,
            "form": form,
            "submission": display_submission,
            "phase_label": facility.get_lifecycle_stage_display(),
            "read_only": not can_edit,
            "can_edit": can_edit,
            "documents": documents,
            "document_form": LifecycleDocumentForm(),
        },
    )


@login_required
def lifecycle_review_queue(request):
    require_endiama_user(request.user)

    submissions = (
        LifecycleSubmission.objects.filter(
            status__in=("SUBMITTED", "UNDER_REVIEW")
        )
        .select_related("facility", "facility__company", "submitted_by")
        .order_by("submitted_at", "facility__name")
    )

    return render(
        request,
        "facilities/lifecycle_review_queue.html",
        {"submissions": submissions},
    )


@login_required
def lifecycle_review_detail(request, submission_id):
    require_endiama_user(request.user)

    submission = get_object_or_404(
        LifecycleSubmission.objects.select_related(
            "facility", "facility__company", "submitted_by", "reviewed_by"
        ).prefetch_related("documents", "decision_history__performed_by"),
        pk=submission_id,
    )

    if request.method == "POST":
        with transaction.atomic():
            # Ordem uniforme de bloqueio: instalação -> processo.
            submission_ref = get_object_or_404(
                LifecycleSubmission.objects.only("facility_id"),
                pk=submission_id,
            )

            get_object_or_404(
                TailingsFacility.objects.select_for_update(),
                pk=submission_ref.facility_id,
            )

            submission = get_object_or_404(
                LifecycleSubmission.objects.select_for_update(),
                pk=submission_id,
            )

            action = request.POST.get("action", "")
            justification = request.POST.get("justification", "").strip()

            if not justification:
                messages.error(
                    request,
                    "A fundamentação da decisão é obrigatória.",
                )
                return redirect(
                    "facilities:lifecycle_review_detail",
                    submission_id=submission_id,
                )

            previous_status = submission.status

            if action == "start_review":
                if previous_status != "SUBMITTED":
                    raise PermissionDenied(
                        "Só é possível iniciar a análise de um processo submetido."
                    )
                new_status = "UNDER_REVIEW"
                log_action = "REVIEW_STARTED"

            elif action == "approve":
                if previous_status != "UNDER_REVIEW":
                    raise PermissionDenied(
                        "O processo tem de estar em análise para ser aprovado."
                    )
                new_status = "APPROVED"
                log_action = "APPROVED"

            elif action == "reject":
                if previous_status != "UNDER_REVIEW":
                    raise PermissionDenied(
                        "O processo tem de estar em análise para ser rejeitado."
                    )
                new_status = "REJECTED"
                log_action = "REJECTED"

            elif action == "request_changes":
                if previous_status != "UNDER_REVIEW":
                    raise PermissionDenied(
                        "O processo tem de estar em análise para solicitar correcções."
                    )
                new_status = "CHANGES_REQUESTED"
                log_action = "CHANGES_REQUESTED"

            else:
                raise PermissionDenied("Decisão inválida.")

            submission.status = new_status
            submission.reviewed_by = request.user
            submission.reviewed_at = timezone.now()
            submission.review_notes = justification
            submission.save(
                update_fields=[
                    "status", "reviewed_by", "reviewed_at",
                    "review_notes", "updated_at",
                ]
            )

            LifecycleSubmissionLog.objects.create(
                submission=submission,
                action=log_action,
                previous_status=previous_status,
                new_status=new_status,
                performed_by=request.user,
                justification=justification,
            )

            messages.success(request, "Decisão registada no histórico.")
            return redirect(
                "facilities:lifecycle_review_detail",
                submission_id=submission_id,
            )

    history = submission.decision_history.select_related(
        "performed_by"
    ).all()

    return render(
        request,
        "facilities/lifecycle_review_detail.html",
        {
            "submission": submission,
            "history": history,
        },
    )


@login_required
def lifecycle_stage_change_view(request, facility_id):
    require_endiama_user(request.user)

    from django import forms
    from django.core.exceptions import ValidationError
    from .services.lifecycle import change_lifecycle_stage

    facility = get_object_or_404(
        TailingsFacility.objects.select_related("company"),
        pk=facility_id,
    )

    stages = list(TailingsFacility.LIFECYCLE_CHOICES)
    current_index = [key for key, label in stages].index(
        facility.lifecycle_stage
    )
    next_stage = stages[current_index + 1] if current_index < len(stages) - 1 else None

    if request.method == "POST":
        notes = request.POST.get("notes", "").strip()
        effective_date = request.POST.get("effective_date") or None

        try:
            if not next_stage:
                raise ValidationError(
                    "A instalação já se encontra na última fase."
                )

            if request.POST.get("new_stage") != next_stage[0]:
                raise ValidationError(
                    "Apenas a fase imediatamente seguinte pode ser seleccionada."
                )

            change_lifecycle_stage(
                facility_id=facility.pk,
                new_stage=next_stage[0],
                actor=request.user,
                effective_date=effective_date,
                notes=notes,
            )
            messages.success(
                request,
                "Fase do ciclo de vida alterada e histórico registado.",
            )
            return redirect("facilities:lifecycle_stage_change", facility_id=facility.pk)

        except (ValidationError, PermissionDenied) as exc:
            messages.error(request, "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc))

    return render(
        request,
        "facilities/lifecycle_stage_change.html",
        {
            "facility": facility,
            "next_stage": next_stage,
            "approved_process": LifecycleSubmission.objects.filter(
                facility=facility,
                lifecycle_stage=facility.lifecycle_stage,
                status="APPROVED",
            ).exists(),
            "history": facility.lifecycle_history.select_related(
                "changed_by"
            ).all() if hasattr(facility, "lifecycle_history") else [],
        },
    )


@login_required
def lifecycle_document_upload(request, submission_id):
    if request.method != "POST":
        raise PermissionDenied("Método não permitido.")

    stored_file_name = None
    storage = None

    try:
        with transaction.atomic():
            # 1. Identificar a instalação associada ao processo.
            initial_submission = get_object_or_404(
                LifecycleSubmission.objects.only("pk", "facility_id"),
                pk=submission_id,
            )
            facility_id = initial_submission.facility_id

            # 2. Bloquear primeiro a instalação.
            facility = get_object_or_404(
                TailingsFacility.objects.select_for_update().select_related(
                    "company"
                ),
                pk=facility_id,
            )

            # 3. Bloquear depois a submissão.
            submission = get_object_or_404(
                LifecycleSubmission.objects.select_for_update(),
                pk=submission_id,
            )

            if submission.facility_id != facility.pk:
                raise PermissionDenied(
                    "A associação do processo à instalação foi alterada."
                )

            membership = get_object_or_404(
                MiningCompanyUser,
                user=request.user,
                company=facility.company,
                is_active=True,
            )

            if membership.role == "COMPANY_VIEWER":
                raise PermissionDenied(
                    "O seu perfil não permite carregar documentos."
                )

            if submission.lifecycle_stage != facility.lifecycle_stage:
                raise PermissionDenied(
                    "O processo não pertence à fase actual da instalação."
                )

            if submission.status != "DRAFT":
                raise PermissionDenied(
                    "Só é permitido anexar documentos a processos em rascunho."
                )

            form = LifecycleDocumentForm(request.POST, request.FILES)

            if form.is_valid():
                document = form.save(commit=False)
                document.submission = submission
                document.uploaded_by = request.user
                document.is_simulated = False
                document.save()

                stored_file_name = document.file.name
                storage = document.file.storage

                LifecycleSubmissionLog.objects.create(
                    submission=submission,
                    action="DOCUMENT_UPLOADED",
                    previous_status=submission.status,
                    new_status=submission.status,
                    performed_by=request.user,
                    justification=(
                        f"Documento anexado: {document.title}. "
                        f"Tipo: {document.document_type}. "
                        f"Referência: {document.reference or 'Não indicada'}."
                    ),
                )

                messages.success(
                    request,
                    "Documento anexado ao processo com sucesso.",
                )
            else:
                messages.error(
                    request,
                    "Não foi possível anexar o documento: "
                    + "; ".join(
                        error
                        for errors in form.errors.values()
                        for error in errors
                    ),
                )

    except Exception:
        # Reverter também o ficheiro físico, se já tiver sido armazenado.
        if storage and stored_file_name:
            try:
                storage.delete(stored_file_name)
            except Exception:
                pass
        raise

    return redirect(
        "facilities:lifecycle_submission",
        facility_id=facility_id,
    )


@login_required
def lifecycle_document_download(request, document_id):
    document = get_object_or_404(
        LifecycleDocument.objects.select_related(
            "submission__facility",
            "submission__facility__company",
        ),
        pk=document_id,
    )

    is_endiama = request.user.is_staff
    is_company_member = MiningCompanyUser.objects.filter(
        user=request.user,
        company=document.submission.facility.company,
        is_active=True,
    ).exists()

    if not (is_endiama or is_company_member):
        raise PermissionDenied("Não tem autorização para consultar este documento.")

    try:
        file_handle = document.file.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404("O ficheiro documental não foi encontrado.")

    return FileResponse(
        file_handle,
        as_attachment=True,
        filename=os.path.basename(document.file.name),
    )
