(function () {
  const CATALOG_URL = "/pwa/catalog.json";
  const CART_INDEX_URL = "/pwa/cart-index.json";
  const PULSE_URL = "/store/pulse";
  const CHECKOUT_URL = "/store/api/stripe-checkout";
  const OUTBOX_KEY = "pocket-pwa-outbox";
  const CART_KEY = "pocket-pwa-cart";

  const statusEl = document.querySelector("[data-status]");
  const viewEl = document.querySelector("[data-view]");
  const routeButtons = Array.from(document.querySelectorAll("[data-route]"));

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

  function productByHandle(handle) {
    return catalog?.products?.find((product) => product.handle === handle);
  }

  function firstVariant(product) {
    return product?.variants?.find((variant) => variant.available !== false) || product?.variants?.[0];
  }

  function productImage(product, variant) {
    return variant?.featured_image?.src || product?.images?.[0]?.src || "";
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
      const image = productImage(product, variant);
      return `
        <article class="card">
          ${image ? `<img src="${image}" alt="${product.title}">` : ""}
          <div class="card-body">
            <h2>${product.title}</h2>
            <p class="price">${price}</p>
            <div class="actions">
              <a class="button button--subtle" href="#product/${product.handle}">View</a>
              <button class="button button--primary" data-add="${variant?.id || ""}" type="button">Add</button>
            </div>
          </div>
        </article>`;
    }).join("");
    viewEl.innerHTML = `<div class="grid">${cards || '<div class="empty">No products available.</div>'}</div>`;
  }

  function renderProduct(handle) {
    const product = productByHandle(handle);
    if (!product) {
      viewEl.innerHTML = '<div class="empty">Product not found.</div>';
      return;
    }
    const variant = firstVariant(product);
    const image = productImage(product, variant);
    viewEl.innerHTML = `
      <div class="stack">
        <a class="button button--subtle" href="#home">Back</a>
        <article class="card">
          ${image ? `<img src="${image}" alt="${product.title}">` : ""}
          <div class="card-body">
            <h2>${product.title}</h2>
            <p class="price">${variant?.price ? money(Number(variant.price) * 100) : ""}</p>
            <p class="muted">${product.body_html ? product.body_html.replace(/<[^>]+>/g, " ").trim() : ""}</p>
            <div class="actions">
              <button class="button button--primary" data-add="${variant?.id || ""}" type="button">Add to bag</button>
            </div>
          </div>
        </article>
      </div>`;
  }

  function renderCart() {
    const lines = cartLines();
    const total = lines.reduce((sum, item) => sum + Number(item.qty || 0) * Number(item.variant?.price || 0) * 100, 0);
    if (!lines.length) {
      viewEl.innerHTML = '<div class="empty">Your bag is empty.</div>';
      return;
    }
    viewEl.innerHTML = `
      <div class="stack">
        ${lines.map((item) => `
          <div class="cart-row">
            <strong>${item.product.title}</strong>
            <div class="muted">${item.variant?.title || ""}</div>
            <div class="muted">Qty ${item.qty} · ${item.variant?.price ? money(Number(item.variant.price) * 100) : ""}</div>
          </div>`).join("")}
        <div class="cart-row">
          <strong>Subtotal</strong>
          <div>${money(total)}</div>
          <div class="actions">
            <button class="button button--primary" data-checkout type="button">Checkout</button>
          </div>
        </div>
      </div>`;
  }

  function renderOutbox() {
    const items = outbox();
    if (!items.length) {
      viewEl.innerHTML = '<div class="empty">Nothing is waiting to sync.</div>';
      return;
    }
    viewEl.innerHTML = `
      <div class="stack">
        ${items.map((item) => `
          <div class="outbox-item">
            <strong>${item.kind}</strong>
            <div class="muted">${new Date(item.createdAt).toLocaleString()}</div>
            <div class="actions">
              <button class="button button--primary" data-retry="${item.id}" type="button">Retry now</button>
            </div>
          </div>`).join("")}
      </div>`;
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
    if (route.startsWith("product/")) {
      renderProduct(route.slice("product/".length));
    } else if (route === "cart") {
      renderCart();
    } else if (route === "outbox") {
      renderOutbox();
    } else {
      renderHome();
    }
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

  window.addEventListener("hashchange", render);
  window.addEventListener("online", () => {
    setStatus("Back online.");
    replayOutbox().then(render);
  });
  window.addEventListener("offline", () => setStatus("Offline. Cached store still available."));

  init();
})();
