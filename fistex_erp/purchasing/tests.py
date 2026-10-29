from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.test import RequestFactory, TestCase
from django.urls import reverse

from .admin import (
    LineaPedidoInline,
    LineaPedidoInlineForm,
    PedidoCompraAdmin,
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


class PedidoCompraAdminFormTests(TestCase):
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
        LineaPedido.objects.create(
            pedido=self.pedido,
            producto=self.producto,
            cantidad=3,
            precio_unitario="12.50",
        )

    def test_total_is_read_only_and_initialized_from_order_lines(self):
        form = PedidoCompraAdminForm(instance=self.pedido)

        self.assertTrue(form.fields["total"].disabled)
        self.assertEqual(form["total"].value(), Decimal("37.50"))

    def test_new_order_total_starts_at_zero(self):
        form = PedidoCompraAdminForm()

        self.assertTrue(form.fields["total"].disabled)
        self.assertEqual(form["total"].value(), 0)


class PedidoCompraAdminListTests(TestCase):
    def test_order_totals_are_annotated_without_extra_queries(self):
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
        pedido_con_lineas = PedidoCompra.objects.create(proveedor=proveedor)
        LineaPedido.objects.create(
            pedido=pedido_con_lineas,
            producto=producto,
            cantidad=3,
            precio_unitario="12.50",
        )
        pedido_sin_lineas = PedidoCompra.objects.create(proveedor=proveedor)
        pedido_admin = PedidoCompraAdmin(PedidoCompra, AdminSite())
        request = RequestFactory().get("/admin/")

        with self.assertNumQueries(1):
            pedidos = list(
                pedido_admin.get_queryset(request)
                .filter(pk__in=[pedido_con_lineas.pk, pedido_sin_lineas.pk])
                .order_by("pk")
            )
            totales = [pedido_admin.total_en_lista(pedido) for pedido in pedidos]

        self.assertEqual(totales, [Decimal("37.50"), Decimal("0.00")])


class AdminActionPermissionTests(TestCase):
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
        LineaPedido.objects.create(
            pedido=self.pedido,
            producto=self.producto,
            cantidad=1,
            precio_unitario="10.00",
        )

    def crear_usuario(self, username, permisos=()):
        usuario = get_user_model().objects.create_user(
            username=username,
            password="test-password",
            is_staff=True,
        )
        permisos_modelo = [
            Permission.objects.get(
                content_type__app_label="purchasing",
                codename=f"{accion}_{modelo}",
            )
            for accion, modelo in permisos
        ]
        usuario.user_permissions.set(permisos_modelo)
        return usuario

    def enviar_accion(self, modelo, accion, objeto_id):
        return self.client.post(
            reverse(f"admin:purchasing_{modelo}_changelist"),
            {
                "action": accion,
                "index": "0",
                "select_across": "0",
                "_selected_action": [str(objeto_id)],
            },
        )

    def test_read_only_user_can_view_but_cannot_run_write_actions(self):
        usuario = self.crear_usuario(
            "lector",
            [
                ("view", "proveedor"),
                ("view", "producto"),
                ("view", "pedidocompra"),
                ("view", "lineapedido"),
            ],
        )
        self.client.force_login(usuario)

        for modelo in ("proveedor", "producto", "pedidocompra"):
            with self.subTest(modelo=modelo):
                response = self.client.get(
                    reverse(f"admin:purchasing_{modelo}_changelist")
                )
                self.assertEqual(response.status_code, 200)

        response = self.client.get(
            reverse(
                "admin:purchasing_pedidocompra_change",
                args=[self.pedido.pk],
            )
        )
        self.assertEqual(response.status_code, 200)

        acciones = (
            ("proveedor", "activar_proveedores", self.proveedor, "activo", False),
            ("proveedor", "desactivar_proveedores", self.proveedor, "activo", True),
            ("producto", "activar_productos", self.producto, "activo", False),
            ("producto", "desactivar_productos", self.producto, "activo", True),
            (
                "pedidocompra",
                "confirmar_pedidos",
                self.pedido,
                "estado",
                PedidoCompra.Estado.BORRADOR,
            ),
            (
                "pedidocompra",
                "recibir_pedidos",
                self.pedido,
                "estado",
                PedidoCompra.Estado.CONFIRMADO,
            ),
            (
                "pedidocompra",
                "cancelar_pedidos",
                self.pedido,
                "estado",
                PedidoCompra.Estado.CONFIRMADO,
            ),
        )
        for modelo, accion, objeto, campo, valor_inicial in acciones:
            with self.subTest(accion=accion):
                if campo == "estado":
                    models.QuerySet.update(
                        type(objeto).objects.filter(pk=objeto.pk),
                        estado=valor_inicial,
                    )
                elif isinstance(objeto, Producto):
                    objeto.activo = valor_inicial
                    objeto.save(update_fields=["activo"])
                else:
                    type(objeto).objects.filter(pk=objeto.pk).update(
                        activo=valor_inicial
                    )

                response = self.enviar_accion(modelo, accion, objeto.pk)

                self.assertEqual(response.status_code, 200)
                objeto.refresh_from_db()
                self.assertEqual(getattr(objeto, campo), valor_inicial)

    def test_user_with_change_permission_can_run_write_actions(self):
        usuario = self.crear_usuario(
            "editor",
            [
                ("change", "proveedor"),
                ("change", "producto"),
                ("change", "pedidocompra"),
            ],
        )
        self.client.force_login(usuario)

        response = self.enviar_accion(
            "pedidocompra", "confirmar_pedidos", self.pedido.pk
        )
        self.assertEqual(response.status_code, 302)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, PedidoCompra.Estado.CONFIRMADO)

        response = self.enviar_accion(
            "proveedor", "desactivar_proveedores", self.proveedor.pk
        )
        self.assertEqual(response.status_code, 302)
        self.proveedor.refresh_from_db()
        self.assertFalse(self.proveedor.activo)

        response = self.enviar_accion(
            "producto", "desactivar_productos", self.producto.pk
        )
        self.assertEqual(response.status_code, 302)
        self.producto.refresh_from_db()
        self.assertFalse(self.producto.activo)

    def test_bulk_delete_action_reports_blocked_orders_without_deleting_anything(self):
        pedido_borrador = PedidoCompra.objects.create(proveedor=self.proveedor)
        LineaPedido.objects.create(
            pedido=pedido_borrador,
            producto=self.producto,
            cantidad=1,
            precio_unitario="10.00",
        )
        self.pedido.confirmar()
        usuario = self.crear_usuario(
            "borrador_delete",
            [
                ("view", "pedidocompra"),
                ("delete", "pedidocompra"),
                ("delete", "lineapedido"),
            ],
        )
        self.client.force_login(usuario)
        response = self.client.post(
            reverse("admin:purchasing_pedidocompra_changelist"),
            {
                "action": "delete_selected",
                "index": "0",
                "select_across": "0",
                "_selected_action": [str(self.pedido.pk), str(pedido_borrador.pk)],
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.redirect_chain,
            [
                (
                    reverse("admin:purchasing_pedidocompra_changelist"),
                    302,
                )
            ],
        )
        self.assertContains(response, "No se eliminó ningún pedido")
        self.assertContains(response, self.pedido.numero)
        self.assertContains(response, "Confirmado")
        self.assertContains(response, "selección")
        self.assertTrue(PedidoCompra.objects.filter(pk=self.pedido.pk).exists())
        self.assertTrue(PedidoCompra.objects.filter(pk=pedido_borrador.pk).exists())
        self.assertEqual(self.pedido.lineas.count(), 1)
        self.assertEqual(pedido_borrador.lineas.count(), 1)

    def test_non_draft_orders_are_read_only_in_admin(self):
        usuario = self.crear_usuario(
            "editor_pedidos",
            [
                ("change", "pedidocompra"),
                ("change", "lineapedido"),
            ],
        )
        self.client.force_login(usuario)
        url = reverse(
            "admin:purchasing_pedidocompra_change",
            args=[self.pedido.pk],
        )

        for estado in (
            PedidoCompra.Estado.CONFIRMADO,
            PedidoCompra.Estado.RECIBIDO,
            PedidoCompra.Estado.CANCELADO,
        ):
            with self.subTest(estado=estado):
                models.QuerySet.update(
                    PedidoCompra.objects.filter(pk=self.pedido.pk),
                    estado=estado,
                )

                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(
                    response,
                    "Solo se pueden editar pedidos que estén en estado Borrador.",
                )

                response = self.client.post(
                    url,
                    {
                        "proveedor": str(self.proveedor.pk),
                        "fecha": "2030-01-01",
                        "_save": "Guardar",
                    },
                )
                self.assertEqual(response.status_code, 403)

                self.pedido.refresh_from_db()
                self.assertEqual(self.pedido.estado, estado)

    def test_order_and_lines_can_only_be_edited_while_draft(self):
        request = RequestFactory().get("/admin/")
        usuario = self.crear_usuario(
            "editor_hooks",
            [
                ("change", "pedidocompra"),
                ("delete", "pedidocompra"),
                ("add", "lineapedido"),
                ("change", "lineapedido"),
                ("delete", "lineapedido"),
            ],
        )
        request.user = usuario
        pedido_admin = PedidoCompraAdmin(PedidoCompra, AdminSite())
        linea_inline = LineaPedidoInline(PedidoCompra, AdminSite())

        self.assertTrue(pedido_admin.has_change_permission(request, self.pedido))
        self.assertTrue(linea_inline.has_add_permission(request, self.pedido))
        self.assertTrue(linea_inline.has_delete_permission(request, self.pedido))

        for estado in (
            PedidoCompra.Estado.CONFIRMADO,
            PedidoCompra.Estado.RECIBIDO,
            PedidoCompra.Estado.CANCELADO,
        ):
            with self.subTest(estado=estado):
                models.QuerySet.update(
                    PedidoCompra.objects.filter(pk=self.pedido.pk),
                    estado=estado,
                )
                self.pedido.refresh_from_db()

                self.assertFalse(
                    pedido_admin.has_change_permission(request, self.pedido)
                )
                self.assertFalse(
                    pedido_admin.has_delete_permission(request, self.pedido)
                )
                self.assertEqual(
                    set(linea_inline.get_readonly_fields(request, self.pedido)),
                    set(linea_inline.fields),
                )
                self.assertFalse(linea_inline.has_add_permission(request, self.pedido))
                self.assertFalse(
                    linea_inline.has_delete_permission(request, self.pedido)
                )

    def test_user_without_model_permissions_cannot_access_or_run_actions(self):
        usuario = self.crear_usuario("sin_permisos")
        self.client.force_login(usuario)

        for modelo in ("proveedor", "producto", "pedidocompra"):
            with self.subTest(modelo=modelo):
                response = self.client.get(
                    reverse(f"admin:purchasing_{modelo}_changelist")
                )
                self.assertEqual(response.status_code, 403)

        response = self.enviar_accion(
            "pedidocompra", "confirmar_pedidos", self.pedido.pk
        )
        self.assertEqual(response.status_code, 403)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, PedidoCompra.Estado.BORRADOR)


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
        models.QuerySet.update(
            PedidoCompra.objects.filter(pk=pedido.pk),
            proveedor=proveedor_inactivo,
        )
        pedido.refresh_from_db()
        form = PedidoCompraAdminForm(instance=pedido)

        self.assertIn(proveedor_activo, form.fields["proveedor"].queryset)
        self.assertIn(proveedor_inactivo, form.fields["proveedor"].queryset)


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

    def test_reference_cannot_be_empty_after_normalization(self):
        existing_product_count = Producto.objects.count()
        for referencia in ("", " \t\n "):
            with self.subTest(referencia=referencia):
                producto = Producto(
                    referencia=referencia,
                    nombre="Producto sin referencia",
                    precio_compra="10.00",
                )
                with self.assertRaises(ValidationError) as error:
                    producto.save()

                self.assertIn("referencia", error.exception.message_dict)
                self.assertEqual(Producto.objects.count(), existing_product_count)

    def test_purchase_price_cannot_be_negative(self):
        with self.assertRaises(ValidationError):
            Producto.objects.create(
                referencia="prod-neg",
                nombre="Producto con precio negativo",
                precio_compra="-1.00",
            )

    def test_product_save_validates_other_required_fields(self):
        with self.assertRaises(ValidationError) as error:
            Producto.objects.create(
                referencia="prod-sin-nombre",
                nombre="",
                precio_compra="10.00",
            )

        self.assertIn("nombre", error.exception.message_dict)

    def test_update_or_create_uses_product_validation(self):
        producto = Producto.objects.create(
            referencia="prod-01",
            nombre="Producto de prueba",
            precio_compra="10.00",
        )

        with self.assertRaises(ValidationError):
            Producto.objects.update_or_create(
                pk=producto.pk,
                defaults={"precio_compra": "-1.00"},
            )

        producto.refresh_from_db()
        self.assertEqual(producto.precio_compra, Decimal("10.00"))

    def test_product_queryset_bulk_writes_are_rejected(self):
        producto = Producto.objects.create(
            referencia="prod-01",
            nombre="Producto de prueba",
            precio_compra="10.00",
        )

        with self.assertRaises(ValidationError):
            Producto.objects.filter(pk=producto.pk).update(activo=False)

        with self.assertRaises(ValidationError):
            Producto.objects.bulk_create(
                [
                    Producto(
                        referencia="prod-02",
                        nombre="Segundo producto",
                        precio_compra="12.00",
                    )
                ]
            )

        producto.activo = False
        with self.assertRaises(ValidationError):
            Producto.objects.bulk_update([producto], ["activo"])

        producto.refresh_from_db()
        self.assertTrue(producto.activo)


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

        with self.assertRaises(ValidationError):
            LineaPedido.objects.filter(pk=self.linea.pk).delete()

    def test_line_cannot_be_moved_out_of_a_confirmed_order(self):
        pedido_borrador = PedidoCompra.objects.create(proveedor=self.proveedor)
        self.pedido.confirmar()
        self.linea.pedido = pedido_borrador

        with self.assertRaises(ValidationError):
            self.linea.save()

        self.assertEqual(
            LineaPedido.objects.get(pk=self.linea.pk).pedido_id,
            self.pedido.pk,
        )

    def test_queryset_update_cannot_bypass_line_guards(self):
        with self.assertRaises(ValidationError):
            LineaPedido.objects.filter(pk=self.linea.pk).update(cantidad=2)

        self.assertEqual(
            LineaPedido.objects.get(pk=self.linea.pk).cantidad,
            1,
        )

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

        self.assertIn(self.producto, form.fields["producto"].queryset)
        self.assertNotIn(producto_inactivo, form.fields["producto"].queryset)

    def test_admin_inline_keeps_inactive_product_visible_on_existing_line(self):
        self.producto.activo = False
        self.producto.save()
        form = LineaPedidoInlineForm(instance=self.linea)

        self.assertIn(self.producto, form.fields["producto"].queryset)

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

        pedido_vacio.refresh_from_db()
        self.assertEqual(pedido_vacio.estado, PedidoCompra.Estado.BORRADOR)

    def test_invalid_order_state_transitions_are_rejected(self):
        with self.assertRaises(ValidationError):
            self.pedido.recibir()

        self.pedido.confirmar()
        self.pedido.recibir()

        with self.assertRaises(ValidationError):
            self.pedido.cancelar()

    def test_ordinary_save_cannot_restore_a_stale_order_state(self):
        pedido_obsoleto = PedidoCompra.objects.get(pk=self.pedido.pk)
        pedido_actual = PedidoCompra.objects.get(pk=self.pedido.pk)
        pedido_actual.confirmar()

        pedido_obsoleto.save()

        pedido_obsoleto.refresh_from_db()
        self.assertEqual(pedido_obsoleto.estado, PedidoCompra.Estado.CONFIRMADO)

    def test_ordinary_save_cannot_change_the_order_state(self):
        self.pedido.estado = PedidoCompra.Estado.CONFIRMADO

        with self.assertRaises(ValidationError):
            self.pedido.save(update_fields=["estado"])

        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, PedidoCompra.Estado.BORRADOR)

    def test_queryset_update_cannot_bypass_order_state_transitions(self):
        with self.assertRaises(ValidationError):
            PedidoCompra.objects.filter(pk=self.pedido.pk).update(
                estado=PedidoCompra.Estado.CONFIRMADO
            )

        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, PedidoCompra.Estado.BORRADOR)

    def test_order_bulk_create_cannot_bypass_initial_state_validation(self):
        pedido = PedidoCompra(
            proveedor=self.proveedor,
            estado=PedidoCompra.Estado.RECIBIDO,
        )

        with self.assertRaises(ValidationError):
            PedidoCompra.objects.bulk_create([pedido])

    def test_ordinary_save_ignores_an_unsaved_state_change(self):
        fecha_original = self.pedido.fecha
        self.pedido.estado = PedidoCompra.Estado.CONFIRMADO
        self.pedido.fecha = fecha_original + timedelta(days=1)

        self.pedido.save()

        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, PedidoCompra.Estado.BORRADOR)
        self.assertEqual(self.pedido.fecha, fecha_original + timedelta(days=1))

    def test_new_order_must_start_as_a_draft(self):
        pedido = PedidoCompra(
            proveedor=self.proveedor,
            estado=PedidoCompra.Estado.RECIBIDO,
        )

        with self.assertRaises(ValidationError):
            pedido.save()

    def test_database_rejects_unknown_order_states(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            models.QuerySet.update(
                PedidoCompra.objects.filter(pk=self.pedido.pk),
                estado="pendiente",
            )

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

    def test_bulk_delete_rejects_mixed_selection_without_deleting_orders_or_lines(self):
        pedido_borrador = PedidoCompra.objects.create(proveedor=self.proveedor)
        LineaPedido.objects.create(
            pedido=pedido_borrador,
            producto=self.producto,
            cantidad=1,
            precio_unitario="10.00",
        )
        self.pedido.confirmar()
        pedidos = PedidoCompra.objects.filter(
            pk__in=[self.pedido.pk, pedido_borrador.pk]
        )

        with self.assertRaises(ValidationError) as error:
            pedidos.delete()

        self.assertIn(self.pedido.numero, str(error.exception))
        self.assertIn("Confirmado", str(error.exception))
        self.assertTrue(PedidoCompra.objects.filter(pk=self.pedido.pk).exists())
        self.assertTrue(PedidoCompra.objects.filter(pk=pedido_borrador.pk).exists())
        self.assertEqual(self.pedido.lineas.count(), 1)
        self.assertEqual(pedido_borrador.lineas.count(), 1)

    def test_bulk_delete_removes_draft_orders_and_their_lines(self):
        resultado = PedidoCompra.objects.filter(pk=self.pedido.pk).delete()

        self.assertEqual(resultado[0], 2)
        self.assertFalse(PedidoCompra.objects.filter(pk=self.pedido.pk).exists())
        self.assertFalse(LineaPedido.objects.filter(pedido_id=self.pedido.pk).exists())

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
