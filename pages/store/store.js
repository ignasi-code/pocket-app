(function () {
  const CART_KEY = "pocket_store_cart";
  const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
  let catalog = null;
  let variants = new Map();

  function loadCart() {
    try {
      const value = JSON.parse(localStorage.getItem(CART_KEY) || "[]");
      return Array.isArray(value) ? value : [];
    } catch {
      return [];
    }
  }

  function saveCart(cart) {
    localStorage.setItem(CART_KEY, JSON.stringify(cart));
    updateCount();
  }

  function updateCount() {
    const count = loadCart().reduce((total, item) => total + Number(item.qty || 0), 0);
    document.querySelectorAll("[data-cart-count]").forEach(node => {
      node.textContent = String(count);
    });
  }

  function addVariant(id, qty = 1) {
    const variantId = Number(id);
    if (!variantId) return;
    const cart = loadCart();
    const existing = cart.find(item => item.id === variantId);
    if (existing) {
      existing.qty += qty;
    } else {
      cart.push({ id: variantId, qty });
    }
    saveCart(cart);
  }

  function changeQty(id, delta) {
    const variantId = Number(id);
    let cart = loadCart();
    const existing = cart.find(item => item.id === variantId);
    if (!existing) return;
    existing.qty += delta;
    cart = cart.filter(item => item.qty > 0);
    saveCart(cart);
    renderCartPage();
  }

  async function loadCatalog() {
    if (catalog) return catalog;
    const response = await fetch("/store/catalog.json");
    catalog = await response.json();
    variants = new Map();
    for (const product of catalog.products || []) {
      for (const variant of product.variants || []) {
        variants.set(Number(variant.id), { product, variant });
      }
    }
    return catalog;
  }

  function productImage(product, variant) {
    return variant?.featured_image?.src || product?.images?.[0]?.src || "https://placehold.co/360x450";
  }

  function price(value) {
    const number = Number.parseFloat(String(value || "0"));
    return money.format(Number.isFinite(number) ? number : 0);
  }

  function cartSubtotal(cart) {
    return cart.reduce((total, item) => {
      const meta = variants.get(Number(item.id));
      return total + (meta ? Number.parseFloat(meta.variant.price || "0") * item.qty : 0);
    }, 0);
  }

  async function renderCartPage() {
    const root = document.querySelector("[data-cart-page]");
    if (!root) return;
    await loadCatalog();
    const cart = loadCart().filter(item => variants.has(Number(item.id)));
    saveCart(cart);

    const lines = document.querySelector("[data-cart-lines]");
    const subtotal = document.querySelector("[data-cart-subtotal]");
    if (subtotal) subtotal.textContent = money.format(cartSubtotal(cart));

    if (!cart.length) {
      lines.innerHTML = '<div class="empty-state"><p>Your bag is empty.</p></div>';
      return;
    }

    lines.innerHTML = cart.map(item => {
      const meta = variants.get(Number(item.id));
      return `
        <div class="cart-line">
          <img src="${productImage(meta.product, meta.variant)}" alt="">
          <div>
            <strong>${meta.product.title}</strong>
            <div class="notice">${meta.variant.title} - ${price(meta.variant.price)}</div>
            <div class="qty-controls">
              <button type="button" data-cart-dec="${item.id}">-</button>
              <span>${item.qty}</span>
              <button type="button" data-cart-inc="${item.id}">+</button>
            </div>
          </div>
          <strong>${money.format(Number.parseFloat(meta.variant.price || "0") * item.qty)}</strong>
        </div>
      `;
    }).join("");
  }

  async function checkout() {
    const output = document.querySelector("[data-checkout-output]");
    if (output) output.textContent = "Verifying cart...";
    const response = await fetch("/store/api/checkout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cartItems: loadCart() })
    });
    const data = await response.json();
    if (!response.ok) {
      if (output) output.textContent = data.error || "Checkout failed.";
      return;
    }
    if (output) {
      output.innerHTML = `
        <p><strong>Verified:</strong> ${data.item_count} items, ${money.format(data.subtotal_cents / 100)}</p>
        <p><a class="button" href="${data.shopify_cart_url}">Open Shopify cart</a></p>
      `;
    }
  }

  document.addEventListener("click", event => {
    const add = event.target.closest("[data-store-add]");
    if (add) {
      const row = add.closest(".quick-row");
      const select = row?.querySelector("[data-variant-select]");
      addVariant(select ? select.value : add.dataset.variantId);
      add.textContent = "Added";
      setTimeout(() => { add.textContent = "Add"; }, 900);
    }

    const inc = event.target.closest("[data-cart-inc]");
    if (inc) changeQty(inc.dataset.cartInc, 1);

    const dec = event.target.closest("[data-cart-dec]");
    if (dec) changeQty(dec.dataset.cartDec, -1);

    if (event.target.closest("[data-checkout]")) checkout();
  });

  document.addEventListener("submit", event => {
    const form = event.target.closest("[data-product-form]");
    if (!form) return;
    event.preventDefault();
    addVariant(new FormData(form).get("variant_id"));
    window.location.href = "/store/cart";
  });

  updateCount();
  renderCartPage();
})();
