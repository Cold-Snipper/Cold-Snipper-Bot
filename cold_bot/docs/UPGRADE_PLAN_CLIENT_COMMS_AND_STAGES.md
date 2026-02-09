# Upgrade plan: Client Communications & Stages

Based on the development done for the **Website Bot** section, this plan outlines upgrades for the **Client Communications** and **Stages** tabs so they match in structure, behaviour, and UX.

---

## What Website Bot has (reference)

- **Clear naming**: "Website Bot" (not generic "Scanner"); mode pills (e.g. "Leads + CRM").
- **Commands & live output**: Dedicated panel with primary actions (Reset scanned data, Save to Excel), "Data feed" heading, and a **live log** showing real-time scan/output.
- **Real data only**: No mocks; all leads from scrapers and API; filters (Sale/Rent, Rooms min) sent to backend and reflected in Leads Preview.
- **Mode switching**: Clicking the **Website Bot** or **Facebook** panel switches scan mode (no separate radio row).
- **Structured filters**: Sale/Rent dropdown, Rooms (min), Target Site, Start URLs; filters drive both scan behaviour and Leads Preview.
- **Leads Preview**: Table with Type, Bedrooms, Size, Listing type filter, Apply filter; sync between Website Bot Sale/Rent and Leads Preview filter.
- **Compact layout**: Tighter spacing, single clear hierarchy; dark coding theme.
- **Backend alignment**: `GET /api/leads?listing_type=...&rooms_min=...`; reset and export endpoints; status includes scan state and last scan.

---

## 1. Client Communications upgrades

### 1.1 Copy and structure

- Fix tab label: **"Client Communciations"** → **"Client Communications"**.
- Add a **"Commands & live output"** panel at the top of the tab (mirroring Website Bot):
  - Heading: e.g. **"CRM commands & live output"**.
  - Short hint: e.g. "Refresh and export from here; log communications in the panels below. All data is real."
  - Primary actions in one row: **Refresh Data**, **Export Summary** (and optionally **Export Comms**, **Export clients to Excel** if we add it).
  - Optional: **"CRM feed"** or **"Last actions"** – a small live log showing "Refresh done", "Communication logged", "Export done", "Client updated", etc. (either reuse the same log stream as scan or a dedicated CRM action log).

### 1.2 Filters and data flow

- **Server-side filters (optional)**: Today client list is fetched once and filtered in the frontend (stage, source, channel, score, automation, search). Optionally add query params to `GET /api/clients` (e.g. `stage`, `source_type`, `channel`, `min_score`, `automation`, `q`) so the backend does filtering and the table reflects server-filtered data (like Leads with `listing_type` and `rooms_min`).
- **Quick filter chips**: Add one-row chips or dropdowns for "Stage" and "Source" (e.g. Website / Facebook) at the top of the clients table, similar to Website Bot’s Sale/Rent + Rooms; keep "Apply Filters" or make filters apply on change (like listing type in Leads Preview).
- **Sync filters with URL (optional)**: Persist stage/source/channel in URL or localStorage so the tab opens with last-used filters.

### 1.3 Tables and actions

- **Clients table**: Ensure columns (ID/Name, Source, Details, Viability, Contact, Progress, Automation, Actions) use the same table styling as Leads Preview (dark theme, compact, bold headers).
- **Client Panel / Log Communication**: Keep layout; ensure "Log Communication" and "Add / Update Lead" use the same input/button style as Website Bot (dark inputs, blue primary buttons). Add clear "Last action" feedback (e.g. "Communication logged" in the commands panel or a small toast).
- **Export**: If not already present, add **"Save to Excel"** for clients (like leads export), same pattern as Website Bot’s "Save to Excel (.xls)" in the commands row.

### 1.4 Real data only

- Confirm there are no mock or demo clients/comms; all data from `GET /api/clients` and `GET /api/comms`. Remove any leftover `simulate*` or mock data in this tab.

### 1.5 Layout and theme

- Apply same compact spacing and dark coding theme: panels, cards, form-grid, buttons, tables so Client Communications feels like the same app as Website Bot.

---

## 2. Stages upgrades

### 2.1 Commands and live output

