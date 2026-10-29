from decimal import Decimal

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase

from .admin import (
    LineaPedidoInline,
    LineaPedidoInlineForm,
    PedidoCompraAdmin,
    dashboard_callback,
)
from .models import LineaPedido, PedidoCompra, Producto, Proveedor


class ProveedorTests(TestCase):
    def test_cif_nif_must_be_unique(self):
        Proveedor.objects.create(
            nombre="Proveedor original",
            cif_nif="B12345678",
            email="original@example.com",
        )

        with self.assertRaises(ValidationError):
            Proveedor.objects.create(
                nombre="Proveedor duplicado",
                cif_nif="b12345678",
                email="duplicado@example.com",
            )

    def test_deactivating_provider_keeps_order_history(self):
        proveedor = Proveedor.objects.create(
            nombre="Proveedor de prueba",
            cif_nif="B12345678",
            email="proveedor@example.com",
        )
        producto = Producto.objects.create(
            referencia="prod-01",
            nombre="Producto de prueba",
            precio_compra="10.00",
        )
        pedido = PedidoCompra.objects.create(proveedor=proveedor)
        LineaPedido.objects.create(
            pedido=pedido,
            producto=producto,
            cantidad=1,
            precio_unitario="10.00",
        )

        proveedor.activo = False
        proveedor.save()

        pedido_guardado = PedidoCompra.objects.get(pk=pedido.pk)
        self.assertFalse(pedido_guardado.proveedor.activo)
        self.assertEqual(pedido_guardado.lineas.count(), 1)


class ProductoTests(TestCase):
    def test_reference_must_be_unique_after_normalization(self):
        Producto.objects.create(
            referencia="prod-01",
            nombre="Primer producto",
            precio_compra="10.00",
        )

        with self.assertRaises(ValidationError):
            Producto.objects.create(
                referencia=" PROD -01 ",
                nombre="Producto duplicado",
                precio_compra="12.00",
            )

    def test_purchase_price_cannot_be_negative(self):
        with self.assertRaises(ValidationError):
            Producto.objects.create(
                referencia="prod-neg",
                nombre="Producto con precio negativo",
                precio_compra="-1.00",
            )


class PedidoCompraTests(TestCase):
    def setUp(self):
        self.proveedor = Proveedor.objects.create(
            nombre="Proveedor de prueba",
            cif_nif="B12345678",
            email="proveedor@example.com",
        )
        self.producto = Producto.objects.create(
            referencia="prod-01",
            nombre="Producto de prueba",
            precio_compra="10.00",
        )
        self.pedido = PedidoCompra.objects.create(proveedor=self.proveedor)
        self.linea = LineaPedido.objects.create(
            pedido=self.pedido,
            producto=self.producto,
            cantidad=2,
            precio_unitario="10.00",
        )

    def test_order_number_total_and_lines_are_available(self):
        producto_dos = Producto.objects.create(
            referencia="prod-02",
            nombre="Segundo producto",
            precio_compra="3.50",
        )
        LineaPedido.objects.create(
            pedido=self.pedido,
            producto=producto_dos,
            cantidad=3,
            precio_unitario="4.25",
        )

        self.assertEqual(self.pedido.numero, f"PC-{self.pedido.pk:06d}")
        self.assertEqual(self.pedido.total, Decimal("32.75"))
        self.assertEqual(self.pedido.lineas.count(), 2)

    def test_draft_order_and_lines_can_be_edited(self):
        self.pedido.fecha = "2030-01-01"
        self.pedido.save(update_fields=["fecha"])
        self.linea.cantidad = 3
        self.linea.save(update_fields=["cantidad"])

        self.pedido.refresh_from_db()
        self.linea.refresh_from_db()
        self.assertEqual(str(self.pedido.fecha), "2030-01-01")
        self.assertEqual(self.linea.cantidad, 3)

    def test_confirmed_order_and_lines_cannot_be_modified(self):
        self.pedido.confirmar()
        fecha_original = self.pedido.fecha

        self.linea.cantidad = 3
        with self.assertRaises(ValidationError):
            self.linea.save()

        self.pedido.fecha = "2030-01-01"
        with self.assertRaises(ValidationError):
            self.pedido.save(update_fields=["fecha"])

        self.pedido.refresh_from_db()
        self.linea.refresh_from_db()
        self.assertEqual(self.pedido.estado, PedidoCompra.Estado.CONFIRMADO)
        self.assertEqual(self.pedido.fecha, fecha_original)
        self.assertEqual(self.linea.cantidad, 2)

    def test_cancelled_order_cannot_be_received_and_received_order_cannot_be_cancelled(self):
        self.pedido.cancelar()
        with self.assertRaises(ValidationError):
            self.pedido.recibir()

        pedido_recibido = PedidoCompra.objects.create(proveedor=self.proveedor)
        LineaPedido.objects.create(
            pedido=pedido_recibido,
            producto=self.producto,
            cantidad=1,
            precio_unitario="10.00",
        )
        pedido_recibido.confirmar()
        pedido_recibido.recibir()

        with self.assertRaises(ValidationError):
            pedido_recibido.cancelar()
        self.assertEqual(pedido_recibido.estado, PedidoCompra.Estado.RECIBIDO)


