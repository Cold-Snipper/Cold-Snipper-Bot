import com.sun.net.httpserver.Headers;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.io.OutputStreamWriter;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class Main {
    private static final List<String> LOGS = new CopyOnWriteArrayList<>();
    private static final List<Lead> LEADS = new CopyOnWriteArrayList<>();
    private static final List<Communication> COMMUNICATIONS = new CopyOnWriteArrayList<>();
    private static final List<FbQueueItem> FB_QUEUE = new CopyOnWriteArrayList<>();
    private static final List<Client> CLIENTS = new CopyOnWriteArrayList<>();
    private static final AtomicInteger ACTION_COUNT = new AtomicInteger(0);
    private static final AtomicInteger NEXT_ID = new AtomicInteger(1);
    private static final AtomicInteger NEXT_COMM_ID = new AtomicInteger(1);
    private static final AtomicInteger NEXT_FB_ID = new AtomicInteger(1);
    private static final AtomicInteger NEXT_CLIENT_ID = new AtomicInteger(1);
    private static final ExecutorService BACKGROUND = Executors.newCachedThreadPool();
    private static final long START_MILLIS = System.currentTimeMillis();
    private static volatile String lastAction = "none";
    private static volatile String scanState = "idle";
    private static volatile String lastScanAt = "never";
    private static Path staticDir;
    private static Path dataDir;
    private static Path leadsFile;
    private static Path commsFile;
    private static Path fbQueueFile;
    private static Path clientsFile;

    public static void main(String[] args) throws Exception {
        int port = 1111;
        String envPort = System.getenv("PORT");
        if (envPort != null && !envPort.isEmpty()) {
            try {
                port = Integer.parseInt(envPort);
            } catch (NumberFormatException ignored) {
            }
        }
        if (args.length > 0) {
            try {
                port = Integer.parseInt(args[0]);
            } catch (NumberFormatException ignored) {
            }
        }

        staticDir = Paths.get("static").toAbsolutePath().normalize();
        dataDir = Paths.get("data").toAbsolutePath().normalize();
        Files.createDirectories(dataDir);
        leadsFile = dataDir.resolve("leads.csv");
        commsFile = dataDir.resolve("communications.csv");
        fbQueueFile = dataDir.resolve("fb_queue.csv");
        clientsFile = dataDir.resolve("clients.csv");
        loadLeads();
        loadCommunications();
        loadFbQueue();
        loadClients();

        HttpServer server = HttpServer.create(new InetSocketAddress(port), 0);
        server.createContext("/api/", new ApiHandler());
        server.createContext("/", new StaticHandler());
        server.setExecutor(Executors.newCachedThreadPool());
        log("UI server starting on http://localhost:" + port);
        server.start();
    }

    private static void log(String message) {
        String line = Instant.now() + " | " + message;
        LOGS.add(line);
        System.out.println(line);
    }

    private static class ApiHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange exchange) throws IOException {
            String path = exchange.getRequestURI().getPath();
            if ("/api/status".equals(path)) {
                handleStatus(exchange);
                return;
            }
            if ("/api/logs".equals(path)) {
                handleLogs(exchange);
                return;
            }
            if ("/api/leads".equals(path)) {
                handleLeads(exchange);
                return;
            }
            if ("/api/comms".equals(path)) {
                handleCommunications(exchange);
                return;
            }
            if ("/api/fbqueue".equals(path)) {
                handleFbQueue(exchange);
                return;
            }
            if ("/api/clients".equals(path)) {
                handleClients(exchange);
                return;
            }
            if ("/api/stage1_config".equals(path)) {
                handleStage1Config(exchange);
                return;
            }
            if ("/api/action".equals(path)) {
                handleAction(exchange);
                return;
            }
            sendJson(exchange, 404, "{\"error\":\"Not found\"}");
        }
    }

    private static class StaticHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange exchange) throws IOException {
            String rawPath = exchange.getRequestURI().getPath();
            if (rawPath == null || rawPath.isEmpty() || "/".equals(rawPath)) {
                rawPath = "/index.html";
            }
            Path target = staticDir.resolve(rawPath.substring(1)).normalize();
            if (!target.startsWith(staticDir)) {
                sendText(exchange, 403, "Forbidden");
                return;
            }
            if (!Files.exists(target) || Files.isDirectory(target)) {
                sendText(exchange, 404, "Not found");
                return;
            }
            byte[] data = Files.readAllBytes(target);
            Headers headers = exchange.getResponseHeaders();
            headers.set("Content-Type", contentType(target));
            exchange.sendResponseHeaders(200, data.length);
            try (OutputStream os = exchange.getResponseBody()) {
                os.write(data);
            }
        }
    }

    private static void handleStatus(HttpExchange exchange) throws IOException {
        long uptimeSeconds = TimeUnit.MILLISECONDS.toSeconds(System.currentTimeMillis() - START_MILLIS);
        String body = "{"
                + "\"uptimeSeconds\":" + uptimeSeconds + ","
                + "\"lastAction\":\"" + jsonEscape(lastAction) + "\","
                + "\"actionCount\":" + ACTION_COUNT.get() + ","
                + "\"logCount\":" + LOGS.size() + ","
                + "\"dbCount\":" + LEADS.size() + ","
                + "\"commCount\":" + COMMUNICATIONS.size() + ","
                + "\"fbQueueCount\":" + FB_QUEUE.size() + ","
                + "\"clientCount\":" + CLIENTS.size() + ","
                + "\"scanState\":\"" + jsonEscape(scanState) + "\","
                + "\"lastScanAt\":\"" + jsonEscape(lastScanAt) + "\""
                + "}";
        sendJson(exchange, 200, body);
    }

    private static void handleLogs(HttpExchange exchange) throws IOException {
        Map<String, String> query = parseQuery(exchange.getRequestURI());
        int since = 0;
        if (query.containsKey("since")) {
            try {
                since = Integer.parseInt(query.get("since"));
            } catch (NumberFormatException ignored) {
            }
        }
        if (since < 0) {
            since = 0;
        }
        int total = LOGS.size();
        int from = Math.min(since, total);
        List<String> slice = new ArrayList<>();
        for (int i = from; i < total; i++) {
            slice.add(LOGS.get(i));
        }

        StringBuilder body = new StringBuilder();
        body.append("{\"from\":").append(from)
                .append(",\"to\":").append(total)
                .append(",\"logs\":[");
        for (int i = 0; i < slice.size(); i++) {
            if (i > 0) {
                body.append(",");
            }
            body.append("\"").append(jsonEscape(slice.get(i))).append("\"");
        }
        body.append("]}");
        sendJson(exchange, 200, body.toString());
    }

    private static void handleLeads(HttpExchange exchange) throws IOException {
        Map<String, String> query = parseQuery(exchange.getRequestURI());
        int limit = 50;
        if (query.containsKey("limit")) {
            try {
                limit = Integer.parseInt(query.get("limit"));
            } catch (NumberFormatException ignored) {
            }
        }
        if (limit <= 0) {
            limit = 50;
        }
        String q = query.getOrDefault("q", "").toLowerCase();
        String status = query.getOrDefault("status", "").toLowerCase();

        List<Lead> filtered = new ArrayList<>();
        for (Lead lead : LEADS) {
            if (!status.isEmpty() && !lead.status.toLowerCase().equals(status)) {
                continue;
            }
            if (!q.isEmpty() && !lead.matches(q)) {
                continue;
            }
            filtered.add(lead);
        }

        int total = filtered.size();
        List<Lead> slice = filtered.subList(0, Math.min(limit, total));
        StringBuilder body = new StringBuilder();
        body.append("{\"total\":").append(total).append(",\"leads\":[");
        for (int i = 0; i < slice.size(); i++) {
            if (i > 0) {
                body.append(",");
            }
            body.append(slice.get(i).toJson());
        }
        body.append("]}");
        sendJson(exchange, 200, body.toString());
    }

    private static void handleCommunications(HttpExchange exchange) throws IOException {
        Map<String, String> query = parseQuery(exchange.getRequestURI());
        int limit = 50;
        if (query.containsKey("limit")) {
            try {
                limit = Integer.parseInt(query.get("limit"));
            } catch (NumberFormatException ignored) {
            }
        }
        if (limit <= 0) {
            limit = 50;
        }
        String q = query.getOrDefault("q", "").toLowerCase();
        String status = query.getOrDefault("status", "").toLowerCase();
        String clientId = query.getOrDefault("client_id", "");

        List<Communication> filtered = new ArrayList<>();
        for (Communication comm : COMMUNICATIONS) {
            if (!status.isEmpty() && !comm.status.toLowerCase().equals(status)) {
                continue;
            }
            if (!clientId.isEmpty() && !clientId.equals(comm.clientId)) {
                continue;
            }
            if (!q.isEmpty() && !comm.matches(q)) {
                continue;
            }
            filtered.add(comm);
        }

        int total = filtered.size();
        List<Communication> slice = filtered.subList(0, Math.min(limit, total));
        StringBuilder body = new StringBuilder();
        body.append("{\"total\":").append(total).append(",\"communications\":[");
        for (int i = 0; i < slice.size(); i++) {
            if (i > 0) {
                body.append(",");
            }
            body.append(slice.get(i).toJson());
        }
        body.append("]}");
        sendJson(exchange, 200, body.toString());
    }

    private static void handleFbQueue(HttpExchange exchange) throws IOException {
        Map<String, String> query = parseQuery(exchange.getRequestURI());
        int limit = 100;
        if (query.containsKey("limit")) {
            try {
                limit = Integer.parseInt(query.get("limit"));
            } catch (NumberFormatException ignored) {
            }
        }
        if (limit <= 0) {
            limit = 100;
        }
        String status = query.getOrDefault("status", "").toLowerCase();
        List<FbQueueItem> filtered = new ArrayList<>();
        for (FbQueueItem item : FB_QUEUE) {
            if (!status.isEmpty() && !item.status.toLowerCase().equals(status)) {
                continue;
            }
            filtered.add(item);
        }
        int total = filtered.size();
        List<FbQueueItem> slice = filtered.subList(0, Math.min(limit, total));
        StringBuilder body = new StringBuilder();
        body.append("{\"total\":").append(total).append(",\"items\":[");
        for (int i = 0; i < slice.size(); i++) {
            if (i > 0) {
                body.append(",");
            }
            body.append(slice.get(i).toJson());
        }
        body.append("]}");
        sendJson(exchange, 200, body.toString());
    }

    private static void handleClients(HttpExchange exchange) throws IOException {
        Map<String, String> query = parseQuery(exchange.getRequestURI());
        int limit = 200;
        if (query.containsKey("limit")) {
            try {
                limit = Integer.parseInt(query.get("limit"));
            } catch (NumberFormatException ignored) {
            }
        }
        if (limit <= 0) {
            limit = 200;
        }
        String q = query.getOrDefault("q", "").toLowerCase();
        String status = query.getOrDefault("status", "").toLowerCase();
        String stage = query.getOrDefault("stage", "").toLowerCase();

        List<Client> filtered = new ArrayList<>();
        for (Client client : CLIENTS) {
            if (!status.isEmpty() && !client.status.toLowerCase().equals(status)) {
                continue;
            }
            if (!stage.isEmpty() && !client.stage.toLowerCase().equals(stage)) {
                continue;
            }
            if (!q.isEmpty() && !client.matches(q)) {
                continue;
            }
            filtered.add(client);
        }
        int total = filtered.size();
        List<Client> slice = filtered.subList(0, Math.min(limit, total));
        StringBuilder body = new StringBuilder();
        body.append("{\"total\":").append(total).append(",\"clients\":[");
        for (int i = 0; i < slice.size(); i++) {
            if (i > 0) {
                body.append(",");
            }
            body.append(slice.get(i).toJson());
        }
        body.append("]}");
        sendJson(exchange, 200, body.toString());
    }

    private static final Path STAGE1_CONFIG_PATH = Paths.get("config.yaml");

    private static void handleStage1Config(HttpExchange exchange) throws IOException {
        if ("GET".equalsIgnoreCase(exchange.getRequestMethod())) {
            Map<String, String> cfg = readStage1Config();
            String body = "{\"source_type\":" + (cfg.get("source_type") == null ? "null" : "\"" + jsonEscape(cfg.get("source_type")) + "\"")
                    + ",\"agents_handling\":" + (cfg.get("agents_handling") == null ? "null" : "\"" + jsonEscape(cfg.get("agents_handling")) + "\"") + "}";
            sendJson(exchange, 200, body);
        } else {
            sendJson(exchange, 405, "{\"error\":\"Method not allowed\"}");
        }
    }

    private static Map<String, String> readStage1Config() {
        Map<String, String> out = new HashMap<>();
        out.put("source_type", null);
        out.put("agents_handling", null);
        if (!Files.exists(STAGE1_CONFIG_PATH)) {
            return out;
        }
        try {
            for (String line : Files.readAllLines(STAGE1_CONFIG_PATH, StandardCharsets.UTF_8)) {
                String trimmed = line.trim();
                if (trimmed.startsWith("source_type:")) {
                    out.put("source_type", trimmed.substring("source_type:".length()).trim().replaceAll("^[\"\']|[\"\']$", ""));
                } else if (trimmed.startsWith("agents_handling:")) {
                    out.put("agents_handling", trimmed.substring("agents_handling:".length()).trim().replaceAll("^[\"\']|[\"\']$", ""));
                }
            }
        } catch (IOException ignored) {
        }
        return out;
    }

    private static void writeStage1Config(String sourceType) throws IOException {
        String yaml = "source_type: " + sourceType + "\nagents_handling: log_and_export\n";
        Files.write(STAGE1_CONFIG_PATH, yaml.getBytes(StandardCharsets.UTF_8));
    }

    private static void handleAction(HttpExchange exchange) throws IOException {
        if (!"POST".equalsIgnoreCase(exchange.getRequestMethod())) {
            sendJson(exchange, 405, "{\"error\":\"Method not allowed\"}");
            return;
        }
        Map<String, String> params = new HashMap<>(parseQuery(exchange.getRequestURI()));
        params.putAll(parseBodyParams(exchange));
        String name = params.getOrDefault("name", "unknown");
        lastAction = name;

        if ("clear_logs".equals(name)) {
            LOGS.clear();
            ACTION_COUNT.incrementAndGet();
            log("Logs cleared");
            sendJson(exchange, 200, "{\"ok\":true,\"message\":\"Logs cleared\"}");
            return;
        }

        ACTION_COUNT.incrementAndGet();
        switch (name) {
            case "start_scan":
                scanState = "running";
                log("Scan started (site=" + params.getOrDefault("target_site", "n/a")
                        + ", country=" + params.getOrDefault("country", "n/a")
                        + ", urls=" + params.getOrDefault("start_urls", "n/a") + ")");
                BACKGROUND.submit(() -> runRealSiteScan(params, false));
                sendJson(exchange, 200, "{\"ok\":true,\"message\":\"Website scan started (browser will open; refresh leads when done)\"}");
                break;
            case "pause_scan":
                scanState = "paused";
                log("Scan paused");
                sendJson(exchange, 200, "{\"ok\":true,\"message\":\"Scan paused\"}");
                break;
            case "stop_scan":
                scanState = "stopped";
                log("Scan stopped");
                sendJson(exchange, 200, "{\"ok\":true,\"message\":\"Scan stopped\"}");
                break;
            case "test_single_page":
                log("Single page test scan queued (site=" + params.getOrDefault("target_site", "n/a")
                        + ", country=" + params.getOrDefault("country", "n/a")
                        + ", url=" + params.getOrDefault("single_url", "n/a") + ")");
                BACKGROUND.submit(() -> runRealSiteScan(params, true));
                sendJson(exchange, 200, "{\"ok\":true,\"message\":\"Single page scan started (browser will open; refresh leads when done)\"}");
                break;
            case "preview_results":
                log("Preview requested");
                sendJson(exchange, 200, "{\"ok\":true,\"message\":\"Preview refreshed\"}");
                break;
            case "view_all_leads":
                log("View all leads requested");
                sendJson(exchange, 200, "{\"ok\":true,\"message\":\"Leads loaded\"}");
                break;
            case "search_db":
                log("DB search requested (query=" + params.getOrDefault("search_query", "") + ")");
                sendJson(exchange, 200, "{\"ok\":true,\"message\":\"Search executed\"}");
                break;
            case "mark_contacted":
                int marked = updateStatus(params.getOrDefault("ids", ""), "contacted");
                log("Marked contacted: " + marked);
                sendJson(exchange, 200, "{\"ok\":true,\"message\":\"Marked contacted: " + marked + "\"}");
                break;
            case "delete_selected":
                int deleted = deleteLeads(params.getOrDefault("ids", ""));
                log("Deleted leads: " + deleted);
                sendJson(exchange, 200, "{\"ok\":true,\"message\":\"Deleted leads: " + deleted + "\"}");
                break;
            case "export_csv":
                String exportPath = exportCsv();
                log("Exported CSV to " + exportPath);
                sendJson(exchange, 200, "{\"ok\":true,\"message\":\"Exported CSV\",\"path\":\"" + jsonEscape(exportPath) + "\"}");
                break;
            case "clear_database":
                clearDatabase();
                log("Database cleared");
                sendJson(exchange, 200, "{\"ok\":true,\"message\":\"Database cleared\"}");
                break;
            case "backup_db":
                String backupPath = backupDatabase();
                log("Database backup created: " + backupPath);
                sendJson(exchange, 200, "{\"ok\":true,\"message\":\"Database backup created\",\"path\":\"" + jsonEscape(backupPath) + "\"}");
                break;
            case "add_comm":
                Communication comm = Communication.fromParams(params);
                if (comm != null) {
                    addCommunication(comm);
                    log("Communication added for " + comm.contactEmail);
                    sendJson(exchange, 200, "{\"ok\":true,\"message\":\"Communication added\"}");
                } else {
                    sendJson(exchange, 400, "{\"ok\":false,\"message\":\"Missing contact info\"}");
                }
                break;
            case "update_comm_status":
                int updatedComm = updateCommStatus(params.getOrDefault("ids", ""), params.getOrDefault("status", "pending"));
                log("Updated communication status: " + updatedComm);
                sendJson(exchange, 200, "{\"ok\":true,\"message\":\"Updated status: " + updatedComm + "\"}");
                break;
            case "delete_comm":
                int deletedComm = deleteCommunications(params.getOrDefault("ids", ""));
                log("Deleted communications: " + deletedComm);
                sendJson(exchange, 200, "{\"ok\":true,\"message\":\"Deleted communications: " + deletedComm + "\"}");
                break;
            case "export_comms":
                String commExport = exportCommunications();
                log("Exported communications CSV to " + commExport);
                sendJson(exchange, 200, "{\"ok\":true,\"message\":\"Exported communications\",\"path\":\"" + jsonEscape(commExport) + "\"}");
                break;
            case "clear_comms":
                clearCommunications();
                log("Communications cleared");
                sendJson(exchange, 200, "{\"ok\":true,\"message\":\"Communications cleared\"}");
                break;
            case "fb_analyze":
                log("FB analyze requested (url=" + params.getOrDefault("fb_search_url", "n/a")
                        + ", logged_in=" + params.getOrDefault("fb_logged_in", "false") + ")");
                BACKGROUND.submit(() -> runRealFbAnalyze(params));
                sendJson(exchange, 200, "{\"ok\":true,\"message\":\"FB analysis started (browser will open; refresh queue when done)\"}");
                break;
            case "fb_save_urls":
                int saved = saveFbUrls(params, 6);
                log("FB URLs saved: " + saved);
                sendJson(exchange, 200, "{\"ok\":true,\"message\":\"Saved URLs: " + saved + "\"}");
                break;
            case "fb_mark_contacted":
                int markedFb = updateFbStatus(params.getOrDefault("ids", ""), "contacted");
                log("FB URLs marked contacted: " + markedFb);
                sendJson(exchange, 200, "{\"ok\":true,\"message\":\"Marked contacted: " + markedFb + "\"}");
                break;
            case "fb_clear_queue":
                clearFbQueue();
                log("FB queue cleared");
                sendJson(exchange, 200, "{\"ok\":true,\"message\":\"FB queue cleared\"}");
                break;
            case "fb_send_messages":
                BACKGROUND.submit(() -> runFbMessenger(params));
                sendJson(exchange, 200, "{\"ok\":true,\"message\":\"FB send queued\"}");
                break;
            case "site_send_messages":
                BACKGROUND.submit(() -> runSiteForms(params));
                sendJson(exchange, 200, "{\"ok\":true,\"message\":\"Website send queued\"}");
                break;
            case "add_client":
                Client client = Client.fromParams(params);
                if (client != null) {
                    addClient(client);
                    log("Client added: " + client.name);
                    sendJson(exchange, 200, "{\"ok\":true,\"message\":\"Client added\"}");
                } else {
                    sendJson(exchange, 400, "{\"ok\":false,\"message\":\"Missing client contact\"}");
                }
                break;
            case "update_client":
                int updatedClient = updateClient(params);
                log("Client updated: " + updatedClient);
                sendJson(exchange, 200, "{\"ok\":true,\"message\":\"Client updated\"}");
                break;
            case "delete_client":
                int deletedClient = deleteClients(params.getOrDefault("ids", ""));
                log("Clients deleted: " + deletedClient);
                sendJson(exchange, 200, "{\"ok\":true,\"message\":\"Clients deleted: " + deletedClient + "\"}");
                break;
            case "export_clients":
                String clientExport = exportClients();
                log("Exported clients CSV to " + clientExport);
                sendJson(exchange, 200, "{\"ok\":true,\"message\":\"Exported clients\",\"path\":\"" + jsonEscape(clientExport) + "\"}");
                break;
            case "stage1_apply":
                String st1 = params.getOrDefault("source_type", "").trim().toLowerCase();
                if (!st1.equals("websites") && !st1.equals("facebook") && !st1.equals("both")) {
                    st1 = "both";
                }
                try {
                    writeStage1Config(st1);
                    log("Stage 1 applied: source_type=" + st1);
                    sendJson(exchange, 200, "{\"ok\":true,\"message\":\"Stage 1 applied\",\"source_type\":\"" + jsonEscape(st1) + "\"}");
                } catch (Exception e) {
                    log("Stage 1 write failed: " + e.getMessage());
                    sendJson(exchange, 500, "{\"ok\":false,\"message\":\"" + jsonEscape(e.getMessage()) + "\"}");
                }
                break;
            case "load_config":
                log("Config loaded (path=" + params.getOrDefault("config_path", "config.yaml") + ")");
                sendJson(exchange, 200, "{\"ok\":true,\"message\":\"Config loaded\"}");
                break;
            case "save_config":
                log("Config saved (path=" + params.getOrDefault("config_path", "config.yaml") + ")");
                sendJson(exchange, 200, "{\"ok\":true,\"message\":\"Config saved\"}");
                break;
            case "test_llm_prompt":
                log("LLM prompt test requested (" + params.getOrDefault("prompt_text", "").length() + " chars)");
                sendJson(exchange, 200, "{\"ok\":true,\"message\":\"LLM prompt tested\"}");
                break;
            default:
                log("Action requested: " + name);
                BACKGROUND.submit(() -> simulateAction(name));
                sendJson(exchange, 200, "{\"ok\":true,\"message\":\"Action accepted\"}");
                break;
        }
    }

    private static void simulateAction(String name) {
        log("Action " + name + " started");
        sleep(300);
        log("Action " + name + " running");
        sleep(500);
        log("Action " + name + " finished");
    }

    private static void runRealSiteScan(Map<String, String> params, boolean singlePageOnly) {
        List<String> urls = new ArrayList<>();
        if (singlePageOnly) {
            String one = params.getOrDefault("single_url", "").trim();
            if (!one.isEmpty()) {
                urls.add(one);
            }
        } else {
            String startUrls = params.getOrDefault("start_urls", "");
            for (String line : startUrls.split("\n")) {
                String u = line.trim();
                if (!u.isEmpty()) {
                    urls.add(u);
                }
            }
        }
        if (urls.isEmpty()) {
            log("Website scan skipped: no URLs (set Start URLs or Single Page URL)");
            return;
        }
        Path script = Paths.get("..", "cold_bot", "site_scraper.py").toAbsolutePath().normalize();
        if (!Files.exists(script)) {
            log("Website scan failed: script not found at " + script);
            return;
        }
        Path leadsPath = dataDir.resolve("leads.csv");
        List<String> command = new ArrayList<>();
        command.add("python3");
        command.add(script.toString());
        command.add("--leads-path");
        command.add(leadsPath.toString());
        for (String url : urls) {
            command.add("--url");
            command.add(url);
        }
        String selector = params.getOrDefault("listing_selector", "").trim();
        if (!selector.isEmpty()) {
            command.add("--listing-selector");
            command.add(selector);
        }
        if ("true".equalsIgnoreCase(params.getOrDefault("site_headless", "false"))) {
            command.add("--headless");
        }
        lastScanAt = DateTimeFormatter.ISO_INSTANT.format(Instant.now());
        log("Website scan running (browser may open)...");
        try {
            ProcessBuilder builder = new ProcessBuilder(command);
            builder.redirectErrorStream(true);
            Process process = builder.start();
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) {
                    log("Site scan: " + line);
                }
            }
            int exitCode = process.waitFor();
            if (exitCode == 0) {
                synchronized (LEADS) {
                    LEADS.clear();
                    try {
                        loadLeads();
                    } catch (IOException e) {
                        log("Leads reload failed: " + e.getMessage());
                    }
                }
                log("Website scan finished; leads updated.");
            } else {
                log("Website scan finished with exit code " + exitCode);
            }
        } catch (Exception e) {
            log("Website scan failed: " + e.getMessage());
        }
    }

    private static void runRealFbAnalyze(Map<String, String> params) {
        List<String> urls = new ArrayList<>();
        String sourceType = params.getOrDefault("fb_source_type", "marketplace");
        if ("groups".equalsIgnoreCase(sourceType)) {
            String groupUrls = params.getOrDefault("fb_group_urls", "");
            for (String line : groupUrls.split("\n")) {
                String u = line.trim();
                if (!u.isEmpty()) {
                    urls.add(u);
                }
            }
        }
        if (urls.isEmpty()) {
            String one = params.getOrDefault("fb_search_url", "").trim();
            if (!one.isEmpty()) {
                urls.add(one);
            }
        }
        if (urls.isEmpty()) {
            log("FB analyze skipped: no URLs (set city/keywords for Marketplace or group URLs for Groups)");
            return;
        }
        Path script = Paths.get("..", "cold_bot", "fb_feed_analyzer.py").toAbsolutePath().normalize();
        if (!Files.exists(script)) {
            log("FB analyze failed: script not found at " + script);
            return;
        }
        Path queuePath = dataDir.resolve("fb_queue.csv");
        List<String> command = new ArrayList<>();
        command.add("python3");
        command.add(script.toString());
        command.add("--queue-path");
        command.add(queuePath.toString());
        for (String url : urls) {
            command.add("--url");
            command.add(url);
        }
        if ("true".equalsIgnoreCase(params.getOrDefault("fb_headless", "false"))) {
            command.add("--headless");
        }
        String storageState = params.getOrDefault("fb_storage_state", "").trim();
        if (!storageState.isEmpty()) {
            Path statePath = Paths.get(storageState).toAbsolutePath().normalize();
            if (Files.exists(statePath)) {
                command.add("--storage-state");
                command.add(statePath.toString());
            }
        }
        log("FB analysis running (browser may open)...");
        try {
            ProcessBuilder builder = new ProcessBuilder(command);
            builder.redirectErrorStream(true);
            Process process = builder.start();
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) {
                    log("FB analyze: " + line);
                }
            }
            int exitCode = process.waitFor();
            if (exitCode == 0) {
                synchronized (FB_QUEUE) {
                    FB_QUEUE.clear();
                    try {
                        loadFbQueue();
                    } catch (IOException e) {
                        log("FB queue reload failed: " + e.getMessage());
                    }
                }
                log("FB analysis finished; queue updated.");
            } else {
                log("FB analysis finished with exit code " + exitCode);
            }
        } catch (Exception e) {
            log("FB analyze failed: " + e.getMessage());
        }
    }

    private static void runFbMessenger(Map<String, String> params) {
        String message = params.getOrDefault("fb_message", "").trim();
        if (message.isEmpty()) {
            log("FB send skipped: message is empty");
            return;
        }
        String limit = params.getOrDefault("fb_send_limit", "5");
        String headless = params.getOrDefault("fb_headless", "false");
        Path script = Paths.get("..", "cold_bot", "fb_messenger.py").toAbsolutePath().normalize();
        Path queuePath = dataDir.resolve("fb_queue.csv");
        List<String> command = new ArrayList<>();
        command.add("python3");
        command.add(script.toString());
        command.add("--queue-path");
        command.add(queuePath.toString());
        command.add("--message");
        command.add(message);
        command.add("--limit");
        command.add(limit);
        if ("true".equalsIgnoreCase(headless)) {
            command.add("--headless");
        }
        try {
            ProcessBuilder builder = new ProcessBuilder(command);
            builder.redirectErrorStream(true);
            Process process = builder.start();
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) {
                    log("FB send: " + line);
                }
            }
            int exitCode = process.waitFor();
            log("FB send finished (exit=" + exitCode + ")");
        } catch (Exception e) {
            log("FB send failed: " + e.getMessage());
        }
    }

    private static void runSiteForms(Map<String, String> params) {
        String message = params.getOrDefault("site_message", "").trim();
        if (message.isEmpty()) {
            log("Website send skipped: message is empty");
            return;
        }
        String limit = params.getOrDefault("site_send_limit", "5");
        String headless = params.getOrDefault("site_headless", "false");
        Path script = Paths.get("..", "cold_bot", "site_forms.py").toAbsolutePath().normalize();
        Path leadsPath = dataDir.resolve("leads.csv");
        List<String> command = new ArrayList<>();
        command.add("python3");
        command.add(script.toString());
        command.add("--leads-path");
        command.add(leadsPath.toString());
        command.add("--message");
        command.add(message);
        command.add("--limit");
        command.add(limit);
        if ("true".equalsIgnoreCase(headless)) {
            command.add("--headless");
        }
        try {
            ProcessBuilder builder = new ProcessBuilder(command);
            builder.redirectErrorStream(true);
            Process process = builder.start();
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) {
                    log("Website send: " + line);
                }
            }
            int exitCode = process.waitFor();
            if (exitCode == 0) {
                synchronized (LEADS) {
                    LEADS.clear();
                    try {
                        loadLeads();
                    } catch (IOException e) {
                        log("Leads reload failed: " + e.getMessage());
                    }
                }
            }
            log("Website send finished (exit=" + exitCode + ")");
        } catch (Exception e) {
            log("Website send failed: " + e.getMessage());
        }
    }

    private static void sleep(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException ignored) {
            Thread.currentThread().interrupt();
        }
    }

    private static Map<String, String> parseQuery(URI uri) {
        String query = uri.getRawQuery();
        if (query == null || query.isEmpty()) {
            return Collections.emptyMap();
        }
        Map<String, String> params = new HashMap<>();
        String[] pairs = query.split("&");
        for (String pair : pairs) {
            if (pair.isEmpty()) {
                continue;
            }
            String[] parts = pair.split("=", 2);
            String key = urlDecode(parts[0]);
            String value = parts.length > 1 ? urlDecode(parts[1]) : "";
            params.put(key, value);
        }
        return params;
    }

    private static Map<String, String> parseBodyParams(HttpExchange exchange) throws IOException {
        String contentType = exchange.getRequestHeaders().getFirst("Content-Type");
        if (contentType == null || !contentType.toLowerCase().contains("application/x-www-form-urlencoded")) {
            return Collections.emptyMap();
        }
        String body = readBody(exchange.getRequestBody());
        if (body.isEmpty()) {
            return Collections.emptyMap();
        }
        Map<String, String> params = new HashMap<>();
        String[] pairs = body.split("&");
        for (String pair : pairs) {
            if (pair.isEmpty()) {
                continue;
            }
            String[] parts = pair.split("=", 2);
            String key = urlDecode(parts[0]);
            String value = parts.length > 1 ? urlDecode(parts[1]) : "";
            params.put(key, value);
        }
        return params;
    }

    private static String readBody(InputStream inputStream) throws IOException {
        StringBuilder body = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(inputStream, StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                body.append(line);
            }
        }
        return body.toString();
    }

    private static String urlDecode(String value) {
        return URLDecoder.decode(value, StandardCharsets.UTF_8);
    }

    private static void sendJson(HttpExchange exchange, int status, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        Headers headers = exchange.getResponseHeaders();
        headers.set("Content-Type", "application/json; charset=utf-8");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream os = exchange.getResponseBody()) {
            os.write(bytes);
        }
    }

    private static void sendText(HttpExchange exchange, int status, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        Headers headers = exchange.getResponseHeaders();
        headers.set("Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream os = exchange.getResponseBody()) {
            os.write(bytes);
        }
    }

    private static String contentType(Path path) {
        String name = path.getFileName().toString().toLowerCase();
        if (name.endsWith(".html")) {
            return "text/html; charset=utf-8";
        }
        if (name.endsWith(".css")) {
            return "text/css; charset=utf-8";
        }
        if (name.endsWith(".js")) {
            return "application/javascript; charset=utf-8";
        }
        if (name.endsWith(".json")) {
            return "application/json; charset=utf-8";
        }
        return "application/octet-stream";
    }

    private static void loadLeads() throws IOException {
        if (!Files.exists(leadsFile)) {
            persistLeads();
            return;
        }
        try (BufferedReader reader = Files.newBufferedReader(leadsFile, StandardCharsets.UTF_8)) {
            String line = reader.readLine();
            if (line == null) {
                return;
            }
            while ((line = reader.readLine()) != null) {
                List<String> parts = parseCsvLine(line);
                if (parts.size() < 10) {
                    continue;
                }
                Lead lead = new Lead(
                        parseInt(parts.get(0), NEXT_ID.get()),
                        parts.get(1),
                        parts.get(2),
                        parts.get(3),
                        parts.get(4),
                        parts.get(5),
                        parts.get(6),
                        parts.get(7),
                        parts.get(8),
                        parts.get(9)
                );
                LEADS.add(lead);
                NEXT_ID.set(Math.max(NEXT_ID.get(), lead.id + 1));
            }
        }
        log("Loaded leads from " + leadsFile + " (" + LEADS.size() + ")");
    }

    private static void loadCommunications() throws IOException {
        if (!Files.exists(commsFile)) {
            persistCommunications();
            return;
        }
        try (BufferedReader reader = Files.newBufferedReader(commsFile, StandardCharsets.UTF_8)) {
            String line = reader.readLine();
            if (line == null) {
                return;
            }
            while ((line = reader.readLine()) != null) {
                List<String> parts = parseCsvLine(line);
                if (parts.size() < 9) {
                    continue;
                }
                String clientId = parts.size() > 9 ? parts.get(9) : "";
                Communication comm = new Communication(
                        parseInt(parts.get(0), NEXT_COMM_ID.get()),
                        parts.get(1),
                        parts.get(2),
                        parts.get(3),
                        parts.get(4),
                        parts.get(5),
                        parts.get(6),
                        parts.get(7),
                        parts.get(8),
                        clientId
                );
                COMMUNICATIONS.add(comm);
                NEXT_COMM_ID.set(Math.max(NEXT_COMM_ID.get(), comm.id + 1));
            }
        }
        log("Loaded communications from " + commsFile + " (" + COMMUNICATIONS.size() + ")");
    }

    private static void loadFbQueue() throws IOException {
        if (!Files.exists(fbQueueFile)) {
            persistFbQueue();
            return;
        }
        try (BufferedReader reader = Files.newBufferedReader(fbQueueFile, StandardCharsets.UTF_8)) {
            String line = reader.readLine();
            if (line == null) {
                return;
            }
            while ((line = reader.readLine()) != null) {
                List<String> parts = parseCsvLine(line);
                if (parts.size() < 4) {
                    continue;
                }
                FbQueueItem item = new FbQueueItem(
                        parseInt(parts.get(0), NEXT_FB_ID.get()),
                        parts.get(1),
                        parts.get(2),
                        parts.get(3)
                );
                FB_QUEUE.add(item);
                NEXT_FB_ID.set(Math.max(NEXT_FB_ID.get(), item.id + 1));
            }
        }
        log("Loaded FB queue from " + fbQueueFile + " (" + FB_QUEUE.size() + ")");
    }

    private static void loadClients() throws IOException {
        if (!Files.exists(clientsFile)) {
            persistClients();
            return;
        }
        try (BufferedReader reader = Files.newBufferedReader(clientsFile, StandardCharsets.UTF_8)) {
            String line = reader.readLine();
            if (line == null) {
                return;
            }
            while ((line = reader.readLine()) != null) {
                List<String> parts = parseCsvLine(line);
                if (parts.size() < 9) {
                    continue;
                }
                String sourceType = parts.size() > 9 ? parts.get(9) : "";
                String outreachChannel = parts.size() > 10 ? parts.get(10) : "";
                String automationEnabled = parts.size() > 11 ? parts.get(11) : "false";
                String viabilityScore = parts.size() > 12 ? parts.get(12) : "";
                String lastInteraction = parts.size() > 13 ? parts.get(13) : "";
                Client client = new Client(
                        parseInt(parts.get(0), NEXT_CLIENT_ID.get()),
                        parts.get(1),
                        parts.get(2),
                        parts.get(3),
                        parts.get(4),
                        parts.get(5),
                        parts.get(6),
                        parts.get(7),
                        parts.get(8),
                        sourceType,
                        outreachChannel,
                        parseBool(automationEnabled),
                        viabilityScore,
                        lastInteraction
                );
                CLIENTS.add(client);
                NEXT_CLIENT_ID.set(Math.max(NEXT_CLIENT_ID.get(), client.id + 1));
            }
        }
        log("Loaded clients from " + clientsFile + " (" + CLIENTS.size() + ")");
    }

    private static int parseInt(String value, int fallback) {
        try {
            return Integer.parseInt(value);
        } catch (NumberFormatException ignored) {
            return fallback;
        }
    }

    private static synchronized void persistLeads() throws IOException {
        try (BufferedWriter writer = new BufferedWriter(new OutputStreamWriter(Files.newOutputStream(leadsFile), StandardCharsets.UTF_8))) {
            writer.write("id,url,title,description,price,location,contact_email,contact_phone,scan_time,status");
            writer.newLine();
            for (Lead lead : LEADS) {
                writer.write(lead.toCsv());
                writer.newLine();
            }
        }
    }

    private static synchronized void persistCommunications() throws IOException {
        try (BufferedWriter writer = new BufferedWriter(new OutputStreamWriter(Files.newOutputStream(commsFile), StandardCharsets.UTF_8))) {
            writer.write("id,contact_name,contact_email,contact_phone,channel,last_message,status,last_contacted_at,notes,client_id");
            writer.newLine();
            for (Communication comm : COMMUNICATIONS) {
                writer.write(comm.toCsv());
                writer.newLine();
            }
        }
    }

    private static synchronized void persistClients() throws IOException {
        try (BufferedWriter writer = new BufferedWriter(new OutputStreamWriter(Files.newOutputStream(clientsFile), StandardCharsets.UTF_8))) {
            writer.write("id,name,email,phone,status,stage,source,last_contacted_at,notes,source_type,outreach_channel,automation_enabled,viability_score,last_interaction");
            writer.newLine();
            for (Client client : CLIENTS) {
                writer.write(client.toCsv());
                writer.newLine();
            }
        }
    }

    private static synchronized void persistFbQueue() throws IOException {
        try (BufferedWriter writer = new BufferedWriter(new OutputStreamWriter(Files.newOutputStream(fbQueueFile), StandardCharsets.UTF_8))) {
            writer.write("id,url,status,saved_at");
            writer.newLine();
            for (FbQueueItem item : FB_QUEUE) {
                writer.write(item.toCsv());
                writer.newLine();
            }
        }
    }

    private static synchronized void addLead(Lead lead) {
        for (Lead existing : LEADS) {
            if (existing.url.equalsIgnoreCase(lead.url)) {
                return;
            }
        }
        LEADS.add(lead);
        try {
            persistLeads();
        } catch (IOException e) {
            log("Failed to persist leads: " + e.getMessage());
        }
    }

    private static synchronized void addCommunication(Communication comm) {
        COMMUNICATIONS.add(comm);
        try {
            persistCommunications();
        } catch (IOException e) {
            log("Failed to persist communications: " + e.getMessage());
        }
    }

    private static synchronized void addClient(Client client) {
        CLIENTS.add(client);
        try {
            persistClients();
        } catch (IOException e) {
            log("Failed to persist clients: " + e.getMessage());
        }
    }

    private static int updateClient(Map<String, String> params) {
        String idParam = params.getOrDefault("client_id", "");
        int id = parseInt(idParam, -1);
        if (id <= 0) {
            return 0;
        }
        int updated = 0;
        for (Client client : CLIENTS) {
            if (client.id == id) {
                client.status = paramOrDefault(params, "status", client.status);
                client.stage = paramOrDefault(params, "stage", client.stage);
                client.notes = paramOrDefault(params, "notes", client.notes);
                client.sourceType = paramOrDefault(params, "source_type", client.sourceType);
                client.outreachChannel = paramOrDefault(params, "outreach_channel", client.outreachChannel);
                if (params.containsKey("automation_enabled")) {
                    client.automationEnabled = parseBool(params.get("automation_enabled"));
                }
                client.viabilityScore = paramOrDefault(params, "viability_score", client.viabilityScore);
                client.lastContactedAt = DateTimeFormatter.ISO_INSTANT.format(Instant.now());
                client.lastInteraction = client.lastContactedAt;
                updated++;
            }
        }
        if (updated > 0) {
            try {
                persistClients();
            } catch (IOException e) {
                log("Failed to persist clients: " + e.getMessage());
            }
        }
        return updated;
    }

    private static int deleteClients(String idsParam) {
        List<Integer> ids = parseIds(idsParam);
        int before = CLIENTS.size();
        CLIENTS.removeIf(client -> ids.contains(client.id));
        int deleted = before - CLIENTS.size();
        if (deleted > 0) {
            try {
                persistClients();
            } catch (IOException e) {
                log("Failed to persist clients: " + e.getMessage());
            }
        }
        return deleted;
    }

    private static int updateCommStatus(String idsParam, String status) {
        List<Integer> ids = parseIds(idsParam);
        int updated = 0;
        for (Communication comm : COMMUNICATIONS) {
            if (ids.contains(comm.id)) {
                comm.status = status;
                comm.lastContactedAt = DateTimeFormatter.ISO_INSTANT.format(Instant.now());
                updated++;
            }
        }
        if (updated > 0) {
            try {
                persistCommunications();
            } catch (IOException e) {
                log("Failed to persist communications: " + e.getMessage());
            }
        }
        return updated;
    }

    private static int deleteCommunications(String idsParam) {
        List<Integer> ids = parseIds(idsParam);
        int before = COMMUNICATIONS.size();
        COMMUNICATIONS.removeIf(comm -> ids.contains(comm.id));
        int deleted = before - COMMUNICATIONS.size();
        if (deleted > 0) {
            try {
                persistCommunications();
            } catch (IOException e) {
                log("Failed to persist communications: " + e.getMessage());
            }
        }
        return deleted;
    }

    private static int saveFbUrls(Map<String, String> params, int count) {
        int saved = 0;
        for (int i = 0; i < count; i++) {
            FbQueueItem item = FbQueueItem.mock(params);
            if (item == null) {
                continue;
            }
            FB_QUEUE.add(item);
            saved++;
        }
        if (saved > 0) {
            try {
                persistFbQueue();
            } catch (IOException e) {
                log("Failed to persist FB queue: " + e.getMessage());
            }
        }
        return saved;
    }

    private static int updateFbStatus(String idsParam, String status) {
        List<Integer> ids = parseIds(idsParam);
        int updated = 0;
        for (FbQueueItem item : FB_QUEUE) {
            if (ids.contains(item.id)) {
                item.status = status;
                updated++;
            }
        }
        if (updated > 0) {
            try {
                persistFbQueue();
            } catch (IOException e) {
                log("Failed to persist FB queue: " + e.getMessage());
            }
        }
        return updated;
    }

    private static int updateStatus(String idsParam, String status) {
        List<Integer> ids = parseIds(idsParam);
        int updated = 0;
        for (Lead lead : LEADS) {
            if (ids.contains(lead.id)) {
                lead.status = status;
                updated++;
            }
        }
        if (updated > 0) {
            try {
                persistLeads();
            } catch (IOException e) {
                log("Failed to persist leads: " + e.getMessage());
            }
        }
        return updated;
    }

    private static int deleteLeads(String idsParam) {
        List<Integer> ids = parseIds(idsParam);
        int before = LEADS.size();
        LEADS.removeIf(lead -> ids.contains(lead.id));
        int deleted = before - LEADS.size();
        if (deleted > 0) {
            try {
                persistLeads();
            } catch (IOException e) {
                log("Failed to persist leads: " + e.getMessage());
            }
        }
        return deleted;
    }

    private static List<Integer> parseIds(String idsParam) {
        List<Integer> ids = new ArrayList<>();
        if (idsParam == null || idsParam.isEmpty()) {
            return ids;
        }
        for (String raw : idsParam.split(",")) {
            try {
                ids.add(Integer.parseInt(raw.trim()));
            } catch (NumberFormatException ignored) {
            }
        }
        return ids;
    }

    private static String exportCsv() {
        String filename = "leads_export_" + System.currentTimeMillis() + ".csv";
        Path target = dataDir.resolve(filename);
        try {
            Files.copy(leadsFile, target, StandardCopyOption.REPLACE_EXISTING);
        } catch (IOException e) {
            log("Export failed: " + e.getMessage());
        }
        return target.toString();
    }

    private static String exportCommunications() {
        String filename = "communications_export_" + System.currentTimeMillis() + ".csv";
        Path target = dataDir.resolve(filename);
        try {
            Files.copy(commsFile, target, StandardCopyOption.REPLACE_EXISTING);
        } catch (IOException e) {
            log("Export failed: " + e.getMessage());
        }
        return target.toString();
    }

    private static String exportClients() {
        String filename = "clients_export_" + System.currentTimeMillis() + ".csv";
        Path target = dataDir.resolve(filename);
        try {
            Files.copy(clientsFile, target, StandardCopyOption.REPLACE_EXISTING);
        } catch (IOException e) {
            log("Export failed: " + e.getMessage());
        }
        return target.toString();
    }

    private static String backupDatabase() {
        String filename = "leads_backup_" + System.currentTimeMillis() + ".csv";
        Path target = dataDir.resolve(filename);
        try {
            Files.copy(leadsFile, target, StandardCopyOption.REPLACE_EXISTING);
        } catch (IOException e) {
            log("Backup failed: " + e.getMessage());
        }
        return target.toString();
    }

    private static void clearDatabase() {
        LEADS.clear();
        NEXT_ID.set(1);
        try {
            persistLeads();
        } catch (IOException e) {
            log("Failed to clear DB: " + e.getMessage());
        }
    }

    private static void clearCommunications() {
        COMMUNICATIONS.clear();
        NEXT_COMM_ID.set(1);
        try {
            persistCommunications();
        } catch (IOException e) {
            log("Failed to clear communications: " + e.getMessage());
        }
    }

    private static void clearClients() {
        CLIENTS.clear();
        NEXT_CLIENT_ID.set(1);
        try {
            persistClients();
        } catch (IOException e) {
            log("Failed to clear clients: " + e.getMessage());
        }
    }

    private static void clearFbQueue() {
        FB_QUEUE.clear();
        NEXT_FB_ID.set(1);
        try {
            persistFbQueue();
        } catch (IOException e) {
            log("Failed to clear FB queue: " + e.getMessage());
        }
    }

    private static List<String> parseCsvLine(String line) {
        List<String> values = new ArrayList<>();
        StringBuilder current = new StringBuilder();
        boolean inQuotes = false;
        for (int i = 0; i < line.length(); i++) {
            char c = line.charAt(i);
            if (c == '"') {
                if (inQuotes && i + 1 < line.length() && line.charAt(i + 1) == '"') {
                    current.append('"');
                    i++;
                } else {
                    inQuotes = !inQuotes;
                }
            } else if (c == ',' && !inQuotes) {
                values.add(current.toString());
                current.setLength(0);
            } else {
                current.append(c);
            }
        }
        values.add(current.toString());
        return values;
    }

    private static String csvEscape(String value) {
        if (value == null) {
            return "";
        }
        if (value.contains(",") || value.contains("\"") || value.contains("\n") || value.contains("\r")) {
            return "\"" + value.replace("\"", "\"\"") + "\"";
        }
        return value;
    }

    private static boolean parseBool(String value) {
        if (value == null) {
            return false;
        }
        String lowered = value.trim().toLowerCase();
        return lowered.equals("true") || lowered.equals("1") || lowered.equals("yes");
    }

    private static String paramOrDefault(Map<String, String> params, String key, String fallback) {
        String value = params.get(key);
        if (value == null || value.isEmpty()) {
            return fallback;
        }
        return value;
    }

    private static String jsonEscape(String value) {
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '\\':
                    out.append("\\\\");
                    break;
                case '"':
                    out.append("\\\"");
                    break;
                case '\n':
                    out.append("\\n");
                    break;
                case '\r':
                    out.append("\\r");
                    break;
                case '\t':
                    out.append("\\t");
                    break;
                default:
                    out.append(c);
            }
        }
        return out.toString();
    }

    private static class Lead {
        private final int id;
        private final String url;
        private final String title;
        private final String description;
        private final String price;
        private final String location;
        private final String contactEmail;
        private final String contactPhone;
        private final String scanTime;
        private String status;

        private Lead(int id, String url, String title, String description, String price, String location,
                     String contactEmail, String contactPhone, String scanTime, String status) {
            this.id = id;
            this.url = url;
            this.title = title;
            this.description = description;
            this.price = price;
            this.location = location;
            this.contactEmail = contactEmail;
            this.contactPhone = contactPhone;
            this.scanTime = scanTime;
            this.status = status;
        }

        private static Lead mock(Map<String, String> params) {
            String city = params.getOrDefault("city", "Miami");
            String priceHint = params.getOrDefault("max_price", "500000");
            String title = "FSBO " + city + " - " + priceHint;
            String url = "https://example.com/listing/" + UUID.randomUUID();
            String description = "Owner selling. Motivated seller. Call today.";
            String email = "owner" + (int) (Math.random() * 900 + 100) + "@example.com";
            String phone = "+1-305-" + (int) (Math.random() * 900 + 100) + "-" + (int) (Math.random() * 9000 + 1000);
            String scanTime = DateTimeFormatter.ISO_INSTANT.format(Instant.now());
            return new Lead(NEXT_ID.getAndIncrement(), url, title, description, "$" + priceHint, city,
                    email, phone, scanTime, "new");
        }

        private boolean matches(String query) {
            String haystack = (title + " " + description + " " + price + " " + location + " " + contactEmail + " " + contactPhone).toLowerCase();
            return haystack.contains(query);
        }

        private String toCsv() {
            return csvEscape(String.valueOf(id)) + ","
                    + csvEscape(url) + ","
                    + csvEscape(title) + ","
                    + csvEscape(description) + ","
                    + csvEscape(price) + ","
                    + csvEscape(location) + ","
                    + csvEscape(contactEmail) + ","
                    + csvEscape(contactPhone) + ","
                    + csvEscape(scanTime) + ","
                    + csvEscape(status);
        }

        private String toJson() {
            return "{"
                    + "\"id\":" + id + ","
                    + "\"url\":\"" + jsonEscape(url) + "\","
                    + "\"title\":\"" + jsonEscape(title) + "\","
                    + "\"description\":\"" + jsonEscape(description) + "\","
                    + "\"price\":\"" + jsonEscape(price) + "\","
                    + "\"location\":\"" + jsonEscape(location) + "\","
                    + "\"contactEmail\":\"" + jsonEscape(contactEmail) + "\","
                    + "\"contactPhone\":\"" + jsonEscape(contactPhone) + "\","
                    + "\"scanTime\":\"" + jsonEscape(scanTime) + "\","
                    + "\"status\":\"" + jsonEscape(status) + "\""
                    + "}";
        }
    }

    private static class Communication {
        private final int id;
        private final String contactName;
        private final String contactEmail;
        private final String contactPhone;
        private final String channel;
        private final String lastMessage;
        private String status;
        private String lastContactedAt;
        private final String notes;
        private final String clientId;

        private Communication(int id, String contactName, String contactEmail, String contactPhone, String channel,
                              String lastMessage, String status, String lastContactedAt, String notes, String clientId) {
            this.id = id;
            this.contactName = contactName;
            this.contactEmail = contactEmail;
            this.contactPhone = contactPhone;
            this.channel = channel;
            this.lastMessage = lastMessage;
            this.status = status;
            this.lastContactedAt = lastContactedAt;
            this.notes = notes;
            this.clientId = clientId;
        }

        private static Communication fromParams(Map<String, String> params) {
            String name = params.getOrDefault("contact_name", "");
            String email = params.getOrDefault("contact_email", "");
            String phone = params.getOrDefault("contact_phone", "");
            if (email.isEmpty() && phone.isEmpty()) {
                return null;
            }
            String channel = params.getOrDefault("channel", "email");
            String message = params.getOrDefault("last_message", "");
            String status = params.getOrDefault("status", "pending");
            String notes = params.getOrDefault("notes", "");
            String contactedAt = DateTimeFormatter.ISO_INSTANT.format(Instant.now());
            String clientId = params.getOrDefault("client_id", "");
            return new Communication(NEXT_COMM_ID.getAndIncrement(), name, email, phone, channel, message, status, contactedAt, notes, clientId);
        }

        private boolean matches(String query) {
            String haystack = (contactName + " " + contactEmail + " " + contactPhone + " " + channel + " " + lastMessage + " " + status + " " + notes).toLowerCase();
            return haystack.contains(query);
        }

        private String toCsv() {
            return csvEscape(String.valueOf(id)) + ","
                    + csvEscape(contactName) + ","
                    + csvEscape(contactEmail) + ","
                    + csvEscape(contactPhone) + ","
                    + csvEscape(channel) + ","
                    + csvEscape(lastMessage) + ","
                    + csvEscape(status) + ","
                    + csvEscape(lastContactedAt) + ","
                    + csvEscape(notes) + ","
                    + csvEscape(clientId);
        }

        private String toJson() {
            return "{"
                    + "\"id\":" + id + ","
                    + "\"contactName\":\"" + jsonEscape(contactName) + "\","
                    + "\"contactEmail\":\"" + jsonEscape(contactEmail) + "\","
                    + "\"contactPhone\":\"" + jsonEscape(contactPhone) + "\","
                    + "\"channel\":\"" + jsonEscape(channel) + "\","
                    + "\"lastMessage\":\"" + jsonEscape(lastMessage) + "\","
                    + "\"status\":\"" + jsonEscape(status) + "\","
                    + "\"lastContactedAt\":\"" + jsonEscape(lastContactedAt) + "\","
                    + "\"notes\":\"" + jsonEscape(notes) + "\","
                    + "\"clientId\":\"" + jsonEscape(clientId) + "\""
                    + "}";
        }
    }

    private static class Client {
        private final int id;
        private final String name;
        private final String email;
        private final String phone;
        private String status;
        private String stage;
        private final String source;
        private String lastContactedAt;
        private String notes;
        private String sourceType;
        private String outreachChannel;
        private boolean automationEnabled;
        private String viabilityScore;
        private String lastInteraction;

        private Client(int id, String name, String email, String phone, String status, String stage,
                       String source, String lastContactedAt, String notes, String sourceType,
                       String outreachChannel, boolean automationEnabled, String viabilityScore,
                       String lastInteraction) {
            this.id = id;
            this.name = name;
            this.email = email;
            this.phone = phone;
            this.status = status;
            this.stage = stage;
            this.source = source;
            this.lastContactedAt = lastContactedAt;
            this.notes = notes;
            this.sourceType = sourceType;
            this.outreachChannel = outreachChannel;
            this.automationEnabled = automationEnabled;
            this.viabilityScore = viabilityScore;
            this.lastInteraction = lastInteraction;
        }

        private static Client fromParams(Map<String, String> params) {
            String name = params.getOrDefault("client_name", "");
            String email = params.getOrDefault("client_email", "");
            String phone = params.getOrDefault("client_phone", "");
            if (email.isEmpty() && phone.isEmpty()) {
                return null;
            }
            String status = params.getOrDefault("client_status", "active");
            String stage = params.getOrDefault("client_stage", "new");
            String source = params.getOrDefault("client_source", "manual");
            String sourceType = params.getOrDefault("client_source_type", "");
            String outreachChannel = params.getOrDefault("client_outreach_channel", "");
            boolean automationEnabled = parseBool(params.getOrDefault("client_automation_enabled", "false"));
            String viabilityScore = params.getOrDefault("client_viability_score", "");
            String notes = params.getOrDefault("client_notes", "");
            String lastContactedAt = DateTimeFormatter.ISO_INSTANT.format(Instant.now());
            return new Client(
                    NEXT_CLIENT_ID.getAndIncrement(),
                    name,
                    email,
                    phone,
                    status,
                    stage,
                    source,
                    lastContactedAt,
                    notes,
                    sourceType,
                    outreachChannel,
                    automationEnabled,
                    viabilityScore,
                    lastContactedAt
            );
        }

        private boolean matches(String query) {
            String haystack = (name + " " + email + " " + phone + " " + status + " " + stage + " " + source + " "
                    + sourceType + " " + outreachChannel + " " + viabilityScore + " " + notes).toLowerCase();
            return haystack.contains(query);
        }

        private String toCsv() {
            return csvEscape(String.valueOf(id)) + ","
                    + csvEscape(name) + ","
                    + csvEscape(email) + ","
                    + csvEscape(phone) + ","
                    + csvEscape(status) + ","
                    + csvEscape(stage) + ","
                    + csvEscape(source) + ","
                    + csvEscape(lastContactedAt) + ","
                    + csvEscape(notes) + ","
                    + csvEscape(sourceType) + ","
                    + csvEscape(outreachChannel) + ","
                    + csvEscape(String.valueOf(automationEnabled)) + ","
                    + csvEscape(viabilityScore) + ","
                    + csvEscape(lastInteraction);
        }

        private String toJson() {
            return "{"
                    + "\"id\":" + id + ","
                    + "\"name\":\"" + jsonEscape(name) + "\","
                    + "\"email\":\"" + jsonEscape(email) + "\","
                    + "\"phone\":\"" + jsonEscape(phone) + "\","
                    + "\"status\":\"" + jsonEscape(status) + "\","
                    + "\"stage\":\"" + jsonEscape(stage) + "\","
                    + "\"source\":\"" + jsonEscape(source) + "\","
                    + "\"lastContactedAt\":\"" + jsonEscape(lastContactedAt) + "\","
                    + "\"notes\":\"" + jsonEscape(notes) + "\","
                    + "\"sourceType\":\"" + jsonEscape(sourceType) + "\","
                    + "\"outreachChannel\":\"" + jsonEscape(outreachChannel) + "\","
                    + "\"automationEnabled\":" + automationEnabled + ","
                    + "\"viabilityScore\":\"" + jsonEscape(viabilityScore) + "\","
                    + "\"lastInteraction\":\"" + jsonEscape(lastInteraction) + "\""
                    + "}";
        }
    }

    private static class FbQueueItem {
        private final int id;
        private final String url;
        private String status;
        private final String savedAt;

        private FbQueueItem(int id, String url, String status, String savedAt) {
            this.id = id;
            this.url = url;
            this.status = status;
            this.savedAt = savedAt;
        }

        private static FbQueueItem mock(Map<String, String> params) {
            String base = params.getOrDefault("fb_search_url", "https://www.facebook.com/marketplace/");
            String url = base + "item/" + UUID.randomUUID();
            String savedAt = DateTimeFormatter.ISO_INSTANT.format(Instant.now());
            return new FbQueueItem(NEXT_FB_ID.getAndIncrement(), url, "queued", savedAt);
        }

        private String toCsv() {
            return csvEscape(String.valueOf(id)) + ","
                    + csvEscape(url) + ","
                    + csvEscape(status) + ","
                    + csvEscape(savedAt);
        }

        private String toJson() {
            return "{"
                    + "\"id\":" + id + ","
                    + "\"url\":\"" + jsonEscape(url) + "\","
                    + "\"status\":\"" + jsonEscape(status) + "\","
                    + "\"savedAt\":\"" + jsonEscape(savedAt) + "\""
                    + "}";
        }
    }
}
