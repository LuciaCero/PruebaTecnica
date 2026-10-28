from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from .models import Proveedor, PedidoCompra, Producto, LineaPedido
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import DecimalField, F, Sum
from unfold.decorators import display

# Register your models here.

@admin.register(Proveedor)
class ProveedorAdmin(ModelAdmin):
    list_display = ("nombre", "cif_nif", "email", "activo", "fecha_alta")
    search_fields = ("nombre", "cif_nif", "email")
    list_filter = ("activo",)

@admin.register(Producto)
class ProductoAdmin(ModelAdmin):
    list_display = ("referencia", "nombre", "precio_compra", "activo")
    search_fields = ("referencia", "nombre")
    list_filter = ("activo",)

class LineaPedidoInline(TabularInline):
    model = LineaPedido
    extra = 1
    fields = ("producto", "cantidad", "precio_unitario")

@admin.register(PedidoCompra)
class PedidoCompraAdmin(ModelAdmin):
    # Display de las lineas de pedido
    inlines = [LineaPedidoInline]

    # Columnas y filtros
    list_display = ("numero", "proveedor", "fecha", "estado_con_etiqueta", "total")
    search_fields = ("numero", "proveedor__nombre", "proveedor__cif_nif")
    list_filter = ("estado", "fecha", "proveedor")

    @display(
        description="Estado",
        label={
            PedidoCompra.Estado.BORRADOR: "warning",
            PedidoCompra.Estado.CONFIRMADO: "info",
            PedidoCompra.Estado.RECIBIDO: "success",
            PedidoCompra.Estado.CANCELADO: "danger",
        },
    )
    def estado_con_etiqueta(self, obj):
        return obj.estado, obj.get_estado_display()

    # Acciones
    actions = ("confirmar_pedidos", "recibir_pedidos", "cancelar_pedidos")

    def confirmar_pedidos(self, request, queryset):
        self.aplicar_cambio_estado(request, queryset, "confirmar")

    def recibir_pedidos(self, request, queryset):
        self.aplicar_cambio_estado(request, queryset, "recibir")

    def cancelar_pedidos(self, request, queryset):
        self.aplicar_cambio_estado(request, queryset, "cancelar")

    def aplicar_cambio_estado(self, request, queryset, metodo):
        correctos = 0

        for pedido in queryset:
            try:
                getattr(pedido, metodo)()
            except ValidationError as error:
                self.message_user(
                    request,
                    f"{pedido}: {error}",
                    level=messages.ERROR,
                )
            else:
                correctos += 1

        if correctos:
            self.message_user(
                request,
                f"Se actualizaron {correctos} pedido(s).",
                level=messages.SUCCESS,
            )

def dashboard_callback(request, context):
    confirmados = PedidoCompra.objects.filter(
        estado=PedidoCompra.Estado.CONFIRMADO
    )

    context.update({
        "pedidos_pendientes": confirmados.count(),
        "pedidos_recibidos": PedidoCompra.objects.filter(
            estado=PedidoCompra.Estado.RECIBIDO
        ).count(),
        "valor_pedidos_confirmados": (
            confirmados.aggregate(
                total=Sum(
                    F("lineas__cantidad") * F("lineas__precio_unitario"),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                )
            )["total"] or 0
        ),
    })
    return context
