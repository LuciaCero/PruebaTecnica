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
    email = models.EmailField("correo electrónico")
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
    return "".join((valor or "").split()).upper()


class ProductoQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError(
            "Los productos deben modificarse mediante save() para validar sus campos."
        )

    def bulk_create(self, objs, **kwargs):
        raise ValidationError(
            "Los productos deben crearse mediante save() para validar sus campos."
        )

    def bulk_update(self, objs, fields, **kwargs):
        raise ValidationError(
            "Los productos deben modificarse mediante save() para validar sus campos."
        )


class Producto(models.Model):
    objects = ProductoQuerySet.as_manager()

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
            models.CheckConstraint(
                condition=~Q(referencia=""),
                name="producto_referencia_no_vacia",
            ),
        ]

    def __str__(self):
        return f"{self.referencia} - {self.nombre}"

    def clean(self):
        # Normaliza antes de validate_unique() para detectar duplicados por formato
        self.referencia = normalizar_referencia(self.referencia)
        if not self.referencia:
            raise ValidationError(
                {"referencia": "La referencia no puede quedar vacía tras normalizarla."}
            )

    def save(self, *args, **kwargs):
        self.referencia = normalizar_referencia(self.referencia)
        if not self.referencia:
            raise ValidationError(
                {"referencia": "La referencia no puede quedar vacía tras normalizarla."}
            )
        self.full_clean()
        super().save(*args, **kwargs)


# ==========================================
# Pedido de compra
# ==========================================


def _validar_borrado_pedidos(pedidos):
    pedidos_no_borrador = [
        pedido for pedido in pedidos if pedido.estado != PedidoCompra.Estado.BORRADOR
    ]
    if pedidos_no_borrador:
        impedimentos = ", ".join(
            f"{pedido} ({pedido.get_estado_display()})"
            for pedido in pedidos_no_borrador
        )
        raise ValidationError(
            "No se puede borrar la selección porque incluye pedidos que no están "
            "en estado Borrador. "
            "No se eliminó ningún pedido. "
            f"Pedidos que lo impiden: {impedimentos}."
        )


class PedidoCompraQuerySet(models.QuerySet):
    def validar_borrado(self):
        _validar_borrado_pedidos(self)

    def update(self, **kwargs):
        raise ValidationError(
            "Los pedidos deben modificarse mediante save() o una transición."
        )

    def bulk_create(self, objs, **kwargs):
        raise ValidationError(
            "Los pedidos deben crearse mediante save() para validar su estado."
        )

    def bulk_update(self, objs, fields, **kwargs):
        raise ValidationError(
            "Los pedidos deben modificarse mediante save() o una transición."
        )

    def delete(self):
        with transaction.atomic():
            pedidos = list(self.select_for_update().order_by("pk"))
            _validar_borrado_pedidos(pedidos)
            return super().delete()


