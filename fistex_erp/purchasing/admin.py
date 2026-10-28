from django.contrib import admin
from django import forms
from django.db.models import Q
from unfold.admin import ModelAdmin, TabularInline
from .models import Proveedor, PedidoCompra, Producto, LineaPedido
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import DecimalField, F, Sum
from unfold.decorators import display
from unfold.widgets import UnfoldAdminSelectWidget

# Register your models here.

def actualizar_estado_activo(modeladmin, request, queryset, activo, entidad):
    cantidad = queryset.update(activo=activo)
    accion = "activaron" if activo else "desactivaron"
    modeladmin.message_user(
        request,
        f"Se {accion} {cantidad} {entidad}(s).",
        level=messages.SUCCESS,
    )

@admin.register(Proveedor)
class ProveedorAdmin(ModelAdmin):
    list_display = ("nombre", "cif_nif", "email", "activo", "fecha_alta")
    search_fields = ("nombre", "cif_nif", "email")
    list_filter = ("activo",)

    actions = ("activar_proveedores", "desactivar_proveedores")

    @admin.action(description="Activar proveedores seleccionados")
    def activar_proveedores(self, request, queryset):
        actualizar_estado_activo(self, request, queryset, True, "proveedor")

    @admin.action(description="Desactivar proveedores seleccionados")
    def desactivar_proveedores(self, request, queryset):
        actualizar_estado_activo(self, request, queryset, False, "proveedor")

@admin.register(Producto)
class ProductoAdmin(ModelAdmin):
    list_display = ("referencia", "nombre", "precio_compra", "activo")
    search_fields = ("referencia", "nombre")
    list_filter = ("activo",)
    
    actions = ("activar_productos", "desactivar_productos")

    @admin.action(description="Activar productos seleccionados")
    def activar_productos(self, request, queryset):
        actualizar_estado_activo(self, request, queryset, True, "producto")

    @admin.action(description="Desactivar productos seleccionados")
    def desactivar_productos(self, request, queryset):
        actualizar_estado_activo(self, request, queryset, False, "producto")

class ProductoPrecioSelect(UnfoldAdminSelectWidget):
    def create_option(
        self,
        name,
        value,
        label,
        selected,
        index,
        subindex=None,
        attrs=None,
    ):
        option = super().create_option(
            name,
            value,
            label,
            selected,
            index,
            subindex=subindex,
            attrs=attrs,
        )
        producto = getattr(value, "instance", None)
        if producto is not None:
            option["attrs"]["data-precio-compra"] = str(producto.precio_compra)
        return option


class LineaPedidoInlineForm(forms.ModelForm):
    class Meta:
        model = LineaPedido
        fields = ("producto", "cantidad", "precio_unitario")
        widgets = {"producto": ProductoPrecioSelect}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        productos = Producto.objects.filter(activo=True)
        if self.instance.pk and not self.instance.producto.activo:
            productos = Producto.objects.filter(
                Q(activo=True) | Q(pk=self.instance.producto_id)
            )
        self.fields["producto"].queryset = productos
        if not self.instance.pk:
            self.fields["precio_unitario"].required = False

    def clean(self):
        cleaned_data = super().clean()
        producto = cleaned_data.get("producto")
        precio_unitario = cleaned_data.get("precio_unitario")
        if producto is not None and precio_unitario is None and not self.instance.pk:
            cleaned_data["precio_unitario"] = producto.precio_compra
        return cleaned_data


class PedidoCompraAdminForm(forms.ModelForm):
    class Meta:
        model = PedidoCompra
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        proveedores = Proveedor.objects.filter(activo=True)
        if self.instance.pk and not self.instance.proveedor.activo:
            proveedores = Proveedor.objects.filter(
                Q(activo=True) | Q(pk=self.instance.proveedor_id)
            )
        self.fields["proveedor"].queryset = proveedores


class LineaPedidoInline(TabularInline):
    model = LineaPedido
    form = LineaPedidoInlineForm
    extra = 1
    fields = ("producto", "cantidad", "precio_unitario")
    class Media:
        js = ("purchasing/admin_pedido.js",)

@admin.register(PedidoCompra)
class PedidoCompraAdmin(ModelAdmin):
    # Display de las lineas de pedido
    inlines = [LineaPedidoInline]
    form = PedidoCompraAdminForm

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
