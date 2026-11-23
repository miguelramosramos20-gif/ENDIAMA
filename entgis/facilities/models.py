
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class MiningCompany(models.Model):
    name = models.CharField(max_length=200, unique=True)
    country = models.CharField(max_length=100, default="Angola")
    province = models.CharField(max_length=100)
    contact_email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)
    is_simulated = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Sociedade Mineira"
        verbose_name_plural = "Sociedades Mineiras"

    def __str__(self):
        return self.name


class TailingsFacility(models.Model):

    CONSEQUENCE_CHOICES = [
        ("LOW", "Baixa"),
        ("MEDIUM", "Média"),
        ("HIGH", "Alta"),
        ("VERY_HIGH", "Muito Alta"),
        ("EXTREME", "Extrema"),
        ("UNASSESSED", "Não avaliada"),
    ]

    STATUS_CHOICES = [
        ("CONSTRUCTION", "Em construção"),
        ("OPERATIONAL", "Operacional"),
        ("CARE", "Em encerramento"),
        ("CLOSED", "Encerrada"),
    ]

    LIFECYCLE_CHOICES = [
        ("PROJECT", "Projecto"),
        ("CONSTRUCTION", "Construção"),
        ("OPERATION", "Operação"),
        ("CLOSURE", "Fechamento"),
        ("POST_CLOSURE", "Pós-fechamento"),
    ]

    company = models.ForeignKey(
        MiningCompany,
        on_delete=models.PROTECT,
        related_name="facilities"
    )

    name = models.CharField(max_length=200)
    province = models.CharField(max_length=100)
    municipality = models.CharField(max_length=100)

    latitude = models.DecimalField(
        max_digits=10, decimal_places=7, null=True, blank=True
    )
    longitude = models.DecimalField(
        max_digits=10, decimal_places=7, null=True, blank=True
    )

    height_m = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    capacity_m3 = models.DecimalField(
        max_digits=16, decimal_places=2, null=True, blank=True
    )

    construction_method = models.CharField(max_length=100, blank=True)

    consequence_class = models.CharField(
        max_length=20,
        choices=CONSEQUENCE_CHOICES,
        default="UNASSESSED"
    )

    operational_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="CONSTRUCTION"
    )

    lifecycle_stage = models.CharField(
        "Fase do ciclo de vida",
        max_length=20,
        choices=LIFECYCLE_CHOICES,
        default="CONSTRUCTION",
        db_index=True,
    )

    is_simulated = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Instalação de Rejeitados"
        verbose_name_plural = "Instalações de Rejeitados"

    def __str__(self):
        return f"{self.name} - {self.company.name}"


class FacilityLifecycleHistoryQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError(
            "O histórico do ciclo de vida não pode ser alterado."
        )

    def delete(self):
        raise ValidationError(
            "O histórico do ciclo de vida não pode ser eliminado."
        )

    def bulk_update(self, objs, fields, **kwargs):
        raise ValidationError(
            "A actualização em massa do histórico está bloqueada."
        )

    def bulk_create(self, objs, **kwargs):
        raise ValidationError(
            "O histórico só pode ser criado pelo serviço de transição."
        )


class FacilityLifecycleHistory(models.Model):
    objects = models.Manager.from_queryset(
        FacilityLifecycleHistoryQuerySet
    )()

    facility = models.ForeignKey(
        TailingsFacility,
        on_delete=models.PROTECT,
        related_name="lifecycle_history",
    )
    previous_stage = models.CharField(
        max_length=20, blank=True,
        choices=TailingsFacility.LIFECYCLE_CHOICES,
    )
    new_stage = models.CharField(
        max_length=20,
        choices=TailingsFacility.LIFECYCLE_CHOICES,
    )
    effective_date = models.DateField(null=True, blank=True)
    changed_by = models.ForeignKey(
        "auth.User", on_delete=models.PROTECT,
        null=True, blank=True,
    )
    notes = models.TextField(blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError(
                "Os registos do histórico do ciclo de vida são imutáveis."
            )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Os registos do histórico do ciclo de vida não podem ser eliminados."
        )

    class Meta:
        ordering = ["-recorded_at"]
        verbose_name = "Histórico do ciclo de vida"
        verbose_name_plural = "Histórico do ciclo de vida"

    def __str__(self):
        return f"{self.facility.name}: {self.previous_stage} -> {self.new_stage}"


class AssociatedStructure(models.Model):
    TYPE_CHOICES = [
        ("RETURN_WATER_DAM", "Barragem de Água de Retorno"),
    ]

    STATUS_CHOICES = [
        ("CONSTRUCTION", "Em construção"),
        ("OPERATIONAL", "Operacional"),
        ("CARE", "Em encerramento"),
        ("CLOSED", "Encerrada"),
    ]

    facility = models.ForeignKey(
        TailingsFacility,
        on_delete=models.PROTECT,
        related_name="associated_structures",
        verbose_name="Instalação de rejeitados associada",
    )
    structure_type = models.CharField(
        max_length=30,
        choices=TYPE_CHOICES,
        default="RETURN_WATER_DAM",
    )
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    municipality = models.CharField(max_length=100, blank=True)

    latitude = models.DecimalField(
        max_digits=10, decimal_places=7, null=True, blank=True
    )
    longitude = models.DecimalField(
        max_digits=10, decimal_places=7, null=True, blank=True
    )
    capacity_m3 = models.DecimalField(
        max_digits=16, decimal_places=2, null=True, blank=True
    )
    height_m = models.DecimalField(
        max_digits=10, decimal_places=3, null=True, blank=True
    )
    crest_level_m = models.DecimalField(
        max_digits=10, decimal_places=3, null=True, blank=True
    )
    operational_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="OPERATIONAL",
    )
    is_simulated = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["facility", "name"]
        verbose_name = "Estrutura associada"
        verbose_name_plural = "Estruturas associadas"

    def __str__(self):
        return f"{self.name} | {self.facility.name}"


