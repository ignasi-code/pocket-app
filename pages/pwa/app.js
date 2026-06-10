(() => {
  const CATALOG_URL = "/pwa/catalog.json";
  const CART_INDEX_URL = "/pwa/cart-index.json";
  const PULSE_URL = "/store/pulse";
  const CHECKOUT_URL = "/store/api/stripe-checkout";
  const OUTBOX_KEY = "pocket-pwa-outbox";
  const CART_KEY = "pocket-pwa-cart";
  const SHIPPING_PROMO_DISMISSED_KEY = "pocket_store_shipping_promo_dismissed";

  const statusEl = document.querySelector("[data-pwa-status]");
  const viewEl = document.querySelector("[data-view]");
  const outboxEl = document.querySelector("[data-outbox]");
  const cartCountEls = Array.from(document.querySelectorAll("[data-cart-count]"));
  const shippingPromo = document.querySelector("[data-shipping-promo]");
  const shippingPromoClose = document.querySelector("[data-shipping-promo-close]");

  let catalog = null;
  let cartIndex = null;

  function readJson(key, fallback) {
    try {
      return JSON.parse(localStorage.getItem(key) || "null") ?? fallback;
    } catch {
      return fallback;
    }
  }

  function writeJson(key, value) {
    localStorage.setItem(key, JSON.stringify(value));
  }

  function money(cents) {
    return `$${(Number(cents || 0) / 100).toFixed(2)}`;
  }

  function getRoute() {
    return (location.hash || "#home").slice(1);
  }

  function setStatus(text) {
    if (statusEl) statusEl.textContent = text;
  }

  function loadCart() {
    return readJson(CART_KEY, []);
  }

  function saveCart(next) {
    writeJson(CART_KEY, next);
    updateCount();
    render();
  }

  function addToCart(variantId) {
    const cart = loadCart();
    const existing = cart.find((item) => Number(item.id) === Number(variantId));
    if (existing) {
      existing.qty = Math.min(99, Number(existing.qty || 0) + 1);
    } else {
      cart.push({ id: Number(variantId), qty: 1 });
    }
    saveCart(cart);
  }

  function cartCount() {
    return loadCart().reduce((total, item) => total + Number(item.qty || 0), 0);
  }

  function updateCount() {
    const count = cartCount();
    const itemLabel = count === 1 ? "item" : "items";
    cartCountEls.forEach((node) => {
      node.textContent = String(count);
      const cartLink = node.closest(".header__cart--page");
      if (cartLink) cartLink.setAttribute("aria-label", `Open bag, ${count} ${itemLabel}`);
    });
  }

  function productByHandle(handle) {
    return catalog?.products?.find((product) => product.handle === handle);
  }

  function firstVariant(product) {
    return product?.variants?.find((variant) => variant.available !== false) || product?.variants?.[0];
  }

  function productImage(product, variant) {
    return variant?.featured_image?.src || product?.images?.[0]?.src || "";
  }

  function shopifyImageUrl(src, width) {
    const value = String(src || "");
    if (!value.includes("cdn.shopify.com/") && !value.includes("/cdn/shop/")) return value;
    try {
      const url = new URL(value, window.location.href);
      url.searchParams.delete("width");
      url.searchParams.delete("height");
      url.searchParams.delete("crop");
      url.searchParams.delete("quality");
      if (width) url.searchParams.set("quality", "60");
      if (width) url.searchParams.set("width", String(width));
      return url.toString();
    } catch {
      return value;
    }
  }

  function cartLines() {
    const lines = [];
    const products = catalog?.products || [];
    const variantIndex = new Map();
    products.forEach((product) => {
      product.variants?.forEach((variant) => {
        variantIndex.set(Number(variant.id), { product, variant });
      });
    });
    loadCart().forEach((item) => {
      const match = variantIndex.get(Number(item.id));
      if (match) lines.push({ ...item, ...match });
    });
    return lines;
  }

  function outbox() {
    return readJson(OUTBOX_KEY, []);
  }

  function saveOutbox(next) {
    writeJson(OUTBOX_KEY, next);
    render();
  }

  function queueAction(kind, payload) {
    const next = outbox();
    next.push({ id: crypto.randomUUID ? crypto.randomUUID() : String(Date.now()), kind, payload, createdAt: Date.now(), attempts: 0 });
    saveOutbox(next);
  }

  async function sendPulse(eventName, data = {}) {
    const payload = { event: eventName, path: location.pathname + location.hash, ...data };
    if (!navigator.onLine) {
      queueAction("pulse", payload);
      return false;
    }
    try {
      const response = await fetch(PULSE_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error("pulse failed");
      return true;
    } catch {
      queueAction("pulse", payload);
      return false;
    }
  }

  async function submitCheckout() {
    const items = cartLines().map((item) => ({ id: Number(item.id), qty: Number(item.qty || 0) }));
    if (!items.length) {
      setStatus("Your bag is empty.");
      return;
    }
    const payload = { cartItems: items };
    if (!navigator.onLine) {
      queueAction("checkout", payload);
      await sendPulse("checkout_initiated", { item_count: items.reduce((n, item) => n + item.qty, 0), offline: true });
      setStatus("Offline. Checkout queued for retry.");
      render();
      return;
    }
    try {
      const response = await fetch(CHECKOUT_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.url) throw new Error(data.error || "Checkout unavailable");
      await sendPulse("checkout_initiated", { item_count: items.reduce((n, item) => n + item.qty, 0), offline: false });
      location.href = data.url;
    } catch {
      queueAction("checkout", payload);
      await sendPulse("checkout_initiated", { item_count: items.reduce((n, item) => n + item.qty, 0), offline: true });
      setStatus("Checkout queued. Retry when back online.");
      render();
    }
  }

  async function replayOutbox() {
    if (!navigator.onLine) return;
    const pending = outbox();
    if (!pending.length) return;
    const remaining = [];
    for (const entry of pending) {
      try {
        entry.attempts += 1;
        if (entry.kind === "pulse") {
          const response = await fetch(PULSE_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(entry.payload),
          });
          if (!response.ok) throw new Error("pulse retry failed");
        } else if (entry.kind === "checkout") {
          const response = await fetch(CHECKOUT_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(entry.payload),
          });
          const data = await response.json().catch(() => ({}));
          if (!response.ok || !data.url) throw new Error("checkout retry failed");
        }
      } catch {
        remaining.push(entry);
      }
    }
    writeJson(OUTBOX_KEY, remaining);
    if (remaining.length) setStatus(`${remaining.length} item(s) still waiting to sync.`);
  }

  function renderHome() {
    const products = catalog?.products || [];
    const cards = products.slice(0, 24).map((product) => {
      const variant = firstVariant(product);
      const price = variant?.price ? money(Number(variant.price) * 100) : "";
      const image = shopifyImageUrl(productImage(product, variant), 540);
      const hoverImage = shopifyImageUrl(product.images?.[1]?.src || productImage(product, variant), 540);
      return `
        <article class="product-card product-tile js-productTile product-tile--collection" data-product-handle="${product.handle}">
          <a href="#product/${product.handle}" class="product-tile__link">
            <div class="product-tile__image">
              <picture>
                <source media="(min-width: 1024px)" srcset="${image}" sizes="25vw">
                <img class="product-tile__image__primary" src="${image}" alt="${product.title}" width="760" height="912" loading="lazy" decoding="async">
              </picture>
              <img class="product-tile__image__hover is-loading" data-src="${hoverImage}" alt="" width="760" height="912" loading="lazy" decoding="async">
            </div>
            <div class="product-tile__top"></div>
          </a>
          <div class="product-card__body product-tile__details product-tile__copy__wrapper">
            <a href="#product/${product.handle}" class="product-tile__copy">
              <h3 class="product-card__title product-tile__title">${product.title}</h3>
              <div class="price product-tile__price">${price}</div>
            </a>
            <div class="quick-row">
              <button class="product-tile__add js-quickshopOpen" type="button" name="add" data-add="${variant?.id || ""}">
                <span class="visually-hidden">open quick shop</span>
                <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                  <path d="M12.4699 12.4697H23.4688V11.4697H12.4699V0.471011H11.4699V11.4697H0.468749V12.4697H11.4699V23.471H12.4699V12.4697Z" fill="black"></path>
                </svg>
              </button>
            </div>
          </div>
        </article>`;
    }).join("");
    viewEl.innerHTML = cards || '<div class="pwa-empty empty-state">No products available.</div>';
  }

  function renderProduct(handle) {
    const product = productByHandle(handle);
    if (!product) {
      viewEl.innerHTML = '<div class="pwa-empty empty-state">Product not found.</div>';
      return;
    }
    const variant = firstVariant(product);
    const image = shopifyImageUrl(productImage(product, variant), 760);
    viewEl.innerHTML = `
      <section class="page product-page">
        <section class="pdp product-info">
          <div class="gallery product-gallery__wrapper">
            <div class="gallery-track product-gallery js-productGallery" data-product-gallery>
              <div class="product-gallery__image__wrapper js-productImage">
                <button class="product-gallery__zoom" type="button" data-add="${variant?.id || ""}">
                  <picture>
                    <source media="(min-width: 1024px)" srcset="${image}" sizes="50vw">
                    <img src="${image}" alt="${product.title}" width="760" height="912" loading="eager" decoding="async">
                  </picture>
                </button>
              </div>
            </div>
          </div>
          <div class="buy-box product-details">
            <div class="product-details-top">
              <div class="product-details-top__images">
                <button class="product-details-top__image" type="button" data-add="${variant?.id || ""}">
                  <span>Zoom image</span>
                  <img src="${image}" alt="${product.title}" width="320" height="384" loading="lazy" decoding="async">
                </button>
              </div>
              <div class="js-productDetailsTop">
                <h1 class="product-details-top__name">${product.title}</h1>
                <div class="price product-details-top__price">${variant?.price ? money(Number(variant.price) * 100) : ""}</div>
              </div>
            </div>
            <div class="product-details-bottom js-productDetailsContent">
              <div class="product-details-bottom__col product-details-bottom__col--info">
                <p class="notice">This is the offline PWA view of the same store catalog.</p>
              </div>
              <div class="product-details-bottom__col product-details-bottom__col--options">
                <div class="product-buy-options">
                  <div class="product-buy-options__add-wrapper">
                    <button class="plain-button button button--blue js-addToBag js-addToBag2" type="button" data-add="${variant?.id || ""}">Add to Bag</button>
                    <div class="product-buy-options__price">${variant?.price ? money(Number(variant.price) * 100) : ""}</div>
                  </div>
                  <p class="notice product-buy-options__shipping">Enjoy complimentary ground shipping on US orders $250+</p>
                </div>
              </div>
            </div>
          </div>
        </section>
      </section>`;
  }

  function renderCart() {
    const lines = cartLines();
    const total = lines.reduce((sum, item) => sum + Number(item.qty || 0) * Math.round(Number(item.variant?.price || 0) * 100), 0);
    if (!lines.length) {
      viewEl.innerHTML = '<div class="pwa-empty empty-state">Your bag is empty.</div>';
      return;
    }
    viewEl.innerHTML = `
      <section class="cart" data-view="cart" data-cart-page>
        <h1 class="visually-hidden">Shopping bag</h1>
        <section class="cart-page js-cartPageSection">
          <div class="cart-page__items" data-cart-lines style="min-height: 497px">
            ${lines.map((item) => `
              <article class="cart-row">
                <strong>${item.product.title}</strong>
                <div class="muted">${item.variant?.title || ""}</div>
                <div class="muted">Qty ${item.qty} · ${item.variant?.price ? money(Number(item.variant.price) * 100) : ""}</div>
              </article>`).join("")}
          </div>
          <div class="cart-page__summary cart-page__totals">
            <div class="cart-page__totals__wrap">
              <p class="cart-page__summary-title cart-page__totals__head">order summary</p>
              <div class="cart-page__totals__list">
                <div class="cart-page__total">
                  <span>order value</span>
                  <strong>${money(total)}</strong>
                </div>
                <div class="cart-page__total cart-page__total--grand">
                  <span>total</span>
                  <strong>${money(total)}</strong>
                </div>
              </div>
              <button class="cart-page__checkout" data-checkout type="button">Checkout</button>
              <button class="cart-page__stripe-checkout" type="button" data-checkout>backup checkout</button>
              <p class="cart-page__shipping cart-page__shipping-info">Enjoy complimentary ground shipping on US orders $250+</p>
              <div class="notice" data-checkout-output></div>
            </div>
          </div>
        </section>
      </section>`;
  }

  function renderOutbox() {
    const items = outbox();
    if (!items.length) {
      viewEl.innerHTML = '<div class="pwa-empty empty-state">Nothing is waiting to sync.</div>';
      return;
    }
    viewEl.innerHTML = `
      <section class="pwa-outbox">
        ${items.map((item) => `
          <article class="pwa-outbox__item cart-row">
            <strong>${item.kind}</strong>
            <div class="pwa-outbox__meta">${new Date(item.createdAt).toLocaleString()}</div>
            <div class="actions">
              <button class="button button--primary" data-retry="${item.id}" type="button">Retry now</button>
            </div>
          </article>`).join("")}
      </section>`;
  }

  async function retryOne(id) {
    const items = outbox();
    const index = items.findIndex((item) => item.id === id);
    if (index === -1 || !navigator.onLine) {
      setStatus("Connect to the network to retry.");
      return;
    }
    const [item] = items.splice(index, 1);
    try {
      if (item.kind === "pulse") {
        await fetch(PULSE_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(item.payload),
        });
      } else {
        await fetch(CHECKOUT_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(item.payload),
        });
      }
      writeJson(OUTBOX_KEY, items);
      setStatus("Synced.");
    } catch {
      items.splice(index, 0, item);
      writeJson(OUTBOX_KEY, items);
      setStatus("Still waiting to sync.");
    }
    render();
  }

  function render() {
    const route = getRoute();
    if (outboxEl) outboxEl.hidden = route !== "outbox";
    if (route.startsWith("product/")) {
      renderProduct(route.slice("product/".length));
    } else if (route === "cart") {
      renderCart();
    } else if (route === "outbox") {
      renderOutbox();
    } else {
      renderHome();
    }
    updateCount();
    setStatus(`${navigator.onLine ? "Online" : "Offline"} · ${cartCount()} item(s) in bag`);
  }

  async function init() {
    try {
      const [catalogResponse, cartIndexResponse] = await Promise.all([fetch(CATALOG_URL), fetch(CART_INDEX_URL)]);
      catalog = await catalogResponse.json();
      cartIndex = await cartIndexResponse.json();
      setStatus(`Loaded ${catalog.products?.length || 0} products.`);
    } catch {
      setStatus("Offline catalogue loaded from cache.");
      catalog = readJson("pocket-pwa-catalog", { products: [] });
      cartIndex = readJson("pocket-pwa-cart-index", {});
    }
    if (catalog) writeJson("pocket-pwa-catalog", catalog);
    if (cartIndex) writeJson("pocket-pwa-cart-index", cartIndex);
    render();
    await replayOutbox();
    await sendPulse("page_view", { source: "pwa" });
    updateCount();
  }

  document.addEventListener("click", (event) => {
    const addButton = event.target.closest("[data-add]");
    if (addButton) {
      addToCart(addButton.getAttribute("data-add"));
      return;
    }
    const checkoutButton = event.target.closest("[data-checkout]");
    if (checkoutButton) {
      submitCheckout();
      return;
    }
    const retryButton = event.target.closest("[data-retry]");
    if (retryButton) {
      retryOne(retryButton.getAttribute("data-retry"));
    }
  });

  if (shippingPromo && shippingPromoClose) {
    try {
      if (localStorage.getItem(SHIPPING_PROMO_DISMISSED_KEY) === "1") {
        shippingPromo.classList.add("is-hidden");
      }
    } catch {}
    shippingPromoClose.addEventListener("click", () => {
      try {
        localStorage.setItem(SHIPPING_PROMO_DISMISSED_KEY, "1");
      } catch {}
      shippingPromo.classList.add("is-hidden");
    });
  }

  window.addEventListener("hashchange", render);
  window.addEventListener("online", () => {
    setStatus("Back online.");
    replayOutbox().then(render);
  });
  window.addEventListener("offline", () => setStatus("Offline. Cached store still available."));

  init();
})();
