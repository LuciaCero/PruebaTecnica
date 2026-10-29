function actualizarTotalPedido() {
    const totalInput = document.getElementById("id_total");
    if (!(totalInput instanceof HTMLInputElement)) {
        return;
    }

    let totalEnCentimos = 0;
    document.querySelectorAll('input[name$="-cantidad"]').forEach((cantidadInput) => {
        const fila = cantidadInput.closest("tr");
        if (!fila || fila.querySelector('input[name$="-DELETE"]')?.checked) {
            return;
        }

        const precioInput = document.getElementById(
            cantidadInput.id.replace(/-cantidad$/, "-precio_unitario"),
        );
        const cantidad = Number(cantidadInput.value);
        const precio = Number(precioInput?.value);
        if (Number.isFinite(cantidad) && Number.isFinite(precio)) {
            totalEnCentimos += Math.round(precio * 100) * cantidad;
        }
    });

    totalInput.value = (totalEnCentimos / 100).toFixed(2);
}

document.addEventListener("input", actualizarTotalPedido);
document.addEventListener("change", (event) => {
    const productoSelect = event.target;
    if (
        productoSelect instanceof HTMLSelectElement &&
        productoSelect.name.endsWith("-producto")
    ) {
        const cantidadInput = document.getElementById(
            productoSelect.id.replace(/-producto$/, "-cantidad"),
        );
        if (cantidadInput instanceof HTMLInputElement) {
            cantidadInput.value = "1";
            cantidadInput.dispatchEvent(new Event("input", { bubbles: true }));
            cantidadInput.dispatchEvent(new Event("change", { bubbles: true }));
        }

        const precioInput = document.getElementById(
            productoSelect.id.replace(/-producto$/, "-precio_unitario"),
        );
        if (precioInput) {
            const precio = productoSelect.selectedOptions[0]?.dataset.precioCompra;
            precioInput.value = precio ?? "";
            precioInput.dispatchEvent(new Event("input", { bubbles: true }));
            precioInput.dispatchEvent(new Event("change", { bubbles: true }));
        }
    }

    actualizarTotalPedido();
});

function inicializarTotalPedido() {
    actualizarTotalPedido();
    const grupoLineas = document.querySelector(".inline-group");
    if (grupoLineas) {
        new MutationObserver(actualizarTotalPedido).observe(grupoLineas, {
            childList: true,
            subtree: true,
        });
    }
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", inicializarTotalPedido);
} else {
    inicializarTotalPedido();
}
