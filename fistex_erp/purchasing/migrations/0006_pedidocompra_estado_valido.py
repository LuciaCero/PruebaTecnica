from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("purchasing", "0005_alter_proveedor_email"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="pedidocompra",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    estado__in=[
                        "borrador",
                        "confirmado",
                        "recibido",
                        "cancelado",
                    ]
                ),
                name="pedido_estado_valido",
            ),
        ),
    ]
