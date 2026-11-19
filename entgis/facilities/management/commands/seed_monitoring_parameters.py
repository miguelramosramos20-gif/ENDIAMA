from django.core.management.base import BaseCommand
from facilities.models import MonitoringParameter


PARAMETERS = [
    # Hidráulica
    ("WATER_LEVEL", "Nível da água na albufeira", "HYDRAULIC", "m", True),
    ("FREEBOARD", "Bordo livre", "HYDRAULIC", "m", False),
    ("POND_DISTANCE", "Distância da albufeira à crista", "HYDRAULIC", "m", False),
    ("BEACH_WIDTH", "Largura da praia de rejeitados", "HYDRAULIC", "m", False),
    ("SEEPAGE_FLOW", "Caudal de percolação", "HYDRAULIC", "m3/h", True),
    ("SEEPAGE_TURBIDITY", "Turbidez da água de percolação", "HYDRAULIC", "NTU", True),
    ("DRAIN_FLOW", "Caudal dos drenos", "HYDRAULIC", "m3/h", True),

    # Piezometria
    ("PIEZO_LEVEL", "Nível piezométrico", "PIEZOMETRIC", "m", True),
    ("PORE_PRESSURE", "Pressão intersticial", "PIEZOMETRIC", "kPa", True),
    ("HYDRAULIC_GRADIENT", "Gradiente hidráulico", "PIEZOMETRIC", "-", False),

    # Geotecnia e deformação
    ("HORIZONTAL_DISP", "Deslocamento horizontal", "GEOTECHNICAL", "mm", True),
    ("VERTICAL_DISP", "Deslocamento vertical / assentamento", "GEOTECHNICAL", "mm", True),
    ("DISP_VELOCITY", "Velocidade de deslocamento", "GEOTECHNICAL", "mm/day", False),
    ("DISP_ACCELERATION", "Aceleração do deslocamento", "GEOTECHNICAL", "mm/day2", False),
    ("INCLINOMETER", "Deslocamento por inclinómetro", "GEOTECHNICAL", "mm", True),
    ("CREST_MOVEMENT", "Movimento da crista", "GEOTECHNICAL", "mm", True),

    # Meteorologia
    ("RAIN_DAILY", "Precipitação diária", "METEOROLOGICAL", "mm", False),
    ("RAIN_CUMULATIVE", "Precipitação acumulada", "METEOROLOGICAL", "mm", False),
    ("RAIN_INTENSITY", "Intensidade da precipitação", "METEOROLOGICAL", "mm/h", False),
    ("AIR_TEMPERATURE", "Temperatura do ar", "METEOROLOGICAL", "°C", False),

    # Operacional
    ("TAILINGS_VOLUME", "Volume de rejeitados depositados", "OPERATIONAL", "m3", False),
    ("DEPOSITION_RATE", "Taxa de deposição de rejeitados", "OPERATIONAL", "m3/h", False),
    ("SLURRY_DENSITY", "Densidade da polpa", "OPERATIONAL", "t/m3", False),
    ("FEED_FLOW", "Caudal de alimentação", "OPERATIONAL", "m3/h", False),
    ("STORED_WATER", "Volume de água armazenada", "OPERATIONAL", "m3", False),
    ("PUMP_STATUS", "Estado operacional das bombas", "OPERATIONAL", "estado", False),

    # Inspecção visual — registo qualitativo codificado
    ("CRACKS", "Fissuras e abatimentos observados", "VISUAL", "registo", False),
    ("EROSION", "Erosão superficial observada", "VISUAL", "registo", False),
    ("WET_AREAS", "Zonas húmidas ou surgências", "VISUAL", "registo", False),
    ("SLOPE_CONDITION", "Condição dos taludes", "VISUAL", "registo", False),
    ("DRAIN_CONDITION", "Condição dos órgãos de drenagem", "VISUAL", "registo", False),
]


class Command(BaseCommand):
    help = "Cria o catálogo inicial de variáveis de monitorização ENT-GIS."

    def handle(self, *args, **options):
        created = 0
        updated = 0

        for code, name, category, unit, instrument_required in PARAMETERS:
            obj, was_created = MonitoringParameter.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "category": category,
                    "unit": unit,
                    "instrument_required": instrument_required,
                    "is_active": True,
                },
            )
            created += int(was_created)
            updated += int(not was_created)

        self.stdout.write(
            self.style.SUCCESS(
                f"Catálogo concluído. Novas variáveis: {created}; actualizadas: {updated}."
            )
        )