class MonitoringParameter(models.Model):
    CATEGORY_CHOICES = [
        ("HYDRAULIC", "Hidráulica"),
        ("PIEZOMETRIC", "Piezométrica"),
        ("GEOTECHNICAL", "Geotécnica e deformação"),
        ("METEOROLOGICAL", "Meteorológica"),
        ("OPERATIONAL", "Operacional"),
        ("VISUAL", "Inspecção visual"),
    ]

    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=180)
    category = models.CharField(max_length=25, choices=CATEGORY_CHOICES)
    unit = models.CharField(max_length=30)
    description = models.TextField(blank=True)
    instrument_required = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["category", "name"]
        verbose_name = "Variável de monitorização"
        verbose_name_plural = "Variáveis de monitorização"

    def __str__(self):
        return f"{self.name} ({self.unit})"


class MonitoringCriterion(models.Model):
    STATUS_CHOICES = [
        ("DRAFT", "Rascunho"),
        ("REVIEW", "Em revisão"),
        ("APPROVED", "Aprovado"),
        ("RETIRED", "Retirado"),
    ]

    facility = models.ForeignKey(
        TailingsFacility, on_delete=models.PROTECT,
        related_name="monitoring_criteria"
    )
    parameter = models.ForeignKey(
        MonitoringParameter, on_delete=models.PROTECT,
        related_name="criteria"
    )
    version = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="entgis_created_criteria",
        verbose_name="Criado por",
    )
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="DRAFT")

    # Intervalos aprovados para cada nível TARP.
    green_min = models.DecimalField(max_digits=16, decimal_places=4, null=True, blank=True)
    green_max = models.DecimalField(max_digits=16, decimal_places=4, null=True, blank=True)
    yellow_min = models.DecimalField(max_digits=16, decimal_places=4, null=True, blank=True)
    yellow_max = models.DecimalField(max_digits=16, decimal_places=4, null=True, blank=True)
    orange_min = models.DecimalField(max_digits=16, decimal_places=4, null=True, blank=True)
    orange_max = models.DecimalField(max_digits=16, decimal_places=4, null=True, blank=True)
    red_min = models.DecimalField(max_digits=16, decimal_places=4, null=True, blank=True)
    red_max = models.DecimalField(max_digits=16, decimal_places=4, null=True, blank=True)

    effective_from = models.DateField(null=True, blank=True)
    source_document = models.CharField(max_length=255, blank=True)
    approval_reference = models.CharField(max_length=180, blank=True)
    approved_by = models.CharField(max_length=180, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["facility", "parameter", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["facility", "parameter", "version"],
                name="unique_facility_parameter_criterion_version"
            )
        ]
        permissions = [
            ("approve_monitoringcriterion", "Pode aprovar critérios de monitorização"),
        ]
        verbose_name = "Critério de Monitorização"
        verbose_name_plural = "Critérios de Monitorização"

    def save(self, *args, **kwargs):
        from django.core.exceptions import ValidationError

        if not self._state.adding:
            original = type(self).objects.filter(pk=self.pk).first()

            if original and original.status in ("APPROVED", "RETIRED"):
                protected_fields = [
                    "facility_id", "parameter_id", "version", "created_by_id",
                    "green_min", "green_max",
                    "yellow_min", "yellow_max",
                    "orange_min", "orange_max",
                    "red_min", "red_max",
                    "effective_from", "source_document",
                    "approval_reference", "approved_by",
                    "approved_at", "notes",
                ]

                changed = [
                    field for field in protected_fields
                    if getattr(original, field) != getattr(self, field)
                ]

                if changed:
                    raise ValidationError(
                        "Critério aprovado ou retirado protegido. "
                        "Crie uma nova versão para alterar os seus dados."
                    )

                if original.status == "RETIRED" and self.status != "RETIRED":
                    raise ValidationError(
                        "Um critério retirado não pode ser reactivado."
                    )

                if original.status == "APPROVED" and self.status not in (
                    "APPROVED", "RETIRED"
                ):
                    raise ValidationError(
                        "Um critério aprovado só pode ser retirado."
                    )

        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.facility} | {self.parameter} | v{self.version}"


class ImmutableMonitoringReadingQuerySet(models.QuerySet):
    """Leituras históricas: permite criar e consultar, mas não alterar."""

    def update(self, **kwargs):
        from django.core.exceptions import ValidationError
        raise ValidationError(
            "As leituras de monitorização são imutáveis."
        )

    def delete(self):
        from django.core.exceptions import ValidationError
        raise ValidationError(
            "As leituras de monitorização não podem ser eliminadas."
        )

    def bulk_update(self, objs, fields, **kwargs):
        from django.core.exceptions import ValidationError
        raise ValidationError(
            "A actualização em massa das leituras está bloqueada."
        )

    def bulk_create(self, objs, **kwargs):
        from django.core.exceptions import ValidationError
        raise ValidationError(
            "As leituras devem ser registadas pelos formulários e serviços autorizados."
        )


