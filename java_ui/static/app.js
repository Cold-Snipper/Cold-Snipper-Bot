const logList = document.getElementById("log-list");
const uptimeEl = document.getElementById("uptime");
const lastActionEl = document.getElementById("last-action");
const actionCountEl = document.getElementById("action-count");
const logCountEl = document.getElementById("log-count");
const dbCountEl = document.getElementById("db-count");
const commCountEl = document.getElementById("comm-count");
const clientCountEl = document.getElementById("client-count");
const scanStateEl = document.getElementById("scan-state");
const lastScanEl = document.getElementById("last-scan");
const leadsBody = document.getElementById("leads-body");
const commsBody = document.getElementById("comms-body");
const fbQueueBody = document.getElementById("fb-queue-body");
const actionResponse = document.getElementById("action-response");
const countrySelect = document.getElementById("country");
const targetSiteSelect = document.getElementById("target-site");
const fbQueueCountEl = document.getElementById("fb-queue-count");
let selectedScanMode = "website";
const websiteScanSetup = document.getElementById("website-scan-setup");
const facebookScanSetup = document.getElementById("facebook-scan-setup");
const clientsBody = document.getElementById("clients-body");
const clientPanelTitle = document.getElementById("client-panel-title");
const detailName = document.getElementById("detail-name");
const detailEmail = document.getElementById("detail-email");
const detailPhone = document.getElementById("detail-phone");
const detailStatus = document.getElementById("detail-status");
const detailStage = document.getElementById("detail-stage");
const detailLastContacted = document.getElementById("detail-last-contacted");
const detailSource = document.getElementById("detail-source");
const detailChannel = document.getElementById("detail-channel");
const detailViability = document.getElementById("detail-viability");
const detailNotes = document.getElementById("detail-notes");
const crmTotalEl = document.getElementById("crm-total");
const crmViableEl = document.getElementById("crm-viable");
const crmContactedEl = document.getElementById("crm-contacted");
const crmConvertedEl = document.getElementById("crm-converted");
const crmAutoEl = document.getElementById("crm-auto");
const crmGlobalAuto = document.getElementById("crm-global-auto");
const crmStageFilter = document.getElementById("crm-stage-filter");
const crmSourceFilter = document.getElementById("crm-source-filter");
const crmChannelFilter = document.getElementById("crm-channel-filter");
const crmScoreFilter = document.getElementById("crm-score-filter");
const crmAutoFilter = document.getElementById("crm-auto-filter");
const crmTabButtons = document.querySelectorAll(".tab-btn[data-crm-tab]");
const stageConfigStatusEl = document.getElementById("stage-config-status");
const stageScanningStatusEl = document.getElementById("stage-scanning-status");
const stageAnalysisStatusEl = document.getElementById("stage-analysis-status");
const stageContactingStatusEl = document.getElementById("stage-contacting-status");
const stageLoggingStatusEl = document.getElementById("stage-logging-status");
const stageCrmStatusEl = document.getElementById("stage-crm-status");

let lastIndex = 0;
let polling = true;
let lastQuery = "";
let lastCommQuery = "";
let lastClientQuery = "";
let lastScanState = "";
let selectedClientId = "";
let selectedClientEmail = "";
let targetsData = null;
let allClients = [];
let activeCrmTab = "all";

function formatUptime(seconds) {
  const mins = Math.floor(seconds / 60);
  const hrs = Math.floor(mins / 60);
  const remMins = mins % 60;
  const remSecs = seconds % 60;
  if (hrs > 0) {
    return `${hrs}h ${remMins}m ${remSecs}s`;
  }
  if (mins > 0) {
    return `${mins}m ${remSecs}s`;
  }
  return `${seconds}s`;
}

