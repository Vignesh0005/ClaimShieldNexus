// ClaimShield Nexus overlay: a floating button plus two ways to pick an ID on any page.
//   1. Click the button, then click an ID.
//   2. Hold Alt and draw a circle around an ID.
// The summary comes from GET {base}/api/v1/overlay/{id}. Nothing on the host page is changed.
(() => {
  if (window.__csnLoaded) return;
  window.__csnLoaded = true;

  const ID_RE = /\b(?:PRV|CLM|MBR|CS)-[0-9][0-9-]*[0-9]\b/g;
  const RISK = {
    critical: { label: "Critical", color: "#fca5a5", dot: "#dc2626" },
    high: { label: "High", color: "#fdba74", dot: "#ea580c" },
    medium: { label: "Medium", color: "#fcd34d", dot: "#f59e0b" },
    low: { label: "Low", color: "#6ee7b7", dot: "#10b981" },
  };
  const DEFAULTS = { base: "http://localhost:3000", tenant: "meridian", enabled: true };
  let settings = DEFAULTS;
  let picking = false;

  const el = (tag, props = {}, children = []) => {
    const node = Object.assign(document.createElement(tag), props);
    for (const c of [].concat(children)) node.append(c);
    return node;
  };

  const root = el("div", { className: "csn-root" });
  const bubble = el("button", { className: "csn-bubble", type: "button", textContent: "CS", title: "ClaimShield: look up an ID" });
  bubble.setAttribute("aria-label", "ClaimShield: look up an ID on this page");
  bubble.setAttribute("aria-pressed", "false");
  const hint = el("div", { className: "csn-hint", textContent: "Click an ID on the page. Press Escape to cancel.", hidden: true });
  hint.setAttribute("role", "status");
  const panel = el("aside", { className: "csn-panel", hidden: true });
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-label", "ClaimShield summary");
  root.append(bubble, hint, panel);

  function setPicking(on) {
    picking = on;
    bubble.setAttribute("aria-pressed", String(on));
    hint.hidden = !on;
    document.documentElement.classList.toggle("csn-picking", on);
  }

  function closePanel() {
    panel.hidden = true;
    panel.replaceChildren();
    bubble.focus();
  }

  function header() {
    const close = el("button", { className: "csn-close", type: "button", textContent: "×" });
    close.setAttribute("aria-label", "Close summary");
    close.addEventListener("click", closePanel);
    return el("header", {}, [el("span", { textContent: "ClaimShield" }), close]);
  }

  function render(id, state, data) {
    panel.hidden = false;
    const body = [header(), el("p", { className: "csn-id", textContent: id })];
    if (state === "loading") body.push(el("p", { className: "csn-muted", textContent: "Looking up this ID" }));
    if (state === "error") {
      body.push(el("p", { className: "csn-muted", textContent: `Could not reach ClaimShield at ${settings.base}. Check the address in the extension settings and that you are signed in.` }));
    }
    if (state === "ready") {
      const r = RISK[data.level] || RISK.low;
      const risk = el("span", { className: "csn-risk" }, [el("span", { className: "csn-dot" }), `${Math.round(data.risk * 100)}% ${r.label}`]);
      risk.style.color = r.color;
      risk.firstChild.style.background = r.dot;
      body.push(el("p", {}, ["Risk ", risk]));
      if (data.reasons.length) {
        body.push(el("p", { className: "csn-muted", textContent: "Top reasons" }));
        body.push(el("ol", {}, data.reasons.map((x) => el("li", { textContent: `${x.label} (${Math.round(x.score * 100)}%)` }))));
      } else {
        body.push(el("p", { className: "csn-muted", textContent: "No open case references this ID." }));
      }
      if (data.caseId) {
        const link = el("a", { className: "csn-btn", textContent: "View full case", href: `${settings.base}/cases/${encodeURIComponent(data.caseId)}`, target: "_blank", rel: "noopener" });
        body.push(el("div", { className: "csn-actions" }, [link]));
      }
      body.push(el("p", { className: "csn-muted", textContent: "A score is a prompt for review, not a finding. Synthetic demo. Not a fraud determination." }));
    }
    panel.replaceChildren(...body);
    panel.querySelector("button, a")?.focus();
  }

  async function lookup(id) {
    setPicking(false);
    render(id, "loading");
    try {
      const res = await fetch(`${settings.base}/api/v1/overlay/${encodeURIComponent(id)}`, { headers: { "x-tenant-id": settings.tenant } });
      if (!res.ok) throw new Error(String(res.status));
      render(id, "ready", await res.json());
    } catch {
      render(id, "error");
    }
  }

  // Finds every ID on the page together with the screen rectangles its text occupies.
  function idsOnPage() {
    const found = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode: (n) => (root.contains(n) || !n.nodeValue || !/\d/.test(n.nodeValue) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
    });
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      for (const m of node.nodeValue.matchAll(ID_RE)) {
        const range = document.createRange();
        range.setStart(node, m.index);
        range.setEnd(node, m.index + m[0].length);
        for (const rect of range.getClientRects()) found.push({ id: m[0], rect });
      }
    }
    return found;
  }

  function idAtPoint(x, y) {
    const hit = idsOnPage().find(({ rect }) => x >= rect.left - 3 && x <= rect.right + 3 && y >= rect.top - 3 && y <= rect.bottom + 3);
    if (hit) return hit.id;
    const value = document.elementFromPoint(x, y)?.value;
    return typeof value === "string" ? (value.match(ID_RE) || [null])[0] : null;
  }

  bubble.addEventListener("click", () => setPicking(!picking));

  document.addEventListener(
    "click",
    (e) => {
      if (!picking || root.contains(e.target)) return;
      const id = idAtPoint(e.clientX, e.clientY);
      e.preventDefault();
      e.stopPropagation();
      if (id) lookup(id);
      else hint.textContent = "No provider, claim, member or case ID there. Click directly on an ID.";
    },
    true,
  );

  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (picking) setPicking(false);
    else if (!panel.hidden) closePanel();
  });

  // Circle gesture: Alt + drag draws a loop; the first ID whose centre lies inside it is looked up.
  let path = null;
  let svg = null;
  let line = null;

  function inside(points, x, y) {
    let odd = false;
    for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
      const [xi, yi] = points[i];
      const [xj, yj] = points[j];
      if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) odd = !odd;
    }
    return odd;
  }

  document.addEventListener(
    "pointerdown",
    (e) => {
      if (!e.altKey || e.button !== 0 || root.contains(e.target)) return;
      e.preventDefault();
      path = [[e.clientX, e.clientY]];
      svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("class", "csn-lasso");
      line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
      line.setAttribute("fill", "rgba(59,130,246,0.12)");
      line.setAttribute("stroke", "#3b82f6");
      line.setAttribute("stroke-width", "3");
      svg.append(line);
      root.append(svg);
    },
    true,
  );

  document.addEventListener(
    "pointermove",
    (e) => {
      if (!path) return;
      path.push([e.clientX, e.clientY]);
      line.setAttribute("points", path.map((p) => p.join(",")).join(" "));
    },
    true,
  );

  document.addEventListener(
    "pointerup",
    () => {
      if (!path) return;
      const points = path;
      path = null;
      svg.remove();
      if (points.length < 8) return;
      const hit = idsOnPage().find(({ rect }) => inside(points, rect.left + rect.width / 2, rect.top + rect.height / 2));
      if (hit) lookup(hit.id);
    },
    true,
  );

  const start = (s) => {
    settings = { ...DEFAULTS, ...s };
    if (settings.enabled) document.documentElement.append(root);
  };
  if (typeof chrome !== "undefined" && chrome.storage?.sync) chrome.storage.sync.get(DEFAULTS, start);
  else start(DEFAULTS);
})();
