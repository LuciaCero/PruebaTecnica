from django.contrib import admin
from django.contrib.admin.actions import delete_selected as delete_selected_action
from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.urls import reverse
from unfold.admin import ModelAdmin, TabularInline
from .models import Proveedor, PedidoCompra, Producto, LineaPedido
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

    @admin.action(
        description="Activar proveedores seleccionados",
        permissions=["change"],
    )
    def activar_proveedores(self, request, queryset):
        actualizar_estado_activo(self, request, queryset, True, "proveedor")

    @admin.action(
        description="Desactivar proveedores seleccionados",
        permissions=["change"],
    )
    def desactivar_proveedores(self, request, queryset):
        actualizar_estado_activo(self, request, queryset, False, "proveedor")

@admin.register(Producto)
class ProductoAdmin(ModelAdmin):
    list_display = ("referencia", "nombre", "precio_compra", "activo")
    search_fields = ("referencia", "nombre")
    list_filter = ("activo",)
    
    actions = ("activar_productos", "desactivar_productos")

    @admin.action(
        description="Activar productos seleccionados",
        permissions=["change"],
    )
    def activar_productos(self, request, queryset):
        actualizar_estado_activo(self, request, queryset, True, "producto")

    @admin.action(
        description="Desactivar productos seleccionados",
        permissions=["change"],
    )
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
        if "producto" in self.fields:
            productos = Producto.objects.filter(activo=True)
            if self.instance.pk and not self.instance.producto.activo:
                productos = Producto.objects.filter(
                    Q(activo=True) | Q(pk=self.instance.producto_id)
                )
            self.fields["producto"].queryset = productos
        if "precio_unitario" in self.fields and not self.instance.pk:
            self.fields["precio_unitario"].required = False

    def clean(self):
        cleaned_data = super().clean()
        producto = cleaned_data.get("producto")
        precio_unitario = cleaned_data.get("precio_unitario")
        if producto is not None and precio_unitario is None and not self.instance.pk:
            cleaned_data["precio_unitario"] = producto.precio_compra
        return cleaned_data


class PedidoCompraAdminForm(forms.ModelForm):
    total = forms.DecimalField(
        label="Total del pedido",
        max_digits=14,
        decimal_places=2,
        required=False,
        disabled=True,
    )

    class Meta:
        model = PedidoCompra
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial["total"] = self.instance.total if self.instance.pk else 0
        proveedores = Proveedor.objects.filter(activo=True)
        if self.instance.pk and not self.instance.proveedor.activo:
            proveedores = Proveedor.objects.filter(
                Q(activo=True) | Q(pk=self.instance.proveedor_id)
            )
        if "proveedor" in self.fields:
            self.fields["proveedor"].queryset = proveedores


class LineaPedidoInline(TabularInline):
    model = LineaPedido
    form = LineaPedidoInlineForm
    extra = 1
    fields = ("producto", "cantidad", "precio_unitario")

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.estado != PedidoCompra.Estado.BORRADOR:
            return self.fields
        return super().get_readonly_fields(request, obj)

    def has_add_permission(self, request, obj=None):
        return (
            super().has_add_permission(request, obj)
            and (obj is None or obj.estado == PedidoCompra.Estado.BORRADOR)
        )

    def has_delete_permission(self, request, obj=None):
        return (
            super().has_delete_permission(request, obj)
            and (obj is None or obj.estado == PedidoCompra.Estado.BORRADOR)
        )

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

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(super().get_readonly_fields(request, obj))
        if obj and obj.estado != PedidoCompra.Estado.BORRADOR:
            readonly_fields.extend(("proveedor", "fecha", "estado"))
            readonly_fields.append("aviso_solo_lectura")
        return tuple(readonly_fields)

    def has_change_permission(self, request, obj=None):
        return (
            super().has_change_permission(request, obj)
            and (obj is None or obj.estado == PedidoCompra.Estado.BORRADOR)
        )

    def has_delete_permission(self, request, obj=None):
        return (
            super().has_delete_permission(request, obj)
            and (obj is None or obj.estado == PedidoCompra.Estado.BORRADOR)
        )

    @admin.display(description="Aviso")
    def aviso_solo_lectura(self, obj):
        return "Solo se pueden editar pedidos que estén en estado Borrador."

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
    actions = (
        "confirmar_pedidos",
        "recibir_pedidos",
        "cancelar_pedidos",
        "delete_selected",
    )

    @admin.action(
        description="Eliminar pedidos seleccionados",
        permissions=["delete"],
    )
    def delete_selected(self, request, queryset):
        try:
            queryset.validar_borrado()
            return delete_selected_action(self, request, queryset)
        except ValidationError as error:
            self.message_user(
                request,
                " ".join(error.messages),
                level=messages.ERROR,
            )
            changelist_url = reverse(
                f"admin:{self.opts.app_label}_{self.opts.model_name}_changelist"
            )
            return HttpResponseRedirect(changelist_url)

    @admin.action(permissions=["change"])
    def confirmar_pedidos(self, request, queryset):
        self.aplicar_cambio_estado(request, queryset, "confirmar")

    @admin.action(permissions=["change"])
    def recibir_pedidos(self, request, queryset):
        self.aplicar_cambio_estado(request, queryset, "recibir")

    @admin.action(permissions=["change"])
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