async function fetchStatus() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();
    uptimeEl.textContent = formatUptime(data.uptimeSeconds);
    lastActionEl.textContent = data.lastAction || "-";
    actionCountEl.textContent = data.actionCount ?? "-";
    logCountEl.textContent = data.logCount ?? "-";
    dbCountEl.textContent = data.dbCount ?? "-";
    commCountEl.textContent = data.commCount ?? "-";
    if (clientCountEl) {
      clientCountEl.textContent = data.clientCount ?? "-";
    }
    if (clientCountEl) {
      clientCountEl.textContent = data.clientCount ?? "-";
    }
    scanStateEl.textContent = data.scanState ?? "-";
    lastScanEl.textContent = data.lastScanAt ?? "-";
    fbQueueCountEl.textContent = data.fbQueueCount ?? "-";
    // Update high-level stage status pills
    if (stageConfigStatusEl) {
      stageConfigStatusEl.textContent = data.dbCount >= 0 ? "Ready" : "Unknown";
    }
    if (stageScanningStatusEl) {
      stageScanningStatusEl.textContent = data.scanState || "Unknown";
    }
    if (stageAnalysisStatusEl) {
      // Use dbCount as a proxy that analysis + LLM pipeline is writing leads.
      stageAnalysisStatusEl.textContent = (data.dbCount ?? 0) > 0 ? "Active" : "Idle";
    }
    if (stageContactingStatusEl) {
      // Use commCount as a proxy for outreach/logged comms.
      stageContactingStatusEl.textContent = (data.commCount ?? 0) > 0 ? "Active" : "Idle";
    }
    if (stageLoggingStatusEl) {
      stageLoggingStatusEl.textContent = (data.logCount ?? 0) > 0 ? "Writing Logs" : "Idle";
    }
    if (stageCrmStatusEl) {
      stageCrmStatusEl.textContent = (data.clientCount ?? 0) > 0 ? "Populated" : "Empty";
    }
    // Update pipeline panel status displays
    const stageConfigDisplay = document.getElementById("stage-config-status-display");
    const stageScanningDisplay = document.getElementById("stage-scanning-status-display");
    const stageAnalysisDisplay = document.getElementById("stage-analysis-status-display");
    const stageContactingDisplay = document.getElementById("stage-contacting-status-display");
    const stageLoggingDisplay = document.getElementById("stage-logging-status-display");
    const stageCrmDisplay = document.getElementById("stage-crm-status-display");
    const stage2LastScan = document.getElementById("stage2-last-scan");
    if (stageConfigDisplay) stageConfigDisplay.textContent = data.dbCount >= 0 ? "Ready" : "Unknown";
    if (stageScanningDisplay) stageScanningDisplay.textContent = data.scanState || "Idle";
    if (stageAnalysisDisplay) stageAnalysisDisplay.textContent = (data.dbCount ?? 0) > 0 ? "Active" : "Idle";
    if (stageContactingDisplay) stageContactingDisplay.textContent = (data.commCount ?? 0) > 0 ? "Active" : "Idle";
    if (stageLoggingDisplay) stageLoggingDisplay.textContent = (data.logCount ?? 0) > 0 ? "Writing" : "Idle";
    if (stageCrmDisplay) stageCrmDisplay.textContent = (data.clientCount ?? 0) > 0 ? "Populated" : "Empty";
    if (stage2LastScan) stage2LastScan.textContent = data.lastScanAt || "Never";
    // Real-time: refresh leads/FB when scan is running (every status poll) or when scan just finished
    const scanState = (data.scanState || "").toLowerCase();
    if (scanState === "running") {
      refreshLeads(lastQuery);
      refreshFbQueue();
    } else if (lastScanState === "running" && scanState === "idle") {
      refreshLeads(lastQuery);
      refreshFbQueue();
    }
    lastScanState = scanState;
  } catch (err) {
    console.warn("Status fetch failed", err);
  }
}

async function fetchLogs() {
  if (!polling) return;
  try {
    const res = await fetch(`/api/logs?since=${lastIndex}`);
    const data = await res.json();
    if (Array.isArray(data.logs) && data.logs.length > 0) {
      appendLogs(data.logs);
      lastIndex = data.to ?? lastIndex;
    }
  } catch (err) {
    console.warn("Log fetch failed", err);
  }
}

function appendLogs(logs) {
  for (const line of logs) {
    const div = document.createElement("div");
    div.className = "log-line";
    div.textContent = line;
    logList.appendChild(div);
    // Also add to pipeline log if it exists
    const pipelineLogList = document.getElementById("pipeline-log-list");
    if (pipelineLogList) {
      const pipelineDiv = document.createElement("div");
      pipelineDiv.className = "log-line";
      pipelineDiv.textContent = line;
      pipelineLogList.appendChild(pipelineDiv);
      pipelineLogList.scrollTop = pipelineLogList.scrollHeight;
    }
  }
  logList.scrollTop = logList.scrollHeight;
}

function addCrmLog(message) {
  const crmLogList = document.getElementById("crm-log-list");
  if (crmLogList) {
    const div = document.createElement("div");
    div.className = "log-line";
    div.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
    crmLogList.appendChild(div);
    crmLogList.scrollTop = crmLogList.scrollHeight;
  }
}

function readValue(id) {
  const el = document.getElementById(id);
  return el ? el.value.trim() : "";
}

function readChecked(id) {
  const el = document.getElementById(id);
  return el ? el.checked : false;
}

function compactPayload(payload) {
  const output = {};
  for (const [key, value] of Object.entries(payload)) {
    if (value === undefined || value === null) continue;
    if (typeof value === "string" && value.trim() === "") continue;
    if (typeof value === "boolean" && value === false) continue;
    output[key] = value;
  }
  return output;
}

