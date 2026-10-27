from django.db import models
from django.core.exceptions import ValidationError

# Restricción para el numero del CIF/NIF
LONGITUD_CIF_NIF = 9

def normalizar_cif_nif(valor: str) -> str:
    """Quita espacios y guiones y pasa a mayúsculas: 'b-123 456' -> 'B123456'"""
    return "".join(valor.split()).replace("-", "").upper()

class Proveedor(models.Model):
    nombre = models.CharField("nombre comercial", max_length=200)
    cif_nif = models.CharField(
        "CIF/NIF", 
        max_length=20, 
        unique=True,
        help_text=f"Debe tener {LONGITUD_CIF_NIF} caracteres. Se ignoran espacios y guiones.")
    email = models.EmailField("email")
    activo = models.BooleanField("activo", default=True)
    fecha_alta = models.DateTimeField("fecha de alta", auto_now_add=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "proveedor"
        verbose_name_plural = "proveedores"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(cif_nif__regex=r"^[A-Z0-9]{9}$"),
                name="cif_nif_formato_valido",
            )
        ]

    def __str__(self):
        return f"{self.nombre} ({self.cif_nif})"

    def clean(self):
        normalizado = normalizar_cif_nif(self.cif_nif)

        # Verificar longitud y alfanumerico
        if ( 
            len(normalizado) != LONGITUD_CIF_NIF
            or not (normalizado.isascii() and normalizado.isalnum())
        ):
            raise ValidationError(
                {"cif_nif": f"El CIF/NIF debe tener {LONGITUD_CIF_NIF} caracteres alfanuméricos."}
            )
        
        self.cif_nif = normalizado

    def save(self, *args, **kwargs):
        self.cif_nif = normalizar_cif_nif(self.cif_nif)
        super().save(*args, **kwargs)

