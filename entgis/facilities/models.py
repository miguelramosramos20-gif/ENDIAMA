
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

    is_simulated = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Instalação de Rejeitados"
        verbose_name_plural = "Instalações de Rejeitados"

    def __str__(self):
        return f"{self.name} - {self.company.name}"