function escapeHtml(str) {
  if (str == null || str === "") return "";
  const s = String(str);
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function truncate(value, maxLength = 60) {
  if (!value) return "";
  const s = String(value);
  if (s.length <= maxLength) return s;
  return `${s.slice(0, maxLength)}...`;
}

function populateSelect(selectId, options, placeholder) {
  const select = document.getElementById(selectId);
  if (!select) return;
  select.innerHTML = "";
  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = placeholder;
  select.appendChild(empty);
  for (const option of options) {
    const opt = document.createElement("option");
    opt.value = option.value;
    opt.textContent = option.label;
    select.appendChild(opt);
  }
}

function getCurrentWebsiteSite() {
  if (!targetsData) return null;
  const country = readValue("country");
  const siteId = readValue("target-site");
  if (!country || !siteId) return null;
  const sites = targetsData.sitesByCountry?.[country] || [];
  return sites.find((s) => s.id === siteId) || null;
}

function updateSitesForCountry(countryName) {
  if (!targetsData) return;
  const sites = targetsData.sitesByCountry?.[countryName] || [];
  const siteOptions = sites.map((site) => ({
    value: site.id,
    label: site.label,
  }));
  populateSelect("target-site", siteOptions, "Select target site");
  const targetSiteEl = document.getElementById("target-site");
  if (targetSiteEl) targetSiteEl.value = "";
  updateListingTypesForSite();
  buildWebsiteStartUrl();
}

function updateListingTypesForSite() {
  const site = getCurrentWebsiteSite();
  const types = site?.listingTypes || targetsData?.defaultListingTypes || [];
  const options = types.map((t) => ({ value: t.path, label: t.label }));
  populateSelect("listing-type", options, "—");
  buildWebsiteStartUrl();
}

function buildWebsiteStartUrl() {
  const site = getCurrentWebsiteSite();
  const path = readValue("listing-type");
  const ta = document.getElementById("start-urls");
  if (!ta) return;
  if (!site?.baseUrl) {
    ta.placeholder = "Select country, site and listing type to build URLs";
    return;
  }
  const base = site.baseUrl.replace(/\/$/, "");
  const url = path ? base + path : base;
  ta.value = url;
  ta.placeholder = "";
}

async function loadTargets() {
  try {
    const res = await fetch("/targets_eu.json");
    targetsData = await res.json();
    const countries = (targetsData.countries || []).map((name) => ({
      value: name,
      label: name,
    }));
    populateSelect("country", countries, "Select EU country");
    updateSitesForCountry("");
  } catch (err) {
    console.warn("Failed to load targets list", err);
    populateSelect("country", [], "Select EU country");
    populateSelect("target-site", [], "Select target site");
    populateSelect("listing-type", [], "—");
  }
}

function selectedLeadIds() {
  return Array.from(document.querySelectorAll("input.lead-select:checked")).map(
    (input) => input.value
  );
}

function selectedClientIds() {
  return Array.from(document.querySelectorAll("input.client-select:checked")).map(
    (input) => input.value
  );
}

function buildPayload(name) {
  switch (name) {
    case "start_scan":
      return {
        scan_mode: currentScanMode(),
        start_urls: readValue("start-urls"),
        criteria: readValue("criteria"),
        city: readValue("city"),
        country: readValue("country"),
        target_site: readValue("target-site"),
        max_price: readValue("max-price"),
        listing_selector: readValue("listing-selector"),
        site_headless: readChecked("site-headless"),
      };
    case "test_single_page":
      return {
        scan_mode: currentScanMode(),
        single_url: readValue("single-url"),
        criteria: readValue("criteria"),
        city: readValue("city"),
        country: readValue("country"),
        target_site: readValue("target-site"),
        max_price: readValue("max-price"),
        listing_selector: readValue("listing-selector"),
        site_headless: readChecked("site-headless"),
      };
    case "fb_analyze": {
      const sourceType = readValue("fb-source-type");
      let fbSearchUrl = readValue("fb-search-url");
      if (sourceType === "marketplace") {
        const city = (readValue("fb-city") || "miami").trim().toLowerCase().replace(/\s+/g, "");
        const radius = readValue("fb-radius") || "25";
        fbSearchUrl = "https://www.facebook.com/marketplace/" + city + "/propertyforsale";
        const kw = readValue("fb-keywords");
        const params = [];
        if (kw) params.push("query=" + encodeURIComponent(kw));
        if (radius) params.push("radius=" + radius);
        if (params.length) fbSearchUrl += "?" + params.join("&");
      }
      return compactPayload({
        fb_search_url: fbSearchUrl,
        fb_source_type: sourceType,
        fb_group_urls: sourceType === "groups" ? readValue("fb-group-urls") : "",
        fb_logged_in: readValue("fb-logged-in"),
        fb_category: readValue("fb-category"),
        fb_city: readValue("fb-city"),
        fb_radius: readValue("fb-radius"),
        fb_property_type: readValue("fb-property-type"),
        fb_min_price: readValue("fb-min-price"),
        fb_max_price: readValue("fb-max-price"),
        fb_bedrooms: readValue("fb-bedrooms"),
        fb_bathrooms: readValue("fb-bathrooms"),
        fb_size_min: readValue("fb-size-min"),
        fb_size_max: readValue("fb-size-max"),
        fb_posted_within: readValue("fb-posted-within"),
        fb_language: readValue("fb-language"),
        fb_keywords: readValue("fb-keywords"),
        fb_fsbo_only: readChecked("fb-fsbo-only"),
      });
    }
    case "fb_mark_contacted":
      return {
        ids: selectedFbIds().join(","),
      };
    case "fb_send_messages":
      return compactPayload({
        fb_search_url: readValue("fb-search-url"),
        fb_message: readValue("fb-message"),
        fb_send_limit: readValue("fb-send-limit"),
        fb_headless: readChecked("fb-headless"),
      });
    case "site_send_messages":
      return compactPayload({
        site_message: readValue("site-message"),
        site_send_limit: readValue("site-send-limit"),
        site_headless: readChecked("site-headless"),
      });
    case "search_db":
      return {
        search_query: readValue("search-query"),
      };
    case "mark_contacted":
    case "delete_selected":
      return {
        ids: selectedLeadIds().join(","),
      };
    case "load_config":
    case "save_config":
      return { config_path: readValue("config-path") };
    case "test_llm_prompt":
      return { prompt_text: readValue("prompt-text") };
    case "add_comm":
      return {
        contact_name: readValue("comm-name"),
        contact_email: readValue("comm-email"),
        contact_phone: readValue("comm-phone"),
        channel: readValue("comm-channel"),
        status: readValue("comm-status"),
        notes: readValue("comm-notes"),
        last_message: readValue("comm-message"),
        client_id: selectedClientId,
      };
    case "update_comm_status":
      return {
        ids: selectedCommIds().join(","),
        status: readValue("comm-status"),
      };
    case "delete_comm":
      return {
        ids: selectedCommIds().join(","),
      };
    case "search_comms":
      return {
        comm_query: readValue("comm-search"),
      };
    case "add_client":
      return compactPayload({
        client_name: readValue("client-name"),
        client_email: readValue("client-email"),
        client_phone: readValue("client-phone"),
        client_status: readValue("client-status"),
        client_stage: readValue("client-stage"),
        client_source: readValue("client-source"),
        client_source_type: readValue("client-source-type"),
        client_outreach_channel: readValue("client-outreach-channel"),
        client_automation_enabled: readChecked("client-automation-enabled"),
        client_viability_score: readValue("client-viability-score"),
        client_notes: readValue("client-notes"),
      });
    case "update_client":
      return compactPayload({
        client_id: selectedClientId,
        status: readValue("client-status"),
        stage: readValue("client-stage"),
        notes: readValue("client-notes"),
        source_type: readValue("client-source-type"),
        outreach_channel: readValue("client-outreach-channel"),
        automation_enabled: readChecked("client-automation-enabled"),
        viability_score: readValue("client-viability-score"),
      });
    case "delete_client":
      return {
        ids: selectedClientIds().join(","),
      };
    case "search_clients":
      return {
        client_query: readValue("client-search"),
      };
    default:
      return {};
  }
}

function currentScanMode() {
  return selectedScanMode;
}

function setScanMode(mode) {
  if (mode === "website" || mode === "facebook") {
    selectedScanMode = mode;
  }
}

function updateScanModeUI() {
  const mode = currentScanMode();
  if (websiteScanSetup) {
    websiteScanSetup.classList.toggle("active", mode === "website");
    websiteScanSetup.classList.toggle("inactive", mode !== "website");
  }
  if (facebookScanSetup) {
    facebookScanSetup.classList.toggle("active", mode === "facebook");
    facebookScanSetup.classList.toggle("inactive", mode !== "facebook");
  }
}

async function sendAction(name) {
  if (name === "reset_all_scanned_data" && !confirm("Clear all leads and FB queue? This cannot be undone.")) {
    return;
  }
  if (name === "export_excel") {
    window.location.href = "/api/export/leads.xls";
    showResponse("Download started (leads_export.xls)");
    return;
  }
  const payload = buildPayload(name);
  const params = new URLSearchParams(payload);
  try {
    const res = await fetch(`/api/action?name=${encodeURIComponent(name)}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: params.toString(),
    });
    const data = await res.json();
    showResponse(data.message || "Action sent");
    if (name === "clear_logs") {
      logList.innerHTML = "";
      lastIndex = 0;
    }
    if (name === "refresh_leads" || name === "preview_results" || name === "view_all_leads") {
      refreshLeads(lastQuery);
    }
    if (name === "search_db") {
      const q = readValue("search-query");
      lastQuery = q;
      refreshLeads(q);
    }
    if (name === "mark_contacted" || name === "delete_selected") {
      refreshLeads(lastQuery);
    }
    if (name === "fb_analyze") {
      refreshFbQueue();
    }
    if (name === "fb_mark_contacted" || name === "fb_clear_queue") {
      refreshFbQueue();
    }
    if (name === "reset_all_scanned_data") {
      refreshLeads(lastQuery);
      refreshFbQueue();
    }
    if (name === "add_comm") {
      refreshComms(lastCommQuery);
      addCrmLog("Communication logged");
    }
    if (name === "add_client" || name === "update_client") {
      refreshClients(lastClientQuery);
      addCrmLog(name === "add_client" ? "Client added" : "Client updated");
    }
    if (name === "search_comms") {
      const q = readValue("comm-search");
      lastCommQuery = q;
      refreshComms(q);
    }
    if (name === "update_comm_status" || name === "delete_comm" || name === "refresh_comms") {
      refreshComms(lastCommQuery);
    }
    if (name === "add_client" || name === "update_client" || name === "delete_client" || name === "refresh_clients") {
      refreshClients(lastClientQuery);
    }
    if (name === "search_clients") {
      const q = readValue("client-search");
      lastClientQuery = q;
      renderCrm();
    }
  } catch (err) {
    console.warn("Action failed", err);
  }
}

function showResponse(message) {
  if (!actionResponse) return;
  actionResponse.textContent = message;
  actionResponse.classList.add("visible");
  setTimeout(() => actionResponse.classList.remove("visible"), 2500);
}

function getListingTypeFilter() {
  const el = document.getElementById("listing-type-filter");
  return el ? (el.value || "") : "";
}

async function refreshLeads(query, listingTypeFilter) {
  try {
    await fetch(window.location.origin + "/api/reload");
  } catch (e) {
    /* ignore */
  }
  const filter = listingTypeFilter !== undefined ? listingTypeFilter : getListingTypeFilter();
  const url = new URL("/api/leads", window.location.origin);
  url.searchParams.set("limit", "200");
  if (query) {
    url.searchParams.set("q", query);
  }
  if (filter) {
    url.searchParams.set("listing_type", filter);
  }
  const roomsMinEl = document.getElementById("rooms-min");
  if (roomsMinEl && roomsMinEl.value.trim() !== "") {
    const r = parseInt(roomsMinEl.value.trim(), 10);
    if (!isNaN(r) && r >= 0) {
      url.searchParams.set("rooms_min", String(r));
    }
  }
  try {
    const res = await fetch(url.toString());
    const data = await res.json();
    renderLeads(data.leads || []);
  } catch (err) {
    console.warn("Leads fetch failed", err);
  }
}

function renderLeads(leads) {
  leadsBody.innerHTML = "";
  for (const lead of leads) {
    const row = document.createElement("tr");
    const type = (lead.listingType || "").toLowerCase();
    const typeLabel = type === "rent" ? "Rent" : type === "buy" ? "Buy" : (lead.listingType || "—");
    const safeUrl = lead.url && (lead.url.startsWith("http://") || lead.url.startsWith("https://")) ? lead.url : "#";
    const privateLabel = (lead.isPrivate || "").toString().toLowerCase() === "true" ? "Yes" : (lead.isPrivate ? lead.isPrivate : "—");
    row.innerHTML = `
      <td><input class="lead-select" type="checkbox" value="${escapeHtml(lead.id)}" /></td>
      <td>${escapeHtml(lead.id)}</td>
      <td><a href="${escapeHtml(safeUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(truncate(lead.title, 40))}</a></td>
      <td>${escapeHtml(typeLabel)}</td>
      <td>${escapeHtml(lead.price || "—")}</td>
      <td>${escapeHtml(lead.bedrooms || "—")}</td>
      <td>${escapeHtml(lead.bathrooms || "—")}</td>
      <td>${escapeHtml(lead.size || "—")}</td>
      <td>${escapeHtml(lead.location || "—")}</td>
      <td>${escapeHtml(lead.source || "—")}</td>
      <td>${escapeHtml(privateLabel)}</td>
      <td>${escapeHtml(lead.agencyName || "—")}</td>
      <td>${escapeHtml(lead.status)}</td>
      <td>${escapeHtml(lead.contactEmail || "—")}</td>
      <td>${escapeHtml(lead.contactPhone || "—")}</td>
      <td>${escapeHtml(lead.scanTime)}</td>
    `;
    leadsBody.appendChild(row);
  }
}

function selectedCommIds() {
  return Array.from(document.querySelectorAll("input.comm-select:checked")).map(
    (input) => input.value
  );
}

function selectedFbIds() {
  return Array.from(document.querySelectorAll("input.fb-select:checked")).map(
    (input) => input.value
  );
}

async function refreshFbQueue() {
  try {
    await fetch(window.location.origin + "/api/reload");
  } catch (e) {
    /* ignore */
  }
  const url = new URL("/api/fbqueue", window.location.origin);
  url.searchParams.set("limit", "200");
  try {
    const res = await fetch(url.toString());
    const data = await res.json();
    renderFbQueue(data.items || []);
  } catch (err) {
    console.warn("FB queue fetch failed", err);
  }
}

function renderFbQueue(items) {
  fbQueueBody.innerHTML = "";
  for (const item of items) {
    const row = document.createElement("tr");
    const fbUrl = item.url && (item.url.startsWith("http://") || item.url.startsWith("https://")) ? item.url : "#";
    row.innerHTML = `
      <td><input class="fb-select" type="checkbox" value="${escapeHtml(item.id)}" /></td>
      <td>${escapeHtml(item.id)}</td>
      <td><a href="${escapeHtml(fbUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(truncate(item.url, 60))}</a></td>
      <td>${escapeHtml(item.status)}</td>
      <td>${escapeHtml(item.savedAt)}</td>
    `;
    fbQueueBody.appendChild(row);
  }
}

async function refreshComms(query) {
  const url = new URL("/api/comms", window.location.origin);
  url.searchParams.set("limit", "200");
  if (query) {
    url.searchParams.set("q", query);
  }
  if (selectedClientId) {
    url.searchParams.set("client_id", selectedClientId);
  }
  try {
    const res = await fetch(url.toString());
    const data = await res.json();
    renderComms(data.communications || []);
  } catch (err) {
    console.warn("Comms fetch failed", err);
  }
}

function renderComms(comms) {
  if (!commsBody) return;
  commsBody.innerHTML = "";
  for (const comm of comms) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><input class="comm-select" type="checkbox" value="${comm.id}" /></td>
      <td>${comm.id}</td>
      <td>${comm.channel || ""}</td>
      <td>${comm.status || ""}</td>
      <td>${comm.lastContactedAt || ""}</td>
      <td>${comm.lastMessage || ""}</td>
      <td>${comm.notes || ""}</td>
    `;
    commsBody.appendChild(row);
  }
}

async function refreshClients(query) {
  const url = new URL("/api/clients", window.location.origin);
  url.searchParams.set("limit", "200");
  if (query) {
    url.searchParams.set("q", query);
  }
  const stage = crmStageFilter ? crmStageFilter.value : "";
  const source = crmSourceFilter ? crmSourceFilter.value : "";
  const channel = crmChannelFilter ? crmChannelFilter.value : "";
  const minScore = crmScoreFilter ? crmScoreFilter.value : "";
  const autoFilter = crmAutoFilter ? crmAutoFilter.value : "";
  if (stage) url.searchParams.set("stage", stage);
  if (source) url.searchParams.set("source_type", source);
  if (channel) url.searchParams.set("channel", channel);
  if (minScore) url.searchParams.set("min_score", minScore);
  if (autoFilter) url.searchParams.set("automation", autoFilter);
  try {
    const res = await fetch(url.toString());
    const data = await res.json();
    allClients = data.clients || [];
    renderCrm();
  } catch (err) {
    console.warn("Clients fetch failed", err);
  }
}

function renderCrm() {
  // Server-side filtering is done, only filter by activeCrmTab (UI state)
  const filtered = allClients.filter((client) => {
    if (activeCrmTab !== "all") {
      if ((client.sourceType || "").toLowerCase() !== activeCrmTab) return false;
    }
    return true;
  });
  renderClients(filtered);
  renderSummary(allClients);
}

function renderSummary(clients) {
  const total = clients.length;
  const viable = clients.filter((c) => parseFloat(c.viabilityScore || "0") >= 7).length;
  const contacted = clients.filter((c) => ["contacted", "proposal_sent", "negotiation", "won"].includes((c.stage || "").toLowerCase())).length;
  const converted = clients.filter((c) => (c.stage || "").toLowerCase() === "won").length;
  const autoEnabled = clients.filter((c) => c.automationEnabled).length;
  if (crmTotalEl) crmTotalEl.textContent = total;
  if (crmViableEl) crmViableEl.textContent = viable;
  if (crmContactedEl) crmContactedEl.textContent = contacted;
  if (crmConvertedEl) crmConvertedEl.textContent = total ? `${Math.round((converted / total) * 100)}%` : "0%";
  if (crmAutoEl) crmAutoEl.textContent = autoEnabled;
}

function renderClients(clients) {
  clientsBody.innerHTML = "";
  for (const client of clients) {
    const row = document.createElement("tr");
    const details = truncate(client.notes || client.source || "", 50);
    const viability = client.viabilityScore ? `${client.viabilityScore}/10` : "-";
    const contact = client.email || client.phone || "-";
    const sourceLabel = client.sourceType || client.source || "-";
    const automationChecked = client.automationEnabled ? "checked" : "";
    row.innerHTML = `
      <td><input class="client-select" type="checkbox" value="${client.id}" /></td>
      <td>${client.id} - ${client.name || "Unnamed"}</td>
      <td>${sourceLabel}</td>
      <td>${details}</td>
      <td>${viability}</td>
      <td>${contact}</td>
      <td>${client.stage || "-"}</td>
      <td><input class="automation-toggle" type="checkbox" data-client-id="${client.id}" ${automationChecked} /></td>
      <td><button class="link-button" data-client-id="${client.id}">View</button></td>
    `;
    clientsBody.appendChild(row);
  }
  clientsBody.querySelectorAll("button[data-client-id]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.dataset.clientId;
      const client = clients.find((c) => String(c.id) === String(id));
      if (client) {
        selectClient(client);
      }
    });
  });
  clientsBody.querySelectorAll("input.automation-toggle").forEach((toggle) => {
    toggle.addEventListener("change", () => {
      const id = toggle.dataset.clientId;
      const payload = new URLSearchParams({
        client_id: id,
        automation_enabled: toggle.checked ? "true" : "false",
      });
      fetch(`/api/action?name=update_client`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: payload.toString(),
      }).then(() => refreshClients(lastClientQuery));
    });
  });
}

