from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from facilities.models import (
    GISTMTopic, GISTMPrinciple, GISTMRequirement,
    GISTMAssessment, GISTMRequirementAssessment, TailingsFacility
)


TOPICS = [
    ("I", "Comunidades afectadas"),
    ("II", "Base de conhecimento integrada"),
    ("III", "Concepção, construção, operação e monitorização"),
    ("IV", "Gestão e governação"),
    ("V", "Resposta a emergências e recuperação a longo prazo"),
    ("VI", "Divulgação pública e acesso à informação"),
]

PRINCIPLES = [
    (1, "I", "Respeitar os direitos das pessoas afectadas e assegurar o seu envolvimento significativo."),
    (2, "II", "Desenvolver e manter uma base de conhecimento interdisciplinar."),
    (3, "II", "Utilizar a base de conhecimento para fundamentar as decisões."),
    (4, "III", "Desenvolver planos e critérios de projecto para minimizar riscos."),
    (5, "III", "Desenvolver um projecto robusto que integre a base de conhecimento."),
    (6, "III", "Planear, construir e operar a instalação para gerir os riscos."),
    (7, "III", "Conceber, implementar e operar sistemas de monitorização."),
    (8, "IV", "Estabelecer políticas, sistemas e responsabilidades para a segurança."),
    (9, "IV", "Nomear e capacitar o Engenheiro de Registo (EoR)."),
    (10, "IV", "Estabelecer níveis de revisão e um sistema de qualidade e gestão de riscos."),
    (11, "IV", "Promover uma cultura organizacional de aprendizagem e comunicação."),
    (12, "IV", "Estabelecer processos de comunicação de preocupações e protecção de denunciantes."),
    (13, "V", "Preparar a resposta a emergências decorrentes de falhas."),
    (14, "V", "Preparar a recuperação a longo prazo após uma falha catastrófica."),
    (15, "VI", "Divulgar publicamente informações sobre a instalação de rejeitados."),
]

# Quantidade oficial de requisitos por princípio: total = 77.
REQUIREMENT_COUNTS = {
    1: 4, 2: 4, 3: 4, 4: 8, 5: 8,
    6: 6, 7: 5, 8: 7, 9: 5, 10: 7,
    11: 5, 12: 2, 13: 4, 14: 5, 15: 3,
}


class Command(BaseCommand):
    help = "Carrega a estrutura central dos 6 temas, 15 princípios e 77 requisitos GISTM."

    @transaction.atomic
    def handle(self, *args, **options):
        if sum(REQUIREMENT_COUNTS.values()) != 77:
            raise CommandError("A distribuição dos requisitos não totaliza 77.")

        topics = {}
        for order, (code, title) in enumerate(TOPICS, start=1):
            topic, _ = GISTMTopic.objects.update_or_create(
                code=code,
                defaults={"title": title, "order": order}
            )
            topics[code] = topic

        principles = {}
        for number, topic_code, title in PRINCIPLES:
            principle, _ = GISTMPrinciple.objects.update_or_create(
                number=number,
                defaults={"topic": topics[topic_code], "title": title}
            )
            principles[number] = principle

        created = 0
        for number, count in REQUIREMENT_COUNTS.items():
            for index in range(1, count + 1):
                code = f"{number}.{index}"
                _, was_created = GISTMRequirement.objects.get_or_create(
                    code=code,
                    defaults={
                        "principle": principles[number],
                        "title": f"Requisito GISTM {code}",
                        "summary": (
                            "Referência do requisito oficial. Inserir ou validar "
                            "o texto e a interpretação com base na versão oficial "
                            "do GISTM antes de efectuar a avaliação."
                        ),
                        "source_reference": "GISTM — Agosto de 2020"
                    }
                )
                created += int(was_created)

        if GISTMRequirement.objects.filter(is_active=True).count() != 77:
            raise CommandError(
                "O catálogo activo não contém exactamente 77 requisitos. "
                "Nenhuma matriz individual foi criada."
            )

        # Criar a primeira matriz para todas as instalações já registadas.
        for facility in TailingsFacility.objects.all():
            assessment, created_assessment = GISTMAssessment.objects.get_or_create(
                facility=facility,
                version=1,
                defaults={
                    "assessment_type": "SELF",
                    "status": "NOT_STARTED",
                    "scope": "Matriz inicial dos 77 requisitos GISTM."
                }
            )
            if created_assessment:
                GISTMRequirementAssessment.objects.bulk_create([
                    GISTMRequirementAssessment(
                        assessment=assessment,
                        requirement=requirement,
                        status="NOT_ASSESSED"
                    )
                    for requirement in GISTMRequirement.objects.filter(is_active=True)
                ])

        self.stdout.write(self.style.SUCCESS(
            f"Catálogo GISTM: {GISTMTopic.objects.count()} temas, "
            f"{GISTMPrinciple.objects.count()} princípios e "
            f"{GISTMRequirement.objects.filter(is_active=True).count()} requisitos."
        ))
        self.stdout.write(self.style.SUCCESS(
            f"Instalações registadas: {TailingsFacility.objects.count()}. "
            "Matrizes iniciais verificadas/criadas."
        ))
        self.stdout.write(
            self.style.WARNING(
                "NOTA: os códigos e a distribuição estão estruturados; "
                "os textos oficiais completos ainda devem ser conferidos/importados "
                "da edição oficial antes de qualquer avaliação de conformidade."
            )
        )
