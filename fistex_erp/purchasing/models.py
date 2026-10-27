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


# ==========================================
# Pedido de compra
# ==========================================

class PedidoCompra(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = "borrador", "Borrador"
        CONFIRMADO = "confirmado", "Confirmado"
        RECIBIDO = "recibido", "Recibido"
        CANCELADO = "cancelado", "Cancelado"

    numero = models.CharField(
        "número de pedido",
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        editable=False,
    )

    proveedor = models.ForeignKey(
        Proveedor,
        on_delete=models.PROTECT,   # No se puede eliminar un proveedor con pedidos
        related_name="pedidos",
        verbose_name="proveedor",
    )

    fecha = models.DateField("fecha", default=timezone.localdate)

    estado = models.CharField(
        "estado",
        max_length=10,
        choices=Estado.choices,
        default=Estado.BORRADOR,
        editable=False,
    )

    class Meta:
        ordering = ["-fecha", "-id"]
        verbose_name = "pedido de compra"
        verbose_name_plural = "pedidos de compra"
 
    def __str__(self):
        return self.numero or "Pedido sin guardar"
 
    def save(self, *args, **kwargs):
        # Aseguramos ejecutar este bloque de manera atómica
        with transaction.atomic():
            super().save(*args, **kwargs)
            if not self.numero:
                self.numero = f"PC-{self.pk:06d}"
                super().save(update_fields=["numero"])

    @property
    def total(self) -> Decimal:
        """Total del pedido calculado en BD con el ORM (no se almacena)"""
        if self.pk is None:
            return Decimal("0.00")
        resultado = self.lineas.aggregate(
            total=Sum(
                F("cantidad") * F("precio_unitario"),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        )
        return resultado["total"] or Decimal("0.00")


# ==========================================
# Línea de pedido
# ==========================================

