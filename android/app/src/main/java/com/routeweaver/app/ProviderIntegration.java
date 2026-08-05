package com.routeweaver.app;

import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class ProviderIntegration {
    public static final String ACTION_APPLY_SPLIT_RULES = "com.routeweaver.APPLY_SPLIT_RULES";
    public static final String EXTRA_SCHEMA_VERSION = "schema_version";
    public static final String EXTRA_MODE = "mode";
    public static final String EXTRA_APP_PACKAGES = "app_packages";
    public static final String EXTRA_DOMAINS = "domains";

    public static final class Provider {
        public final String label;
        public final String packageName;
        public final boolean supportsBridge;

        Provider(String label, String packageName, boolean supportsBridge) {
            this.label = label;
            this.packageName = packageName;
            this.supportsBridge = supportsBridge;
        }

        @Override public String toString() {
            return label + (supportsBridge ? "（支持直接交接）" : "（需在 VPN 内配置）") + "\n" + packageName;
        }
    }

    private ProviderIntegration() {}

    public static List<Provider> discover(Context context) {
        PackageManager pm = context.getPackageManager();
        Intent vpnIntent = new Intent("android.net.VpnService");
        List<ResolveInfo> services = pm.queryIntentServices(vpnIntent, PackageManager.GET_META_DATA);
        Map<String, Provider> unique = new LinkedHashMap<>();
        for (ResolveInfo info : services) {
            if (info.serviceInfo == null) continue;
            String packageName = info.serviceInfo.packageName;
            String label;
            try {
                label = pm.getApplicationLabel(pm.getApplicationInfo(packageName, 0)).toString();
            } catch (PackageManager.NameNotFoundException e) {
                label = packageName;
            }
            boolean bridge = !pm.queryBroadcastReceivers(
                    new Intent(ACTION_APPLY_SPLIT_RULES).setPackage(packageName), 0
            ).isEmpty();
            unique.put(packageName, new Provider(label, packageName, bridge));
        }
        List<Provider> result = new ArrayList<>(unique.values());
        result.sort(Comparator.comparing(provider -> provider.label, String.CASE_INSENSITIVE_ORDER));
        return result;
    }

    public static boolean handOff(
            Context context,
            Provider provider,
            RoutePolicy.Mode mode,
            Set<String> apps,
            Set<String> domains
    ) {
        if (provider == null || !provider.supportsBridge) return false;
        Intent intent = new Intent(ACTION_APPLY_SPLIT_RULES).setPackage(provider.packageName);
        intent.putExtra(EXTRA_SCHEMA_VERSION, 1);
        intent.putExtra(EXTRA_MODE, mode == RoutePolicy.Mode.FORWARD ? "forward" : "reverse");
        intent.putStringArrayListExtra(EXTRA_APP_PACKAGES, new ArrayList<>(apps));
        intent.putStringArrayListExtra(EXTRA_DOMAINS, new ArrayList<>(domains));
        context.sendBroadcast(intent);
        return true;
    }

    public static boolean launch(Context context, Provider provider) {
        if (provider == null) return false;
        Intent launch = context.getPackageManager().getLaunchIntentForPackage(provider.packageName);
        if (launch == null) return false;
        launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        context.startActivity(launch);
        return true;
    }

    public static String ruleSummary(RoutePolicy.Mode mode, Set<String> apps, Set<String> domains) {
        StringBuilder text = new StringBuilder();
        text.append(mode == RoutePolicy.Mode.FORWARD ? "正向映射（以下项目走 VPN）" : "反向隔离（以下项目直连）");
        text.append("\n\n应用包名：\n");
        if (apps.isEmpty()) text.append("（无）\n");
        else apps.stream().sorted().forEach(value -> text.append(value).append('\n'));
        text.append("\n网站域名：\n");
        if (domains.isEmpty()) text.append("（无）\n");
        else domains.stream().sorted().forEach(value -> text.append(value).append('\n'));
        return text.toString();
    }
}