class MonitoringReading(models.Model):
    objects = models.Manager.from_queryset(ImmutableMonitoringReadingQuerySet)()
    INTERPRETATION_CHOICES = [
        ("NOT_CONFIGURED", "Critério não configurado"),
        ("NOT_EFFECTIVE", "Critério ainda não vigente"),
        ("GREEN", "Verde — Normal"),
        ("YELLOW", "Amarelo — Atenção"),
        ("ORANGE", "Laranja — Alerta"),
        ("RED", "Vermelho — Crítico"),
        ("UNCLASSIFIED", "Fora dos intervalos configurados"),
        ("REVIEW", "Requer revisão dos dados"),
    ]

    facility = models.ForeignKey(
        TailingsFacility, on_delete=models.PROTECT,
        related_name="monitoring_readings"
    )
    parameter = models.ForeignKey(
        MonitoringParameter, on_delete=models.PROTECT,
        related_name="readings"
    )
    associated_structure = models.ForeignKey(
        "AssociatedStructure",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="monitoring_readings",
        verbose_name="Estrutura monitorizada",
    )
    criterion = models.ForeignKey(
        MonitoringCriterion, on_delete=models.PROTECT,
        null=True, blank=True, related_name="readings"
    )
    instrument_code = models.CharField(max_length=100, blank=True)
    observed_at = models.DateTimeField()
    value = models.DecimalField(max_digits=16, decimal_places=4)
    unit = models.CharField(max_length=30)
    interpretation = models.CharField(
        max_length=20, choices=INTERPRETATION_CHOICES,
        default="NOT_CONFIGURED"
    )
    notes = models.TextField(blank=True)
    entered_by = models.ForeignKey(
        "auth.User", on_delete=models.PROTECT,
        null=True, blank=True, related_name="entgis_monitoring_readings"
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-observed_at"]
        indexes = [
            models.Index(fields=["facility", "parameter", "-observed_at"]),
            models.Index(fields=["interpretation", "-observed_at"]),
        ]
        verbose_name = "Leitura de monitorização"
        verbose_name_plural = "Leituras de monitorização"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            from django.core.exceptions import ValidationError
            raise ValidationError(
                "Uma leitura registada não pode ser alterada. "
                "Registe uma nova leitura para documentar uma correcção."
            )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        raise ValidationError(
            "Uma leitura de monitorização registada não pode ser eliminada."
        )

    def __str__(self):
        return f"{self.facility} | {self.parameter} | {self.observed_at}"


class MonitoringAlert(models.Model):
    STATUS_CHOICES = [
        ("OPEN", "Aberto"),
        ("ACKNOWLEDGED", "Reconhecido"),
        ("CLOSED", "Encerrado"),
    ]

    reading = models.OneToOneField(
        MonitoringReading, on_delete=models.PROTECT,
        related_name="alert"
    )
    severity = models.CharField(max_length=10)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="OPEN")
    action_taken = models.TextField(blank=True)
    responsible = models.CharField(max_length=180, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Alerta de monitorização"
        verbose_name_plural = "Alertas de monitorização"

    def __str__(self):
        return f"{self.severity} | {self.reading}"



class ImmutableAuditQuerySet(models.QuerySet):
    """Impede alterações em massa aos registos históricos de auditoria."""

    def update(self, **kwargs):
        raise ValidationError(
            "Os registos de auditoria não podem ser alterados em massa."
        )

    def delete(self):
        raise ValidationError(
            "Os registos de auditoria não podem ser eliminados em massa."
        )

    def bulk_update(self, objs, fields, **kwargs):
        raise ValidationError(
            "A actualização em massa dos registos de auditoria está bloqueada."
        )

    def bulk_create(self, objs, **kwargs):
        raise ValidationError(
            "Os registos de auditoria devem ser criados pelos serviços autorizados."
        )


class CriterionApprovalLog(models.Model):
    objects = models.Manager.from_queryset(ImmutableAuditQuerySet)()

    ACTION_CHOICES = [
        ("SUBMITTED", "Submetido para revisão"),
        ("APPROVED", "Aprovado"),
        ("REJECTED", "Devolvido para correcção"),
        ("RETIRED", "Retirado"),
        ("UPDATED", "Critério actualizado"),
    ]

    criterion = models.ForeignKey(
        MonitoringCriterion,
        on_delete=models.PROTECT,
        related_name="approval_history"
    )
    action = models.CharField(max_length=12, choices=ACTION_CHOICES)
    performed_by = models.ForeignKey(
        "auth.User",
        on_delete=models.PROTECT,
        related_name="entgis_criterion_decisions"
    )
    performed_at = models.DateTimeField(auto_now_add=True)
    justification = models.TextField()
    reference = models.CharField(max_length=180, blank=True)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError(
                "Os registos de auditoria são imutáveis."
            )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Os registos de auditoria não podem ser eliminados."
        )

    class Meta:
        ordering = ["-performed_at"]
        verbose_name = "Registo de aprovação TARP"
        verbose_name_plural = "Registos de aprovação TARP"

    def __str__(self):
        return f"{self.criterion} | {self.get_action_display()}"


# ============================================================
# ENT-GIS — MÓDULO DE COMPLIANCE GISTM
# Catálogo central e avaliação individual por instalação
# ============================================================

class GISTMTopic(models.Model):
    code = models.CharField(max_length=5, unique=True)
    title = models.CharField(max_length=220)
    order = models.PositiveSmallIntegerField(unique=True)

    class Meta:
        ordering = ["order"]
        verbose_name = "Tema GISTM"
        verbose_name_plural = "Temas GISTM"

    def __str__(self):
        return f"{self.code} — {self.title}"


class GISTMPrinciple(models.Model):
    number = models.PositiveSmallIntegerField(unique=True)
    topic = models.ForeignKey(
        GISTMTopic, on_delete=models.PROTECT, related_name="principles"
    )
    title = models.CharField(max_length=500)
    summary = models.TextField(blank=True)

    class Meta:
        ordering = ["number"]
        verbose_name = "Princípio GISTM"
        verbose_name_plural = "Princípios GISTM"

    def __str__(self):
        return f"Princípio {self.number} — {self.title}"