class PedidoCompra(models.Model):
    objects = PedidoCompraQuerySet.as_manager()

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
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    estado__in=[
                        "borrador",
                        "confirmado",
                        "recibido",
                        "cancelado",
                    ]
                ),
                name="pedido_estado_valido",
            ),
        ]

    def __str__(self):
        return self.numero or "Pedido sin guardar"
 
    def save(self, *args, **kwargs):
        with transaction.atomic():
            pedido_actual = None
            if self.pk is not None:
                pedido_actual = type(self).objects.select_for_update().get(pk=self.pk)
                update_fields = kwargs.get("update_fields")
                if update_fields is not None and "estado" in update_fields:
                    raise ValidationError(
                        "El estado solo se puede modificar mediante una transición."
                    )
                if pedido_actual.estado != self.Estado.BORRADOR:
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
                self.estado = pedido_actual.estado
            elif self.estado != self.Estado.BORRADOR:
                raise ValidationError(
                    "Un pedido nuevo debe comenzar en estado borrador."
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
            ):
                proveedor = Proveedor.objects.select_for_update().filter(
                    pk=self.proveedor_id,
                ).first()
                if proveedor is None or not proveedor.activo:
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
            pedido_actual = type(self).objects.select_for_update().get(pk=self.pk)
            if nuevo not in self.TRANSICIONES.get(pedido_actual.estado, set()):
                raise ValidationError(
                    f"No se puede pasar un pedido de '{pedido_actual.estado}' a '{nuevo}'."
                )
            pedido_actual._validar_precondiciones_transicion(nuevo)
            queryset = type(self).objects.filter(
                pk=pedido_actual.pk,
                estado=pedido_actual.estado,
            )
            actualizado = models.QuerySet.update(queryset, estado=nuevo)
            if actualizado != 1:
                raise ValidationError(
                    "El estado del pedido cambió durante la transición."
                )
            self.estado = nuevo

    def _validar_precondiciones_transicion(self, nuevo):
        if nuevo != self.Estado.CONFIRMADO:
            return
        if not self.lineas.exists():
            raise ValidationError(
                "No se puede confirmar un pedido que no tiene ninguna linea"
            )
        proveedor = Proveedor.objects.select_for_update().filter(
            pk=self.proveedor_id,
        ).first()
        if proveedor is None or not proveedor.activo:
            raise ValidationError(
                "No se puede confirmar un pedido de un proveedor inactivo"
            )
        productos_ids = list(
            self.lineas.values_list("producto_id", flat=True).distinct()
        )
        productos = list(
            Producto.objects.select_for_update()
            .filter(pk__in=productos_ids)
            .order_by("pk")
        )
        if len(productos) != len(productos_ids):
            raise ValidationError(
                "No se puede confirmar un pedido con productos que ya no existen."
            )
        if any(not producto.activo for producto in productos):
            raise ValidationError(
                "No se puede confirmar un pedido con productos inactivos."
            )

    def confirmar(self):
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
            producto_actual = Producto.objects.select_for_update().filter(
                pk=producto.pk,
            ).first()
            if producto_actual is None or not producto_actual.activo:
                raise ValidationError(
                    {"producto": "No se puede añadir un producto inactivo a un pedido."}
                )
            linea, creada = LineaPedido.objects.get_or_create(
                pedido=pedido,
                producto=producto_actual,
                defaults={
                    "cantidad": cantidad,
                    "precio_unitario": Decimal(str(producto_actual.precio_compra)),
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
        if self.pk is None:
            return super().delete(*args, **kwargs)
        with transaction.atomic():
            pedido_actual = type(self).objects.select_for_update().get(pk=self.pk)
            _validar_borrado_pedidos([pedido_actual])
            return super().delete(*args, **kwargs)

# ==========================================
# Línea de pedido
# ==========================================

class LineaPedidoQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError(
            "Las líneas deben modificarse mediante save() para validar el pedido."
        )

    def bulk_create(self, objs, **kwargs):
        raise ValidationError(
            "Las líneas deben crearse mediante save() para validar el pedido."
        )

    def bulk_update(self, objs, fields, **kwargs):
        raise ValidationError(
            "Las líneas deben modificarse mediante save() para validar el pedido."
        )

    def delete(self):
        with transaction.atomic():
            filas_iniciales = dict(self.values_list("pk", "pedido_id"))
            if not filas_iniciales:
                return 0, {}

            pedidos_ids = set(filas_iniciales.values())
            pedidos = list(
                PedidoCompra.objects.select_for_update()
                .filter(pk__in=pedidos_ids)
                .order_by("pk")
            )
            pedidos_por_id = {pedido.pk: pedido for pedido in pedidos}
            if len(pedidos_por_id) != len(pedidos_ids):
                raise ValidationError("El pedido asociado a una línea no existe.")

            filas_actuales = dict(
                LineaPedido.objects.filter(pk__in=filas_iniciales)
                .values_list("pk", "pedido_id")
            )
            if any(
                filas_actuales.get(linea_id) != pedido_id
                for linea_id, pedido_id in filas_iniciales.items()
                if linea_id in filas_actuales
            ):
                raise ValidationError(
                    "Una línea cambió mientras se estaba eliminando. Inténtalo de nuevo."
                )

            for pedido in pedidos:
                pedido.validar_pedido_editable()

            seleccion = self.filter(pk__in=filas_iniciales)
            return models.QuerySet.delete(seleccion)


class LineaPedido(models.Model):
    objects = LineaPedidoQuerySet.as_manager()

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
        with transaction.atomic():
            pedido_original_id = None
            if self.pk is not None:
                pedido_original_id = (
                    type(self).objects.filter(pk=self.pk)
                    .values_list("pedido_id", flat=True)
                    .first()
                )

            pedidos_ids = {
                pedido_id
                for pedido_id in (pedido_original_id, self.pedido_id)
                if pedido_id is not None
            }
            pedidos = list(
                PedidoCompra.objects.select_for_update()
                .filter(pk__in=pedidos_ids)
                .order_by("pk")
            )
            pedidos_por_id = {pedido.pk: pedido for pedido in pedidos}

            if len(pedidos_por_id) != len(pedidos_ids):
                raise ValidationError("El pedido asociado a la línea no existe.")

            if self.pk is not None:
                pedido_actual_id = (
                    type(self).objects.filter(pk=self.pk)
                    .values_list("pedido_id", flat=True)
                    .first()
                )
                if pedido_actual_id != pedido_original_id:
                    raise ValidationError(
                        "La línea cambió mientras se estaba guardando. Inténtalo de nuevo."
                    )

            for pedido in pedidos:
                pedido.validar_pedido_editable()

            if self.producto_id:
                producto = Producto.objects.select_for_update().filter(
                    pk=self.producto_id,
                ).first()
                if producto is None or not producto.activo:
                    raise ValidationError(
                        {"producto": "No se puede añadir un producto inactivo a un pedido."}
                    )
            super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            pedido_id = self.pedido_id
            if self.pk is not None:
                pedido_id = (
                    type(self).objects.filter(pk=self.pk)
                    .values_list("pedido_id", flat=True)
                    .first()
                )

            if pedido_id is not None:
                pedido = PedidoCompra.objects.select_for_update().get(pk=pedido_id)
                if self.pk is not None:
                    pedido_actual_id = (
                        type(self).objects.filter(pk=self.pk)
                        .values_list("pedido_id", flat=True)
                        .first()
                    )
                    if pedido_actual_id != pedido_id:
                        raise ValidationError(
                            "La línea cambió mientras se estaba eliminando. Inténtalo de nuevo."
                        )
                pedido.validar_pedido_editable()

            return super().delete(*args, **kwargs)
 
    @property
    def subtotal(self) -> Decimal:
        if self.cantidad is None or self.precio_unitario is None:
            return Decimal("0.00")
        return self.cantidad * self.precio_unitario