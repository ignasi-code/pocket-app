(function () {
  const source = document.querySelector("[data-source-pane]");
  const frame = document.querySelector("[data-skeleton-frame]");
  const toggle = document.querySelector("[data-sync-toggle]");
  const reset = document.querySelector("[data-reset]");
  let syncing = false;

  function frameDoc() {
    return frame.contentDocument || frame.contentWindow.document;
  }

  function ratio(el) {
    const max = Math.max(1, el.scrollHeight - el.clientHeight);
    return el.scrollTop / max;
  }

  function setSourceRatio(value) {
    const max = Math.max(1, source.scrollHeight - source.clientHeight);
    source.scrollTop = value * max;
  }

  function setFrameRatio(value) {
    const doc = frameDoc().documentElement;
    const max = Math.max(1, doc.scrollHeight - frame.clientHeight);
    frame.contentWindow.scrollTo(0, value * max);
  }

  function withSync(fn) {
    if (!toggle.checked || syncing) return;
    syncing = true;
    fn();
    requestAnimationFrame(() => {
      syncing = false;
    });
  }

  source.addEventListener("scroll", () => {
    withSync(() => setFrameRatio(ratio(source)));
  });

  frame.addEventListener("load", () => {
    frame.contentWindow.addEventListener("scroll", () => {
      withSync(() => {
        const doc = frameDoc().documentElement;
        const max = Math.max(1, doc.scrollHeight - frame.clientHeight);
        setSourceRatio(frame.contentWindow.scrollY / max);
      });
    });
  });

  reset.addEventListener("click", () => {
    source.scrollTop = 0;
    frame.contentWindow.scrollTo(0, 0);
  });
})();
