from datetime import date
from decimal import Decimal

from django.db import migrations


def crear_datos_de_ejemplo(apps, schema_editor):
    Proveedor = apps.get_model("purchasing", "Proveedor")
    Producto = apps.get_model("purchasing", "Producto")
    PedidoCompra = apps.get_model("purchasing", "PedidoCompra")
    LineaPedido = apps.get_model("purchasing", "LineaPedido")
    alias_db = schema_editor.connection.alias

    proveedores = {}
    for cif_nif, nombre, email, activo in (
        (
            "B33221144",
            "Suministros Industriales del Sur S.L.",
            "pedidos@suministrossur.es",
            True,
        ),
        (
            "A99887766",
            "Ferretería y Herramientas Técnicas S.A.",
            "comercial@herramientastecnicas.com",
            True,
        ),
        (
            "B55443322",
            "Tornillería y Anclajes Levante (Antiguo)",
            "contacto@levantetornillos.es",
            False,
        ),
    ):
        valores = {"nombre": nombre, "email": email}
        if not activo:
            valores["activo"] = False
        proveedor, _ = Proveedor.objects.using(alias_db).get_or_create(
            cif_nif=cif_nif,
            defaults=valores,
        )
        proveedores[cif_nif] = proveedor

    productos = {}
    for referencia, nombre, precio_compra, activo in (
        ("TOR-501", "Caja de 100 tornillos rosca chapa", "3.20", True),
        ("CIN-502", "Cinta aislante negra 10m", "1.10", True),
        ("GUA-503", "Par de guantes de protección anticorte", "4.50", True),
        ("SIL-504", "Cartucho de silicona neutra", "3.80", True),
        ("DIS-999", "Disco de corte descontinuado", "2.00", False),
    ):
        valores = {
            "nombre": nombre,
            "precio_compra": Decimal(precio_compra),
        }
        if not activo:
            valores["activo"] = False
        producto, _ = Producto.objects.using(alias_db).get_or_create(
            referencia=referencia,
            defaults=valores,
        )
        productos[referencia] = producto

    pedidos = (
        (
            "B33221144",
            date(2026, 10, 10),
            "borrador",
            (("TOR-501", 10, "3.20"), ("CIN-502", 5, "1.10")),
        ),
        (
            "A99887766",
            date(2026, 10, 20),
            "confirmado",
            (("GUA-503", 20, "4.50"),),
        ),
        (
            "B33221144",
            date(2026, 9, 15),
            "recibido",
            (("SIL-504", 15, "3.80"), ("CIN-502", 10, "1.10")),
        ),
        (
            "A99887766",
            date(2026, 10, 1),
            "cancelado",
            (("TOR-501", 50, "3.20"),),
        ),
    )

    for cif_nif, fecha, estado, lineas in pedidos:
        pedido = PedidoCompra.objects.using(alias_db).create(
            proveedor=proveedores[cif_nif],
            fecha=fecha,
        )
        # El modelo histórico de la migración no incluye el save() que genera el número.
        PedidoCompra.objects.using(alias_db).filter(pk=pedido.pk).update(
            numero=f"PC-{pedido.pk:06d}",
        )
        for referencia, cantidad, precio_unitario in lineas:
            LineaPedido.objects.using(alias_db).create(
                pedido=pedido,
                producto=productos[referencia],
                cantidad=cantidad,
                precio_unitario=Decimal(precio_unitario),
            )
        if estado != "borrador":
            PedidoCompra.objects.using(alias_db).filter(pk=pedido.pk).update(
                estado=estado,
            )


class Migration(migrations.Migration):

    dependencies = [
        ("purchasing", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            crear_datos_de_ejemplo,
            migrations.RunPython.noop,
        ),
    ]