class GISTMRequirement(models.Model):
    code = models.CharField(max_length=12, unique=True)
    principle = models.ForeignKey(
        GISTMPrinciple, on_delete=models.PROTECT, related_name="requirements"
    )
    title = models.CharField(max_length=220)
    summary = models.TextField(blank=True)
    official_text = models.TextField(blank=True)
    source_reference = models.CharField(
        max_length=255, default="GISTM — Agosto de 2020"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["principle__number", "code"]
        verbose_name = "Requisito GISTM"
        verbose_name_plural = "Requisitos GISTM"

    def __str__(self):
        return f"{self.code} — {self.title}"


class GISTMAssessment(models.Model):
    TYPE_CHOICES = [
        ("SELF", "Autoavaliação interna"),
        ("INDEPENDENT", "Validação independente"),
        ("CERTIFICATION", "Auditoria para certificação"),
    ]

    STATUS_CHOICES = [
        ("NOT_STARTED", "Não iniciada"),
        ("IN_PROGRESS", "Em curso"),
        ("UNDER_REVIEW", "Em revisão"),
        ("COMPLETED", "Concluída"),
    ]

    facility = models.ForeignKey(
        TailingsFacility, on_delete=models.PROTECT,
        related_name="gistm_assessments"
    )
    assessment_type = models.CharField(
        max_length=20, choices=TYPE_CHOICES, default="SELF"
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="NOT_STARTED"
    )
    version = models.PositiveIntegerField(default=1)
    assessment_date = models.DateField(null=True, blank=True)
    assessor_name = models.CharField(max_length=180, blank=True)
    assessor_organisation = models.CharField(max_length=180, blank=True)
    reference = models.CharField(max_length=255, blank=True)
    scope = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "auth.User", on_delete=models.PROTECT,
        null=True, blank=True, related_name="gistm_assessments_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["facility", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["facility", "version"],
                name="unique_gistm_assessment_facility_version"
            )
        ]
        verbose_name = "Avaliação GISTM"
        verbose_name_plural = "Avaliações GISTM"

    def __str__(self):
        return f"{self.facility} — GISTM v{self.version}"


class GISTMRequirementAssessment(models.Model):
    STATUS_CHOICES = [
        ("NOT_ASSESSED", "Não avaliado"),
        ("CONFORMANT", "Conforme"),
        ("PARTIAL", "Parcialmente conforme"),
        ("NON_CONFORMANT", "Não conforme"),
        ("UNDER_REVIEW", "Em validação"),
        ("NOT_APPLICABLE", "Não aplicável — justificação obrigatória"),
    ]

    assessment = models.ForeignKey(
        GISTMAssessment, on_delete=models.PROTECT,
        related_name="requirement_results"
    )
    requirement = models.ForeignKey(
        GISTMRequirement, on_delete=models.PROTECT,
        related_name="facility_results"
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="NOT_ASSESSED"
    )
    finding = models.TextField(blank=True)
    evidence_description = models.TextField(blank=True)
    evidence_reference = models.CharField(max_length=255, blank=True)
    not_applicable_justification = models.TextField(blank=True)
    assessed_by = models.ForeignKey(
        "auth.User", on_delete=models.PROTECT,
        null=True, blank=True, related_name="gistm_results_assessed"
    )
    assessed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        "auth.User", on_delete=models.PROTECT,
        null=True, blank=True, related_name="gistm_results_reviewed"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["requirement__principle__number", "requirement__code"]
        constraints = [
            models.UniqueConstraint(
                fields=["assessment", "requirement"],
                name="unique_gistm_requirement_per_assessment"
            )
        ]
        indexes = [
            models.Index(fields=["status"]),
        ]
        verbose_name = "Resultado de requisito GISTM"
        verbose_name_plural = "Resultados dos requisitos GISTM"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.status == "NOT_APPLICABLE" and not self.not_applicable_justification.strip():
            raise ValidationError({
                "not_applicable_justification":
                    "É obrigatória uma justificação para classificar um requisito como não aplicável."
            })

    def __str__(self):
        return f"{self.assessment.facility} — {self.requirement.code}"


class GISTMCorrectiveAction(models.Model):
    STATUS_CHOICES = [
        ("OPEN", "Aberta"),
        ("IN_PROGRESS", "Em execução"),
        ("PENDING_VERIFICATION", "A aguardar verificação"),
        ("CLOSED", "Concluída"),
        ("CANCELLED", "Cancelada com justificação"),
    ]

    result = models.ForeignKey(
        GISTMRequirementAssessment, on_delete=models.PROTECT,
        related_name="corrective_actions"
    )
    description = models.TextField()
    responsible = models.CharField(max_length=180)
    department = models.CharField(max_length=150, blank=True)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default="OPEN")
    completion_evidence = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["due_date", "created_at"]
        verbose_name = "Acção correctiva GISTM"
        verbose_name_plural = "Acções correctivas GISTM"

    def __str__(self):
        return f"{self.result.requirement.code} — {self.responsible}"


class GISTMAuditLog(models.Model):
    objects = models.Manager.from_queryset(ImmutableAuditQuerySet)()

    assessment = models.ForeignKey(
        GISTMAssessment, on_delete=models.PROTECT,
        related_name="audit_logs"
    )
    requirement_result = models.ForeignKey(
        GISTMRequirementAssessment, on_delete=models.PROTECT,
        null=True, blank=True, related_name="audit_logs"
    )
    performed_by = models.ForeignKey(
        "auth.User", on_delete=models.PROTECT,
        null=True, blank=True, related_name="gistm_audit_events"
    )
    action = models.CharField(max_length=80)
    previous_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    justification = models.TextField(blank=True)
    performed_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError(
                "Os registos de auditoria são imutáveis."
            )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Os registos de auditoria não podem ser eliminados."
        )

    class Meta:
        ordering = ["-performed_at"]
        verbose_name = "Registo de auditoria GISTM"
        verbose_name_plural = "Registos de auditoria GISTM"


# Cada nova instalação recebe uma matriz própria após o catálogo
# central de 77 requisitos estar carregado.
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=TailingsFacility)
def create_initial_gistm_assessment(sender, instance, created, **kwargs):
    if not created:
        return

    if GISTMRequirement.objects.filter(is_active=True).count() != 77:
        return

    assessment = GISTMAssessment.objects.create(
        facility=instance,
        assessment_type="SELF",
        status="NOT_STARTED",
        version=1,
        scope="Matriz inicial dos 77 requisitos GISTM."
    )

    GISTMRequirementAssessment.objects.bulk_create([
        GISTMRequirementAssessment(
            assessment=assessment,
            requirement=requirement,
            status="NOT_ASSESSED"
        )
        for requirement in GISTMRequirement.objects.filter(is_active=True)
    ])


# ============================================================
# ENT-GIS — TARP: critérios, modos de falha e respostas
# ============================================================

