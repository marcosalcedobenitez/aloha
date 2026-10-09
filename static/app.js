const WHATSAPP_NUMBER = "573215679037";

const cart = new Map();

const productGrid = document.getElementById("product-grid");
const cartItems = document.getElementById("cart-items");
const cartCount = document.getElementById("cart-count");
const cartTotal = document.getElementById("cart-total");
const searchInput = document.getElementById("search");
const emptyResults = document.getElementById("empty-results");
const orderNotes = document.getElementById("order-notes");

let activeCategory = "destacados";

function formatCOP(value) {
    return "$" + Number(value).toLocaleString("es-CO");
}

function getProduct(id) {
    return productos.find(
        product => product.id === Number(id)
    );
}

function getCartTotal() {
    let total = 0;

    cart.forEach((quantity, id) => {
        const product = getProduct(id);

        if (product) {
            total += Number(product.precio) * quantity;
        }
    });

    return total;
}

function getCartCount() {
    let count = 0;

    cart.forEach(quantity => {
        count += quantity;
    });

    return count;
}

function renderCart() {
    cartItems.replaceChildren();

    if (cart.size === 0) {
        const empty = document.createElement("p");
        empty.className = "cart-empty";
        empty.textContent =
            "Tu carrito está vacío. ¡Elige algo del menú!";
        cartItems.appendChild(empty);
    }

    cart.forEach((quantity, id) => {
        const product = getProduct(id);

        if (!product) {
            return;
        }

        const item = document.createElement("div");
        item.className = "cart-item";

        const info = document.createElement("div");

        const name = document.createElement("h3");
        name.textContent = product.nombre;

        const reference = document.createElement("small");
        reference.textContent = "Ref.: " + product.referencia;

        const price = document.createElement("div");
        price.className = "cart-item-price";
        price.textContent = formatCOP(
            Number(product.precio) * quantity
        );

        info.append(name, reference, price);

        const controls = document.createElement("div");
        controls.className = "quantity-controls";

        const minus = document.createElement("button");
        minus.type = "button";
        minus.textContent = "−";
        minus.setAttribute(
            "aria-label",
            "Disminuir cantidad"
        );
        minus.addEventListener(
            "click",
            () => changeQuantity(id, -1)
        );

        const quantityLabel = document.createElement("span");
        quantityLabel.textContent = quantity;

        const plus = document.createElement("button");
        plus.type = "button";
        plus.textContent = "+";
        plus.setAttribute(
            "aria-label",
            "Aumentar cantidad"
        );
        plus.addEventListener(
            "click",
            () => changeQuantity(id, 1)
        );

        controls.append(minus, quantityLabel, plus);
        item.append(info, controls);
        cartItems.appendChild(item);
    });

    cartCount.textContent = getCartCount();
    cartTotal.textContent = formatCOP(getCartTotal());
}

function addProduct(id) {
    const product = getProduct(id);

    if (!product || !product.disponible) {
        return;
    }

    const currentQuantity = cart.get(product.id) || 0;
    cart.set(product.id, currentQuantity + 1);

    renderCart();
}

function changeQuantity(id, change) {
    const product = getProduct(id);

    if (!product) {
        return;
    }

    const currentQuantity = cart.get(product.id) || 0;
    const newQuantity = currentQuantity + change;

    if (newQuantity <= 0) {
        cart.delete(product.id);
    } else {
        cart.set(product.id, newQuantity);
    }

    renderCart();
}

function filterProducts() {
    const search = searchInput.value
        .trim()
        .toLocaleLowerCase("es");

    let visibleCount = 0;

    document.querySelectorAll(".product-card").forEach(card => {
        const category = (card.dataset.category || "")
            .trim()
            .toLocaleLowerCase("es");

        const name = (card.dataset.name || "")
            .toLocaleLowerCase("es");

        const product = getProduct(card.dataset.id);

        let matchesCategory = false;

        if (activeCategory === "destacados") {
            matchesCategory = Boolean(
                product && product.destacado
            );
        } else if (activeCategory === "combos") {
            matchesCategory = category === "combos";
        } else {
            matchesCategory =
                category === activeCategory
                    .trim()
                    .toLocaleLowerCase("es");
        }

        const reference = product
            ? String(product.referencia || "")
                .toLocaleLowerCase("es")
            : "";

        const matchesSearch =
            name.includes(search) ||
            reference.includes(search);

        const visible = matchesCategory && matchesSearch;

        card.hidden = !visible;

        if (visible) {
            visibleCount++;
        }
    });

    emptyResults.hidden = visibleCount > 0;
}

document.querySelectorAll("[data-add]").forEach(button => {
    button.addEventListener("click", () => {
        addProduct(button.dataset.add);
    });
});

document.querySelectorAll(".category").forEach(button => {
    button.addEventListener("click", () => {
        activeCategory = button.dataset.category;

        document.querySelectorAll(".category").forEach(
            categoryButton => {
                categoryButton.classList.toggle(
                    "active",
                    categoryButton === button
                );
            }
        );

        filterProducts();
    });
});

searchInput.addEventListener("input", filterProducts);

document.getElementById("clear-cart").addEventListener(
    "click",
    () => {
        cart.clear();
        orderNotes.value = "";
        renderCart();
    }
);

document.getElementById("whatsapp-order").addEventListener(
    "click",
    () => {
        if (cart.size === 0) {
            alert(
                "Añade al menos un producto antes de continuar."
            );
            return;
        }

        if (!/^\d{10,15}$/.test(WHATSAPP_NUMBER)) {
            alert(
                "El carrito funciona correctamente. Para activar " +
                "WhatsApp, configura el número comercial en " +
                "static/app.js."
            );
            return;
        }

        const lines = [
            "🍔 PEDIDO — ALOHA",
            "",
        ];

        cart.forEach((quantity, id) => {
            const product = getProduct(id);

            if (!product) {
                return;
            }

            lines.push(
                product.nombre,
                `Referencia: ${product.referencia}`,
                `Cantidad: ${quantity}`,
                `Precio unitario: ${formatCOP(Number(product.precio))}`,
                `Subtotal: ${formatCOP(Number(product.precio) * quantity)}`,
                ""
            );
        });

        const notes = orderNotes.value.trim();

        if (notes) {
            lines.push(
                "Observaciones generales:",
                notes,
                ""
            );
        }

        lines.push(`TOTAL: ${formatCOP(getCartTotal())}`);

        const message = encodeURIComponent(lines.join("\n"));

        window.open(
            `https://wa.me/${WHATSAPP_NUMBER}?text=${message}`,
            "_blank",
            "noopener,noreferrer"
        );
    }
);

renderCart();
filterProducts();