from decimal import Decimal
from datetime import timedelta
import os
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from django.urls import reverse

from facilities.models import (
    MiningCompany,
    MiningCompanyUser,
    TailingsFacility,
    LifecycleSubmission,
    LifecycleDocument,
    LifecycleSubmissionLog,
    FacilityLifecycleHistory,
    MonitoringParameter,
    MonitoringCriterion,
    MonitoringAlert,
    MonitoringAlertLog,
    MonitoringReading,
    CriterionApprovalLog,
    GISTMAssessment,
    GISTMAuditLog,
    TARPEvent,
    TARPEventLog,
    TARPCriterion,
    TARPCriterionApprovalLog,
)
from facilities.services.lifecycle import change_lifecycle_stage
from facilities.services.monitoring import (
    interpret_reading,
    create_monitoring_alert,
)
from facilities.services.monitoring_alerts import (
    acknowledge_monitoring_alert,
    assign_monitoring_alert,
    record_monitoring_alert_action,
    close_monitoring_alert,
)
from facilities.services.tarp import interpret_tarp_reading


User = get_user_model()


class LifecycleTestBase(TestCase):
    def setUp(self):
        self.media_dir = tempfile.mkdtemp(prefix="entgis-tests-")
        self.media_override = override_settings(MEDIA_ROOT=self.media_dir)
        self.media_override.enable()

        self.company = MiningCompany.objects.create(
            name="Empresa de Teste ENT-GIS",
            country="Angola",
            province="Lunda Sul",
            is_simulated=True,
        )

        self.facility = TailingsFacility.objects.create(
            company=self.company,
            name="Instalação de Teste",
            province="Lunda Sul",
            municipality="Saurimo",
            lifecycle_stage="CONSTRUCTION",
            is_simulated=True,
        )

        self.editor = User.objects.create_user(
            username="empresa_editor",
            password="TesteSeguro123!",
        )

        self.viewer = User.objects.create_user(
            username="empresa_viewer",
            password="TesteSeguro123!",
        )

        self.staff = User.objects.create_user(
            username="endiama_staff",
            password="TesteSeguro123!",
            is_staff=True,
        )

        MiningCompanyUser.objects.create(
            company=self.company,
            user=self.editor,
            role="COMPANY_EDITOR",
            is_active=True,
        )

        MiningCompanyUser.objects.create(
            company=self.company,
            user=self.viewer,
            role="COMPANY_VIEWER",
            is_active=True,
        )

    def tearDown(self):
        self.media_override.disable()
        shutil.rmtree(self.media_dir, ignore_errors=True)
        super().tearDown()

    def create_submission(self, status="DRAFT", stage="CONSTRUCTION"):
        return LifecycleSubmission.objects.create(
            facility=self.facility,
            lifecycle_stage=stage,
            revision=1,
            status=status,
            phase_data={"construction_method": "Aterro de jusante"},
        )

    def valid_pdf(self):
        return SimpleUploadedFile(
            "relatorio_teste.pdf",
            b"%PDF-1.4\nDocumento de teste ENT-GIS\n%%EOF",
            content_type="application/pdf",
        )


class MonitoringEntryAuthorizationTests(LifecycleTestBase):

    def setUp(self):
        super().setUp()
        self.url = reverse("facilities:monitoring_entry")

        self.parameter = MonitoringParameter.objects.create(
            code="HTTP-MON-TEST",
            name="Variável HTTP de teste",
            category="GEOTECHNICAL",
            unit="mm",
            instrument_required=False,
            is_active=True,
        )

    def payload(self, facility=None):
        return {
            "facility": (facility or self.facility).pk,
            "associated_structure": "",
            "parameter": self.parameter.pk,
            "observed_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
            "value": "3.5",
            "instrument_code": "",
            "notes": "Teste HTTP de autorização",
        }

    def test_utilizador_nao_autenticado_e_redireccionado(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_editor_acede_ao_formulario_da_sua_empresa(self):
        self.client.force_login(self.editor)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Instalação de Teste")

    def test_viewer_nao_pode_aceder_ao_registo(self):
        self.client.force_login(self.viewer)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_utilizador_sem_associacao_nao_pode_registar(self):
        outsider = User.objects.create_user(
            username="utilizador_sem_empresa",
            password="TesteSeguro123!",
        )
        self.client.force_login(outsider)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_editor_nao_pode_submeter_instalacao_de_outra_empresa(self):
        other_company = MiningCompany.objects.create(
            name="Outra Empresa de Teste",
            country="Angola",
            province="Lunda Sul",
            is_simulated=True,
        )
        other_facility = TailingsFacility.objects.create(
            company=other_company,
            name="Instalação Não Autorizada",
            province="Lunda Sul",
            municipality="Saurimo",
            lifecycle_stage="CONSTRUCTION",
            is_simulated=True,
        )

        self.client.force_login(self.editor)

        response = self.client.post(
            self.url,
            self.payload(other_facility),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(MonitoringReading.objects.count(), 0)

    def test_editor_regista_leitura_na_sua_instalacao(self):
        self.client.force_login(self.editor)

        response = self.client.post(
            self.url,
            self.payload(),
        )

        self.assertEqual(response.status_code, 302)

        reading = MonitoringReading.objects.get()

        self.assertEqual(reading.facility, self.facility)
        self.assertEqual(reading.parameter, self.parameter)
        self.assertEqual(reading.entered_by, self.editor)
        self.assertEqual(reading.unit, self.parameter.unit)
        self.assertEqual(reading.interpretation, "NOT_CONFIGURED")

    def test_staff_endiama_pode_registar_em_qualquer_instalacao(self):
        self.client.force_login(self.staff)

        response = self.client.post(
            self.url,
            self.payload(),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(MonitoringReading.objects.count(), 1)
        self.assertEqual(
            MonitoringReading.objects.get().entered_by,
            self.staff,
        )


class MonitoringReadViewsAuthorizationTests(LifecycleTestBase):

    def setUp(self):
        super().setUp()

        self.dashboard_url = reverse("facilities:monitoring_dashboard")
        self.history_url = reverse("facilities:monitoring_history")

        self.parameter = MonitoringParameter.objects.create(
            code="READ-VIEW-TEST",
            name="Variável de isolamento",
            category="GEOTECHNICAL",
            unit="mm",
            instrument_required=False,
            is_active=True,
        )

        self.other_company = MiningCompany.objects.create(
            name="Empresa Externa de Teste",
            country="Angola",
            province="Lunda Sul",
            is_simulated=True,
        )

        self.other_facility = TailingsFacility.objects.create(
            company=self.other_company,
            name="Instalação Externa de Teste",
            province="Lunda Sul",
            municipality="Saurimo",
            lifecycle_stage="CONSTRUCTION",
            is_simulated=True,
        )

        self.own_reading = MonitoringReading.objects.create(
            facility=self.facility,
            parameter=self.parameter,
            observed_at=timezone.now(),
            value=Decimal("12.0"),
            unit="mm",
            interpretation="ORANGE",
            entered_by=self.staff,
        )

        self.other_reading = MonitoringReading.objects.create(
            facility=self.other_facility,
            parameter=self.parameter,
            observed_at=timezone.now(),
            value=Decimal("25.0"),
            unit="mm",
            interpretation="RED",
            entered_by=self.staff,
        )

        MonitoringAlert.objects.create(
            reading=self.own_reading,
            severity="ORANGE",
        )

        MonitoringAlert.objects.create(
            reading=self.other_reading,
            severity="RED",
        )

    def test_editor_so_consulta_leituras_da_sua_empresa_no_dashboard(self):
        self.client.force_login(self.editor)
        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_readings"], 1)

        readings = list(response.context["latest_readings"])
        self.assertEqual(len(readings), 1)
        self.assertEqual(readings[0].facility, self.facility)

    def test_dashboard_isola_alertas_por_empresa(self):
        self.client.force_login(self.editor)
        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["open_alerts"], 1)

        alerts = list(response.context["open_alert_list"])
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].reading.facility, self.facility)

    def test_historico_so_apresenta_instalacoes_autorizadas(self):
        self.client.force_login(self.editor)
        response = self.client.get(self.history_url)

        self.assertEqual(response.status_code, 200)

        facilities = list(response.context["facilities"])
        self.assertEqual(facilities, [self.facility])

        readings = list(response.context["readings"])
        self.assertEqual(len(readings), 1)
        self.assertEqual(readings[0].facility, self.facility)

    def test_filtro_do_historico_nao_expoe_outra_empresa(self):
        self.client.force_login(self.editor)

        response = self.client.get(
            self.history_url,
            {"facility": self.other_facility.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["readings"]), [])

        facilities = list(response.context["facilities"])
        self.assertNotIn(self.other_facility, facilities)

    def test_viewer_pode_consultar_dashboard_e_historico(self):
        self.client.force_login(self.viewer)

        dashboard = self.client.get(self.dashboard_url)
        history = self.client.get(self.history_url)

        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(history.status_code, 200)
        self.assertEqual(dashboard.context["total_readings"], 1)

    def test_utilizador_sem_empresa_recebe_acesso_negado(self):
        outsider = User.objects.create_user(
            username="monitoring_outsider",
            password="TesteSeguro123!",
        )
        self.client.force_login(outsider)

        dashboard = self.client.get(self.dashboard_url)
        history = self.client.get(self.history_url)

        self.assertEqual(dashboard.status_code, 403)
        self.assertEqual(history.status_code, 403)

    def test_staff_endiama_consulta_instalacoes_de_ambas_empresas(self):
        self.client.force_login(self.staff)

        dashboard = self.client.get(self.dashboard_url)
        history = self.client.get(self.history_url)

        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(history.status_code, 200)
        self.assertEqual(dashboard.context["total_readings"], 2)

        facilities = list(history.context["facilities"])
        self.assertIn(self.facility, facilities)
        self.assertIn(self.other_facility, facilities)

        readings = list(history.context["readings"])
        self.assertEqual(len(readings), 2)


