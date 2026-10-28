from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase

from .admin import (
    LineaPedidoInlineForm,
    PedidoCompraAdminForm,
    ProductoAdmin,
    ProveedorAdmin,
)
from .models import LineaPedido, PedidoCompra, Producto, Proveedor


class AdminEstadoActivoTests(TestCase):
    def setUp(self):
        self.request = RequestFactory().post("/admin/")

    def test_provider_admin_can_activate_and_deactivate_selected_providers(self):
        proveedor = Proveedor.objects.create(
            nombre="Proveedor de prueba",
            cif_nif="B12345678",
            email="proveedor@example.com",
        )
        proveedor_admin = ProveedorAdmin(Proveedor, AdminSite())

        with patch.object(proveedor_admin, "message_user"):
            proveedor_admin.desactivar_proveedores(
                self.request,
                Proveedor.objects.filter(pk=proveedor.pk),
            )
        proveedor.refresh_from_db()
        self.assertFalse(proveedor.activo)

        with patch.object(proveedor_admin, "message_user"):
            proveedor_admin.activar_proveedores(
                self.request,
                Proveedor.objects.filter(pk=proveedor.pk),
            )
        proveedor.refresh_from_db()
        self.assertTrue(proveedor.activo)

    def test_product_admin_can_activate_and_deactivate_selected_products(self):
        producto = Producto.objects.create(
            referencia="prod-01",
            nombre="Producto de prueba",
            precio_compra="10.00",
        )
        producto_admin = ProductoAdmin(Producto, AdminSite())

        with patch.object(producto_admin, "message_user"):
            producto_admin.desactivar_productos(
                self.request,
                Producto.objects.filter(pk=producto.pk),
            )
        producto.refresh_from_db()
        self.assertFalse(producto.activo)

        with patch.object(producto_admin, "message_user"):
            producto_admin.activar_productos(
                self.request,
                Producto.objects.filter(pk=producto.pk),
            )
        producto.refresh_from_db()
        self.assertTrue(producto.activo)


class ProveedorTests(TestCase):
    def test_save_only_converts_cif_nif_to_uppercase(self):
        proveedor = Proveedor.objects.create(
            nombre="Proveedor de prueba",
            cif_nif="a12345678",
            email="proveedor@example.com",
        )

        self.assertEqual(proveedor.cif_nif, "A12345678")

    def test_save_rejects_cif_nif_longer_than_nine_characters(self):
        proveedor = Proveedor(
            nombre="Proveedor de prueba",
            cif_nif="B123456789",
            email="proveedor@example.com",
        )

        with self.assertRaises(ValidationError):
            proveedor.save()

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

    def test_order_without_provider_fails_validation_cleanly(self):
        pedido = PedidoCompra()

        with self.assertRaises(ValidationError):
            pedido.full_clean()

    def test_order_admin_hides_inactive_providers_for_new_orders(self):
        proveedor_inactivo = Proveedor.objects.create(
            nombre="Proveedor inactivo",
            cif_nif="C12345678",
            email="inactivo@example.com",
            activo=False,
        )
        form = PedidoCompraAdminForm()

        self.assertQuerySetEqual(
            form.fields["proveedor"].queryset,
            [],
        )
        self.assertNotIn(proveedor_inactivo, form.fields["proveedor"].queryset)

    def test_order_admin_keeps_inactive_provider_visible_on_existing_order(self):
        proveedor_inactivo = Proveedor.objects.create(
            nombre="Proveedor inactivo",
            cif_nif="C12345678",
            email="inactivo@example.com",
            activo=False,
        )
        proveedor_activo = Proveedor.objects.create(
            nombre="Proveedor activo",
            cif_nif="D12345678",
            email="activo@example.com",
        )
        pedido = PedidoCompra.objects.create(
            proveedor=proveedor_activo,
        )
        PedidoCompra.objects.filter(pk=pedido.pk).update(
            proveedor=proveedor_inactivo
        )
        pedido.refresh_from_db()
        form = PedidoCompraAdminForm(instance=pedido)

        self.assertQuerySetEqual(
            form.fields["proveedor"].queryset,
            [proveedor_activo, proveedor_inactivo],
        )


