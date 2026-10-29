from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("purchasing", "0006_pedidocompra_estado_valido"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="producto",
            constraint=models.CheckConstraint(
                condition=~models.Q(referencia=""),
                name="producto_referencia_no_vacia",
            ),
        ),
    ]