function selectClient(client) {
  selectedClientId = String(client.id);
  selectedClientEmail = client.email || "";
  if (clientPanelTitle) {
    clientPanelTitle.textContent = `Client #${client.id}`;
  }
  if (detailName) detailName.textContent = client.name || "-";
  if (detailEmail) detailEmail.textContent = client.email || "-";
  if (detailPhone) detailPhone.textContent = client.phone || "-";
  if (detailStatus) detailStatus.textContent = client.status || "-";
  if (detailStage) detailStage.textContent = client.stage || "-";
  if (detailLastContacted) detailLastContacted.textContent = client.lastInteraction || client.lastContactedAt || "-";
  if (detailSource) detailSource.textContent = client.sourceType || client.source || "-";
  if (detailChannel) detailChannel.textContent = client.outreachChannel || "-";
  if (detailViability) detailViability.textContent = client.viabilityScore ? `${client.viabilityScore}/10` : "-";
  if (detailNotes) detailNotes.textContent = client.notes || "-";
  const commName = document.getElementById("comm-name");
  const commEmail = document.getElementById("comm-email");
  const commPhone = document.getElementById("comm-phone");
  if (commName) commName.value = client.name || "";
  if (commEmail) commEmail.value = client.email || "";
  if (commPhone) commPhone.value = client.phone || "";
  const clientName = document.getElementById("client-name");
  const clientEmail = document.getElementById("client-email");
  const clientPhone = document.getElementById("client-phone");
  const clientStatus = document.getElementById("client-status");
  const clientStage = document.getElementById("client-stage");
  const clientSource = document.getElementById("client-source");
  const clientSourceType = document.getElementById("client-source-type");
  const clientOutreach = document.getElementById("client-outreach-channel");
  const clientViability = document.getElementById("client-viability-score");
  const clientAutomation = document.getElementById("client-automation-enabled");
  const clientNotes = document.getElementById("client-notes");
  if (clientName) clientName.value = client.name || "";
  if (clientEmail) clientEmail.value = client.email || "";
  if (clientPhone) clientPhone.value = client.phone || "";
  if (clientStatus) clientStatus.value = client.status || "active";
  if (clientStage) clientStage.value = client.stage || "new";
  if (clientSource) clientSource.value = client.source || "";
  if (clientSourceType) clientSourceType.value = client.sourceType || "";
  if (clientOutreach) clientOutreach.value = client.outreachChannel || "";
  if (clientViability) clientViability.value = client.viabilityScore || "";
  if (clientAutomation) clientAutomation.checked = Boolean(client.automationEnabled);
  if (clientNotes) clientNotes.value = client.notes || "";
  refreshComms(lastCommQuery);
}