class PedidoCompraAdminTests(TestCase):
    def setUp(self):
        self.proveedor = Proveedor.objects.create(
            nombre="Proveedor de prueba",
            cif_nif="B12345678",
            email="proveedor@example.com",
        )
        self.producto = Producto.objects.create(
            referencia="prod-01",
            nombre="Producto de prueba",
            precio_compra="10.00",
        )
        self.pedido = PedidoCompra.objects.create(proveedor=self.proveedor)
        self.linea = LineaPedido.objects.create(
            pedido=self.pedido,
            producto=self.producto,
            cantidad=2,
            precio_unitario="10.00",
        )

    def test_admin_lists_order_fields_and_calculated_total(self):
        pedido_admin = PedidoCompraAdmin(PedidoCompra, AdminSite())
        request = RequestFactory().get("/admin/")
        pedido = pedido_admin.get_queryset(request).get(pk=self.pedido.pk)

        self.assertTrue(
            {
                "numero",
                "proveedor",
                "fecha",
                "estado_con_etiqueta",
                "total_en_lista",
            }.issubset(pedido_admin.list_display)
        )
        self.assertEqual(pedido_admin.total_en_lista(pedido), Decimal("20.00"))

    def test_dashboard_shows_pending_and_received_order_indicators(self):
        request = RequestFactory().get("/admin/")
        before = dashboard_callback(request, {})
        self.pedido.confirmar()
        pedido_recibido = PedidoCompra.objects.create(proveedor=self.proveedor)
        LineaPedido.objects.create(
            pedido=pedido_recibido,
            producto=self.producto,
            cantidad=1,
            precio_unitario="5.00",
        )
        pedido_recibido.confirmar()
        pedido_recibido.recibir()

        context = dashboard_callback(request, {})

        self.assertEqual(context["pedidos_pendientes"], before["pedidos_pendientes"] + 1)
        self.assertEqual(context["pedidos_recibidos"], before["pedidos_recibidos"] + 1)
        self.assertEqual(
            context["valor_pedidos_pendientes"],
            before["valor_pedidos_pendientes"] + Decimal("20.00"),
        )
        self.assertEqual(
            context["valor_pedidos_recibidos"],
            before["valor_pedidos_recibidos"] + Decimal("5.00"),
        )

    def test_admin_inline_defaults_quantity_and_copies_product_price(self):
        form = LineaPedidoInlineForm(instance=LineaPedido(pedido=self.pedido))
        self.assertEqual(form["cantidad"].value(), 1)
        option_html = form.fields["producto"].widget.render(
            "producto",
            self.producto.pk,
        )
        self.assertIn('data-precio-compra="10.00"', str(option_html))

        producto_dos = Producto.objects.create(
            referencia="prod-02",
            nombre="Segundo producto",
            precio_compra="3.50",
        )
        form = LineaPedidoInlineForm(
            data={
                "producto": producto_dos.pk,
                "cantidad": "2",
                "precio_unitario": "",
            },
            instance=LineaPedido(pedido=self.pedido),
        )

        self.assertTrue(form.is_valid(), form.errors)
        linea = form.save()
        self.assertEqual(linea.precio_unitario, Decimal("3.50"))

    def test_admin_inline_rejects_duplicate_products(self):
        linea_inline = LineaPedidoInline(PedidoCompra, AdminSite())
        request = RequestFactory().get("/admin/")
        request.user = AnonymousUser()
        formset_class = linea_inline.get_formset(
            request,
            self.pedido,
        )
        prefix = formset_class.get_default_prefix()
        data = {
            f"{prefix}-TOTAL_FORMS": "2",
            f"{prefix}-INITIAL_FORMS": "1",
            f"{prefix}-MIN_NUM_FORMS": "0",
            f"{prefix}-MAX_NUM_FORMS": "1000",
            f"{prefix}-0-producto": str(self.producto.pk),
            f"{prefix}-0-cantidad": "2",
            f"{prefix}-0-precio_unitario": "10.00",
            f"{prefix}-1-producto": str(self.producto.pk),
            f"{prefix}-1-cantidad": "2",
            f"{prefix}-1-precio_unitario": "10.00",
        }
        formset = formset_class(data=data, instance=self.pedido)

        self.assertFalse(formset.is_valid(), formset.errors)
