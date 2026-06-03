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
    renderCartDrawer();
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
    const quantity = Math.max(1, Number(qty) || 1);
    const cart = loadCart();
    const existing = cart.find(item => item.id === variantId);
    if (existing) {
      existing.qty += quantity;
    } else {
      cart.push({ id: variantId, qty: quantity });
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

  function escapeHtml(value) {
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
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

  async function renderCartDrawer() {
    const root = document.querySelector("[data-cart-drawer]");
    if (!root) return;
    await loadCatalog();
    const cart = loadCart().filter(item => variants.has(Number(item.id)));
    const lines = root.querySelector("[data-cart-drawer-lines]");
    const subtotal = root.querySelector("[data-cart-drawer-subtotal]");

    if (subtotal) subtotal.textContent = money.format(cartSubtotal(cart));
    if (!lines) return;

    if (!cart.length) {
      lines.innerHTML = '<div class="empty-state"><p>Your shopping bag is empty</p><p><a class="button" href="/store/collections/shop">start shopping</a></p></div>';
      return;
    }

    lines.innerHTML = cart.map(item => {
      const meta = variants.get(Number(item.id));
      const lineTotal = Number.parseFloat(meta.variant.price || "0") * item.qty;
      return `
        <div class="cart-drawer__line">
          <img src="${productImage(meta.product, meta.variant)}" alt="">
          <div class="cart-drawer__line-title">${escapeHtml(meta.product.title)}</div>
          <div class="cart-drawer__line-meta">${escapeHtml(meta.variant.title)}<br>qty ${item.qty}</div>
          <div class="qty-controls">
            <button type="button" data-cart-dec="${item.id}">-</button>
            <span>${item.qty}</span>
            <button type="button" data-cart-inc="${item.id}">+</button>
          </div>
          <div class="cart-drawer__line-price">${money.format(lineTotal)}</div>
        </div>
      `;
    }).join("");
  }

  function setOverlay(active) {
    document.querySelector("[data-drawer-overlay]")?.classList.toggle("is-active", active);
    document.body.classList.toggle("drawer-is-open", active);
  }

  function closeMenuDrawer() {
    const drawer = document.querySelector("[data-menu-drawer]");
    const toggle = document.querySelector("[data-menu-toggle]");
    if (drawer) drawer.setAttribute("aria-hidden", "true");
    if (toggle) toggle.setAttribute("aria-expanded", "false");
    if (document.querySelector("[data-cart-drawer]")?.getAttribute("aria-hidden") !== "false") {
      setOverlay(false);
    }
  }

  function openMenuDrawer() {
    closeCartDrawer();
    const drawer = document.querySelector("[data-menu-drawer]");
    const toggle = document.querySelector("[data-menu-toggle]");
    if (drawer) drawer.setAttribute("aria-hidden", "false");
    if (toggle) toggle.setAttribute("aria-expanded", "true");
    setOverlay(true);
  }

  function closeCartDrawer() {
    const drawer = document.querySelector("[data-cart-drawer]");
    if (drawer) drawer.setAttribute("aria-hidden", "true");
    if (document.querySelector("[data-menu-drawer]")?.getAttribute("aria-hidden") !== "false") {
      setOverlay(false);
    }
  }

  async function openCartDrawer() {
    closeMenuDrawer();
    await renderCartDrawer();
    const drawer = document.querySelector("[data-cart-drawer]");
    if (drawer) drawer.setAttribute("aria-hidden", "false");
    setOverlay(true);
  }

  function updatePdpGallery(select) {
    const selected = select.selectedOptions?.[0];
    const target = selected?.dataset.imageSrc;
    if (!target) return;
    const image = document.querySelector(`[data-gallery-image-src="${CSS.escape(target)}"]`);
    image?.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "start" });
  }

  function changeProductQty(button, delta) {
    const form = button.closest("[data-product-form]");
    const input = form?.querySelector("[data-product-qty]");
    if (!input) return;
    const value = Math.max(1, Math.min(99, Number(input.value || 1) + delta));
    input.value = String(value);
  }

  async function checkout(scope = document) {
    const root = scope || document;
    const output = root.querySelector("[data-checkout-output]");
    if (output) output.textContent = "Verifying cart...";
    const endpoint = root.dataset.checkoutEndpoint || "/store/api/checkout";
    const response = await fetch(endpoint, {
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
    const menuToggle = event.target.closest("[data-menu-toggle]");
    if (menuToggle) {
      if (menuToggle.getAttribute("aria-expanded") === "true") {
        closeMenuDrawer();
      } else {
        openMenuDrawer();
      }
    }

    if (event.target.closest("[data-menu-close]")) closeMenuDrawer();

    const overlay = event.target.closest("[data-drawer-overlay]");
    if (overlay) {
      closeMenuDrawer();
      closeCartDrawer();
    }

    const cartOpen = event.target.closest("[data-cart-open]");
    if (cartOpen) {
      event.preventDefault();
      openCartDrawer();
    }

    if (event.target.closest("[data-cart-close]")) closeCartDrawer();

    const add = event.target.closest("[data-store-add]");
    if (add) {
      const row = add.closest(".quick-row");
      const select = row?.querySelector("[data-variant-select]");
      addVariant(select ? select.value : add.dataset.variantId);
      add.textContent = "Added";
      setTimeout(() => { add.textContent = "Add"; }, 900);
      openCartDrawer();
    }

    const inc = event.target.closest("[data-cart-inc]");
    if (inc) changeQty(inc.dataset.cartInc, 1);

    const dec = event.target.closest("[data-cart-dec]");
    if (dec) changeQty(dec.dataset.cartDec, -1);

    const qtyInc = event.target.closest("[data-qty-inc]");
    if (qtyInc) changeProductQty(qtyInc, 1);

    const qtyDec = event.target.closest("[data-qty-dec]");
    if (qtyDec) changeProductQty(qtyDec, -1);

    const galleryDot = event.target.closest("[data-gallery-dot]");
    if (galleryDot) {
      const target = galleryDot.dataset.galleryTarget;
      const image = document.querySelector(`[data-gallery-image-src="${CSS.escape(target)}"]`);
      image?.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "start" });
    }

    const checkoutButton = event.target.closest("[data-checkout]");
    if (checkoutButton) checkout(checkoutButton.closest("[data-cart-page], [data-cart-drawer]") || document);
  });

  document.addEventListener("change", event => {
    const select = event.target.closest("[data-pdp-variant-select]");
    if (select) updatePdpGallery(select);
  });

  document.addEventListener("submit", event => {
    const form = event.target.closest("[data-product-form]");
    if (!form) return;
    event.preventDefault();
    const data = new FormData(form);
    addVariant(data.get("variant_id"), Number(data.get("quantity") || 1));
    openCartDrawer();
  });

  updateCount();
  renderCartDrawer();
  renderCartPage();
})();