class ProductoTests(TestCase):
    def test_reference_must_be_unique_after_normalization(self):
        Producto.objects.create(
            referencia="prod-01",
            nombre="Primer producto",
            precio_compra="10.00",
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            Producto.objects.create(
                referencia=" PROD -01 ",
                nombre="Producto duplicado",
                precio_compra="12.00",
            )

    def test_purchase_price_cannot_be_negative(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Producto.objects.create(
                referencia="prod-neg",
                nombre="Producto con precio negativo",
                precio_compra="-1.00",
            )


class LineaPedidoTests(TestCase):
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
            cantidad=1,
            precio_unitario="10.00",
        )

    def test_confirmed_order_lines_cannot_be_changed_or_deleted(self):
        self.pedido.confirmar()

        self.linea.cantidad = 2
        with self.assertRaises(ValidationError):
            self.linea.save()

        with self.assertRaises(ValidationError):
            self.linea.delete()

    def test_line_can_be_changed_while_order_is_draft(self):
        self.linea.cantidad = 2
        self.linea.save()

        self.assertEqual(
            LineaPedido.objects.get(pk=self.linea.pk).cantidad,
            2,
        )

    def test_adding_existing_product_increases_quantity_and_keeps_price(self):
        self.producto.precio_compra = Decimal("12.00")
        self.producto.save()

        linea = self.pedido.agregar_producto(self.producto, cantidad=3)

        self.assertEqual(linea.pk, self.linea.pk)
        self.assertEqual(linea.cantidad, 4)
        self.assertEqual(linea.precio_unitario, Decimal("10.00"))
        self.assertEqual(self.pedido.lineas.count(), 1)

    def test_adding_new_product_creates_line_at_current_price(self):
        producto_dos = Producto.objects.create(
            referencia="prod-02",
            nombre="Segundo producto",
            precio_compra="3.50",
        )

        linea = self.pedido.agregar_producto(producto_dos, cantidad=2)

        self.assertEqual(linea.cantidad, 2)
        self.assertEqual(linea.precio_unitario, Decimal("3.50"))
        self.assertEqual(self.pedido.lineas.count(), 2)

    def test_admin_inline_copies_product_price_when_price_is_blank(self):
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

    def test_admin_inline_product_options_include_purchase_price(self):
        form = LineaPedidoInlineForm(instance=LineaPedido(pedido=self.pedido))

        option_html = form.fields["producto"].widget.render(
            "producto",
            self.producto.pk,
        )

        self.assertIn('data-precio-compra="10.00"', str(option_html))
        self.assertEqual(
            form.fields["producto"].widget.template_name,
            "unfold/widgets/select.html",
        )
        self.assertIn(
            "appearance-none",
            form.fields["producto"].widget.attrs["class"],
        )

    def test_admin_inline_hides_inactive_products_for_new_lines(self):
        producto_inactivo = Producto.objects.create(
            referencia="prod-inactivo",
            nombre="Producto inactivo",
            precio_compra="7.00",
            activo=False,
        )
        form = LineaPedidoInlineForm(instance=LineaPedido(pedido=self.pedido))

        self.assertQuerySetEqual(
            form.fields["producto"].queryset,
            [self.producto],
        )
        self.assertNotIn(producto_inactivo, form.fields["producto"].queryset)

    def test_admin_inline_keeps_inactive_product_visible_on_existing_line(self):
        self.producto.activo = False
        self.producto.save()
        form = LineaPedidoInlineForm(instance=self.linea)

        self.assertQuerySetEqual(
            form.fields["producto"].queryset,
            [self.producto],
        )

    def test_inactive_product_cannot_be_added_to_an_order(self):
        self.producto.activo = False
        self.producto.save()

        with self.assertRaises(ValidationError):
            self.pedido.agregar_producto(self.producto)

        with self.assertRaises(ValidationError):
            LineaPedido.objects.create(
                pedido=self.pedido,
                producto=self.producto,
                cantidad=1,
                precio_unitario="10.00",
            )

    def test_order_with_product_deactivated_after_adding_cannot_be_confirmed(self):
        self.producto.activo = False
        self.producto.save()

        with self.assertRaises(ValidationError):
            self.pedido.confirmar()

    def test_adding_product_rejects_invalid_quantity_or_non_draft_order(self):
        with self.assertRaises(ValidationError):
            self.pedido.agregar_producto(self.producto, cantidad=0)

        self.pedido.confirmar()
        with self.assertRaises(ValidationError):
            self.pedido.agregar_producto(self.producto)

    def test_quantity_must_be_at_least_one(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            LineaPedido.objects.create(
                pedido=self.pedido,
                producto=self.producto,
                cantidad=0,
                precio_unitario="10.00",
            )

    def test_unit_price_cannot_be_negative(self):
        producto_dos = Producto.objects.create(
            referencia="prod-02",
            nombre="Segundo producto",
            precio_compra="10.00",
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            LineaPedido.objects.create(
                pedido=self.pedido,
                producto=producto_dos,
                cantidad=1,
                precio_unitario="-1.00",
            )

    def test_confirmed_order_can_be_received(self):
        self.pedido.confirmar()
        self.pedido.recibir()

        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, PedidoCompra.Estado.RECIBIDO)

    def test_order_number_and_total_are_calculated(self):
        producto_dos = Producto.objects.create(
            referencia="prod-02",
            nombre="Segundo producto",
            precio_compra="3.50",
        )
        LineaPedido.objects.create(
            pedido=self.pedido,
            producto=producto_dos,
            cantidad=2,
            precio_unitario="3.50",
        )

        self.assertEqual(self.pedido.numero, f"PC-{self.pedido.pk:06d}")
        self.assertEqual(self.pedido.total, Decimal("17.00"))

    def test_order_without_lines_cannot_be_confirmed(self):
        pedido_vacio = PedidoCompra.objects.create(proveedor=self.proveedor)

        with self.assertRaises(ValidationError):
            pedido_vacio.confirmar()

    def test_invalid_order_state_transitions_are_rejected(self):
        with self.assertRaises(ValidationError):
            self.pedido.recibir()

        self.pedido.confirmar()
        self.pedido.recibir()

        with self.assertRaises(ValidationError):
            self.pedido.cancelar()

    def test_canceled_order_cannot_be_received(self):
        self.pedido.cancelar()

        with self.assertRaises(ValidationError):
            self.pedido.recibir()

    def test_inactive_provider_cannot_be_assigned_to_an_order(self):
        proveedor_inactivo = Proveedor.objects.create(
            nombre="Proveedor inactivo",
            cif_nif="C12345678",
            email="inactivo@example.com",
            activo=False,
        )

        with self.assertRaises(ValidationError):
            PedidoCompra.objects.create(proveedor=proveedor_inactivo)

        self.pedido.proveedor = proveedor_inactivo
        with self.assertRaises(ValidationError):
            self.pedido.save()

        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.proveedor_id, self.proveedor.pk)

    def test_inactive_provider_cannot_confirm_an_order(self):
        self.proveedor.activo = False
        self.proveedor.save()

        with self.assertRaises(ValidationError):
            self.pedido.confirmar()

    def test_deactivating_provider_keeps_order_history(self):
        self.proveedor.activo = False
        self.proveedor.save()

        pedido_guardado = PedidoCompra.objects.get(pk=self.pedido.pk)
        self.assertFalse(pedido_guardado.proveedor.activo)
        self.assertEqual(pedido_guardado.lineas.count(), 1)

    def test_confirmed_order_cannot_be_deleted(self):
        self.pedido.confirmar()

        with self.assertRaises(ValidationError):
            self.pedido.delete()

    def test_confirmed_order_header_cannot_be_changed(self):
        self.pedido.confirmar()
        fecha_original = self.pedido.fecha
        proveedor_original_id = self.pedido.proveedor_id

        self.pedido.fecha = fecha_original + timedelta(days=1)
        with self.assertRaises(ValidationError):
            self.pedido.save(update_fields=["fecha"])

        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.fecha, fecha_original)

        otro_proveedor = Proveedor.objects.create(
            nombre="Otro proveedor",
            cif_nif="A12345678",
            email="otro@example.com",
        )
        self.pedido.proveedor = otro_proveedor
        with self.assertRaises(ValidationError):
            self.pedido.save()

        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.proveedor_id, proveedor_original_id)