document.querySelectorAll("button[data-action]").forEach((button) => {
  button.addEventListener("click", () => {
    const action = button.dataset.action;
    if (action === "refresh_leads") {
      refreshLeads(lastQuery);
      return;
    }
    if (action === "refresh_comms") {
      refreshComms(lastCommQuery);
      return;
    }
    if (action === "search_comms") {
      const q = readValue("comm-search");
      lastCommQuery = q;
      refreshComms(q);
      return;
    }
    if (action === "search_clients") {
      const q = readValue("client-search");
      lastClientQuery = q;
      refreshClients(q);
      return;
    }
    if (action === "refresh_clients") {
      refreshClients(lastClientQuery);
      addCrmLog("Refresh done");
      return;
    }
    if (action === "export_clients_excel") {
      window.location.href = "/api/export/clients.xls";
      addCrmLog("Export clients to Excel");
      return;
    }
    if (action === "go_to_website_bot") {
      const tab = document.querySelector('.tab[data-tab="scanner"]');
      if (tab) {
        tab.click();
        window.scrollTo(0, 0);
      }
      return;
    }
    if (action === "go_to_client_comms") {
      const tab = document.querySelector('.tab[data-tab="client-communications"]');
      if (tab) {
        tab.click();
        window.scrollTo(0, 0);
      }
      return;
    }
    sendAction(action);
  });
});

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((btn) => btn.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach((panel) => panel.classList.remove("active"));
    tab.classList.add("active");
    const target = document.getElementById(`tab-${tab.dataset.tab}`);
    if (target) {
      target.classList.add("active");
    }
    if (tab.dataset.tab === "stages") {
      fetchStage1Config();
    }
  });
});

