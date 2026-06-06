(function () {
  const CART_KEY = "pocket_store_cart";
  const SHIPPING_PROMO_DISMISSED_KEY = "pocket_store_shipping_promo_dismissed";
  const storeBaseUrl = (document.body?.dataset.storeBaseUrl || "https://roxanneassoulin.com").replace(/\/+$/, "");
  const displayCurrency = document.body?.dataset.storeDisplayCurrency || "eur";
  const displayEurRate = Number.parseFloat(document.body?.dataset.storeDisplayEurRate || "0.875");
  const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
  const deferredMonoFontCss = '@font-face{font-family:RelativeMono;font-style:normal;font-weight:400;font-display:swap;src:url("https://roxanneassoulin.com/cdn/shop/t/147/assets/relative-mono-10-pitch-pro.woff2") format("woff2")}';
  let catalog = null;
  let catalogPromise = null;
  let cartCatalog = null;
  let cartCatalogKey = "";
  let cartCatalogPromise = null;
  let cartDrawerUpsellsPromise = null;
  let variants = new Map();
  let deferredMonoFontLoaded = false;

  function loadCart() {
    try {
      const value = JSON.parse(localStorage.getItem(CART_KEY) || "[]");
      return Array.isArray(value) ? value : [];
    } catch {
      return [];
    }
  }

  function saveCart(cart, options = {}) {
    localStorage.setItem(CART_KEY, JSON.stringify(cart));
    updateCount();
    if (options.renderDrawer !== false) renderCartDrawer();
  }

  function loadDeferredMonoFont() {
    if (deferredMonoFontLoaded || document.getElementById("store-deferred-mono-font")) return;
    deferredMonoFontLoaded = true;
    const style = document.createElement("style");
    style.id = "store-deferred-mono-font";
    style.textContent = deferredMonoFontCss;
    document.head.appendChild(style);
  }

  function bindDeferredMonoFont() {
    if (!document.querySelector(".product-motto, .product-related-section .section-title, .cart-upsell__title")) return;
    window.addEventListener("scroll", loadDeferredMonoFont, { passive: true, once: true });
    window.addEventListener("pointerdown", loadDeferredMonoFont, { passive: true, once: true });
    window.addEventListener("touchstart", loadDeferredMonoFont, { passive: true, once: true });
    document.addEventListener("focusin", loadDeferredMonoFont, { once: true });
  }

  function shippingPromoDismissed() {
    try {
      return localStorage.getItem(SHIPPING_PROMO_DISMISSED_KEY) === "1";
    } catch {
      return false;
    }
  }

  function hideDismissedShippingPromos() {
    if (!shippingPromoDismissed()) return;
    document.documentElement.classList.add("shipping-promo-dismissed");
    document.querySelectorAll("[data-shipping-promo]").forEach(promo => {
      promo.classList.add("is-hidden");
    });
  }

  function persistShippingPromoDismissal() {
    try {
      localStorage.setItem(SHIPPING_PROMO_DISMISSED_KEY, "1");
    } catch {}
    document.documentElement.classList.add("shipping-promo-dismissed");
    document.querySelectorAll("[data-shipping-promo]").forEach(promo => {
      promo.classList.add("is-hidden");
    });
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

  function buildVariantIndex(products) {
    variants = new Map();
    for (const product of products || []) {
      for (const variant of product.variants || []) {
        variants.set(Number(variant.id), { product, variant });
      }
    }
  }

  async function loadCatalog() {
    if (catalog) return catalog;
    if (catalogPromise) return catalogPromise;
    catalogPromise = fetch("/store/catalog.json")
      .then(response => response.json())
      .then(data => {
        catalog = data;
        buildVariantIndex(catalog.products);
        return catalog;
      })
      .catch(error => {
        catalogPromise = null;
        throw error;
      });
    return catalogPromise;
  }

  function cartCatalogUrl(cart) {
    const ids = [...new Set((cart || [])
      .map(item => Number(item.id))
      .filter(id => Number.isFinite(id) && id > 0))]
      .sort((a, b) => a - b);
    if (!ids.length) return "/store/cart-index.json";
    return `/store/cart-items.json?ids=${ids.join(",")}`;
  }

  async function loadCartCatalog(cart = []) {
    if (catalog) {
      cartCatalog = catalog;
      cartCatalogKey = "catalog";
      buildVariantIndex(cartCatalog.products);
      return cartCatalog;
    }
    const url = cartCatalogUrl(cart);
    if (cartCatalog && cartCatalogKey === url) return cartCatalog;
    if (cartCatalogPromise && cartCatalogKey === url) return cartCatalogPromise;
    cartCatalogKey = url;
    cartCatalogPromise = fetch(url)
      .then(response => response.json())
      .then(data => {
        cartCatalog = data;
        buildVariantIndex(cartCatalog.products);
        return cartCatalog;
      })
      .catch(error => {
        cartCatalogPromise = null;
        cartCatalogKey = "";
        throw error;
      });
    return cartCatalogPromise;
  }

  async function productByHandle(handle) {
    const data = await loadCatalog();
    return (data.products || []).find(product => product.handle === handle);
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

  function productImage(product, variant, width) {
    const src = variant?.featured_image?.src || product?.images?.[0]?.src || "https://placehold.co/360x450";
    return shopifyImageUrl(src, width);
  }

  function hydrateDeferredImage(image) {
    if (!image || image.dataset.loaded === "true") return;
    image.closest("picture")?.querySelectorAll("source[data-srcset]").forEach(source => {
      source.srcset = source.dataset.srcset;
      if (source.dataset.sizes) source.sizes = source.dataset.sizes;
    });
    image.addEventListener("load", () => {
      image.classList.remove("is-loading");
      image.classList.add("is-loaded");
    }, { once: true });
    image.src = image.dataset.src;
    if (image.dataset.srcset) image.srcset = image.dataset.srcset;
    if (image.dataset.sizes) image.sizes = image.dataset.sizes;
    image.dataset.loaded = "true";
  }

  function hydrateProductTileHoverImage(tile) {
    hydrateDeferredImage(tile?.querySelector(".product-tile__image__hover[data-src]"));
  }

  function updateDeferredImageSource(image, src, srcset, sizes) {
    if (!image || !src) return;
    image.dataset.src = src;
    if (srcset) image.dataset.srcset = srcset;
    if (sizes) image.dataset.sizes = sizes;
    if (image.dataset.loaded === "true") {
      image.src = src;
      if (srcset) image.srcset = srcset;
      if (sizes) image.sizes = sizes;
    }
  }

  function hydrateCartDrawerImages() {
    document.querySelectorAll("[data-cart-drawer] [data-cart-deferred-image][data-src]").forEach(hydrateDeferredImage);
  }

  async function loadCartDrawerUpsells() {
    const target = document.querySelector("[data-cart-drawer-upsell-fragment]");
    if (!target || target.dataset.loaded === "true") return;
    if (cartDrawerUpsellsPromise) return cartDrawerUpsellsPromise;
    if (!target.dataset.fragmentUrl) return;
    cartDrawerUpsellsPromise = fetch(target.dataset.fragmentUrl)
      .then(response => response.text())
      .then(html => {
        target.innerHTML = html;
        target.dataset.loaded = "true";
      })
      .catch(() => {
        cartDrawerUpsellsPromise = null;
      });
    return cartDrawerUpsellsPromise;
  }

  function hydrateVisibleHomeImages() {
    const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
    const buffer = viewportHeight * 0.65;
    document.querySelectorAll("[data-home-deferred-image][data-src]").forEach(image => {
      const target = image.closest(".shopify-section") || image;
      const rect = target.getBoundingClientRect();
      if (rect.top < viewportHeight + buffer && rect.bottom > -buffer) {
        hydrateDeferredImage(image);
      }
    });
  }

  function bindDeferredHomeImageHydration() {
    if (!document.querySelector("[data-home-deferred-image][data-src]")) return;
    let scheduled = false;
    const scheduleHydration = () => {
      if (scheduled) return;
      scheduled = true;
      requestAnimationFrame(() => {
        scheduled = false;
        hydrateVisibleHomeImages();
      });
    };
    window.addEventListener("scroll", scheduleHydration, { passive: true });
    window.addEventListener("pointerdown", scheduleHydration, { passive: true });
    window.addEventListener("touchstart", scheduleHydration, { passive: true });
  }

  function hydrateVisibleProductCardImages() {
    const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
    const buffer = viewportHeight * 0.75;
    document.querySelectorAll("[data-product-card-deferred-image][data-src]").forEach(image => {
      const target = image.closest(".product-tile") || image;
      const rect = target.getBoundingClientRect();
      if (rect.top < viewportHeight + buffer && rect.bottom > -buffer) {
        hydrateDeferredImage(image);
      }
    });
  }

  function bindDeferredProductCardImageHydration() {
    if (!document.querySelector("[data-product-card-deferred-image][data-src]")) return;
    let scheduled = false;
    const scheduleHydration = () => {
      if (scheduled) return;
      scheduled = true;
      requestAnimationFrame(() => {
        scheduled = false;
        hydrateVisibleProductCardImages();
      });
    };
    window.addEventListener("scroll", scheduleHydration, { passive: true });
    window.addEventListener("pointerdown", scheduleHydration, { passive: true });
    window.addEventListener("touchstart", scheduleHydration, { passive: true });
  }

  function loadDeferredCollectionProducts(sentinel) {
    if (!sentinel || sentinel.dataset.loading === "true" || sentinel.dataset.loaded === "true") return;
    const grid = document.querySelector("[data-collection-grid]");
    if (!grid || !sentinel.dataset.fragmentUrl) return;
    sentinel.dataset.loading = "true";
    fetch(sentinel.dataset.fragmentUrl)
      .then(response => response.text())
      .then(html => {
        const template = document.createElement("template");
        template.innerHTML = html.trim();
        grid.appendChild(template.content);
        sentinel.dataset.loaded = "true";
        sentinel.remove();
        hydrateVisibleProductCardImages();
      })
      .catch(() => {
        sentinel.dataset.loading = "false";
      });
  }

  function bindDeferredCollectionProducts() {
    const sentinel = document.querySelector("[data-collection-deferred-products]");
    if (!sentinel) return;
    if ("IntersectionObserver" in window) {
      const observer = new IntersectionObserver(entries => {
        if (!entries.some(entry => entry.isIntersecting)) return;
        observer.disconnect();
        loadDeferredCollectionProducts(sentinel);
      }, { rootMargin: "900px 0px" });
      observer.observe(sentinel);
      return;
    }
    window.addEventListener("scroll", () => loadDeferredCollectionProducts(sentinel), { passive: true, once: true });
    window.addEventListener("pointerdown", () => loadDeferredCollectionProducts(sentinel), { passive: true, once: true });
    window.addEventListener("touchstart", () => loadDeferredCollectionProducts(sentinel), { passive: true, once: true });
  }

  function loadDeferredCartPageUpsells(sentinel) {
    if (!sentinel || sentinel.dataset.loading === "true" || sentinel.dataset.loaded === "true") return;
    if (!sentinel.dataset.fragmentUrl) return;
    sentinel.dataset.loading = "true";
    fetch(sentinel.dataset.fragmentUrl)
      .then(response => response.text())
      .then(html => {
        sentinel.innerHTML = html.trim();
        sentinel.dataset.loaded = "true";
        loadDeferredMonoFont();
        hydrateVisibleProductCardImages();
      })
      .catch(() => {
        sentinel.dataset.loading = "false";
      });
  }

  function bindDeferredCartPageUpsells() {
    const sentinel = document.querySelector("[data-cart-page-upsell-fragment]");
    if (!sentinel) return;
    window.addEventListener("scroll", () => loadDeferredCartPageUpsells(sentinel), { passive: true, once: true });
    window.addEventListener("pointerdown", () => loadDeferredCartPageUpsells(sentinel), { passive: true, once: true });
    window.addEventListener("touchstart", () => loadDeferredCartPageUpsells(sentinel), { passive: true, once: true });
  }

  function hydrateVisibleProductDetailImages() {
    const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
    const buffer = viewportHeight * 0.5;
    document.querySelectorAll("[data-product-details-deferred-image][data-src]").forEach(image => {
      const target = image.closest(".product-details-top") || image;
      const rect = target.getBoundingClientRect();
      if (rect.top < viewportHeight + buffer && rect.bottom > -buffer) {
        hydrateDeferredImage(image);
      }
    });
  }

  function bindDeferredProductDetailImageHydration() {
    if (!document.querySelector("[data-product-details-deferred-image][data-src]")) return;
    let scheduled = false;
    const scheduleHydration = () => {
      if (scheduled) return;
      scheduled = true;
      requestAnimationFrame(() => {
        scheduled = false;
        hydrateVisibleProductDetailImages();
      });
    };
    window.addEventListener("scroll", scheduleHydration, { passive: true });
    window.addEventListener("pointerdown", scheduleHydration, { passive: true });
    window.addEventListener("touchstart", scheduleHydration, { passive: true });
  }

  function hydrateVisibleGalleryImages(gallery) {
    if (!gallery) return;
    const galleryRect = gallery.getBoundingClientRect();
    gallery.querySelectorAll("[data-gallery-image][data-src]").forEach(image => {
      const target = image.closest(".product-gallery__image__wrapper") || image;
      const rect = target.getBoundingClientRect();
      const buffer = galleryRect.width * 0.35;
      if (rect.left < galleryRect.right + buffer && rect.right > galleryRect.left - buffer) {
        hydrateDeferredImage(image);
      }
    });
  }

  function bindDeferredGalleryHydration() {
    document.querySelectorAll("[data-product-gallery]").forEach(gallery => {
      let scheduled = false;
      const scheduleHydration = () => {
        if (scheduled) return;
        scheduled = true;
        requestAnimationFrame(() => {
          scheduled = false;
          hydrateVisibleGalleryImages(gallery);
        });
      };
      gallery.addEventListener("scroll", scheduleHydration, { passive: true });
      gallery.addEventListener("pointerdown", scheduleHydration, { passive: true });
      gallery.addEventListener("touchstart", scheduleHydration, { passive: true });
    });
  }

  function hydrateVisibleFooterImages() {
    const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
    const buffer = viewportHeight * 0.65;
    document.querySelectorAll("[data-footer-deferred-image][data-src]").forEach(image => {
      const target = image.closest(".footer") || image;
      const rect = target.getBoundingClientRect();
      if (rect.top < viewportHeight + buffer && rect.bottom > -buffer) {
        hydrateDeferredImage(image);
      }
    });
  }

  function bindDeferredFooterImageHydration() {
    if (!document.querySelector("[data-footer-deferred-image][data-src]")) return;
    let scheduled = false;
    const scheduleHydration = () => {
      if (scheduled) return;
      scheduled = true;
      requestAnimationFrame(() => {
        scheduled = false;
        hydrateVisibleFooterImages();
      });
    };
    window.addEventListener("scroll", scheduleHydration, { passive: true });
    window.addEventListener("pointerdown", scheduleHydration, { passive: true });
    window.addEventListener("touchstart", scheduleHydration, { passive: true });
  }

  function escapeHtml(value) {
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function displayAmount(value) {
    const number = Number.parseFloat(String(value || "0"));
    if (!Number.isFinite(number) || number <= 0) return 0;
    if (displayCurrency !== "eur") return number;
    const convertedWholeUnits = Math.floor(number * displayEurRate);
    return convertedWholeUnits + 0.95;
  }

  function formatDisplayAmount(amount) {
    if (displayCurrency === "eur") {
      const [whole, cents] = Number(amount || 0).toFixed(2).split(".");
      return `\u20ac${whole},${cents}`;
    }
    return money.format(Number.isFinite(amount) ? amount : 0);
  }

  function formatDisplayPrice(value) {
    return formatDisplayAmount(displayAmount(value));
  }

  function price(value) {
    return formatDisplayPrice(value);
  }

  function isBundleVariant(product, variant) {
    const title = `${product?.title || ""} ${variant?.title || ""}`;
    return Number(variant?.position || 0) === 1
      && Array.isArray(product?.variants)
      && product.variants.length > 1
      && /\b(set|stack)\b/i.test(title);
  }

  function isSetProduct(product) {
    return Array.isArray(product?.variants)
      && product.variants.length > 1
      && /\b(set|stack)\b/i.test(String(product?.title || ""));
  }

  function isBundleStyleLine(product, variant) {
    return isSetProduct(product) || isBundleVariant(product, variant);
  }

  function bundleIncludeTitle(product, variant) {
    const title = String(variant?.title || "");
    const productTitle = String(product?.title || "");
    const family = productTitle.includes("Bracelet") ? "Bracelet" : "Necklace";

    if (/Cylinder Cord/i.test(title)) {
      return title.replace(/\s+in\s+/i, " - ");
    }

    if (/Bone & Black Coconut/i.test(title) || /Striped Moss Agate/i.test(title)) {
      return `The Salt & Pepper ${family} Duo - ${title}`;
    }

    return title;
  }

  function bundleIncludes(product, variant) {
    return bundleIncludeItems(product, variant).map(item => item.title);
  }

  function bundleIncludeItems(product, variant) {
    if (!isBundleStyleLine(product, variant)) return [];
    const children = isBundleVariant(product, variant)
      ? product.variants.filter(child => Number(child.id) !== Number(variant.id)).slice().reverse()
      : [variant];

    return children.map(child => ({
      id: child.id,
      image: productImage(product, child, 64),
      title: bundleIncludeTitle(product, child)
    }));
  }

  function cartPageOptionsHtml(meta) {
    const includes = bundleIncludeItems(meta.product, meta.variant);
    if (!includes.length) {
      return `<div class="cart-page__item__options">${escapeHtml(meta.variant.title)}</div>`;
    }

    return `
      <ul class="cart-page__item__options cart-page__item__options--includes">
        <li>${escapeHtml(meta.variant.title)}</li>
        <li class="bundle-options-label">includes:</li>
        ${includes.map((item, index) => `
          <li class="${index === 0 ? "bundle-child first" : "bundle-child"}">
            <img loading="lazy" decoding="async" src="${item.image}" alt="">
            <span>${escapeHtml(item.title)}</span>
          </li>
        `).join("")}
      </ul>
    `;
  }

  function drawerOptionsHtml(meta, item) {
    const includes = bundleIncludes(meta.product, meta.variant);
    if (!includes.length) {
      return `
        <ul class="cart-drawer__item__options">
          <li>${escapeHtml(meta.variant.title)}</li>
          <li>quantity: ${item.qty}</li>
        </ul>
      `;
    }

    return `
      <ul class="cart-drawer__item__options cart-drawer__item__options--includes">
        <li>${escapeHtml(meta.variant.title)}</li>
        ${includes.map(title => `<li>${escapeHtml(title)}</li>`).join("")}
        <li>quantity: ${item.qty}</li>
      </ul>
    `;
  }

  function cartPageQuantityHtml(item, meta) {
    if (isBundleStyleLine(meta.product, meta.variant)) return "";

    return `
      <div class="cart-page__item__quantity qty-controls cart-page__quantity">
        <span>quantity</span>
        <button class="cart-page__item__button cart-page__item__button--minus" type="button" data-cart-dec="${item.id}" aria-label="Decrease quantity">-</button>
        <span>${item.qty}</span>
        <button class="cart-page__item__button cart-page__item__button--plus" type="button" data-cart-inc="${item.id}" aria-label="Increase quantity">+</button>
      </div>
    `;
  }

  function cartGiftMessageHtml() {
    return `
      <div class="cart-page__gift-message__wrap">
        <input aria-controls="gift-message" class="js-cartGiftToggle cart-page__gift-toggle" id="cart-gift" name="gift" type="checkbox" data-gift-toggle>
        <label for="cart-gift"><span>this is a gift</span></label>
        <div class="cart-page__gift-message" id="gift-message" aria-labelledby="gift-message-label" aria-hidden="true" data-gift-message style="height: 0">
          <div>
            <div class="cart-page__gift-message__head" id="gift-message-label">
              <span>add a gift message (up to 100 characters)</span>
            </div>
            <textarea placeholder="type your message" class="js-cartGiftMessage" maxlength="100" disabled data-gift-textarea></textarea>
            <button class="button button--cart-message-save js-cartGiftMessageSave" type="button" aria-live="polite" disabled data-gift-save>Save</button>
          </div>
        </div>
      </div>
    `;
  }

  function cartSubtotal(cart) {
    return cart.reduce((total, item) => {
      const meta = variants.get(Number(item.id));
      return total + (meta ? displayAmount(meta.variant.price) * item.qty : 0);
    }, 0);
  }

  async function renderCartPage() {
    const root = document.querySelector("[data-cart-page]");
    if (!root) return;
    const rawCart = loadCart().filter(item => Number(item.qty || 0) > 0);
    const lines = document.querySelector("[data-cart-lines]");
    const subtotal = document.querySelector("[data-cart-subtotal]");
    const total = document.querySelector("[data-cart-total]");
    const checkoutButton = root.querySelector(".cart-page__checkout");

    if (!rawCart.length) {
      if (subtotal) subtotal.textContent = formatDisplayAmount(0);
      if (total) total.textContent = formatDisplayAmount(0);
      if (checkoutButton) checkoutButton.toggleAttribute("disabled", true);
      if (lines) lines.innerHTML = '<div class="empty-state cart-page__empty"><p>Your bag is empty.</p><p><a class="button" href="/store/collections/shop">continue shopping</a></p></div>';
      return;
    }

    await loadCartCatalog(rawCart);
    const cart = rawCart.filter(item => variants.has(Number(item.id)));
    saveCart(cart, { renderDrawer: false });

    const subtotalLabel = formatDisplayAmount(cartSubtotal(cart));
    if (subtotal) subtotal.textContent = subtotalLabel;
    if (total) total.textContent = subtotalLabel;
    if (checkoutButton) checkoutButton.toggleAttribute("disabled", !cart.length);

    if (!cart.length) {
      if (lines) lines.innerHTML = '<div class="empty-state cart-page__empty"><p>Your bag is empty.</p><p><a class="button" href="/store/collections/shop">continue shopping</a></p></div>';
      return;
    }

    if (!lines) return;
    const cartLinesHtml = cart.map(item => {
      const meta = variants.get(Number(item.id));
      const lineTotal = displayAmount(meta.variant.price) * item.qty;
      const productUrl = `/store/products/${meta.product.handle}`;
      const bundleStyle = isBundleStyleLine(meta.product, meta.variant);
      const bundleSingleClass = bundleStyle && bundleIncludeItems(meta.product, meta.variant).length <= 1 ? " cart-page__item--bundle-single" : "";
      const bundleClass = bundleStyle ? ` cart-page__item--bundle${bundleSingleClass}` : "";
      return `
        <div class="cart-page__item${bundleClass}">
          <div class="cart-page__item__copy">
            <div class="cart-page__item__details">
              <a class="cart-page__item__image-mobile cart-page__item__image-mobile--top" href="${productUrl}" aria-label="${escapeHtml(meta.product.title)}">
                <img class="cart-page__item__image" src="${productImage(meta.product, meta.variant, 180)}" alt="">
              </a>
              <a class="cart-page__item__title" href="${productUrl}">${escapeHtml(meta.product.title)}</a>
              <strong class="cart-page__item__line-price">${formatDisplayAmount(lineTotal)}</strong>
            </div>
            ${cartPageOptionsHtml(meta)}
            ${cartPageQuantityHtml(item, meta)}
            <button class="cart-page__item__remove" type="button" data-cart-remove="${item.id}">remove</button>
          </div>
        </div>
      `;
    }).join("");
    lines.innerHTML = `
      ${cartLinesHtml}
      ${cartGiftMessageHtml()}
    `;
  }

  async function renderCartDrawer() {
    const root = document.querySelector("[data-cart-drawer]");
    if (!root) return;
    const rawCart = loadCart().filter(item => Number(item.qty || 0) > 0);
    const lines = root.querySelector("[data-cart-drawer-lines]");
    const subtotal = root.querySelector("[data-cart-drawer-subtotal]");
    const title = root.querySelector("[data-cart-drawer-title]");
    const content = root.querySelector(".js-cartContent");
    const checkoutButton = root.querySelector(".cart-drawer__checkout");

    if (!rawCart.length) {
      if (subtotal) subtotal.textContent = formatDisplayAmount(0);
      if (title) title.textContent = "Bag (0 items)";
      if (content) content.dataset.itemCount = "0";
      if (checkoutButton) checkoutButton.toggleAttribute("disabled", true);
      if (lines) lines.innerHTML = '<div class="empty-state"><p>Your shopping bag is empty</p><p><a class="button" href="/store/collections/shop">start shopping</a></p></div>';
      return;
    }

    await loadCartCatalog(rawCart);
    const cart = rawCart.filter(item => variants.has(Number(item.id)));
    const count = cart.reduce((total, item) => total + Number(item.qty || 0), 0);

    if (subtotal) subtotal.textContent = formatDisplayAmount(cartSubtotal(cart));
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
      const lineTotal = displayAmount(meta.variant.price) * item.qty;
      const productUrl = `/store/products/${meta.product.handle}`;
      const drawerBundleClass = isBundleStyleLine(meta.product, meta.variant) ? " cart-drawer__item--bundle" : "";
      return `
        <li class="cart-drawer__item${drawerBundleClass}">
          <a class="cart-drawer__item__link" href="${productUrl}">
            <img class="cart-drawer__item__image" src="${productImage(meta.product, meta.variant, 180)}" alt="">
            <div class="cart-drawer__item__details">
              <span>${escapeHtml(meta.product.title)}</span>
              <span class="cart-drawer__item__price">${formatDisplayAmount(lineTotal)}</span>
            </div>
            ${drawerOptionsHtml(meta, item)}
          </a>
        </li>
      `;
    }).join("");
  }

  function toggleGiftMessage(input) {
    const wrap = input.closest(".cart-page__gift-message__wrap");
    const panel = wrap?.querySelector("[data-gift-message]");
    const textarea = wrap?.querySelector(".js-cartGiftMessage");
    const saveButton = wrap?.querySelector("[data-gift-save]");
    const active = input.checked;
    if (panel) {
      panel.setAttribute("aria-hidden", active ? "false" : "true");
      panel.style.height = active ? `${panel.scrollHeight}px` : "0";
    }
    if (textarea) textarea.disabled = !active;
    if (saveButton) saveButton.disabled = !active;
  }

  function setOverlay(active) {
    const overlay = document.querySelector("[data-drawer-overlay]");
    overlay?.classList.toggle("is-active", active);
    overlay?.setAttribute("aria-expanded", active ? "true" : "false");
    document.body.classList.toggle("drawer-is-open", active);
  }

  function cartDrawerOpenRight() {
    return window.matchMedia("(min-width: 1024px)").matches ? "8px" : "10px";
  }

  function setCartDrawerVisibility(drawer, visible) {
    if (!drawer) return;
    drawer.classList.toggle("is-open", visible);
    if (visible) {
      drawer.style.setProperty("height", "auto", "important");
      drawer.style.setProperty("left", "auto", "important");
      drawer.style.setProperty("opacity", "1", "important");
      drawer.style.setProperty("overflow", "visible", "important");
      drawer.style.setProperty("right", cartDrawerOpenRight(), "important");
      drawer.style.setProperty("transition", "none", "important");
      drawer.style.setProperty("transform", "none", "important");
      drawer.style.setProperty("visibility", "visible", "important");
      return;
    }
    drawer.style.removeProperty("height");
    drawer.style.removeProperty("left");
    drawer.style.removeProperty("opacity");
    drawer.style.removeProperty("overflow");
    drawer.style.removeProperty("right");
    drawer.style.removeProperty("transition");
    drawer.style.removeProperty("transform");
    drawer.style.removeProperty("visibility");
  }

  function setMenuDrawerVisibility(drawer, visible) {
    if (!drawer) return;
    drawer.classList.toggle("is-open", visible);
    if (visible) {
      drawer.style.setProperty("transition", "none", "important");
      drawer.style.setProperty("transform", "translateX(0)", "important");
      drawer.style.setProperty("visibility", "visible", "important");
      return;
    }
    drawer.style.removeProperty("transition");
    drawer.style.removeProperty("transform");
    drawer.style.removeProperty("visibility");
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
    if (drawer) {
      drawer.setAttribute("aria-hidden", "true");
      setMenuDrawerVisibility(drawer, false);
    }
    if (toggle) toggle.setAttribute("aria-expanded", "false");
    if (document.querySelector("[data-cart-drawer]")?.getAttribute("aria-hidden") !== "false") {
      setOverlay(false);
    }
  }

  function openMenuDrawer() {
    closeCartDrawer();
    const drawer = document.querySelector("[data-menu-drawer]");
    const toggle = document.querySelector("[data-menu-toggle]");
    if (drawer) {
      drawer.setAttribute("aria-hidden", "false");
      setMenuDrawerVisibility(drawer, true);
    }
    if (toggle) toggle.setAttribute("aria-expanded", "true");
    setOverlay(true);
  }

  function closeCartDrawer() {
    const drawer = document.querySelector("[data-cart-drawer]");
    const toggle = document.querySelector("[data-cart-open]");
    if (drawer) {
      drawer.setAttribute("aria-hidden", "true");
      setCartDrawerVisibility(drawer, false);
    }
    if (toggle) toggle.setAttribute("aria-expanded", "false");
    if (document.querySelector("[data-menu-drawer]")?.getAttribute("aria-hidden") !== "false") {
      setOverlay(false);
    }
  }

  function setQuickshopVisibility(visible) {
    const drawer = document.querySelector(".js-quickshopDrawer");
    const overlay = document.querySelector(".js-quickshopClose.quickshop__overlay");
    if (drawer) {
      drawer.setAttribute("aria-hidden", visible ? "false" : "true");
      if (visible) {
        drawer.style.setProperty("height", "auto", "important");
        drawer.style.setProperty("opacity", "1", "important");
        drawer.style.setProperty("top", "auto", "important");
        drawer.style.setProperty("transition", "none", "important");
        drawer.style.setProperty("transform", "translateY(0)", "important");
        drawer.style.setProperty("visibility", "visible", "important");
      } else {
        drawer.style.removeProperty("height");
        drawer.style.removeProperty("opacity");
        drawer.style.removeProperty("top");
        drawer.style.removeProperty("transition");
        drawer.style.removeProperty("transform");
        drawer.style.removeProperty("visibility");
      }
    }
    if (overlay) overlay.setAttribute("aria-expanded", visible ? "true" : "false");
    document.body.classList.toggle("quickshop-is-open", visible);
  }

  function closeQuickshopDrawer() {
    setQuickshopVisibility(false);
  }

  function quickshopOptionHtml(product, selectedVariant) {
    return (product.variants || []).map(variant => `
      <option value="${variant.id}" data-price="${formatDisplayPrice(variant.price)}" data-image-src="${productImage(product, variant, 480)}" ${Number(variant.id) === Number(selectedVariant.id) ? "selected" : ""} ${variant.available === false ? "disabled" : ""}>
        ${escapeHtml(variant.title)} - ${formatDisplayPrice(variant.price)}${variant.available === false ? " - sold out" : ""}
      </option>
    `).join("");
  }

  async function renderQuickshop(handle) {
    const drawer = document.querySelector(".js-quickshopDrawer");
    if (!drawer) return null;
    const product = await productByHandle(handle);
    if (!product) return null;
    const selectedVariant = (product.variants || []).find(variant => variant.available !== false) || product.variants?.[0];
    if (!selectedVariant) return null;

    const top = drawer.querySelector("[data-quickshop-top]");
    const image = drawer.querySelector("[data-quickshop-image]");
    const details = drawer.querySelector("[data-quickshop-details]");
    if (top) {
      top.innerHTML = `
        <p class="quickshop__title">${escapeHtml(product.title)}</p>
        <p class="quickshop__price" data-quickshop-price>${formatDisplayPrice(selectedVariant.price)}</p>
      `;
    }
    if (image) {
      image.innerHTML = `<img src="${productImage(product, selectedVariant, 480)}" alt="${escapeHtml(product.title)}" data-quickshop-image-current>`;
    }
    if (details) {
      details.innerHTML = `
        <form class="quickshop__form" data-quickshop-form>
          <select aria-label="Variant for ${escapeHtml(product.title)}" data-quickshop-select>
            ${quickshopOptionHtml(product, selectedVariant)}
          </select>
          <button class="quickshop__add button button--blue" type="button" data-quickshop-add>Add to Bag</button>
        </form>
      `;
    }
    return product;
  }

  async function openQuickshopDrawer(handle) {
    closeMenuDrawer();
    closeCartDrawer();
    closeSearchDrawer();
    closeCollectionDrawers();
    const product = await renderQuickshop(handle);
    if (!product) return;
    setQuickshopVisibility(true);
  }

  async function openCartDrawer() {
    closeMenuDrawer();
    closeQuickshopDrawer();
    await renderCartDrawer();
    await loadCartDrawerUpsells();
    const drawer = document.querySelector("[data-cart-drawer]");
    const toggle = document.querySelector("[data-cart-open]");
    if (drawer) {
      hydrateCartDrawerImages();
      drawer.setAttribute("aria-hidden", "false");
      setCartDrawerVisibility(drawer, true);
    }
    if (toggle) toggle.setAttribute("aria-expanded", "true");
    setOverlay(true);
  }

  function setCollectionDrawerVisibility(drawer, visible) {
    if (!drawer) return;
    if (visible) {
      drawer.style.setProperty("opacity", "1", "important");
      drawer.style.setProperty("pointer-events", "auto", "important");
      drawer.style.setProperty("transform", "translateY(0)", "important");
      drawer.style.setProperty("visibility", "visible", "important");
      return;
    }
    drawer.style.removeProperty("opacity");
    drawer.style.removeProperty("pointer-events");
    drawer.style.removeProperty("transform");
    drawer.style.removeProperty("visibility");
  }

  function closeCollectionDrawers() {
    const filterDrawer = document.querySelector("[data-filter-drawer]");
    const sortDrawer = document.querySelector("[data-sort-drawer]");
    filterDrawer?.setAttribute("aria-hidden", "true");
    sortDrawer?.setAttribute("aria-hidden", "true");
    setCollectionDrawerVisibility(filterDrawer, false);
    setCollectionDrawerVisibility(sortDrawer, false);
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
    if (drawer) {
      drawer.setAttribute("aria-hidden", "false");
      setCollectionDrawerVisibility(drawer, true);
    }
    if (toggle) toggle.setAttribute("aria-expanded", "true");
    setCollectionOverlay(true);
  }

  function updatePdpGallery(select) {
    const selected = select.selectedOptions?.[0];
    const target = selected?.dataset.imageSrc;
    if (!target) return;
    const image = document.querySelector(`[data-gallery-image-src="${CSS.escape(target)}"]`);
    hydrateDeferredImage(image);
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
    const detailImage = document.querySelector("[data-product-details-image]");
    const imageSrc = selected.dataset.imageSrc;
    const imageSrcset = selected.dataset.imageSrcset;
    const imageSizes = selected.dataset.imageSizes;
    const fullImageSrc = selected.dataset.fullImageSrc || imageSrc;

    if (triggerTitle) triggerTitle.textContent = title;
    if (priceNode && price) priceNode.textContent = price;
    if (detailImage && imageSrc) {
      if (detailImage.matches("[data-product-details-deferred-image]")) {
        updateDeferredImageSource(detailImage, imageSrc, imageSrcset, imageSizes);
        if (scrollGallery) hydrateDeferredImage(detailImage);
      } else {
        detailImage.src = imageSrc;
        if (imageSrcset) detailImage.srcset = imageSrcset;
        if (imageSizes) detailImage.sizes = imageSizes;
      }
      detailImage.closest("[data-lightbox-open]")?.setAttribute("data-lightbox-src", fullImageSrc);
    }
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

  function shopifyCartPermalink(cart = loadCart()) {
    const lines = cart
      .map(item => {
        const id = Number(item.id);
        const qty = Math.max(0, Math.min(99, Number(item.qty || 0)));
        if (!Number.isFinite(id) || id <= 0 || qty <= 0) return null;
        return `${Math.trunc(id)}:${Math.trunc(qty)}`;
      })
      .filter(Boolean);
    return lines.length ? `${storeBaseUrl}/cart/${lines.join(",")}` : "";
  }

  function checkout(scope = document) {
    const root = scope || document;
    const output = root.querySelector("[data-checkout-output]");
    const url = shopifyCartPermalink();
    if (url) {
      window.location.href = url;
      return;
    }
    if (output) output.textContent = "Your shopping bag is empty.";
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

    const shippingPromoClose = event.target.closest("[data-shipping-promo-close]");
    if (shippingPromoClose) {
      shippingPromoClose.closest("[data-shipping-promo]")?.classList.add("is-hidden");
      persistShippingPromoDismissal();
    }

    if (event.target.closest("[data-filter-toggle]")) openCollectionDrawer("filter");
    if (event.target.closest("[data-sort-toggle]")) openCollectionDrawer("sort");
    if (event.target.closest("[data-filter-close], [data-sort-close]")) closeCollectionDrawers();

    const optionTrigger = event.target.closest("[data-option-trigger]");
    if (optionTrigger) openOptionDrawer(optionTrigger);

    if (event.target.closest("[data-option-close]")) closeOptionDrawers();

    const optionChoice = event.target.closest("[data-option-choice]");
    if (optionChoice) selectPdpOption(optionChoice);

    const quickshopOpen = event.target.closest("[data-quickshop-open]");
    if (quickshopOpen) {
      event.preventDefault();
      event.stopPropagation();
      openQuickshopDrawer(quickshopOpen.dataset.handle);
      return;
    }

    if (event.target.closest("[data-quickshop-close]")) closeQuickshopDrawer();

    const quickshopAdd = event.target.closest("[data-quickshop-add]");
    if (quickshopAdd) {
      const form = quickshopAdd.closest("[data-quickshop-form]");
      const select = form?.querySelector("[data-quickshop-select]");
      addVariant(select?.value || quickshopAdd.dataset.variantId);
      closeQuickshopDrawer();
      openCartDrawer();
      return;
    }

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
      hydrateDeferredImage(image);
      image?.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "start" });
    }

    const lightboxOpen = event.target.closest("[data-lightbox-open]");
    if (lightboxOpen) openLightbox(lightboxOpen);

    if (event.target.closest("[data-lightbox-close]")) closeLightbox();

    const checkoutButton = event.target.closest("[data-checkout]");
    if (checkoutButton) {
      event.preventDefault();
      checkout(checkoutButton.closest("[data-cart-page], [data-cart-drawer]") || document);
    }
  });

  document.addEventListener("change", event => {
    const select = event.target.closest("[data-pdp-variant-select]");
    if (select) updatePdpSelection(select);

    const giftToggle = event.target.closest("[data-gift-toggle]");
    if (giftToggle) toggleGiftMessage(giftToggle);

    const quickshopSelect = event.target.closest("[data-quickshop-select]");
    if (quickshopSelect) {
      const selected = quickshopSelect.selectedOptions?.[0];
      const drawer = quickshopSelect.closest(".js-quickshopDrawer");
      const priceNode = drawer?.querySelector("[data-quickshop-price]");
      const imageNode = drawer?.querySelector("[data-quickshop-image-current]");
      if (priceNode && selected?.dataset.price) priceNode.textContent = selected.dataset.price;
      if (imageNode && selected?.dataset.imageSrc) imageNode.src = selected.dataset.imageSrc;
    }
  });

  document.addEventListener("pointerover", event => {
    hydrateProductTileHoverImage(event.target.closest(".js-productTile"));
  });

  document.addEventListener("mouseover", event => {
    hydrateProductTileHoverImage(event.target.closest(".js-productTile"));
  });

  document.addEventListener("focusin", event => {
    hydrateProductTileHoverImage(event.target.closest(".js-productTile"));
  });

  document.addEventListener("keydown", event => {
    if (event.key === "Escape") {
      closeSearchDrawer();
      closeCollectionDrawers();
      closeOptionDrawers();
      closeLightbox();
      closeQuickshopDrawer();
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
  hideDismissedShippingPromos();
  document.querySelectorAll("[data-pdp-variant-select]").forEach(select => updatePdpSelection(select, false));
  bindDeferredHomeImageHydration();
  bindDeferredProductCardImageHydration();
  bindDeferredCollectionProducts();
  bindDeferredCartPageUpsells();
  bindDeferredProductDetailImageHydration();
  bindDeferredGalleryHydration();
  bindDeferredFooterImageHydration();
  bindDeferredMonoFont();
  renderCartPage();
})();