class TARPCriterion(models.Model):
    STATUS_CHOICES = [
        ("DRAFT", "Rascunho"),
        ("REVIEW", "Em revisão"),
        ("APPROVED", "Aprovado"),
        ("RETIRED", "Retirado"),
    ]

    DIRECTION_CHOICES = [
        ("HIGHER", "Aumenta o risco quando aumenta"),
        ("LOWER", "Aumenta o risco quando diminui"),
    ]

    facility = models.ForeignKey(
        TailingsFacility,
        on_delete=models.PROTECT,
        related_name="tarp_criteria",
    )
    associated_structure = models.ForeignKey(
        AssociatedStructure,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="tarp_criteria",
    )
    parameter = models.ForeignKey(
        MonitoringParameter,
        on_delete=models.PROTECT,
        related_name="tarp_criteria",
    )
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)
    version = models.PositiveIntegerField(default=1)

    level_1 = models.DecimalField(max_digits=16, decimal_places=4)
    level_2 = models.DecimalField(max_digits=16, decimal_places=4)
    level_3 = models.DecimalField(max_digits=16, decimal_places=4)
    level_4 = models.DecimalField(max_digits=16, decimal_places=4)

    status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default="DRAFT"
    )
    effective_from = models.DateField(null=True, blank=True)
    source_document = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="entgis_created_tarp_criteria",
    )
    approved_by = models.ForeignKey(
        "auth.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="entgis_approved_tarp_criteria",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approval_reference = models.CharField(max_length=180, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["facility", "associated_structure", "parameter", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["facility", "parameter", "version"],
                condition=models.Q(associated_structure__isnull=True),
                name="uniq_tarp_facility_parameter_version",
            ),
            models.UniqueConstraint(
                fields=[
                    "facility", "associated_structure", "parameter", "version"
                ],
                condition=models.Q(associated_structure__isnull=False),
                name="uniq_tarp_structure_parameter_version",
            ),
        ]
        permissions = [
            ("approve_tarpcriterion", "Pode aprovar critérios TARP"),
            ("retire_tarpcriterion", "Pode retirar critérios TARP"),
        ]
        verbose_name = "Critério TARP"
        verbose_name_plural = "Critérios TARP"

    def clean(self):
        from django.core.exceptions import ValidationError

        if (
            self.associated_structure_id
            and self.associated_structure.facility_id != self.facility_id
        ):
            raise ValidationError(
                "A estrutura associada tem de pertencer à instalação seleccionada."
            )

        values = [
            self.level_1, self.level_2, self.level_3, self.level_4
        ]
        if self.direction == "HIGHER" and not (
            values[0] <= values[1] <= values[2] <= values[3]
        ):
            raise ValidationError(
                "Para risco crescente com o valor, L1 <= L2 <= L3 <= L4."
            )

        if self.direction == "LOWER" and not (
            values[0] >= values[1] >= values[2] >= values[3]
        ):
            raise ValidationError(
                "Para risco crescente com a diminuição do valor, "
                "L1 >= L2 >= L3 >= L4."
            )

    def __str__(self):
        asset = self.associated_structure or self.facility
        return f"{asset} | {self.parameter} | TARP v{self.version}"


class TARPResponseConfiguration(models.Model):
    LEVEL_CHOICES = [
        ("S1", "S1 — Rotina"),
        ("S2", "S2 — Vigilância reforçada"),
        ("S3", "S3 — Alerta"),
        ("S4", "S4 — Crítico"),
    ]

    facility = models.ForeignKey(
        TailingsFacility, on_delete=models.PROTECT,
        related_name="tarp_responses",
    )
    associated_structure = models.ForeignKey(
        AssociatedStructure, on_delete=models.PROTECT,
        null=True, blank=True,
        related_name="tarp_responses",
    )
    response_level = models.CharField(max_length=2, choices=LEVEL_CHOICES)
    monitoring_frequency = models.CharField(max_length=100)
    required_action = models.TextField()
    responsible_role = models.CharField(max_length=180, blank=True)
    deadline_hours = models.PositiveIntegerField(null=True, blank=True)
    notify_eor = models.BooleanField(default=False)
    activate_pae = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["facility", "response_level"]
        constraints = [
            models.UniqueConstraint(
                fields=["facility", "response_level"],
                condition=models.Q(associated_structure__isnull=True),
                name="uniq_tarp_response_facility_level",
            ),
            models.UniqueConstraint(
                fields=["facility", "associated_structure", "response_level"],
                condition=models.Q(associated_structure__isnull=False),
                name="uniq_tarp_response_structure_level",
            ),
        ]
        verbose_name = "Configuração de resposta TARP"
        verbose_name_plural = "Configurações de resposta TARP"

    def clean(self):
        from django.core.exceptions import ValidationError
        if (
            self.associated_structure_id
            and self.associated_structure.facility_id != self.facility_id
        ):
            raise ValidationError(
                "A estrutura tem de pertencer à instalação seleccionada."
            )

    def __str__(self):
        return f"{self.facility} | {self.response_level}"


class TARPFailureMode(models.Model):
    MODE_CHOICES = [
        ("LIQUEFACTION", "Liquefacção"),
        ("OVERTOPPING", "Galgamento"),
        ("PIPING", "Piping"),
    ]

    facility = models.ForeignKey(
        TailingsFacility, on_delete=models.PROTECT,
        related_name="tarp_failure_modes",
    )
    associated_structure = models.ForeignKey(
        AssociatedStructure, on_delete=models.PROTECT,
        null=True, blank=True,
        related_name="tarp_failure_modes",
    )
    mode = models.CharField(max_length=20, choices=MODE_CHOICES)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["facility", "mode"],
                condition=models.Q(associated_structure__isnull=True),
                name="uniq_tarp_failure_facility_mode",
            ),
            models.UniqueConstraint(
                fields=["facility", "associated_structure", "mode"],
                condition=models.Q(associated_structure__isnull=False),
                name="uniq_tarp_failure_structure_mode",
            ),
        ]
        verbose_name = "Modo de falha TARP"
        verbose_name_plural = "Modos de falha TARP"

    def clean(self):
        from django.core.exceptions import ValidationError
        if (
            self.associated_structure_id
            and self.associated_structure.facility_id != self.facility_id
        ):
            raise ValidationError(
                "A estrutura tem de pertencer à instalação seleccionada."
            )

    def __str__(self):
        return f"{self.facility} | {self.get_mode_display()}"


