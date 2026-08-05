package com.routeweaver.app;

import java.net.IDN;
import java.util.Locale;
import java.util.Set;

public final class RoutePolicy {
    public enum Mode { FORWARD, REVERSE }
    public enum Target { VPN, DIRECT }

    private RoutePolicy() {}

    public static Target decide(Mode mode, String packageName, String host, Set<String> apps, Set<String> domains) {
        boolean matched = apps.contains(packageName) || matchesDomain(host, domains);
        if (mode == Mode.FORWARD) {
            return matched ? Target.VPN : Target.DIRECT;
        }
        return matched ? Target.DIRECT : Target.VPN;
    }

    public static boolean matchesDomain(String rawHost, Set<String> rules) {
        if (rawHost == null) return false;
        String host = normalizeHost(rawHost);
        for (String rawRule : rules) {
            String rule = normalizeHost(rawRule);
            if (rule.startsWith("*.")) rule = rule.substring(2);
            if (host.equals(rule) || host.endsWith("." + rule)) return true;
        }
        return false;
    }

    public static String normalizeHost(String raw) {
        String value = raw.trim().toLowerCase(Locale.ROOT);
        int scheme = value.indexOf("://");
        if (scheme >= 0) value = value.substring(scheme + 3);
        int slash = value.indexOf('/');
        if (slash >= 0) value = value.substring(0, slash);
        int port = value.lastIndexOf(':');
        if (port > 0 && value.indexOf(':') == port) value = value.substring(0, port);
        while (value.endsWith(".")) value = value.substring(0, value.length() - 1);
        if (value.startsWith("*.")) return "*." + IDN.toASCII(value.substring(2));
        return IDN.toASCII(value);
    }
}

