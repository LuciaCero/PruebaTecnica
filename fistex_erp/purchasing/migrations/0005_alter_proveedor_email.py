from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("purchasing", "0004_remove_proveedor_cif_nif_formato_valido_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="proveedor",
            name="email",
            field=models.EmailField(
                max_length=254,
                verbose_name="correo electrónico",
            ),
        ),
    ]