class TARPFailureModeIndicator(models.Model):
    DIRECTION_CHOICES = [
        ("HIGHER", "Aumenta o risco quando aumenta"),
        ("LOWER", "Aumenta o risco quando diminui"),
    ]

    failure_mode = models.ForeignKey(
        TARPFailureMode, on_delete=models.PROTECT,
        related_name="indicators",
    )
    parameter = models.ForeignKey(
        MonitoringParameter, on_delete=models.PROTECT,
        related_name="tarp_failure_indicators",
    )
    weight = models.DecimalField(max_digits=5, decimal_places=4)
    critical_limit = models.DecimalField(max_digits=16, decimal_places=4)
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["failure_mode", "parameter"],
                name="uniq_tarp_failure_indicator",
            )
        ]
        verbose_name = "Indicador de modo de falha"
        verbose_name_plural = "Indicadores de modos de falha"

    def __str__(self):
        return f"{self.failure_mode} | {self.parameter}"


class TARPFoSAssessment(models.Model):
    CLASSIFICATION_CHOICES = [
        ("SAFE", "SAFE — Seguro"),
        ("ADEQUATE", "ADEQUATE — Adequado"),
        ("ATTENTION", "ATTENTION — Atenção"),
        ("CRITICAL", "CRITICAL — Crítico"),
    ]

    facility = models.ForeignKey(
        TailingsFacility, on_delete=models.PROTECT,
        related_name="tarp_fos_assessments",
    )
    associated_structure = models.ForeignKey(
        AssociatedStructure, on_delete=models.PROTECT,
        null=True, blank=True,
        related_name="fos_assessments",
    )
    assessed_at = models.DateTimeField()
    factor_of_safety = models.DecimalField(max_digits=8, decimal_places=4)
    classification = models.CharField(
        max_length=12, choices=CLASSIFICATION_CHOICES, editable=False
    )
    analysis_reference = models.CharField(max_length=255)
    failure_mechanism = models.CharField(max_length=180, blank=True)
    assessed_by = models.ForeignKey(
        "auth.User", on_delete=models.PROTECT,
        related_name="entgis_fos_assessments",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-assessed_at"]
        verbose_name = "Avaliação do Factor de Segurança"
        verbose_name_plural = "Avaliações do Factor de Segurança"

    def save(self, *args, **kwargs):
        value = self.factor_of_safety
        if value >= 3:
            self.classification = "SAFE"
        elif value >= 2:
            self.classification = "ADEQUATE"
        elif value >= 1.5:
            self.classification = "ATTENTION"
        else:
            self.classification = "CRITICAL"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.facility} | FoS {self.factor_of_safety}"


