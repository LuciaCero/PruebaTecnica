from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from decimal import Decimal
from django.db.models import DecimalField, F, Q, Sum
from django.utils import timezone


# ==========================================
# Proveedor
# ==========================================

def normalizar_cif_nif(valor: str) -> str:
    return valor.upper()

class Proveedor(models.Model):
    nombre = models.CharField("nombre comercial", max_length=200)
    cif_nif = models.CharField(
        "CIF/NIF",
        max_length=9,
        unique=True,
        help_text="Máximo 9 caracteres.",
    )
    email = models.EmailField("email")
    activo = models.BooleanField("activo", default=True)
    fecha_alta = models.DateTimeField("fecha de alta", auto_now_add=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "proveedor"
        verbose_name_plural = "proveedores"

    def __str__(self):
        return f"{self.nombre} ({self.cif_nif})"

    def clean(self):
        self.cif_nif = normalizar_cif_nif(self.cif_nif)

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
        self.referencia = normalizar_referencia(self.referencia)
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
        with transaction.atomic():
            pedido_actual = None
            if self.pk is not None:
                pedido_actual = type(self).objects.select_for_update().get(pk=self.pk)
                if pedido_actual.estado != self.Estado.BORRADOR:
                    update_fields = kwargs.get("update_fields")
                    campos_cabecera = {
                        "proveedor_id": {"proveedor", "proveedor_id"},
                        "fecha": {"fecha"},
                        "numero": {"numero"},
                    }
                    for campo, nombres in campos_cabecera.items():
                        if update_fields is not None and not nombres.intersection(update_fields):
                            continue
                        if getattr(self, campo) != getattr(pedido_actual, campo):
                            raise ValidationError(
                                "No se puede modificar la cabecera de un pedido "
                                "que ya no está en borrador."
                            )

            update_fields = kwargs.get("update_fields")
            proveedor_se_guarda = (
                pedido_actual is None
                or update_fields is None
                or {"proveedor", "proveedor_id"}.intersection(update_fields)
            )
            proveedor_cambia = (
                pedido_actual is None
                or self.proveedor_id != pedido_actual.proveedor_id
            )
            if (
                proveedor_se_guarda
                and proveedor_cambia
                and self.proveedor_id
                and not Proveedor.objects.filter(
                    pk=self.proveedor_id,
                    activo=True,
                ).exists()
            ):
                raise ValidationError(
                    {"proveedor": "No se puede asignar un proveedor inactivo a un pedido."}
                )

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

    TRANSICIONES = {
        Estado.BORRADOR: {Estado.CONFIRMADO, Estado.CANCELADO},
        Estado.CONFIRMADO: {Estado.RECIBIDO, Estado.CANCELADO},
        Estado.RECIBIDO: set(),
        Estado.CANCELADO: set(),
    }

    def cambiar_estado(self, nuevo):
        with transaction.atomic():
            actual = type(self).objects.select_for_update().get(pk=self.pk).estado
            if nuevo not in self.TRANSICIONES[actual]:
                raise ValidationError(
                    f"No se puede pasar un pedido de '{actual}' a '{nuevo}'."
                )
            self.estado = nuevo
            self.save(update_fields=["estado"])

    def confirmar(self):
        if self.lineas.count() <= 0:
            raise ValidationError("No se puede confirmar un pedido que no tiene ninguna linea")
        if not Proveedor.objects.filter(pk=self.proveedor_id, activo=True).exists():
            raise ValidationError("No se puede confirmar un pedido de un proveedor inactivo")
        if self.lineas.filter(producto__activo=False).exists():
            raise ValidationError("No se puede confirmar un pedido con productos inactivos.")
        self.cambiar_estado(self.Estado.CONFIRMADO)

    def recibir(self):
        self.cambiar_estado(self.Estado.RECIBIDO)

    def cancelar(self):
        self.cambiar_estado(self.Estado.CANCELADO)

    def agregar_producto(self, producto, cantidad=1):
        if cantidad < 1:
            raise ValidationError("La cantidad debe ser al menos 1.")
        if self.pk is None:
            raise ValidationError("Guarda el pedido antes de añadir productos.")

        with transaction.atomic():
            pedido = type(self).objects.select_for_update().get(pk=self.pk)
            pedido.validar_pedido_editable()
            linea, creada = LineaPedido.objects.get_or_create(
                pedido=pedido,
                producto=producto,
                defaults={
                    "cantidad": cantidad,
                    "precio_unitario": Decimal(str(producto.precio_compra)),
                },
            )
            if not creada:
                linea.cantidad += cantidad
                linea.save(update_fields=["cantidad"])

        return linea

    def validar_pedido_editable(self):
        if self.pk is None:
            return
        estado = type(self).objects.values_list("estado", flat=True).get(pk=self.pk)
        if estado != PedidoCompra.Estado.BORRADOR:
            raise ValidationError("Solo se pueden modificar las líneas de un pedido en borrador.")

    def clean(self):
        if self.proveedor_id and not self.proveedor.activo:
            raise ValidationError("No se puede crear un pedido de un proveedor inactivo")
        self.validar_pedido_editable()

    def delete(self, *args, **kwargs):
        self.validar_pedido_editable()
        return super().delete(*args, **kwargs)

# ==========================================
# Línea de pedido
# ==========================================

class LineaPedido(models.Model):
    pedido = models.ForeignKey(
        PedidoCompra,
        on_delete=models.CASCADE,   # Las líneas no tienen sentido sin su pedido
        related_name="lineas",
        verbose_name="pedido",
    )

    producto = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT,   # No se puede borrar un producto con historial
        related_name="lineas_pedido",
        verbose_name="producto",
    )

    cantidad = models.PositiveIntegerField(
        "cantidad",
        validators=[MinValueValidator(1)],  # No tendría sentido una linea de cantidad 0
    )

    # Precio propio de la línea (copiada en el momento del pedido)
    # No es una lectura en vivo de producto.precio_compra
    # Permite que el historial no cambie
    precio_unitario = models.DecimalField(
        "precio unitario",
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )

    class Meta:
        ordering = ["id"]
        verbose_name = "línea de pedido"
        verbose_name_plural = "líneas de pedido"
        constraints = [
            # Restriccion: tiene que haber al menos una linea
            models.CheckConstraint(
                condition=Q(cantidad__gte=1),
                name="linea_cantidad_minima_1",
            ),
            # Restriccion: el precio unitario debe ser positivo
            models.CheckConstraint(
                condition=Q(precio_unitario__gte=0),
                name="linea_precio_unitario_no_negativo",
            ),
            # Restriccion: un producto solo puede aparecer una vez por linea (si se quisieran mas se modifica la cantidad)
            models.UniqueConstraint(
                fields=["pedido", "producto"],
                name="linea_producto_unico_por_pedido",
            ),
        ]
 
    def __str__(self):
        return f"{self.producto} x {self.cantidad}"

    def validar_pedido_editable(self):
        pedidos_ids = {self.pedido_id}
        if self.pk is not None:
            pedido_original_id = (
                type(self).objects.filter(pk=self.pk)
                .values_list("pedido_id", flat=True)
                .first()
            )
            if pedido_original_id is not None:
                pedidos_ids.add(pedido_original_id)

        for pedido_id in pedidos_ids:
            if pedido_id is not None:
                PedidoCompra.objects.get(pk=pedido_id).validar_pedido_editable()

    def clean(self):
        self.validar_pedido_editable()
        if self.producto_id and not Producto.objects.filter(
            pk=self.producto_id,
            activo=True,
        ).exists():
            raise ValidationError(
                {"producto": "No se puede añadir un producto inactivo a un pedido."}
            )

    def save(self, *args, **kwargs):
        self.validar_pedido_editable()
        if self.producto_id and not Producto.objects.filter(
            pk=self.producto_id,
            activo=True,
        ).exists():
            raise ValidationError(
                {"producto": "No se puede añadir un producto inactivo a un pedido."}
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self.validar_pedido_editable()
        return super().delete(*args, **kwargs)
 
    @property
    def subtotal(self) -> Decimal:
        if self.cantidad is None or self.precio_unitario is None:
            return Decimal("0.00")
        return self.cantidad * self.precio_unitario