class LifecycleSubmissionTests(LifecycleTestBase):

    def test_empresa_editor_guarda_rascunho(self):
        self.client.force_login(self.editor)

        response = self.client.post(
            reverse(
                "facilities:lifecycle_submission",
                args=[self.facility.pk],
            ),
            {
                "construction_method": "Aterro de jusante",
                "action": "draft",
            },
        )

        self.assertEqual(response.status_code, 302)

        submission = LifecycleSubmission.objects.get(
            facility=self.facility
        )

        self.assertEqual(submission.status, "DRAFT")
        self.assertEqual(submission.lifecycle_stage, "CONSTRUCTION")
        self.assertEqual(submission.revision, 1)

        self.assertTrue(
            LifecycleSubmissionLog.objects.filter(
                submission=submission,
                action="DRAFT_SAVED",
            ).exists()
        )

    def test_empresa_submete_processo(self):
        self.client.force_login(self.editor)

        response = self.client.post(
            reverse(
                "facilities:lifecycle_submission",
                args=[self.facility.pk],
            ),
            {
                "construction_method": "Aterro de jusante",
                "action": "submit",
            },
        )

        self.assertEqual(response.status_code, 302)

        submission = LifecycleSubmission.objects.get(
            facility=self.facility
        )

        self.assertEqual(submission.status, "SUBMITTED")
        self.assertEqual(submission.submitted_by, self.editor)
        self.assertIsNotNone(submission.submitted_at)

        self.assertTrue(
            LifecycleSubmissionLog.objects.filter(
                submission=submission,
                action="SUBMITTED",
            ).exists()
        )

    def test_rascunho_e_reutilizado_na_submissao(self):
        self.client.force_login(self.editor)

        url = reverse(
            "facilities:lifecycle_submission",
            args=[self.facility.pk],
        )

        self.client.post(
            url,
            {
                "construction_method": "Aterro de jusante",
                "action": "draft",
            },
        )

        self.client.post(
            url,
            {
                "construction_method": "Aterro de jusante",
                "action": "submit",
            },
        )

        submissions = LifecycleSubmission.objects.filter(
            facility=self.facility,
            lifecycle_stage="CONSTRUCTION",
        )

        self.assertEqual(submissions.count(), 1)
        self.assertEqual(submissions.get().revision, 1)
        self.assertEqual(submissions.get().status, "SUBMITTED")

    def test_formulario_nao_aceita_processo_vazio(self):
        self.client.force_login(self.editor)

        self.client.post(
            reverse(
                "facilities:lifecycle_submission",
                args=[self.facility.pk],
            ),
            {"action": "draft"},
        )

        self.assertFalse(
            LifecycleSubmission.objects.filter(
                facility=self.facility
            ).exists()
        )

    def test_viewer_nao_pode_submeter(self):
        self.client.force_login(self.viewer)

        response = self.client.post(
                reverse(
                    "facilities:lifecycle_submission",
                    args=[self.facility.pk],
                ),
                {
                    "construction_method": "Aterro de jusante",
                    "action": "submit",
                },
            )
        self.assertEqual(response.status_code, 403)

        self.assertFalse(
            LifecycleSubmission.objects.filter(
                facility=self.facility
            ).exists()
        )

    def test_empresa_nao_acede_a_instalacao_de_outra_empresa(self):
        outra_empresa = MiningCompany.objects.create(
            name="Outra Empresa",
            province="Luanda",
        )

        outra_instalacao = TailingsFacility.objects.create(
            company=outra_empresa,
            name="Instalação não autorizada",
            province="Luanda",
            municipality="Luanda",
            lifecycle_stage="CONSTRUCTION",
        )

        self.client.force_login(self.editor)

        response = self.client.get(
            reverse(
                "facilities:lifecycle_submission",
                args=[outra_instalacao.pk],
            )
        )

        self.assertEqual(response.status_code, 404)


