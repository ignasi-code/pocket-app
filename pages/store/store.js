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

  function removeVariant(id) {
    const variantId = Number(id);
    const cart = loadCart().filter(item => item.id !== variantId);
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
    const total = document.querySelector("[data-cart-total]");
    const checkoutButton = root.querySelector(".cart-page__checkout");
    const subtotalLabel = money.format(cartSubtotal(cart));
    if (subtotal) subtotal.textContent = subtotalLabel;
    if (total) total.textContent = subtotalLabel;
    if (checkoutButton) checkoutButton.toggleAttribute("disabled", !cart.length);

    if (!cart.length) {
      if (lines) lines.innerHTML = '<div class="empty-state cart-page__empty"><p>Your bag is empty.</p><p><a class="button" href="/store/collections/shop">continue shopping</a></p></div>';
      return;
    }

    if (!lines) return;
    lines.innerHTML = cart.map(item => {
      const meta = variants.get(Number(item.id));
      const lineTotal = Number.parseFloat(meta.variant.price || "0") * item.qty;
      const productUrl = `/store/products/${meta.product.handle}`;
      return `
        <div class="cart-page__item">
          <a class="cart-page__item__image-wrap" href="${productUrl}">
            <img class="cart-page__item__image" src="${productImage(meta.product, meta.variant)}" alt="">
          </a>
          <div class="cart-page__item__copy">
            <div class="cart-page__item__details">
              <a class="cart-page__item__title" href="${productUrl}">${escapeHtml(meta.product.title)}</a>
              <strong class="cart-page__item__line-price">${money.format(lineTotal)}</strong>
            </div>
            <div class="cart-page__item__options">${escapeHtml(meta.variant.title)}<br>${price(meta.variant.price)}</div>
            <div class="cart-page__item__quantity qty-controls cart-page__quantity">
              <span>quantity</span>
              <button class="cart-page__item__button cart-page__item__button--minus" type="button" data-cart-dec="${item.id}" aria-label="Decrease quantity">-</button>
              <span>${item.qty}</span>
              <button class="cart-page__item__button cart-page__item__button--plus" type="button" data-cart-inc="${item.id}" aria-label="Increase quantity">+</button>
            </div>
            <button class="cart-page__item__remove" type="button" data-cart-remove="${item.id}">remove</button>
          </div>
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
    const title = root.querySelector("[data-cart-drawer-title]");
    const content = root.querySelector(".js-cartContent");
    const checkoutButton = root.querySelector(".cart-drawer__checkout");
    const count = cart.reduce((total, item) => total + Number(item.qty || 0), 0);

    if (subtotal) subtotal.textContent = money.format(cartSubtotal(cart));
    if (title) title.textContent = count === 1 ? "Bag (1 item)" : `Bag (${count} items)`;
    if (content) content.dataset.itemCount = String(count);
    if (checkoutButton) checkoutButton.toggleAttribute("disabled", !cart.length);
    if (!lines) return;

    if (!cart.length) {
      lines.innerHTML = '<div class="empty-state"><p>Your shopping bag is empty</p><p><a class="button" href="/store/collections/shop">start shopping</a></p></div>';
      return;
    }

    lines.innerHTML = cart.map(item => {
      const meta = variants.get(Number(item.id));
      const lineTotal = Number.parseFloat(meta.variant.price || "0") * item.qty;
      const productUrl = `/store/products/${meta.product.handle}`;
      return `
        <div class="cart-drawer__item">
          <img class="cart-drawer__item__image" src="${productImage(meta.product, meta.variant)}" alt="">
          <div class="cart-drawer__item__details">
            <a href="${productUrl}">${escapeHtml(meta.product.title)}</a>
            <div class="cart-drawer__item__options">${escapeHtml(meta.variant.title)}</div>
          </div>
          <div class="qty-controls cart-drawer__quantity">
            <button type="button" data-cart-dec="${item.id}">-</button>
            <span>${item.qty}</span>
            <button type="button" data-cart-inc="${item.id}">+</button>
          </div>
          <div class="cart-drawer__item__price">${money.format(lineTotal)}</div>
        </div>
      `;
    }).join("");
  }

  function setOverlay(active) {
    const overlay = document.querySelector("[data-drawer-overlay]");
    overlay?.classList.toggle("is-active", active);
    overlay?.setAttribute("aria-expanded", active ? "true" : "false");
    document.body.classList.toggle("drawer-is-open", active);
  }

  function closeSearchDrawer() {
    const drawer = document.querySelector("[data-search-drawer], .js-searchDrawer");
    const toggle = document.querySelector("[data-search-open]");
    if (drawer) drawer.setAttribute("aria-hidden", "true");
    if (toggle) toggle.setAttribute("aria-expanded", "false");
    document.body.classList.remove("search-is-open");
  }

  function openSearchDrawer() {
    closeMenuDrawer();
    closeCartDrawer();
    closeCollectionDrawers();
    const drawer = document.querySelector("[data-search-drawer], .js-searchDrawer");
    const toggle = document.querySelector("[data-search-open]");
    if (drawer) drawer.setAttribute("aria-hidden", "false");
    if (toggle) toggle.setAttribute("aria-expanded", "true");
    document.body.classList.add("search-is-open");
    drawer?.querySelector("input[type='search']")?.focus();
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
    const toggle = document.querySelector("[data-cart-open]");
    if (drawer) drawer.setAttribute("aria-hidden", "true");
    if (toggle) toggle.setAttribute("aria-expanded", "false");
    if (document.querySelector("[data-menu-drawer]")?.getAttribute("aria-hidden") !== "false") {
      setOverlay(false);
    }
  }

  async function openCartDrawer() {
    closeMenuDrawer();
    await renderCartDrawer();
    const drawer = document.querySelector("[data-cart-drawer]");
    const toggle = document.querySelector("[data-cart-open]");
    if (drawer) drawer.setAttribute("aria-hidden", "false");
    if (toggle) toggle.setAttribute("aria-expanded", "true");
    setOverlay(true);
  }

  function closeCollectionDrawers() {
    document.querySelector("[data-filter-drawer]")?.setAttribute("aria-hidden", "true");
    document.querySelector("[data-sort-drawer]")?.setAttribute("aria-hidden", "true");
    document.querySelector("[data-filter-toggle]")?.setAttribute("aria-expanded", "false");
    document.querySelector("[data-sort-toggle]")?.setAttribute("aria-expanded", "false");
    setCollectionOverlay(false);
  }

  function setCollectionOverlay(active) {
    const overlay = document.querySelector("[data-filter-overlay]");
    overlay?.setAttribute("aria-expanded", active ? "true" : "false");
    document.body.classList.toggle("collection-filter-is-open", active);
  }

  function closeOptionDrawers() {
    document.querySelectorAll("[data-option-selector]").forEach(selector => {
      selector.classList.remove("is-open");
      selector.querySelector("[data-option-trigger]")?.setAttribute("aria-expanded", "false");
      selector.querySelector("[data-option-drawer]")?.setAttribute("aria-hidden", "true");
    });
    document.body.classList.remove("option-is-open");
  }

  function openOptionDrawer(trigger) {
    const selector = trigger.closest("[data-option-selector]");
    if (!selector) return;
    closeOptionDrawers();
    selector.classList.add("is-open");
    trigger.setAttribute("aria-expanded", "true");
    selector.querySelector("[data-option-drawer]")?.setAttribute("aria-hidden", "false");
    document.body.classList.add("option-is-open");
  }

  function openCollectionDrawer(kind) {
    const drawer = document.querySelector(kind === "sort" ? "[data-sort-drawer]" : "[data-filter-drawer]");
    const toggle = document.querySelector(kind === "sort" ? "[data-sort-toggle]" : "[data-filter-toggle]");
    closeCollectionDrawers();
    if (drawer) drawer.setAttribute("aria-hidden", "false");
    if (toggle) toggle.setAttribute("aria-expanded", "true");
    setCollectionOverlay(true);
  }

  function updatePdpGallery(select) {
    const selected = select.selectedOptions?.[0];
    const target = selected?.dataset.imageSrc;
    if (!target) return;
    const image = document.querySelector(`[data-gallery-image-src="${CSS.escape(target)}"]`);
    image?.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "start" });
  }

  function updatePdpSelection(select, scrollGallery = true) {
    const selected = select.selectedOptions?.[0];
    if (!selected) return;
    const form = select.closest("[data-product-form]");
    const title = selected.dataset.title || selected.textContent.trim();
    const triggerTitle = form?.querySelector("[data-option-selected-title]");
    const priceNode = form?.querySelector(".product-buy-options__price");
    const price = selected.dataset.price;

    if (triggerTitle) triggerTitle.textContent = title;
    if (priceNode && price) priceNode.textContent = price;
    if (form && price) form.dataset.selectedPrice = price;
    if (scrollGallery) updatePdpGallery(select);
  }

  function selectPdpOption(choice) {
    const form = choice.closest("[data-product-form]");
    const select = form?.querySelector("[data-pdp-variant-select]");
    if (!select) return;

    const targetUrl = choice.dataset.optionUrl;
    if (targetUrl && targetUrl !== window.location.pathname) {
      window.location.href = targetUrl;
      return;
    }

    select.value = choice.dataset.variantId;
    select.dispatchEvent(new Event("change", { bubbles: true }));

    const selector = choice.closest("[data-option-selector]");
    selector?.querySelectorAll("[data-option-choice]").forEach(node => {
      node.classList.toggle("is-current", node === choice);
      node.closest(".option-selector__variant")?.classList.toggle("option-selector__variant--selected", node === choice);
    });

    closeOptionDrawers();
  }

  function openLightbox(button) {
    const lightbox = document.querySelector("[data-product-lightbox]");
    const image = lightbox?.querySelector("[data-lightbox-image]");
    if (!lightbox || !image) return;
    image.src = button.dataset.lightboxSrc || "";
    image.alt = button.dataset.lightboxAlt || "";
    lightbox.setAttribute("aria-hidden", "false");
    document.body.classList.add("lightbox-is-open");
  }

  function closeLightbox() {
    const lightbox = document.querySelector("[data-product-lightbox]");
    const image = lightbox?.querySelector("[data-lightbox-image]");
    if (!lightbox) return;
    lightbox.setAttribute("aria-hidden", "true");
    if (image) image.removeAttribute("src");
    document.body.classList.remove("lightbox-is-open");
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
      closeCollectionDrawers();
      closeOptionDrawers();
    }

    const cartOpen = event.target.closest("[data-cart-open]");
    if (cartOpen) {
      event.preventDefault();
      openCartDrawer();
    }

    if (event.target.closest("[data-cart-close]")) closeCartDrawer();

    if (event.target.closest("[data-search-open]")) {
      event.preventDefault();
      openSearchDrawer();
    }

    if (event.target.closest("[data-search-close]")) closeSearchDrawer();

    if (event.target.closest("[data-filter-toggle]")) openCollectionDrawer("filter");
    if (event.target.closest("[data-sort-toggle]")) openCollectionDrawer("sort");
    if (event.target.closest("[data-filter-close], [data-sort-close]")) closeCollectionDrawers();

    const optionTrigger = event.target.closest("[data-option-trigger]");
    if (optionTrigger) openOptionDrawer(optionTrigger);

    if (event.target.closest("[data-option-close]")) closeOptionDrawers();

    const optionChoice = event.target.closest("[data-option-choice]");
    if (optionChoice) selectPdpOption(optionChoice);

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

    const remove = event.target.closest("[data-cart-remove]");
    if (remove) removeVariant(remove.dataset.cartRemove);

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

    const lightboxOpen = event.target.closest("[data-lightbox-open]");
    if (lightboxOpen) openLightbox(lightboxOpen);

    if (event.target.closest("[data-lightbox-close]")) closeLightbox();

    const checkoutButton = event.target.closest("[data-checkout]");
    if (checkoutButton) checkout(checkoutButton.closest("[data-cart-page], [data-cart-drawer]") || document);
  });

  document.addEventListener("change", event => {
    const select = event.target.closest("[data-pdp-variant-select]");
    if (select) updatePdpSelection(select);
  });

  document.addEventListener("keydown", event => {
    if (event.key === "Escape") {
      closeSearchDrawer();
      closeCollectionDrawers();
      closeOptionDrawers();
      closeLightbox();
    }
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
  document.querySelectorAll("[data-pdp-variant-select]").forEach(select => updatePdpSelection(select, false));
  renderCartDrawer();
  renderCartPage();
})();