async function fetchStage1Config() {
  try {
    const res = await fetch("/api/stage1_config");
    const data = await res.json();
    const el = document.getElementById("stage1-current");
    if (el) {
      const st = data.source_type || "—";
      const ah = data.agents_handling || "—";
      el.textContent = "source_type = " + st + ", agents_handling = " + ah;
    }
    const pill = document.getElementById("stage-config-status");
    if (pill) pill.textContent = data.source_type ? "Ready" : "Pending";
  } catch (err) {
    const el = document.getElementById("stage1-current");
    if (el) el.textContent = "— (error)";
  }
}

document.querySelectorAll(".stage1-btn").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const sourceType = btn.dataset.stage1;
    const msgEl = document.getElementById("stage1-result-msg");
    try {
      const res = await fetch("/api/action?name=stage1_apply", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: "source_type=" + encodeURIComponent(sourceType),
      });
      const data = await res.json();
      if (msgEl) {
        msgEl.textContent = data.ok ? "Applied: " + sourceType : (data.message || "Failed");
      }
      fetchStage1Config();
    } catch (err) {
      if (msgEl) msgEl.textContent = "Error";
    }
  });
});

if (countrySelect) {
  countrySelect.addEventListener("change", () => {
    updateSitesForCountry(countrySelect.value);
  });
}