class TARPEvent(models.Model):
    STATUS_CHOICES = [
        ("OPEN", "Aberto"),
        ("ACKNOWLEDGED", "Reconhecido"),
        ("CLOSED", "Encerrado"),
    ]
    RESPONSE_CHOICES = [
        ("S1", "S1 — Rotina"),
        ("S2", "S2 — Vigilância reforçada"),
        ("S3", "S3 — Alerta"),
        ("S4", "S4 — Crítico"),
    ]
    TRIGGER_CHOICES = [
        ("L1", "L1 — Referência"),
        ("L2", "L2 — Atenção"),
        ("L3", "L3 — Alerta elevado"),
        ("L4", "L4 — Alerta máximo"),
    ]

    facility = models.ForeignKey(
        TailingsFacility, on_delete=models.PROTECT,
        related_name="tarp_events",
    )
    associated_structure = models.ForeignKey(
        AssociatedStructure, on_delete=models.PROTECT,
        null=True, blank=True,
        related_name="tarp_events",
    )
    reading = models.ForeignKey(
        MonitoringReading, on_delete=models.PROTECT,
        null=True, blank=True,
        related_name="tarp_events",
    )
    criterion = models.ForeignKey(
        TARPCriterion, on_delete=models.PROTECT,
        null=True, blank=True,
        related_name="events",
    )
    trigger_level = models.CharField(
        max_length=2,
        choices=TRIGGER_CHOICES,
        null=True,
        blank=True,
        verbose_name="Nível de alerta da monitorização",
    )
    response_level = models.CharField(
        max_length=2,
        choices=RESPONSE_CHOICES,
        null=True,
        blank=True,
        verbose_name="Nível de resposta operacional",
    )
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="OPEN")
    trigger_description = models.TextField()
    action_taken = models.TextField(blank=True)
    responsible = models.CharField(max_length=180, blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    pae_activated = models.BooleanField(default=False)
    opened_at = models.DateTimeField(auto_now_add=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-opened_at"]
        verbose_name = "Evento TARP"
        verbose_name_plural = "Eventos TARP"
        constraints = [
            models.UniqueConstraint(
                fields=["reading"],
                condition=models.Q(reading__isnull=False),
                name="uniq_tarp_event_per_reading",
            ),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        if (
            self.associated_structure_id
            and self.associated_structure.facility_id != self.facility_id
        ):
            raise ValidationError(
                "A estrutura do evento tem de pertencer à instalação."
            )

        if self.criterion_id and self.criterion.facility_id != self.facility_id:
            raise ValidationError(
                "O critério TARP pertence a outra instalação."
            )

        if self.reading_id:
            if self.reading.facility_id != self.facility_id:
                raise ValidationError("A leitura pertence a outra instalação.")

            if self.reading.associated_structure_id != self.associated_structure_id:
                raise ValidationError("A leitura pertence a outra estrutura.")

            if not self.criterion_id:
                raise ValidationError(
                    "Um evento originado por leitura exige um critério TARP."
                )

            criterion = self.criterion

            if criterion.parameter_id != self.reading.parameter_id:
                raise ValidationError(
                    "O critério TARP não corresponde à variável da leitura."
                )

            if criterion.associated_structure_id != self.reading.associated_structure_id:
                raise ValidationError(
                    "O critério TARP não corresponde à estrutura da leitura."
                )

            if criterion.status != "APPROVED":
                raise ValidationError(
                    "O critério associado ao evento tem de estar aprovado."
                )

            if (
                not criterion.effective_from
                or criterion.effective_from > self.reading.observed_at.date()
            ):
                raise ValidationError(
                    "O critério TARP não estava vigente na data da leitura."
                )

    def __str__(self):
        return f"{self.facility} | {self.response_level} | {self.opened_at}"


class TARPEventLog(models.Model):
    objects = models.Manager.from_queryset(ImmutableAuditQuerySet)()

    event = models.ForeignKey(
        TARPEvent, on_delete=models.PROTECT, related_name="history"
    )
    action = models.CharField(max_length=40)
    performed_by = models.ForeignKey(
        "auth.User", on_delete=models.PROTECT,
        related_name="entgis_tarp_event_actions",
    )
    performed_at = models.DateTimeField(auto_now_add=True)
    details = models.TextField()

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError(
                "Os registos de auditoria são imutáveis."
            )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Os registos de auditoria não podem ser eliminados."
        )

    class Meta:
        ordering = ["-performed_at"]
        verbose_name = "Histórico de evento TARP"
        verbose_name_plural = "Histórico de eventos TARP"

    def __str__(self):
        return f"{self.event} | {self.action}"




# ============================================================
# ENT-GIS — HISTÓRICO DE APROVAÇÃO DOS CRITÉRIOS TARP
# ============================================================

class TARPCriterionApprovalLog(models.Model):
    objects = models.Manager.from_queryset(ImmutableAuditQuerySet)()

    ACTION_CHOICES = [
        ("SUBMITTED", "Submetido para revisão"),
        ("APPROVED", "Aprovado"),
        ("REJECTED", "Rejeitado"),
        ("RETIRED", "Retirado"),
    ]

    criterion = models.ForeignKey(
        TARPCriterion,
        on_delete=models.PROTECT,
        related_name="approval_history",
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    performed_by = models.ForeignKey(
        "auth.User",
        on_delete=models.PROTECT,
        related_name="entgis_tarp_criterion_actions",
    )
    performed_at = models.DateTimeField(auto_now_add=True)
    justification = models.TextField()
    reference = models.CharField(max_length=180, blank=True)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError(
                "Os registos de auditoria são imutáveis."
            )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Os registos de auditoria não podem ser eliminados."
        )

    class Meta:
        ordering = ["-performed_at"]
        verbose_name = "Histórico de aprovação de critério TARP"
        verbose_name_plural = "Histórico de aprovações de critérios TARP"

    def __str__(self):
        return f"{self.criterion} | {self.action} | {self.performed_at}"


class MiningCompanyUser(models.Model):
    ROLE_CHOICES = [
        ("COMPANY_ADMIN", "Administrador da empresa"),
        ("COMPANY_EDITOR", "Técnico da empresa"),
        ("COMPANY_VIEWER", "Consulta"),
    ]

    company = models.ForeignKey(
        MiningCompany,
        on_delete=models.PROTECT,
        related_name="user_memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="mining_company_memberships",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "user"],
                name="unique_mining_company_user",
            )
        ]
        verbose_name = "Acesso de utilizador à empresa"
        verbose_name_plural = "Acessos de utilizadores às empresas"

    def __str__(self):
        return f"{self.user} | {self.company} | {self.role}"


class LifecycleSubmissionQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError(
            "Alterações em massa de processos não são permitidas. "
            "Utilize o fluxo controlado do ENT-GIS."
        )

    def delete(self):
        raise ValidationError(
            "Eliminação em massa de processos não é permitida."
        )


class LifecycleSubmissionLogQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError(
            "O histórico de auditoria não pode ser alterado em massa."
        )

    def delete(self):
        raise ValidationError(
            "O histórico de auditoria não pode ser eliminado em massa."
        )


class LifecycleSubmission(models.Model):

    objects = models.Manager.from_queryset(LifecycleSubmissionQuerySet
    )()

    STATUS_CHOICES = [
        ("DRAFT", "Rascunho"),
        ("SUBMITTED", "Submetido"),
        ("UNDER_REVIEW", "Em análise"),
        ("APPROVED", "Aprovado"),
        ("REJECTED", "Rejeitado"),
        ("CHANGES_REQUESTED", "Correcções solicitadas"),
    ]

    facility = models.ForeignKey(
        TailingsFacility,
        on_delete=models.PROTECT,
        related_name="lifecycle_submissions",
    )
    lifecycle_stage = models.CharField(
        max_length=20,
        choices=TailingsFacility.LIFECYCLE_CHOICES,
    )
    revision = models.PositiveIntegerField(default=1)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="DRAFT",
        db_index=True,
    )

    # Dados específicos da fase, validados pelos formulários do ENT-GIS.
    phase_data = models.JSONField(default=dict, blank=True)

    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="lifecycle_submissions_created",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="lifecycle_submissions_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["facility", "lifecycle_stage", "-revision"]
        constraints = [
            models.UniqueConstraint(
                fields=["facility", "lifecycle_stage", "revision"],
                name="unique_facility_stage_revision",
            )
        ]
        verbose_name = "Processo da fase do ciclo de vida"
        verbose_name_plural = "Processos das fases do ciclo de vida"


    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Os processos do ciclo de vida não podem ser eliminados."
        )

    # SUBMISSION_IMMUTABILITY_GUARD
    def save(self, *args, **kwargs):
        if self.pk:
            original = type(self).objects.get(pk=self.pk)

            if original.status != "DRAFT":
                protected_fields = (
                    "facility_id",
                    "lifecycle_stage",
                    "revision",
                    "phase_data",
                    "submitted_by_id",
                    "submitted_at",
                    "created_at",
                )

                changed_fields = [
                    field for field in protected_fields
                    if getattr(original, field) != getattr(self, field)
                ]

                if changed_fields:
                    raise ValidationError(
                        "Os dados de uma submissão já enviada não podem "
                        "ser alterados. Utilize uma nova revisão."
                    )

        return super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.facility.name} | "
            f"{self.get_lifecycle_stage_display()} | "
            f"Rev. {self.revision}"
        )


class LifecycleDocumentQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError(
            "Alterações em massa de documentos não são permitidas."
        )

    def delete(self):
        raise ValidationError(
            "A eliminação em massa de documentos não é permitida."
        )

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError(
            "A actualização em massa de documentos não é permitida."
        )

    def bulk_create(self, objs, **kwargs):
        objs = list(objs)

        if not objs:
            return []

        submission_ids = {obj.submission_id for obj in objs}

        if None in submission_ids:
            raise ValidationError(
                "Todos os documentos devem estar associados a um processo."
            )

        valid_submissions = LifecycleSubmission.objects.filter(
            pk__in=submission_ids,
            status="DRAFT",
        ).count()

        if valid_submissions != len(submission_ids):
            raise ValidationError(
                "Só é permitido criar documentos em processos em rascunho."
            )

        return super().bulk_create(objs, **kwargs)


class LifecycleDocument(models.Model):
    objects = models.Manager.from_queryset(LifecycleDocumentQuerySet)()

    submission = models.ForeignKey(
        LifecycleSubmission,
        on_delete=models.PROTECT,
        related_name="documents",
    )
    title = models.CharField(max_length=200)
    document_type = models.CharField(max_length=100)
    file = models.FileField(upload_to="entgis/lifecycle_documents/%Y/%m/")
    reference = models.CharField(max_length=100, blank=True)
    document_date = models.DateField(null=True, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    is_simulated = models.BooleanField(default=True)

    class Meta:
        ordering = ["-uploaded_at"]
        verbose_name = "Documento do processo"
        verbose_name_plural = "Documentos dos processos"

    # DOCUMENT_IMMUTABILITY_GUARD
    def save(self, *args, **kwargs):
        if self.pk:
            original = type(self).objects.select_related("submission").get(pk=self.pk)

            if original.submission_id != self.submission_id:
                raise ValidationError(
                    "Um documento não pode ser transferido para outra revisão."
                )

            if original.submission.status != "DRAFT":
                raise ValidationError(
                    "Documentos de processos submetidos não podem ser alterados."
                )

            if not self.file._committed or self.file.name != original.file.name:
                raise ValidationError(
                    "O ficheiro original não pode ser substituído."
                )
        elif self.submission.status != "DRAFT":
            raise ValidationError(
                "Só é permitido anexar documentos a processos em rascunho."
            )

        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.submission.status != "DRAFT":
            raise ValidationError(
                "Documentos de processos submetidos não podem ser eliminados."
            )
        return super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.title} | {self.submission}"



class LifecycleSubmissionLog(models.Model):
    objects = models.Manager.from_queryset(LifecycleSubmissionLogQuerySet
    )()

    ACTION_CHOICES = [
        ("DRAFT_SAVED", "Rascunho guardado"),
        ("DOCUMENT_UPLOADED", "Documento anexado ao processo"),
        ("SUBMITTED", "Processo submetido"),
        ("REVIEW_STARTED", "Análise iniciada"),
        ("APPROVED", "Processo aprovado"),
        ("REJECTED", "Processo rejeitado"),
        ("CHANGES_REQUESTED", "Correcções solicitadas"),
    ]

    submission = models.ForeignKey(
        LifecycleSubmission,
        on_delete=models.PROTECT,
        related_name="decision_history",
    )
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    previous_status = models.CharField(max_length=30)
    new_status = models.CharField(max_length=30)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
    )
    justification = models.TextField()
    performed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-performed_at"]
        verbose_name = "Histórico de decisão do processo"
        verbose_name_plural = "Histórico de decisões dos processos"


    # SUBMISSION_LOG_IMMUTABILITY_GUARD
    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError(
                "Os eventos do histórico não podem ser alterados."
            )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Os eventos do histórico não podem ser eliminados."
        )

    def __str__(self):
        return (
            f"{self.submission} | {self.get_action_display()} | "
            f"{self.performed_at}"
        )


# ============================================================
# ENT-GIS — HISTÓRICO AUDITÁVEL DOS ALERTAS DE MONITORIZAÇÃO
# ============================================================

class MonitoringAlertLog(models.Model):
    objects = models.Manager.from_queryset(ImmutableAuditQuerySet)()

    ACTION_CHOICES = [
        ("CREATED", "Alerta criado"),
        ("ACKNOWLEDGED", "Alerta reconhecido"),
        ("ASSIGNED", "Responsável atribuído ou alterado"),
        ("ACTION_RECORDED", "Intervenção registada"),
        ("CLOSED", "Alerta encerrado"),
    ]

    alert = models.ForeignKey(
        MonitoringAlert,
        on_delete=models.PROTECT,
        related_name="audit_history",
    )
    action = models.CharField(max_length=24, choices=ACTION_CHOICES)
    status_before = models.CharField(max_length=15, blank=True)
    status_after = models.CharField(max_length=15, blank=True)
    responsible_before = models.CharField(max_length=180, blank=True)
    responsible_after = models.CharField(max_length=180, blank=True)
    performed_by = models.ForeignKey(
        "auth.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="entgis_monitoring_alert_actions",
    )
    performed_at = models.DateTimeField(auto_now_add=True)
    details = models.TextField()

    class Meta:
        ordering = ["-performed_at", "-pk"]
        verbose_name = "Histórico de alerta de monitorização"
        verbose_name_plural = "Históricos de alertas de monitorização"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError(
                "Os registos de auditoria dos alertas são imutáveis."
            )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Os registos de auditoria dos alertas não podem ser eliminados."
        )

    def __str__(self):
        return f"Alerta {self.alert_id} | {self.get_action_display()}"
