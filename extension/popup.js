const DEFAULTS = { base: "http://localhost:3000", tenant: "meridian", enabled: true };
const $ = (id) => document.getElementById(id);

chrome.storage.sync.get(DEFAULTS, (s) => {
  $("base").value = s.base;
  $("tenant").value = s.tenant;
  $("enabled").checked = s.enabled;
});

$("save").addEventListener("click", () => {
  const base = $("base").value.trim().replace(/\/+$/, "") || DEFAULTS.base;
  if (!/^https?:\/\//.test(base)) {
    $("status").textContent = "Enter an address that starts with http:// or https://.";
    return;
  }
  chrome.storage.sync.set({ base, tenant: $("tenant").value.trim() || DEFAULTS.tenant, enabled: $("enabled").checked }, () => {
    $("status").textContent = "Settings saved. Reload open pages to apply them.";
  });
});
