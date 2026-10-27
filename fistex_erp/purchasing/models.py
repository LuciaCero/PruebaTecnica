from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from decimal import Decimal
from django.db.models import DecimalField, F, Q, Sum
from django.utils import timezone


# ==========================================
# Proveedor
# ==========================================

# Restricción para el numero del CIF/NIF
LONGITUD_CIF_NIF = 9

def normalizar_cif_nif(valor: str) -> str:
    """Quita espacios y guiones y pasa a mayúsculas: 'b-123 456' -> 'B123456'"""
    return "".join(valor.split()).replace("-", "").upper()

class Proveedor(models.Model):
    nombre = models.CharField("nombre comercial", max_length=200)
    cif_nif = models.CharField(
        "CIF/NIF", 
        max_length=20, 
        unique=True,
        help_text=f"Debe tener {LONGITUD_CIF_NIF} caracteres. Se ignoran espacios y guiones.")
    email = models.EmailField("email")
    activo = models.BooleanField("activo", default=True)
    fecha_alta = models.DateTimeField("fecha de alta", auto_now_add=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "proveedor"
        verbose_name_plural = "proveedores"
        constraints = [
            # Restriccion: Debe ser alfanumerico y un numero de digitos concreto
            models.CheckConstraint(
                condition=models.Q(cif_nif__regex=rf"^[A-Z0-9]{LONGITUD_CIF_NIF}$"),
                name="cif_nif_formato_valido",
            )
        ]

    def __str__(self):
        return f"{self.nombre} ({self.cif_nif})"

    def clean(self):
        normalizado = normalizar_cif_nif(self.cif_nif)

        # Restriccion: Debe ser alfanumerico y numero de digitos
        if ( 
            len(normalizado) != LONGITUD_CIF_NIF
            or not (normalizado.isascii() and normalizado.isalnum())
        ):
            raise ValidationError(
                {"cif_nif": f"El CIF/NIF debe tener {LONGITUD_CIF_NIF} caracteres alfanuméricos."}
            )
        
        self.cif_nif = normalizado

    def save(self, *args, **kwargs):
        # Hacemos un full clean antes de guardar los datos
        self.full_clean()
        super().save(*args, **kwargs)


# ==========================================
# Producto
# ==========================================

def normalizar_referencia(valor: str) -> str:
    """Quita espacios y pasa a mayúsculas: ' ab 12 ' -> 'AB12'."""
    return "".join(valor.split()).upper()

class Producto(models.Model):
    referencia = models.CharField("referencia", max_length=200, unique=True)
    nombre = models.CharField("nombre comercial", max_length=200)
    precio_compra = models.DecimalField(
        "precio de compra",
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))]
    )
    activo = models.BooleanField("activo", default=True)

    class Meta:
        ordering = ["referencia"]
        verbose_name = "producto"
        verbose_name_plural = "productos"
        constraints = [
            # Restriccion: el precio nunca puede ser negativo
            models.CheckConstraint(
                condition=Q(precio_compra__gte=0),
                name="producto_precio_compra_no_negativo",
            ),
        ]

    def __str__(self):
        return f"{self.referencia} - {self.nombre}"

    def clean(self):
        # Normaliza antes de validate_unique() para detectar duplicados por formato
        self.referencia = normalizar_referencia(self.referencia)

    def save(self, *args, **kwargs):
        # Hacemos un full clean antes de guardar los datos
        self.full_clean()
        super().save(*args, **kwargs)

