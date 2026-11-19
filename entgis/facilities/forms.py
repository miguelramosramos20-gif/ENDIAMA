from django import forms
from facilities.models import (
    MonitoringParameter,
    MonitoringReading,
    TailingsFacility,
    AssociatedStructure,
)


class MonitoringReadingForm(forms.ModelForm):
    class Meta:
        model = MonitoringReading
        fields = [
            "facility",
            "associated_structure",
            "parameter",
            "observed_at",
            "value",
            "instrument_code",
            "notes",
        ]
        widgets = {
            "observed_at": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "form-control"},
                format="%Y-%m-%dT%H:%M",
            ),
            "value": forms.NumberInput(
                attrs={"class": "form-control", "step": "any"}
            ),
            "instrument_code": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "notes": forms.Textarea(
                attrs={"class": "form-control", "rows": 3}
            ),
            "facility": forms.Select(attrs={"class": "form-control"}),
            "associated_structure": forms.Select(
                attrs={"class": "form-control"}
            ),
            "parameter": forms.Select(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        allowed_facilities = kwargs.pop("allowed_facilities", None)
        super().__init__(*args, **kwargs)

        if allowed_facilities is None:
            self.fields["facility"].queryset = (
                TailingsFacility.objects.order_by("name")
            )
            structures = AssociatedStructure.objects.all()
        else:
            self.fields["facility"].queryset = allowed_facilities
            structures = AssociatedStructure.objects.filter(
                facility__in=allowed_facilities
            )

        self.fields["facility"].queryset = (
            self.fields["facility"].queryset.order_by("name")
        )

        self.fields["parameter"].queryset = (
            MonitoringParameter.objects.filter(is_active=True)
            .order_by("category", "name")
        )

        self.fields["associated_structure"].required = False
        self.fields["associated_structure"].queryset = (
            structures.order_by("facility__name", "name")
        )

        facility_id = None

        if self.is_bound:
            facility_id = self.data.get("facility")
        elif self.instance and self.instance.facility_id:
            facility_id = self.instance.facility_id
        elif self.initial.get("facility"):
            facility_id = self.initial.get("facility")

        if facility_id:
            try:
                self.fields["associated_structure"].queryset = (
                    self.fields["associated_structure"].queryset.filter(
                        facility_id=int(facility_id)
                    ).order_by("name")
                )
            except (TypeError, ValueError):
                self.fields["associated_structure"].queryset = (
                    AssociatedStructure.objects.none()
                )

    def clean(self):
        cleaned = super().clean()
        parameter = cleaned.get("parameter")
        instrument = cleaned.get("instrument_code")
        facility = cleaned.get("facility")
        structure = cleaned.get("associated_structure")

        if parameter and parameter.instrument_required and not instrument:
            self.add_error(
                "instrument_code",
                "Esta variável exige a identificação do instrumento."
            )

        if structure and facility and structure.facility_id != facility.pk:
            self.add_error(
                "associated_structure",
                "A estrutura seleccionada não pertence à instalação indicada."
            )

        return cleaned


from django import forms as django_forms
from facilities.models import MonitoringCriterion


class MonitoringCriterionForm(django_forms.ModelForm):

    class Meta:
        model = MonitoringCriterion
        fields = [
            "facility",
            "parameter",
            "version",
            "effective_from",
            "green_min",
            "green_max",
            "yellow_min",
            "yellow_max",
            "orange_min",
            "orange_max",
            "red_min",
            "red_max",
            "source_document",
            "notes",
        ]

        widgets = {
            "effective_from": django_forms.DateInput(
                attrs={"type": "date"}
            ),
            "notes": django_forms.Textarea(
                attrs={"rows": 3}
            ),
        }

    def clean(self):
        cleaned_data = super().clean()

        levels = [
            ("GREEN", "green_min", "green_max"),
            ("YELLOW", "yellow_min", "yellow_max"),
            ("ORANGE", "orange_min", "orange_max"),
            ("RED", "red_min", "red_max"),
        ]

        intervals = []

        for name, min_field, max_field in levels:
            low = cleaned_data.get(min_field)
            high = cleaned_data.get(max_field)

            if low is not None and high is not None and low > high:
                self.add_error(
                    max_field,
                    f"O limite máximo de {name} deve ser superior ou igual ao mínimo."
                )
                continue

            if low is not None or high is not None:
                intervals.append((name, low, high))

        for index, first in enumerate(intervals):
            for second in intervals[index + 1:]:
                name_a, low_a, high_a = first
                name_b, low_b, high_b = second

                lower_a = low_a if low_a is not None else float("-inf")
                upper_a = high_a if high_a is not None else float("inf")
                lower_b = low_b if low_b is not None else float("-inf")
                upper_b = high_b if high_b is not None else float("inf")

                if lower_a <= upper_b and lower_b <= upper_a:
                    raise django_forms.ValidationError(
                        f"Os intervalos {name_a} e {name_b} sobrepõem-se. "
                        "Revise os limites antes de guardar."
                    )

        return cleaned_data

    def save(self, commit=True):
        criterion = super().save(commit=False)

        criterion.status = "DRAFT"
        criterion.approved_by = ""
        criterion.approved_at = None

        if commit:
            criterion.save()
            self.save_m2m()

        return criterion


# ============================================================
# ENT-GIS — FORMULÁRIOS ESPECÍFICOS DO CICLO DE VIDA
# ============================================================

class LifecyclePhaseForm(forms.Form):
    """
    Base dos formulários de cada fase.
    Os campos não aplicáveis às outras fases não são apresentados.
    """

    def clean(self):
        cleaned = super().clean()

        if not any(
            value not in (None, "", [], {})
            for value in cleaned.values()
        ):
            raise forms.ValidationError(
                "Introduza pelo menos uma informação do processo."
            )

        return cleaned


class ProjectPhaseForm(LifecyclePhaseForm):
    design_basis = forms.CharField(
        label="Critérios e bases de projecto",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    design_report_ref = forms.CharField(
        label="Referência do relatório de projecto",
        required=False,
    )
    design_engineer = forms.CharField(
        label="Responsável técnico pelo projecto",
        required=False,
    )
    consequence_assessment = forms.CharField(
        label="Avaliação da classe de consequência",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    environmental_study_ref = forms.CharField(
        label="Referência do estudo ambiental",
        required=False,
    )
    approvals = forms.CharField(
        label="Licenças e aprovações aplicáveis",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )


class ConstructionPhaseForm(LifecyclePhaseForm):
    construction_method = forms.CharField(
        label="Método de construção",
        required=False,
    )
    design_revision = forms.CharField(
        label="Revisão do projecto de execução",
        required=False,
    )
    quality_control_summary = forms.CharField(
        label="Controlo e garantia da qualidade",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    material_testing_summary = forms.CharField(
        label="Ensaios e caracterização dos materiais",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    inspections = forms.CharField(
        label="Inspecções e registos de construção",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    construction_reports = forms.CharField(
        label="Relatórios de progresso da construção",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )


class OperationPhaseForm(LifecyclePhaseForm):
    commissioning_date = forms.DateField(
        label="Data de entrada em operação",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    operating_manual_ref = forms.CharField(
        label="Referência do manual de operação",
        required=False,
    )
    monitoring_plan_ref = forms.CharField(
        label="Referência do plano de monitorização",
        required=False,
    )
    emergency_response_plan_ref = forms.CharField(
        label="Referência do plano de acção de emergência",
        required=False,
    )
    current_operation_summary = forms.CharField(
        label="Descrição do estado actual da operação",
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
    )


class ClosurePhaseForm(LifecyclePhaseForm):
    closure_plan_ref = forms.CharField(
        label="Referência do plano de fechamento",
        required=False,
    )
    closure_design_ref = forms.CharField(
        label="Referência do projecto de fechamento",
        required=False,
    )
    works_progress = forms.CharField(
        label="Progresso dos trabalhos de fechamento",
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
    )
    stability_assessment_ref = forms.CharField(
        label="Referência da avaliação de estabilidade",
        required=False,
    )
    monitoring_plan_ref = forms.CharField(
        label="Plano de monitorização durante o fechamento",
        required=False,
    )


class PostClosurePhaseForm(LifecyclePhaseForm):
    post_closure_plan_ref = forms.CharField(
        label="Referência do plano de pós-fechamento",
        required=False,
    )
    inspection_frequency = forms.CharField(
        label="Frequência das inspecções",
        required=False,
    )
    maintenance_program = forms.CharField(
        label="Programa de manutenção",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    long_term_monitoring_ref = forms.CharField(
        label="Referência da monitorização de longo prazo",
        required=False,
    )
    residual_risk_summary = forms.CharField(
        label="Avaliação dos riscos residuais",
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
    )


LIFECYCLE_PHASE_FORMS = {
    "PROJECT": ProjectPhaseForm,
    "CONSTRUCTION": ConstructionPhaseForm,
    "OPERATION": OperationPhaseForm,
    "CLOSURE": ClosurePhaseForm,
    "POST_CLOSURE": PostClosurePhaseForm,
}


def get_lifecycle_phase_form(stage):
    """
    Devolve exclusivamente o formulário correspondente à fase indicada.
    """
    form_class = LIFECYCLE_PHASE_FORMS.get(stage)

    if form_class is None:
        raise ValueError("Fase do ciclo de vida não reconhecida.")

    return form_class


# ============================================================
# ENT-GIS — DOCUMENTOS DOS PROCESSOS DO CICLO DE VIDA
# ============================================================

import os
import zipfile
from facilities.models import LifecycleDocument


class LifecycleDocumentForm(forms.ModelForm):
    MAX_SIZE = 20 * 1024 * 1024
    ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".jpg", ".jpeg", ".png"}

    class Meta:
        model = LifecycleDocument
        fields = ["title", "document_type", "reference", "document_date", "file"]
        widgets = {
            "document_date": forms.DateInput(attrs={"type": "date"}),
        }

    def clean_file(self):
        uploaded = self.cleaned_data.get("file")
        if not uploaded:
            raise forms.ValidationError("Seleccione um documento.")

        extension = os.path.splitext(uploaded.name)[1].lower()
        if extension not in self.ALLOWED_EXTENSIONS:
            raise forms.ValidationError(
                "Formato não permitido. Utilize PDF, DOCX, XLSX, JPG ou PNG."
            )

        if uploaded.size > self.MAX_SIZE:
            raise forms.ValidationError("O ficheiro não pode exceder 20 MB.")

        header = uploaded.read(8)
        uploaded.seek(0)

        if extension == ".pdf" and not header.startswith(b"%PDF-"):
            raise forms.ValidationError("O conteúdo não corresponde a um PDF válido.")

        if extension in (".jpg", ".jpeg") and not header.startswith(b"\xff\xd8\xff"):
            raise forms.ValidationError("O conteúdo não corresponde a uma imagem JPEG.")

        if extension == ".png" and not header.startswith(b"\x89PNG\r\n\x1a\n"):
            raise forms.ValidationError("O conteúdo não corresponde a uma imagem PNG.")

        if extension in (".docx", ".xlsx"):
            try:
                with zipfile.ZipFile(uploaded) as archive:
                    names = archive.namelist()
                    required = (
                        "word/document.xml"
                        if extension == ".docx"
                        else "xl/workbook.xml"
                    )
                    if required not in names:
                        raise forms.ValidationError(
                            "O ficheiro não corresponde ao formato Office indicado."
                        )
            except (zipfile.BadZipFile, OSError):
                raise forms.ValidationError("O documento Office está inválido.")
            finally:
                uploaded.seek(0)

        return uploaded