if (targetSiteSelect) {
  targetSiteSelect.addEventListener("change", () => {
    updateListingTypesForSite();
    buildWebsiteStartUrl();
  });
}

const listingTypeSelectEl = document.getElementById("listing-type");
if (listingTypeSelectEl) {
  listingTypeSelectEl.addEventListener("change", buildWebsiteStartUrl);
}

crmTabButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    crmTabButtons.forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    activeCrmTab = btn.dataset.crmTab || "all";
    renderCrm();
  });
});

const filterElements = [crmStageFilter, crmSourceFilter, crmChannelFilter, crmScoreFilter, crmAutoFilter];
filterElements.forEach((el) => {
  if (el) {
    el.addEventListener("change", () => refreshClients(lastClientQuery));
  }
});

[websiteScanSetup, facebookScanSetup].forEach((panel) => {
  if (!panel) return;
  panel.addEventListener("click", (e) => {
    if (e.target.closest("button, input, select, textarea, a, [data-action]")) return;
    const mode = panel.getAttribute("data-scan-mode");
    if (mode) {
      setScanMode(mode);
      updateScanModeUI();
    }
  });
  panel.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      const mode = panel.getAttribute("data-scan-mode");
      if (mode) {
        setScanMode(mode);
        updateScanModeUI();
      }
    }
  });
});