class LifecycleDocumentTests(LifecycleTestBase):

    def test_empresa_editor_carrega_documento_no_rascunho(self):
        submission = self.create_submission()

        self.client.force_login(self.editor)

        response = self.client.post(
            reverse(
                "facilities:lifecycle_document_upload",
                args=[submission.pk],
            ),
            {
                "title": "Relatório de construção",
                "document_type": "Relatório técnico",
                "reference": "REL-001",
                "document_date": "",
                "file": self.valid_pdf(),
            },
        )

        self.assertEqual(response.status_code, 302)

        document = LifecycleDocument.objects.get(
            submission=submission
        )

        self.assertEqual(document.title, "Relatório de construção")
        self.assertEqual(document.uploaded_by, self.editor)
        self.assertFalse(document.is_simulated)

        self.assertTrue(
            LifecycleSubmissionLog.objects.filter(
                submission=submission,
                action="DOCUMENT_UPLOADED",
            ).exists()
        )

    def test_viewer_nao_pode_carregar_documento(self):
        submission = self.create_submission()

        self.client.force_login(self.viewer)

        response = self.client.post(
                reverse(
                    "facilities:lifecycle_document_upload",
                    args=[submission.pk],
                ),
                {
                    "title": "Documento",
                    "document_type": "Relatório",
                    "file": self.valid_pdf(),
                },
            )
        self.assertEqual(response.status_code, 403)

        self.assertFalse(
            LifecycleDocument.objects.filter(
                submission=submission
            ).exists()
        )

    def test_documento_nao_pode_ser_carregado_apos_submissao(self):
        submission = self.create_submission(status="SUBMITTED")

        self.client.force_login(self.editor)

        response = self.client.post(
                reverse(
                    "facilities:lifecycle_document_upload",
                    args=[submission.pk],
                ),
                {
                    "title": "Documento",
                    "document_type": "Relatório",
                    "file": self.valid_pdf(),
                },
            )
        self.assertEqual(response.status_code, 403)

        self.assertFalse(
            LifecycleDocument.objects.filter(
                submission=submission
            ).exists()
        )

    def test_download_permitido_a_membro_da_empresa(self):
        submission = self.create_submission()

        document = LifecycleDocument.objects.create(
            submission=submission,
            title="Relatório",
            document_type="Relatório técnico",
            file=self.valid_pdf(),
            uploaded_by=self.editor,
            is_simulated=False,
        )

        self.client.force_login(self.editor)

        response = self.client.get(
            reverse(
                "facilities:lifecycle_document_download",
                args=[document.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Disposition"].split(";")[0],
                         "attachment")

        response.close()

    def test_download_bloqueado_a_utilizador_externo(self):
        submission = self.create_submission()

        document = LifecycleDocument.objects.create(
            submission=submission,
            title="Relatório",
            document_type="Relatório técnico",
            file=self.valid_pdf(),
            uploaded_by=self.editor,
        )

        externo = User.objects.create_user(
            username="utilizador_externo",
            password="TesteSeguro123!",
        )

        self.client.force_login(externo)

        response = self.client.get(
                reverse(
                    "facilities:lifecycle_document_download",
                    args=[document.pk],
                )
            )
        self.assertEqual(response.status_code, 403)


class LifecycleReviewTests(LifecycleTestBase):

    def test_fluxo_completo_de_analise_e_aprovacao(self):
        submission = self.create_submission(status="SUBMITTED")

        self.client.force_login(self.staff)

        url = reverse(
            "facilities:lifecycle_review_detail",
            args=[submission.pk],
        )

        response_start = self.client.post(
            url,
            {
                "action": "start_review",
                "justification": "Início da análise documental.",
            },
        )

        self.assertEqual(response_start.status_code, 302)

        submission.refresh_from_db()
        self.assertEqual(submission.status, "UNDER_REVIEW")

        response_approve = self.client.post(
            url,
            {
                "action": "approve",
                "justification": "Documentação analisada e aceite.",
            },
        )

        self.assertEqual(response_approve.status_code, 302)

        submission.refresh_from_db()
        self.assertEqual(submission.status, "APPROVED")
        self.assertEqual(submission.reviewed_by, self.staff)
        self.assertTrue(submission.reviewed_at)

        self.assertEqual(
            LifecycleSubmissionLog.objects.filter(
                submission=submission
            ).count(),
            2,
        )

    def test_decisao_sem_justificacao_nao_altera_estado(self):
        submission = self.create_submission(status="SUBMITTED")

        self.client.force_login(self.staff)

        response = self.client.post(
            reverse(
                "facilities:lifecycle_review_detail",
                args=[submission.pk],
            ),
            {
                "action": "start_review",
                "justification": "",
            },
        )

        self.assertEqual(response.status_code, 302)

        submission.refresh_from_db()
        self.assertEqual(submission.status, "SUBMITTED")

        self.assertFalse(
            LifecycleSubmissionLog.objects.filter(
                submission=submission
            ).exists()
        )

    def test_utilizador_nao_staff_nao_pode_analisar(self):
        submission = self.create_submission(status="SUBMITTED")

        self.client.force_login(self.editor)

        response = self.client.post(
                reverse(
                    "facilities:lifecycle_review_detail",
                    args=[submission.pk],
                ),
                {
                    "action": "start_review",
                    "justification": "Tentativa não autorizada.",
                },
            )
        self.assertEqual(response.status_code, 403)

        submission.refresh_from_db()
        self.assertEqual(submission.status, "SUBMITTED")


class LifecycleStageTransitionTests(LifecycleTestBase):

    def test_transicao_exige_aprovacao_da_fase_actual(self):
        self.create_submission(status="SUBMITTED")

        with self.assertRaises(ValidationError):
            change_lifecycle_stage(
                self.facility.pk,
                "OPERATION",
                self.staff,
                notes="Transição de teste.",
            )

        self.facility.refresh_from_db()
        self.assertEqual(
            self.facility.lifecycle_stage,
            "CONSTRUCTION",
        )

    def test_transicao_aprovada_regista_historico(self):
        self.create_submission(status="APPROVED")

        facility, history = change_lifecycle_stage(
            self.facility.pk,
            "OPERATION",
            self.staff,
            notes="Conclusão e aprovação da fase de construção.",
        )

        self.assertEqual(facility.lifecycle_stage, "OPERATION")
        self.assertEqual(history.previous_stage, "CONSTRUCTION")
        self.assertEqual(history.new_stage, "OPERATION")
        self.assertEqual(history.changed_by, self.staff)

        self.assertTrue(
            FacilityLifecycleHistory.objects.filter(
                facility=self.facility,
                previous_stage="CONSTRUCTION",
                new_stage="OPERATION",
            ).exists()
        )

    def test_transicao_nao_pode_saltar_fases(self):
        self.create_submission(status="APPROVED")

        with self.assertRaises(ValidationError):
            change_lifecycle_stage(
                self.facility.pk,
                "CLOSURE",
                self.staff,
                notes="Tentativa de saltar a fase de operação.",
            )

        self.facility.refresh_from_db()
        self.assertEqual(
            self.facility.lifecycle_stage,
            "CONSTRUCTION",
        )

    def test_transicao_exige_utilizador_autorizado(self):
        self.create_submission(status="APPROVED")

        with self.assertRaises(PermissionDenied):
            change_lifecycle_stage(
                self.facility.pk,
                "OPERATION",
                self.editor,
                notes="Tentativa não autorizada.",
            )

    def test_transicao_exige_justificacao(self):
        self.create_submission(status="APPROVED")

        with self.assertRaises(ValidationError):
            change_lifecycle_stage(
                self.facility.pk,
                "OPERATION",
                self.staff,
                notes="",
            )


class LifecycleIntegrityTests(LifecycleTestBase):

    def test_dados_de_submissao_enviada_nao_podem_ser_alterados(self):
        submission = self.create_submission(status="SUBMITTED")

        submission.phase_data = {
            "construction_method": "Alteração não autorizada"
        }

        with self.assertRaises(ValidationError):
            submission.save()

    def test_historico_nao_pode_ser_actualizado_em_massa(self):
        submission = self.create_submission()

        LifecycleSubmissionLog.objects.create(
            submission=submission,
            action="DRAFT_SAVED",
            previous_status="DRAFT",
            new_status="DRAFT",
            performed_by=self.editor,
            justification="Registo de teste.",
        )

        with self.assertRaises(ValidationError):
            LifecycleSubmissionLog.objects.filter(
                submission=submission
            ).update(justification="Tentativa de alteração.")

    def test_historico_nao_pode_ser_eliminado_em_massa(self):
        submission = self.create_submission()

        LifecycleSubmissionLog.objects.create(
            submission=submission,
            action="DRAFT_SAVED",
            previous_status="DRAFT",
            new_status="DRAFT",
            performed_by=self.editor,
            justification="Registo de teste.",
        )

        with self.assertRaises(ValidationError):
            LifecycleSubmissionLog.objects.filter(
                submission=submission
            ).delete()

    def test_submissao_nao_pode_ser_eliminada_em_massa(self):
        submission = self.create_submission()

        with self.assertRaises(ValidationError):
            LifecycleSubmission.objects.filter(
                pk=submission.pk
            ).delete()


class LifecycleDocumentIntegrityTests(LifecycleTestBase):

    def test_documentos_nao_podem_ser_actualizados_em_massa(self):
        submission = self.create_submission()
        with self.assertRaises(ValidationError):
            LifecycleDocument.objects.filter(
                submission=submission
            ).update(title="Alterado")

    def test_documentos_nao_podem_ser_eliminados_em_massa(self):
        submission = self.create_submission()
        with self.assertRaises(ValidationError):
            LifecycleDocument.objects.filter(
                submission=submission
            ).delete()

    def test_documentos_nao_podem_usar_bulk_update(self):
        submission = self.create_submission()
        document = LifecycleDocument.objects.create(
            submission=submission,
            title="Relatório",
            document_type="Relatório técnico",
            file=self.valid_pdf(),
            uploaded_by=self.editor,
        )
        document.title = "Título alterado"

        with self.assertRaises(ValidationError):
            LifecycleDocument.objects.bulk_update(
                [document],
                ["title"],
            )

    def test_bulk_create_bloqueado_em_processo_submetido(self):
        submission = self.create_submission(status="SUBMITTED")
        document = LifecycleDocument(
            submission=submission,
            title="Documento não autorizado",
            document_type="Relatório",
            file=self.valid_pdf(),
            uploaded_by=self.editor,
        )

        with self.assertRaises(ValidationError):
            LifecycleDocument.objects.bulk_create([document])


class FacilityLifecycleHistoryIntegrityTests(LifecycleTestBase):

    def create_history(self):
        self.create_submission(status="APPROVED")
        _, history = change_lifecycle_stage(
            self.facility.pk,
            "OPERATION",
            self.staff,
            notes="Transição aprovada para teste de integridade.",
        )
        return history

    def test_historico_bloqueia_queryset_update(self):
        history = self.create_history()
        with self.assertRaises(ValidationError):
            FacilityLifecycleHistory.objects.filter(
                pk=history.pk
            ).update(notes="Alteração não autorizada.")

    def test_historico_bloqueia_queryset_delete(self):
        history = self.create_history()
        with self.assertRaises(ValidationError):
            FacilityLifecycleHistory.objects.filter(
                pk=history.pk
            ).delete()

    def test_historico_bloqueia_bulk_update(self):
        history = self.create_history()
        history.notes = "Tentativa de alteração em massa."
        with self.assertRaises(ValidationError):
            FacilityLifecycleHistory.objects.bulk_update(
                [history], ["notes"]
            )

    def test_historico_bloqueia_bulk_create(self):
        with self.assertRaises(ValidationError):
            FacilityLifecycleHistory.objects.bulk_create([
                FacilityLifecycleHistory(
                    facility=self.facility,
                    previous_stage="CONSTRUCTION",
                    new_stage="OPERATION",
                    changed_by=self.staff,
                    notes="Tentativa de criação em massa.",
                )
            ])

    def test_historico_bloqueia_save_individual(self):
        history = self.create_history()
        history.notes = "Tentativa de edição individual."
        with self.assertRaises(ValidationError):
            history.save()

    def test_historico_bloqueia_delete_individual(self):
        history = self.create_history()
        with self.assertRaises(ValidationError):
            history.delete()

    def test_transicao_autorizada_continua_a_criar_historico(self):
        history = self.create_history()
        self.assertTrue(
            FacilityLifecycleHistory.objects.filter(
                pk=history.pk,
                facility=self.facility,
                changed_by=self.staff,
            ).exists()
        )


class ImmutableAuditLogsIntegrityTests(LifecycleTestBase):
    """
    Testes de integridade dos quatro históricos de auditoria.
    A criação é permitida; a alteração e eliminação são bloqueadas.
    """

    def setUp(self):
        super().setUp()

        self.parameter = MonitoringParameter.objects.create(
            code="TEST-AUDIT-PARAM",
            name="Parâmetro de teste",
            category="GEOTECHNICAL",
            unit="mm",
        )

        self.monitoring_criterion = MonitoringCriterion.objects.create(
            facility=self.facility,
            parameter=self.parameter,
            created_by=self.staff,
        )

        self.gistm_assessment = GISTMAssessment.objects.create(
            facility=self.facility,
            assessment_type="SELF",
            status="NOT_STARTED",
            version=1,
        )

        self.tarp_criterion = TARPCriterion.objects.create(
            facility=self.facility,
            parameter=self.parameter,
            direction="HIGHER",
            level_1="2.0000",
            level_2="5.0000",
            level_3="10.0000",
            level_4="15.0000",
        )

        self.tarp_event = TARPEvent.objects.create(
            facility=self.facility,
            trigger_description="Evento de teste de integridade.",
        )

    def audit_factories(self):
        return [
            (
                CriterionApprovalLog,
                {
                    "criterion": self.monitoring_criterion,
                    "action": "SUBMITTED",
                    "performed_by": self.staff,
                    "justification": "Teste de auditoria.",
                },
                "justification",
            ),
            (
                GISTMAuditLog,
                {
                    "assessment": self.gistm_assessment,
                    "action": "TEST_EVENT",
                    "performed_by": self.staff,
                    "justification": "Teste de auditoria.",
                },
                "new_value",
            ),
            (
                TARPEventLog,
                {
                    "event": self.tarp_event,
                    "action": "TEST_EVENT",
                    "performed_by": self.staff,
                    "details": "Teste de auditoria.",
                },
                "details",
            ),
            (
                TARPCriterionApprovalLog,
                {
                    "criterion": self.tarp_criterion,
                    "action": "SUBMITTED",
                    "performed_by": self.staff,
                    "justification": "Teste de auditoria.",
                },
                "justification",
            ),
        ]

    def test_criacao_autorizada_dos_quatro_historicos(self):
        for model, fields, _ in self.audit_factories():
            with self.subTest(model=model.__name__):
                record = model.objects.create(**fields)
                self.assertIsNotNone(record.pk)
                self.assertTrue(model.objects.filter(pk=record.pk).exists())

    def test_save_individual_bloqueado_nos_quatro_historicos(self):
        for model, fields, editable_field in self.audit_factories():
            with self.subTest(model=model.__name__):
                record = model.objects.create(**fields)
                setattr(record, editable_field, "Tentativa de alteração.")

                with self.assertRaises(ValidationError):
                    record.save()

    def test_delete_individual_bloqueado_nos_quatro_historicos(self):
        for model, fields, _ in self.audit_factories():
            with self.subTest(model=model.__name__):
                record = model.objects.create(**fields)

                with self.assertRaises(ValidationError):
                    record.delete()

                self.assertTrue(model.objects.filter(pk=record.pk).exists())

    def test_queryset_update_bloqueado_nos_quatro_historicos(self):
        for model, fields, editable_field in self.audit_factories():
            with self.subTest(model=model.__name__):
                record = model.objects.create(**fields)

                with self.assertRaises(ValidationError):
                    model.objects.filter(pk=record.pk).update(
                        **{editable_field: "Tentativa de alteração."}
                    )

    def test_queryset_delete_bloqueado_nos_quatro_historicos(self):
        for model, fields, _ in self.audit_factories():
            with self.subTest(model=model.__name__):
                record = model.objects.create(**fields)

                with self.assertRaises(ValidationError):
                    model.objects.filter(pk=record.pk).delete()

                self.assertTrue(model.objects.filter(pk=record.pk).exists())

    def test_bulk_update_bloqueado_nos_quatro_historicos(self):
        for model, fields, editable_field in self.audit_factories():
            with self.subTest(model=model.__name__):
                record = model.objects.create(**fields)
                setattr(record, editable_field, "Tentativa de alteração.")

                with self.assertRaises(ValidationError):
                    model.objects.bulk_update(
                        [record],
                        [editable_field],
                    )

    def test_bulk_create_bloqueado_nos_quatro_historicos(self):
        for model, fields, _ in self.audit_factories():
            with self.subTest(model=model.__name__):
                record = model(**fields)

                with self.assertRaises(ValidationError):
                    model.objects.bulk_create([record])


class ImmutableMonitoringReadingTests(LifecycleTestBase):
    """As leituras podem ser criadas, mas não alteradas nem eliminadas."""

    def setUp(self):
        super().setUp()
        self.parameter = MonitoringParameter.objects.create(
            code="IMMUTABLE-READING-TEST",
            name="Variável de teste de imutabilidade",
            category="GEOTECHNICAL",
            unit="mm",
        )
        self.reading = MonitoringReading.objects.create(
            facility=self.facility,
            parameter=self.parameter,
            observed_at=timezone.now(),
            value=Decimal("3.0000"),
            unit="mm",
            entered_by=self.staff,
        )

    def test_criacao_de_leitura_permitida(self):
        self.assertIsNotNone(self.reading.pk)
        self.assertTrue(
            MonitoringReading.objects.filter(pk=self.reading.pk).exists()
        )

    def test_save_de_leitura_existente_bloqueado(self):
        self.reading.notes = "Tentativa de alteração."
        with self.assertRaises(ValidationError):
            self.reading.save()

    def test_delete_individual_bloqueado(self):
        with self.assertRaises(ValidationError):
            self.reading.delete()
        self.assertTrue(
            MonitoringReading.objects.filter(pk=self.reading.pk).exists()
        )

    def test_queryset_update_bloqueado(self):
        with self.assertRaises(ValidationError):
            MonitoringReading.objects.filter(pk=self.reading.pk).update(
                notes="Tentativa de alteração em massa."
            )

    def test_queryset_delete_bloqueado(self):
        with self.assertRaises(ValidationError):
            MonitoringReading.objects.filter(pk=self.reading.pk).delete()
        self.assertTrue(
            MonitoringReading.objects.filter(pk=self.reading.pk).exists()
        )

    def test_bulk_update_bloqueado(self):
        self.reading.notes = "Tentativa de alteração em massa."
        with self.assertRaises(ValidationError):
            MonitoringReading.objects.bulk_update(
                [self.reading], ["notes"]
            )

    def test_bulk_create_bloqueado(self):
        new_reading = MonitoringReading(
            facility=self.facility,
            parameter=self.parameter,
            observed_at=timezone.now(),
            value=Decimal("4.0000"),
            unit="mm",
            entered_by=self.staff,
        )
        with self.assertRaises(ValidationError):
            MonitoringReading.objects.bulk_create([new_reading])


class MonitoringTARPIntegrationTests(LifecycleTestBase):
    """Testes integrados dos serviços de monitorização e TARP."""

    def setUp(self):
        super().setUp()
        self.parameter = MonitoringParameter.objects.create(
            code="INTEGRATION-TEST",
            name="Variável integrada de teste",
            category="GEOTECHNICAL",
            unit="mm",
        )

    def create_monitoring_criterion(self, effective_from=None):
        return MonitoringCriterion.objects.create(
            facility=self.facility,
            parameter=self.parameter,
            version=1,
            status="APPROVED",
            effective_from=effective_from or timezone.now().date(),
            green_min=Decimal("0"),
            green_max=Decimal("4.9999"),
            yellow_min=Decimal("5"),
            yellow_max=Decimal("9.9999"),
            orange_min=Decimal("10"),
            orange_max=Decimal("14.9999"),
            red_min=Decimal("15"),
            red_max=Decimal("20"),
            approved_by="Responsável autorizado de teste",
            approval_reference="TEST-APPROVAL-001",
            approved_at=timezone.now(),
        )

    def create_reading(self, value, unit="mm"):
        reading = MonitoringReading(
            facility=self.facility,
            parameter=self.parameter,
            observed_at=timezone.now(),
            value=Decimal(str(value)),
            unit=unit,
            entered_by=self.staff,
        )
        return reading

    def create_tarp_criterion(self, direction="HIGHER"):
        return TARPCriterion.objects.create(
            facility=self.facility,
            parameter=self.parameter,
            direction=direction,
            version=1,
            level_1=Decimal("5"),
            level_2=Decimal("10"),
            level_3=Decimal("15"),
            level_4=Decimal("20"),
            status="APPROVED",
            effective_from=timezone.now().date(),
            created_by=self.staff,
            approved_by=self.staff,
            approved_at=timezone.now(),
            approval_reference="TARP-TEST-001",
        )

    def test_classificacao_dos_quatro_niveis_de_monitorizacao(self):
        self.create_monitoring_criterion()

        cases = [
            ("2", "GREEN"),
            ("7", "YELLOW"),
            ("12", "ORANGE"),
            ("17", "RED"),
        ]

        for value, expected in cases:
            with self.subTest(value=value):
                reading = self.create_reading(value)
                result = interpret_reading(reading)
                self.assertEqual(result, expected)
                self.assertEqual(reading.interpretation, expected)
                self.assertIsNotNone(reading.criterion)
                self.assertIsNone(reading.pk)

    def test_valor_fora_dos_intervalos_fica_nao_classificado(self):
        self.create_monitoring_criterion()
        reading = self.create_reading("25")

        result = interpret_reading(reading)

        self.assertEqual(result, "UNCLASSIFIED")
        self.assertIsNotNone(reading.criterion)

    def test_ausencia_de_criterio_e_identificada(self):
        reading = self.create_reading("5")

        result = interpret_reading(reading)

        self.assertEqual(result, "NOT_CONFIGURED")
        self.assertIsNone(reading.criterion)

    def test_criterio_aprovado_mas_ainda_nao_vigente(self):
        future_date = timezone.now().date() + timedelta(days=10)
        self.create_monitoring_criterion(effective_from=future_date)
        reading = self.create_reading("5")

        result = interpret_reading(reading)

        self.assertEqual(result, "NOT_EFFECTIVE")
        self.assertIsNone(reading.criterion)

    def test_unidade_incompativel_exige_revisao(self):
        self.create_monitoring_criterion()
        reading = self.create_reading("7", unit="cm")

        result = interpret_reading(reading)

        self.assertEqual(result, "REVIEW")

    def test_alertas_sao_criados_e_nao_duplicados(self):
        self.create_monitoring_criterion()

        for value, severity in [
            ("7", "YELLOW"),
            ("12", "ORANGE"),
            ("17", "RED"),
        ]:
            with self.subTest(severity=severity):
                reading = self.create_reading(value)
                interpret_reading(reading)
                reading.save()

                first_alert = create_monitoring_alert(reading)
                second_alert = create_monitoring_alert(reading)

                self.assertIsNotNone(first_alert)
                self.assertEqual(first_alert.pk, second_alert.pk)
                self.assertEqual(first_alert.severity, severity)
                self.assertEqual(
                    MonitoringAlert.objects.filter(reading=reading).count(),
                    1,
                )

    def test_nivel_green_nao_cria_alerta(self):
        self.create_monitoring_criterion()
        reading = self.create_reading("2")
        interpret_reading(reading)
        reading.save()

        result = create_monitoring_alert(reading)

        self.assertIsNone(result)
        self.assertFalse(
            MonitoringAlert.objects.filter(reading=reading).exists()
        )

    def test_tarp_l1_nao_cria_evento(self):
        self.create_tarp_criterion()
        reading = self.create_reading("5")
        reading.save()

        result = interpret_tarp_reading(reading, actor=self.staff)

        self.assertEqual(result["status"], "CLASSIFIED")
        self.assertEqual(result["level"], "L1")
        self.assertIsNone(result["event"])
        self.assertEqual(TARPEvent.objects.filter(reading=reading).count(), 0)

    def test_tarp_l2_l3_l4_criam_eventos_sem_resposta_automatica(self):
        self.create_tarp_criterion()

        cases = [
            ("10", "L2"),
            ("15", "L3"),
            ("20", "L4"),
        ]

        for value, expected_level in cases:
            with self.subTest(level=expected_level):
                reading = self.create_reading(value)
                reading.save()

                original = (
                    reading.value,
                    reading.unit,
                    reading.interpretation,
                    reading.criterion_id,
                )

                result = interpret_tarp_reading(
                    reading,
                    actor=self.staff,
                )

                self.assertEqual(result["status"], "EVENT_CREATED")
                self.assertEqual(result["level"], expected_level)

                event = result["event"]
                self.assertIsNotNone(event)
                self.assertEqual(event.trigger_level, expected_level)
                self.assertIsNone(event.response_level)
                self.assertEqual(event.status, "OPEN")

                self.assertEqual(
                    TARPEventLog.objects.filter(event=event).count(),
                    1,
                )

                reading.refresh_from_db()
                self.assertEqual(
                    (
                        reading.value,
                        reading.unit,
                        reading.interpretation,
                        reading.criterion_id,
                    ),
                    original,
                )

    def test_tarp_rejeita_criterio_de_parametro_diferente_da_leitura(self):
        criterion = self.create_tarp_criterion()

        other_parameter = MonitoringParameter.objects.create(
            code="INTEGRATION-OTHER",
            name="Outra variável de teste",
            category="GEOTECHNICAL",
            unit="mm",
        )

        criterion.parameter = other_parameter
        criterion.save(update_fields=["parameter"])

        reading = self.create_reading("15")
        reading.save()

        event = TARPEvent(
            facility=self.facility,
            reading=reading,
            criterion=criterion,
            trigger_level="L3",
            trigger_description="Teste de integridade do critério.",
        )

        with self.assertRaises(ValidationError):
            event.full_clean()

        self.assertFalse(
            TARPEvent.objects.filter(reading=reading).exists()
        )

    def test_tarp_sem_utilizador_responsavel_nao_cria_evento(self):
        self.create_tarp_criterion()

        reading = self.create_reading("15")
        reading.entered_by = None
        reading.save()

        with self.assertRaises(ValidationError):
            interpret_tarp_reading(reading, actor=None)

        self.assertFalse(
            TARPEvent.objects.filter(reading=reading).exists()
        )

    def test_tarp_nao_duplica_evento_para_a_mesma_leitura(self):
        self.create_tarp_criterion()
        reading = self.create_reading("15")
        reading.save()

        first = interpret_tarp_reading(reading, actor=self.staff)
        second = interpret_tarp_reading(reading, actor=self.staff)

        self.assertEqual(first["status"], "EVENT_CREATED")
        self.assertEqual(second["status"], "EVENT_EXISTS")
        self.assertEqual(first["event"].pk, second["event"].pk)
        self.assertEqual(TARPEvent.objects.filter(reading=reading).count(), 1)

    def test_tarp_sem_criterio_nao_cria_evento(self):
        reading = self.create_reading("15")
        reading.save()

        result = interpret_tarp_reading(reading, actor=self.staff)

        self.assertEqual(result["status"], "NOT_CONFIGURED")
        self.assertIsNone(result["event"])
        self.assertEqual(TARPEvent.objects.filter(reading=reading).count(), 0)

    def test_tarp_unidade_incompativel_nao_cria_evento(self):
        self.create_tarp_criterion()
        reading = self.create_reading("15", unit="cm")
        reading.save()

        result = interpret_tarp_reading(reading, actor=self.staff)

        self.assertEqual(result["status"], "UNIT_MISMATCH")
        self.assertIsNone(result["event"])
        self.assertEqual(TARPEvent.objects.filter(reading=reading).count(), 0)


class MonitoringCriterionAuthorizationTests(LifecycleTestBase):

    def setUp(self):
        super().setUp()

        self.parameter = MonitoringParameter.objects.create(
            code="CRIT-AUTH-TEST",
            name="Deslocamento de teste",
            category="GEOTECHNICAL",
            unit="mm",
            instrument_required=False,
            is_active=True,
        )

    def create_criterion(
        self,
        facility=None,
        creator=None,
        status="DRAFT",
        version=1,
    ):
        return MonitoringCriterion.objects.create(
            facility=facility or self.facility,
            parameter=self.parameter,
            version=version,
            created_by=creator or self.editor,
            status=status,
            effective_from=timezone.now().date(),
            source_document="Procedimento técnico de monitorização",
            green_min=Decimal("0"),
            green_max=Decimal("4"),
            yellow_min=Decimal("5"),
            yellow_max=Decimal("9"),
            orange_min=Decimal("10"),
            orange_max=Decimal("14"),
            red_min=Decimal("15"),
            red_max=Decimal("20"),
        )

    def create_other_company_facility(self):
        company = MiningCompany.objects.create(
            name="Segunda Empresa de Teste",
            country="Angola",
            province="Lunda Sul",
            is_simulated=True,
        )
        return TailingsFacility.objects.create(
            company=company,
            name="Segunda Instalação de Teste",
            province="Lunda Sul",
            municipality="Saurimo",
            lifecycle_stage="CONSTRUCTION",
            is_simulated=True,
        )

    def authorize_reviewer(self, user=None):
        from django.contrib.auth.models import Permission

        reviewer = user or self.staff
        permission = Permission.objects.get(
            content_type__app_label="facilities",
            codename="approve_monitoringcriterion",
        )
        reviewer.user_permissions.add(permission)
        return reviewer

    def test_lista_isola_criterios_por_empresa(self):
        own = self.create_criterion()

        other_facility = self.create_other_company_facility()
        other = self.create_criterion(
            facility=other_facility,
            version=2,
        )

        self.client.force_login(self.editor)
        response = self.client.get(
            reverse("facilities:monitoring_criteria_list")
        )

        self.assertEqual(response.status_code, 200)
        visible_ids = set(
            response.context["criteria"].values_list("id", flat=True)
        )

        self.assertIn(own.pk, visible_ids)
        self.assertNotIn(other.pk, visible_ids)

    def test_viewer_consulta_mas_nao_submete(self):
        criterion = self.create_criterion()

        self.client.force_login(self.viewer)

        response = self.client.get(
            reverse("facilities:monitoring_criteria_list")
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            reverse(
                "facilities:monitoring_criterion_submit",
                args=[criterion.pk],
            ),
            {"justification": "Submissão de teste"},
        )

        self.assertEqual(response.status_code, 403)
        criterion.refresh_from_db()
        self.assertEqual(criterion.status, "DRAFT")

    def test_editor_submete_criterio_da_sua_empresa(self):
        criterion = self.create_criterion()

        self.client.force_login(self.editor)
        response = self.client.post(
            reverse(
                "facilities:monitoring_criterion_submit",
                args=[criterion.pk],
            ),
            {"justification": "Critério tecnicamente preparado."},
        )

        self.assertEqual(response.status_code, 302)

        criterion.refresh_from_db()
        self.assertEqual(criterion.status, "REVIEW")

        log = CriterionApprovalLog.objects.get(
            criterion=criterion,
            action="SUBMITTED",
        )
        self.assertEqual(log.performed_by, self.editor)
        self.assertEqual(
            log.justification,
            "Critério tecnicamente preparado.",
        )

    def test_editor_nao_submete_criterio_de_outra_empresa(self):
        other_facility = self.create_other_company_facility()
        criterion = self.create_criterion(facility=other_facility)

        self.client.force_login(self.editor)
        response = self.client.post(
            reverse(
                "facilities:monitoring_criterion_submit",
                args=[criterion.pk],
            ),
            {"justification": "Tentativa não autorizada."},
        )

        self.assertEqual(response.status_code, 404)

        criterion.refresh_from_db()
        self.assertEqual(criterion.status, "DRAFT")

    def test_staff_submete_criterio_com_import_correcto(self):
        criterion = self.create_criterion()

        self.client.force_login(self.staff)
        response = self.client.post(
            reverse(
                "facilities:monitoring_criterion_submit",
                args=[criterion.pk],
            ),
            {"justification": "Submissão institucional de teste."},
        )

        self.assertEqual(response.status_code, 302)

        criterion.refresh_from_db()
        self.assertEqual(criterion.status, "REVIEW")

    def test_staff_sem_permissao_nao_aprova(self):
        criterion = self.create_criterion(status="REVIEW")

        self.client.force_login(self.staff)
        response = self.client.post(
            reverse(
                "facilities:monitoring_criterion_decide",
                args=[criterion.pk],
            ),
            {
                "action": "APPROVE",
                "justification": "Revisão de teste.",
                "reference": "REF-TESTE-001",
            },
        )

        self.assertEqual(response.status_code, 403)

        criterion.refresh_from_db()
        self.assertEqual(criterion.status, "REVIEW")

    def test_revisor_autorizado_aprova_criterio(self):
        criterion = self.create_criterion(status="REVIEW")
        self.authorize_reviewer()

        self.client.force_login(self.staff)
        response = self.client.post(
            reverse(
                "facilities:monitoring_criterion_decide",
                args=[criterion.pk],
            ),
            {
                "action": "APPROVE",
                "justification": "Limites tecnicamente revistos.",
                "reference": "ENDIAMA-APROVACAO-001",
            },
        )

        self.assertEqual(response.status_code, 302)

        criterion.refresh_from_db()
        self.assertEqual(criterion.status, "APPROVED")
        self.assertEqual(criterion.approved_by, self.staff.username)
        self.assertIsNotNone(criterion.approved_at)
        self.assertEqual(
            criterion.approval_reference,
            "ENDIAMA-APROVACAO-001",
        )

        self.assertTrue(
            CriterionApprovalLog.objects.filter(
                criterion=criterion,
                action="APPROVED",
                performed_by=self.staff,
                reference="ENDIAMA-APROVACAO-001",
            ).exists()
        )

    def test_autor_nao_pode_aprovar_o_proprio_criterio(self):
        criterion = self.create_criterion(
            creator=self.staff,
            status="REVIEW",
        )
        self.authorize_reviewer()

        self.client.force_login(self.staff)
        response = self.client.post(
            reverse(
                "facilities:monitoring_criterion_decide",
                args=[criterion.pk],
            ),
            {
                "action": "APPROVE",
                "justification": "Tentativa de auto-aprovação.",
                "reference": "REF-TESTE-002",
            },
        )

        self.assertEqual(response.status_code, 403)

        criterion.refresh_from_db()
        self.assertEqual(criterion.status, "REVIEW")

    def test_revisor_autorizado_pode_rejeitar_criterio(self):
        criterion = self.create_criterion(status="REVIEW")
        self.authorize_reviewer()

        self.client.force_login(self.staff)
        response = self.client.post(
            reverse(
                "facilities:monitoring_criterion_decide",
                args=[criterion.pk],
            ),
            {
                "action": "REJECT",
                "justification": "É necessário rever os limites.",
            },
        )

        self.assertEqual(response.status_code, 302)

        criterion.refresh_from_db()
        self.assertEqual(criterion.status, "DRAFT")

        self.assertTrue(
            CriterionApprovalLog.objects.filter(
                criterion=criterion,
                action="REJECTED",
                performed_by=self.staff,
            ).exists()
        )

    def test_historico_de_auditoria_e_imutavel(self):
        criterion = self.create_criterion()

        log = CriterionApprovalLog.objects.create(
            criterion=criterion,
            action="SUBMITTED",
            performed_by=self.editor,
            justification="Registo inicial de teste.",
        )

        with self.assertRaises(ValidationError):
            log.save()

        with self.assertRaises(ValidationError):
            log.delete()

        self.assertTrue(
            CriterionApprovalLog.objects.filter(pk=log.pk).exists()
        )


class MonitoringCriterionLifecycleActionsTests(LifecycleTestBase):

    def setUp(self):
        super().setUp()
        self.parameter = MonitoringParameter.objects.create(
            code="CRIT-LIFECYCLE-ACTIONS",
            name="Deslocamento de teste",
            category="GEOTECHNICAL",
            unit="mm",
            instrument_required=False,
            is_active=True,
        )

    def create_criterion(self, status="DRAFT", facility=None):
        return MonitoringCriterion.objects.create(
            facility=facility or self.facility,
            parameter=self.parameter,
            version=1,
            created_by=self.editor,
            status=status,
            effective_from=timezone.now().date(),
            source_document="Procedimento técnico de teste",
            green_min=Decimal("0"),
            green_max=Decimal("4"),
            yellow_min=Decimal("5"),
            yellow_max=Decimal("9"),
            orange_min=Decimal("10"),
            orange_max=Decimal("14"),
            red_min=Decimal("15"),
            red_max=Decimal("20"),
        )

    def valid_edit_payload(self):
        return {
            "facility": self.facility.pk,
            "parameter": self.parameter.pk,
            "version": 1,
            "effective_from": timezone.now().date().isoformat(),
            "green_min": "0",
            "green_max": "4",
            "yellow_min": "5",
            "yellow_max": "9",
            "orange_min": "10",
            "orange_max": "14",
            "red_min": "15",
            "red_max": "20",
            "source_document": "Procedimento técnico actualizado",
            "notes": "Actualização controlada de teste",
            "justification": "Actualização técnica devidamente fundamentada.",
        }

    def test_editor_edita_rascunho_e_cria_registo_auditoria(self):
        criterion = self.create_criterion()
        self.client.force_login(self.editor)

        response = self.client.post(
            reverse("facilities:monitoring_criterion_edit", args=[criterion.pk]),
            self.valid_edit_payload(),
        )

        self.assertEqual(response.status_code, 302)
        criterion.refresh_from_db()
        self.assertEqual(criterion.status, "DRAFT")
        self.assertEqual(
            criterion.source_document,
            "Procedimento técnico actualizado",
        )
        self.assertTrue(
            CriterionApprovalLog.objects.filter(
                criterion=criterion,
                action="UPDATED",
                performed_by=self.editor,
                justification="Actualização técnica devidamente fundamentada.",
            ).exists()
        )

    def test_viewer_nao_edita_rascunho(self):
        criterion = self.create_criterion()
        self.client.force_login(self.viewer)

        response = self.client.get(
            reverse("facilities:monitoring_criterion_edit", args=[criterion.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_editor_nao_edita_criterio_de_outra_empresa(self):
        other_company = MiningCompany.objects.create(
            name="Empresa externa de teste",
            country="Angola",
            province="Lunda Sul",
            is_simulated=True,
        )
        other_facility = TailingsFacility.objects.create(
            company=other_company,
            name="Instalação externa",
            province="Lunda Sul",
            municipality="Saurimo",
            lifecycle_stage="CONSTRUCTION",
            is_simulated=True,
        )
        criterion = self.create_criterion(facility=other_facility)
        self.client.force_login(self.editor)

        response = self.client.get(
            reverse("facilities:monitoring_criterion_edit", args=[criterion.pk])
        )
        self.assertEqual(response.status_code, 403 if response.status_code == 403 else 404)

    def test_criterio_aprovado_nao_pode_ser_editado(self):
        criterion = self.create_criterion(status="APPROVED")
        self.client.force_login(self.editor)

        response = self.client.get(
            reverse("facilities:monitoring_criterion_edit", args=[criterion.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_revisor_autorizado_retira_criterio_aprovado(self):
        from django.contrib.auth.models import Permission

        criterion = self.create_criterion(status="APPROVED")
        permission = Permission.objects.get(
            content_type__app_label="facilities",
            codename="approve_monitoringcriterion",
        )
        self.staff.user_permissions.add(permission)
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("facilities:monitoring_criterion_retire", args=[criterion.pk]),
            {"justification": "Critério substituído por nova versão aprovada."},
        )

        self.assertEqual(response.status_code, 302)
        criterion.refresh_from_db()
        self.assertEqual(criterion.status, "RETIRED")
        self.assertTrue(
            CriterionApprovalLog.objects.filter(
                criterion=criterion,
                action="RETIRED",
                performed_by=self.staff,
                justification="Critério substituído por nova versão aprovada.",
            ).exists()
        )

    def test_retirada_exige_justificacao(self):
        from django.contrib.auth.models import Permission

        criterion = self.create_criterion(status="APPROVED")
        permission = Permission.objects.get(
            content_type__app_label="facilities",
            codename="approve_monitoringcriterion",
        )
        self.staff.user_permissions.add(permission)
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("facilities:monitoring_criterion_retire", args=[criterion.pk]),
            {"justification": ""},
        )

        self.assertEqual(response.status_code, 302)
        criterion.refresh_from_db()
        self.assertEqual(criterion.status, "APPROVED")
        self.assertFalse(
            CriterionApprovalLog.objects.filter(
                criterion=criterion,
                action="RETIRED",
            ).exists()
        )


# ============================================================
# ENT-GIS — TESTES DE AUTORIZAÇÃO E FLUXO DAS VIEWS TARP
# ============================================================

class TARPViewAuthorizationTests(LifecycleTestBase):

    def setUp(self):
        super().setUp()

        self.other_company = MiningCompany.objects.create(
            name="Outra Empresa de Teste",
            country="Angola",
            province="Lunda Sul",
            is_simulated=True,
        )

        self.other_facility = TailingsFacility.objects.create(
            company=self.other_company,
            name="Outra Instalação de Teste",
            province="Lunda Sul",
            municipality="Saurimo",
            lifecycle_stage="OPERATION",
            is_simulated=True,
        )

        self.event = TARPEvent.objects.create(
            facility=self.facility,
            trigger_level="L3",
            trigger_description="Evento TARP da empresa autorizada.",
        )

        self.other_event = TARPEvent.objects.create(
            facility=self.other_facility,
            trigger_level="L4",
            trigger_description="Evento TARP de outra empresa.",
        )

        self.dashboard_url = reverse(
            "facilities:tarp_events_dashboard"
        )

    def test_relatorio_tarp_consulta_instalacao_autorizada(self):
        self.client.force_login(self.editor)

        url = reverse(
            "facilities:tarp_facility_report",
            args=[self.facility.pk],
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["facility"], self.facility)
        self.assertEqual(response.context["total_events"], 1)
        self.assertEqual(response.context["open_events"], 1)
        self.assertEqual(response.context["trigger_counts"]["L3"], 1)
        self.assertEqual(response.context["critical_events"], 0)
        self.assertContains(response, self.facility.name)
        self.assertContains(response, "Consultar histórico de auditoria")

    def test_relatorio_tarp_bloqueia_instalacao_de_outra_empresa(self):
        self.client.force_login(self.editor)

        url = reverse(
            "facilities:tarp_facility_report",
            args=[self.other_facility.pk],
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_viewer_consulta_relatorio_tarp_sem_permissao_de_gestao(self):
        self.client.force_login(self.viewer)

        url = reverse(
            "facilities:tarp_facility_report",
            args=[self.facility.pk],
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_events"], 1)
        self.assertEqual(response.context["trigger_counts"]["L3"], 1)

    def test_filtros_actualizam_indicadores_sem_expor_outra_empresa(self):
        self.client.force_login(self.editor)

        # O evento L4 pertence a outra empresa e não pode aparecer.
        response_l4 = self.client.get(
            self.dashboard_url,
            {"trigger_level": "L4"},
        )
        self.assertEqual(response_l4.status_code, 200)
        self.assertEqual(response_l4.context["total_events"], 0)
        self.assertNotIn(
            self.other_event.pk,
            [event.pk for event in response_l4.context["events"]],
        )

        # O evento L3 da empresa autorizada deve ser contabilizado.
        response_l3 = self.client.get(
            self.dashboard_url,
            {"trigger_level": "L3"},
        )
        self.assertEqual(response_l3.status_code, 200)
        self.assertEqual(response_l3.context["total_events"], 1)
        self.assertEqual(response_l3.context["critical_events"], 0)
        self.assertEqual(response_l3.context["displayed_events_count"], 1)

    def test_eventos_em_atraso_excluem_eventos_encerrados(self):
        self.client.force_login(self.editor)

        # Criar um prazo já ultrapassado.
        self.event.due_at = timezone.now() - timedelta(hours=2)
        self.event.save(update_fields=["due_at"])

        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["overdue_events"], 1)

        # Encerrar o evento: deixa de contar como evento em atraso.
        self.event.status = "CLOSED"
        self.event.closed_at = timezone.now()
        self.event.save(update_fields=["status", "closed_at"])

        response_closed = self.client.get(self.dashboard_url)

        self.assertEqual(response_closed.status_code, 200)
        self.assertEqual(response_closed.context["overdue_events"], 0)
        self.assertEqual(response_closed.context["closed_events"], 1)

    def test_editor_so_consulta_eventos_da_sua_empresa(self):
        self.client.force_login(self.editor)

        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_events"], 1)

        event_ids = [
            event.pk for event in response.context["events"]
        ]

        self.assertIn(self.event.pk, event_ids)
        self.assertNotIn(self.other_event.pk, event_ids)

    def test_viewer_consulta_eventos_sem_poder_gerir(self):
        self.client.force_login(self.viewer)

        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_events"], 1)
        self.assertFalse(response.context["can_manage_tarp"])

    def test_viewer_nao_pode_executar_accao_tarp(self):
        self.client.force_login(self.viewer)

        response = self.client.post(
            reverse(
                "facilities:tarp_event_action",
                args=[self.event.pk],
            ),
            {
                "action": "acknowledge",
                "details": "Tentativa de reconhecimento.",
            },
        )

        self.assertEqual(response.status_code, 403)

        self.event.refresh_from_db()
        self.assertEqual(self.event.status, "OPEN")

        self.assertFalse(
            TARPEventLog.objects.filter(
                event=self.event
            ).exists()
        )

    def test_editor_nao_pode_alterar_evento_de_outra_empresa(self):
        self.client.force_login(self.editor)

        response = self.client.post(
            reverse(
                "facilities:tarp_event_action",
                args=[self.other_event.pk],
            ),
            {
                "action": "acknowledge",
                "details": "Tentativa de acesso cruzado.",
            },
        )

        self.assertEqual(response.status_code, 404)

        self.other_event.refresh_from_db()
        self.assertEqual(self.other_event.status, "OPEN")

        self.assertFalse(
            TARPEventLog.objects.filter(
                event=self.other_event
            ).exists()
        )

    def test_fluxo_completo_tarp_com_historico_auditavel(self):
        self.client.force_login(self.editor)

        action_url = reverse(
            "facilities:tarp_event_action",
            args=[self.event.pk],
        )

        # Primeiro: reconhecer o evento
        response = self.client.post(
            action_url,
            {
                "action": "acknowledge",
                "details": "Evento avaliado e reconhecido.",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.event.refresh_from_db()
        self.assertEqual(self.event.status, "ACKNOWLEDGED")
        self.assertIsNotNone(self.event.acknowledged_at)

        # Segundo: atribuir resposta e responsável
        response = self.client.post(
            action_url,
            {
                "action": "assign_response",
                "response_level": "S3",
                "responsible": "Engenheiro responsável de turno",
                "details": "Vigilância reforçada e intervenção definida.",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.event.refresh_from_db()
        self.assertEqual(self.event.response_level, "S3")
        self.assertEqual(
            self.event.responsible,
            "Engenheiro responsável de turno",
        )

        # Reatribuir: a atribuição anterior deve permanecer auditável.
        response = self.client.post(
            action_url,
            {
                "action": "assign_response",
                "response_level": "S4",
                "responsible": "Engenheiro responsável de segurança",
                "details": "Reavaliação técnica justifica reforço da resposta.",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.event.refresh_from_db()
        self.assertEqual(self.event.response_level, "S4")
        self.assertEqual(
            self.event.responsible,
            "Engenheiro responsável de segurança",
        )

        reassignment_log = TARPEventLog.objects.get(
            event=self.event,
            action="RESPONSE_REASSIGNED",
        )
        self.assertIn("S3", reassignment_log.details)
        self.assertIn(
            "Engenheiro responsável de turno",
            reassignment_log.details,
        )
        self.assertIn("S4", reassignment_log.details)
        self.assertIn(
            "Engenheiro responsável de segurança",
            reassignment_log.details,
        )

        # Terceiro: encerrar o evento
        response = self.client.post(
            action_url,
            {
                "action": "close",
                "details": "Acções concluídas e verificadas.",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.event.refresh_from_db()
        self.assertEqual(self.event.status, "CLOSED")
        self.assertIsNotNone(self.event.closed_at)

        # Confirmar os quatro registos de auditoria
        logs = TARPEventLog.objects.filter(
            event=self.event
        ).order_by("performed_at")

        self.assertEqual(logs.count(), 4)

        self.assertEqual(
            list(logs.values_list("action", flat=True)),
            [
                "ACKNOWLEDGED",
                "RESPONSE_ASSIGNED",
                "RESPONSE_REASSIGNED",
                "CLOSED",
            ],
        )


class MonitoringAlertWorkflowTests(LifecycleTestBase):
    """Testes do ciclo de vida e da auditoria dos alertas."""

    def setUp(self):
        super().setUp()

        self.parameter = MonitoringParameter.objects.create(
            code="ALERT-WORKFLOW-TEST",
            name="Variável de teste do ciclo de alertas",
            category="GEOTECHNICAL",
            unit="mm",
            instrument_required=False,
            is_active=True,
        )

    def create_alert(self, facility=None, company=None):
        facility = facility or self.facility

        reading = MonitoringReading.objects.create(
            facility=facility,
            parameter=self.parameter,
            observed_at=timezone.now(),
            value=Decimal("8"),
            unit="mm",
            interpretation="YELLOW",
            entered_by=self.staff,
        )

        alert = create_monitoring_alert(reading)

        self.assertIsNotNone(alert)
        return alert

    def test_fluxo_completo_do_alerta_e_historico(self):
        alert = self.create_alert()

        self.assertEqual(alert.status, "OPEN")
        self.assertEqual(
            alert.audit_history.count(),
            1,
        )
        self.assertEqual(
            alert.audit_history.first().action,
            "CREATED",
        )

        alert = acknowledge_monitoring_alert(
            alert,
            self.editor,
            "Alerta analisado pela equipa técnica.",
        )
        self.assertEqual(alert.status, "ACKNOWLEDGED")
        self.assertIsNotNone(alert.acknowledged_at)

        alert = assign_monitoring_alert(
            alert,
            self.editor,
            "Engenheiro responsável de turno",
            "Responsabilidade atribuída para investigação.",
        )
        self.assertEqual(
            alert.responsible,
            "Engenheiro responsável de turno",
        )

        alert = record_monitoring_alert_action(
            alert,
            self.editor,
            "Inspecção do instrumento e verificação da leitura.",
        )
        self.assertIn(
            "Inspecção do instrumento",
            alert.action_taken,
        )

        alert = close_monitoring_alert(
            alert,
            self.editor,
            "Condição avaliada e medidas correctivas concluídas.",
        )

        self.assertEqual(alert.status, "CLOSED")
        self.assertIsNotNone(alert.closed_at)
        self.assertEqual(alert.responsible, "Engenheiro responsável de turno")
        self.assertIn("Justificação de encerramento", alert.action_taken)

        actions = list(
            alert.audit_history.order_by("pk").values_list(
                "action",
                flat=True,
            )
        )
        self.assertEqual(
            actions,
            [
                "CREATED",
                "ACKNOWLEDGED",
                "ASSIGNED",
                "ACTION_RECORDED",
                "CLOSED",
            ],
        )

        closing_log = alert.audit_history.get(action="CLOSED")
        self.assertEqual(closing_log.performed_by, self.editor)
        self.assertEqual(closing_log.status_before, "ACKNOWLEDGED")
        self.assertEqual(closing_log.status_after, "CLOSED")

    def test_transicoes_invalidas_sao_rejeitadas(self):
        alert = self.create_alert()

        with self.assertRaises(ValidationError):
            record_monitoring_alert_action(
                alert,
                self.editor,
                "Tentativa de intervenção antes do reconhecimento.",
            )

        with self.assertRaises(ValidationError):
            close_monitoring_alert(
                alert,
                self.editor,
                "Tentativa de encerramento antes do reconhecimento.",
            )

        acknowledge_monitoring_alert(
            alert,
            self.editor,
            "Alerta reconhecido para análise.",
        )

        with self.assertRaises(ValidationError):
            acknowledge_monitoring_alert(
                alert,
                self.editor,
                "Tentativa de reconhecimento duplicado.",
            )

        self.assertEqual(
            alert.audit_history.filter(action="ACKNOWLEDGED").count(),
            1,
        )

    def test_encerramento_exige_responsavel_atribuido(self):
        alert = self.create_alert()

        alert = acknowledge_monitoring_alert(
            alert,
            self.editor,
            "Alerta reconhecido.",
        )

        with self.assertRaises(ValidationError):
            close_monitoring_alert(
                alert,
                self.editor,
                "Tentativa de encerramento sem responsável.",
            )

        alert.refresh_from_db()
        self.assertEqual(alert.status, "ACKNOWLEDGED")
        self.assertIsNone(alert.closed_at)
        self.assertFalse(
            alert.audit_history.filter(action="CLOSED").exists()
        )

    def test_historico_de_auditoria_e_imutavel(self):
        alert = self.create_alert()
        log = alert.audit_history.first()

        log.details = "Tentativa de alteração do histórico."
        with self.assertRaises(ValidationError):
            log.save()

        with self.assertRaises(ValidationError):
            log.delete()

        with self.assertRaises(ValidationError):
            MonitoringAlertLog.objects.filter(
                pk=log.pk
            ).update(details="Alteração em massa.")

        with self.assertRaises(ValidationError):
            MonitoringAlertLog.objects.filter(
                pk=log.pk
            ).delete()

        with self.assertRaises(ValidationError):
            MonitoringAlertLog.objects.bulk_update(
                [log],
                ["details"],
            )

        new_log = MonitoringAlertLog(
            alert=alert,
            action="CREATED",
            details="Tentativa de inserção em massa.",
        )
        with self.assertRaises(ValidationError):
            MonitoringAlertLog.objects.bulk_create([new_log])

        log.refresh_from_db()
        self.assertNotEqual(
            log.details,
            "Tentativa de alteração do histórico.",
        )
        self.assertEqual(
            alert.audit_history.count(),
            1,
        )

    def test_empresa_nao_pode_gerir_alerta_de_outra_empresa(self):
        other_company = MiningCompany.objects.create(
            name="Outra Empresa ENT-GIS",
            country="Angola",
            province="Lunda Sul",
            is_simulated=True,
        )

        other_facility = TailingsFacility.objects.create(
            company=other_company,
            name="Instalação de Outra Empresa",
            province="Lunda Sul",
            municipality="Saurimo",
            lifecycle_stage="CONSTRUCTION",
            is_simulated=True,
        )

        other_alert = self.create_alert(facility=other_facility)

        self.client.force_login(self.editor)

        response = self.client.post(
            reverse(
                "facilities:monitoring_alert_action",
                args=[other_alert.pk],
            ),
            {
                "action": "acknowledge",
                "details": "Tentativa de acesso cruzado.",
            },
        )

        self.assertEqual(response.status_code, 404)

        other_alert.refresh_from_db()
        self.assertEqual(other_alert.status, "OPEN")
        self.assertFalse(
            other_alert.audit_history.filter(
                action="ACKNOWLEDGED"
            ).exists()
        )

    def test_editor_pode_reconhecer_alerta_da_sua_empresa(self):
        alert = self.create_alert()

        self.client.force_login(self.editor)

        response = self.client.post(
            reverse(
                "facilities:monitoring_alert_action",
                args=[alert.pk],
            ),
            {
                "action": "acknowledge",
                "details": "Alerta analisado pelo editor da empresa.",
            },
        )

        self.assertEqual(response.status_code, 302)

        alert.refresh_from_db()
        self.assertEqual(alert.status, "ACKNOWLEDGED")
        self.assertTrue(
            alert.audit_history.filter(
                action="ACKNOWLEDGED",
                performed_by=self.editor,
            ).exists()
        )