- Add a **"Stage pipeline & output"** panel at the top of the Stages tab:
  - Heading: e.g. **"Pipeline status & last actions"**.
  - One row of status pills or a short summary (e.g. "Config: Ready | Scan: Idle | Analysis: Idle | Contact: Idle | Log: Idle | CRM: Empty") – can reuse the same status already shown in the header bar or in each stage card.
  - A **live log** area showing last stage-related actions: e.g. "Stage 1 config written", "Scan started", "Scan finished", "Export done". This can be the same global log as the Website Bot tab, or a filtered view (e.g. only lines tagged with stage name).

### 2.2 Per-stage actions and links

- **Stage 1 – Setup**: Already has "Test Stage 1" (Websites / Facebook / Both) and current config display. Keep as is; optionally add a one-line "Output" under the buttons that shows last config write (like stage1-result-msg).
- **Stage 2 – Scanning**: Add **"Run scan"** or **"Go to Website Bot → Start Scan"** (link to Website Bot tab or same action as Start Scan) and show **Last scan time** (from status). So the stage is actionable and reflects real state.
- **Stage 3 – Analysis**: Add short text: "Runs on scan data; see Leads Preview in Website Bot." and a **"View leads"** link that switches to Website Bot tab and scrolls to Leads Preview (or opens in same tab).
- **Stage 4 – Contact**: Add "Send from Website Bot (Send via Website Forms) or Facebook panel." and **"Go to Website Bot"** link. Optionally show last contact time or count from status if we add it.
- **Stage 5 – Logging**: Add "Logging is automatic. Export from Website Bot (Save to Excel)." and **"Go to Website Bot"** or **"Export leads"** link/button.
- **Stage 6 – CRM**: Add "Manage clients and log communications in the Client Communications tab." and **"Go to Client Communications"** link (switch tab).

### 2.3 Status pills

- Ensure each stage’s status pill (e.g. "Ready", "Idle", "Active", "Populated") is driven by real data from `GET /api/status` (dbCount, scanState, commCount, clientCount, etc.) and update the copy in the doc if any pill is still hardcoded.

### 2.4 Layout and theme

- Use the same panel, flow-node, and button styles as the rest of the app (dark theme, code-like flow nodes, blue primary buttons). Keep flow diagrams readable; optionally add a single "Pipeline overview" diagram at the top (Stage 1 → 2 → 3 → 4 → 5 → 6) with links to each section.

---

## 3. Implementation order (suggested)

| Priority | Item | Tab | Effort |
|----------|------|-----|--------|
| 1 | Fix "Client Communciations" typo | Client Comms | Tiny |
| 2 | Add "CRM commands & live output" panel (actions + optional log) | Client Comms | Small |
| 3 | Add "Pipeline status & output" panel + stage links | Stages | Small |
| 4 | Add "Go to Website Bot" / "Go to Client Communications" links on Stages | Stages | Small |
| 5 | Optional: server-side client filters (`/api/clients?stage=...`) | Backend + Client Comms | Medium |
| 6 | Optional: Export clients to Excel (button + endpoint) | Backend + Client Comms | Small |
| 7 | Optional: CRM action log (dedicated or filtered from global log) | Client Comms | Medium |
| 8 | Apply compact spacing and dark theme consistency | Both tabs | Small |

---

## 4. Backend (if needed)

- **Client filters**: Extend `handleClients` in `Main.java` to accept query params: `stage`, `source_type`, `channel`, `min_score`, `automation`, `q` (search), and filter the in-memory list before returning (same pattern as `handleLeads` with `listing_type` and `rooms_min`).
- **Export clients**: Add `GET /api/export/clients.xls` (or similar) that returns an Excel file of current clients, mirroring the leads export.
- **Status**: Already exposes `clientCount`, `commCount`, etc.; ensure any new "last CRM action" or "last stage action" is either derived from existing logs or added to status/log stream and consumed by the new panels.

---

## 5. Summary

- **Client Communications**: Same pattern as Website Bot – commands panel with primary actions and optional live output; real data only; optional server-side filters and client export; consistent layout and dark theme.
- **Stages**: Same pattern – pipeline status and output at top; each stage has clear next action or link to the right tab (Website Bot or Client Communications); status pills from real API; same theme and compact layout.

This keeps the two tabs aligned with the Website Bot improvements (real data, clear commands, live feedback, compact coding-style UI) without changing the underlying data model or backend contract more than necessary.
