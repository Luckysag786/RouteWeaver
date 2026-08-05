package com.routeweaver.app;

import android.net.Network;
import org.json.JSONObject;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;

public final class IpProbe {
    private static final String ENDPOINT = "https://ipwho.is/";
    private IpProbe() {}

    public static JSONObject lookup(Network network) throws Exception {
        URL url = new URL(ENDPOINT);
        HttpURLConnection connection = (HttpURLConnection) (network == null ? url.openConnection() : network.openConnection(url));
        connection.setConnectTimeout(10000);
        connection.setReadTimeout(12000);
        connection.setRequestProperty("User-Agent", "RouteWeaver-Android/1.0");
        connection.setRequestProperty("Accept", "application/json");
        int code = connection.getResponseCode();
        if (code != 200) throw new IllegalStateException("HTTP " + code);
        StringBuilder body = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(connection.getInputStream(), StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) body.append(line);
        } finally {
            connection.disconnect();
        }
        JSONObject data = new JSONObject(body.toString());
        if (!data.optBoolean("success", false) || data.optString("ip").isEmpty()) {
            throw new IllegalStateException(data.optString("message", "服务未返回 IP"));
        }
        data.put("source", ENDPOINT);
        data.put("checked_at", OffsetDateTime.now().toString());
        return data;
    }
}