function updateFbSourceUI() {
  const sourceType = document.getElementById("fb-source-type").value;
  document.querySelectorAll(".fb-marketplace-only").forEach((el) => {
    el.style.display = sourceType === "marketplace" ? "" : "none";
  });
  document.querySelectorAll(".fb-groups-only").forEach((el) => {
    el.style.display = sourceType === "groups" ? "" : "none";
  });
}

function buildFbSearchUrl() {
  const sourceType = document.getElementById("fb-source-type").value;
  if (sourceType !== "marketplace") return;
  const city = (readValue("fb-city") || "miami").trim().toLowerCase().replace(/\s+/g, "");
  const radius = readValue("fb-radius") || "25";
  let url = "https://www.facebook.com/marketplace/" + city + "/propertyforsale";
  const kw = readValue("fb-keywords");
  const params = [];
  if (kw) params.push("query=" + encodeURIComponent(kw));
  if (radius) params.push("radius=" + radius);
  if (params.length) url += "?" + params.join("&");
  const input = document.getElementById("fb-search-url");
  if (input) input.value = url;
}

const fbSourceType = document.getElementById("fb-source-type");
if (fbSourceType) {
  fbSourceType.addEventListener("change", updateFbSourceUI);
}
["fb-city", "fb-radius", "fb-keywords"].forEach((id) => {
  const el = document.getElementById(id);
  if (el) {
    el.addEventListener("input", buildFbSearchUrl);
    el.addEventListener("change", buildFbSearchUrl);
  }
});

fetchStatus();
fetchLogs();
refreshLeads("");
refreshComms("");
refreshFbQueue();
refreshClients("");
loadTargets();
updateScanModeUI();
updateFbSourceUI();
buildFbSearchUrl();
fetchStage1Config();
setInterval(fetchStatus, 1500);
setInterval(fetchLogs, 1000);
setInterval(() => refreshLeads(lastQuery), 5000);

const listingTypeFilterEl = document.getElementById("listing-type-filter");
const btnApplyListingFilter = document.getElementById("btn-apply-listing-filter");
if (listingTypeFilterEl) {
  listingTypeFilterEl.addEventListener("change", () => refreshLeads(lastQuery));
}
if (btnApplyListingFilter) {
  btnApplyListingFilter.addEventListener("click", () => refreshLeads(lastQuery));
}
const websiteListingTypeEl = document.getElementById("website-listing-type");
if (websiteListingTypeEl) {
  websiteListingTypeEl.addEventListener("change", () => {
    if (listingTypeFilterEl) {
      listingTypeFilterEl.value = websiteListingTypeEl.value || "";
    }
    refreshLeads(lastQuery);
  });
}
setInterval(() => refreshComms(lastCommQuery), 7000);
setInterval(() => refreshFbQueue(), 6000);
setInterval(() => refreshClients(lastClientQuery), 8000);
