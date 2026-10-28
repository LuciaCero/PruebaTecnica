document.addEventListener("change", (event) => {
    const productoSelect = event.target;
    if (
        !(productoSelect instanceof HTMLSelectElement) ||
        !productoSelect.name.endsWith("-producto")
    ) {
        return;
    }

    const precioInput = document.getElementById(
        productoSelect.id.replace(/-producto$/, "-precio_unitario"),
    );
    if (!precioInput) {
        return;
    }

    const precio = productoSelect.selectedOptions[0]?.dataset.precioCompra;
    precioInput.value = precio ?? "";
    precioInput.dispatchEvent(new Event("input", { bubbles: true }));
    precioInput.dispatchEvent(new Event("change", { bubbles: true }));
});
