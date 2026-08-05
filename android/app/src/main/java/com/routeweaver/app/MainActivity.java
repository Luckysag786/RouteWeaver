package com.routeweaver.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.net.Uri;
import android.os.Bundle;
import android.provider.Settings;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.RadioButton;
import android.widget.RadioGroup;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {
    private static final int BLUE = Color.rgb(37, 99, 235);
    private static final int INK = Color.rgb(20, 33, 61);
    private static final int MUTED = Color.rgb(95, 107, 122);
    private static final int BG = Color.rgb(244, 247, 251);
    private static final int REQ_EXPORT = 201;
    private static final int REQ_IMPORT = 202;

    private final ExecutorService executor = Executors.newFixedThreadPool(2);
    private SharedPreferences prefs;
    private final Set<String> selectedApps = new HashSet<>();
    private final Set<String> selectedDomains = new HashSet<>();
    private RoutePolicy.Mode mode = RoutePolicy.Mode.FORWARD;
    private LinearLayout pageHost;
    private LinearLayout rulesList;
    private TextView vpnStatus;
    private TextView currentIp;
    private TextView physicalIp;
    private TextView providerStatus;
    private ProviderIntegration.Provider selectedProvider;

    private static final class AppChoice {
        final String label;
        final String packageName;
        AppChoice(String label, String packageName) { this.label = label; this.packageName = packageName; }
        @Override public String toString() { return label + "\n" + packageName; }
    }

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = getSharedPreferences("routeweaver", MODE_PRIVATE);
        selectedApps.addAll(prefs.getStringSet("apps", Collections.emptySet()));
        selectedDomains.addAll(prefs.getStringSet("domains", Collections.emptySet()));
        mode = RoutePolicy.Mode.valueOf(prefs.getString("mode", RoutePolicy.Mode.FORWARD.name()));
        selectedProvider = findSavedProvider();
        buildShell();
        showOverview();
    }

    private void buildShell() {
        LinearLayout root = column();
        root.setBackgroundColor(BG);
        TextView header = text("路由织网\nAndroid 伴侣", 22, Color.WHITE, true);
        header.setPadding(dp(22), dp(18), dp(22), dp(18));
        header.setBackgroundColor(BLUE);
        root.addView(header, matchWrap());

        LinearLayout nav = row();
        nav.setPadding(dp(10), dp(8), dp(10), dp(8));
        nav.addView(navButton("概览", v -> showOverview()), weighted());
        nav.addView(navButton("规则", v -> showRules()), weighted());
        nav.addView(navButton("设置", v -> showSettings()), weighted());
        root.addView(nav, matchWrap());

        ScrollView scroll = new ScrollView(this);
        pageHost = column();
        pageHost.setPadding(dp(14), dp(4), dp(14), dp(24));
        scroll.addView(pageHost, matchWrap());
        root.addView(scroll, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        setContentView(root);
    }

    private void clearPage() { pageHost.removeAllViews(); }

    private void showOverview() {
        clearPage();
        LinearLayout statusCard = card("兼容性状态");
        vpnStatus = text("正在检测…", 15, INK, true);
        statusCard.addView(vpnStatus, matchWrap());
        TextView limit = text("Android 每个用户只能有一个活动 VpnService。本 APK 不会抢占或关闭你当前的第三方 VPN；规则必须由当前 VPN 提供商原生支持后才能真正应用。", 14, MUTED, false);
        limit.setPadding(0, dp(10), 0, 0);
        statusCard.addView(limit, matchWrap());
        pageHost.addView(statusCard, cardParams());

        LinearLayout providerCard = card("第三方 VPN 交接");
        providerStatus = text(providerStatusText(), 14, INK, true);
        providerCard.addView(providerStatus, matchWrap());
        providerCard.addView(text("支持桥接接口的 VPN 可直接接收规则；其他 VPN 会打开其应用并提供可复制的包名/域名清单。", 13, MUTED, false), matchWrapMargins(0, 8, 0, 0));
        providerCard.addView(primaryButton("选择 VPN 提供商", v -> chooseProvider()), matchWrapMargins(0, 12, 0, 0));
        providerCard.addView(primaryButton("交接规则 / 打开 VPN", v -> applyOrOpenProvider()), matchWrapMargins(0, 8, 0, 0));
        pageHost.addView(providerCard, cardParams());

        LinearLayout modeCard = card("已保存规则");
        modeCard.addView(text(mode == RoutePolicy.Mode.FORWARD ? "正向映射：命中才走 VPN" : "反向隔离：命中则直连", 16, INK, true), matchWrap());
        modeCard.addView(text(selectedApps.size() + " 个应用，" + selectedDomains.size() + " 个网站", 14, MUTED, false), matchWrap());
        Button apply = primaryButton("检查并打开 VPN 设置", v -> openVpnSettingsWithExplanation());
        modeCard.addView(apply, matchWrapMargins(0, 12, 0, 0));
        pageHost.addView(modeCard, cardParams());

        LinearLayout ipCard = card("真实出口验证");
        currentIp = text("当前默认出口：尚未检测", 14, INK, true);
        physicalIp = text("物理网络绑定出口：尚未检测", 14, INK, true);
        ipCard.addView(currentIp, matchWrap());
        ipCard.addView(physicalIp, matchWrapMargins(0, 10, 0, 0));
        ipCard.addView(primaryButton("刷新双出口", v -> refreshIp()), matchWrapMargins(0, 14, 0, 0));
        ipCard.addView(text("物理出口检测使用 Android Network.openConnection 绑定 Wi‑Fi/蜂窝网络；若当前 VPN 禁止 bypass，检测会如实失败。", 12, MUTED, false), matchWrapMargins(0, 10, 0, 0));
        pageHost.addView(ipCard, cardParams());
        updateVpnStatus();
    }

    private void showRules() {
        clearPage();
        LinearLayout modeCard = card("工作模式");
        RadioGroup group = new RadioGroup(this);
        RadioButton forward = new RadioButton(this);
        forward.setText("正向映射（所选应用/网站走 VPN）");
        RadioButton reverse = new RadioButton(this);
        reverse.setText("反向隔离（所选应用/网站直连）");
        group.addView(forward); group.addView(reverse);
        group.check(mode == RoutePolicy.Mode.FORWARD ? forward.getId() : reverse.getId());
        // Programmatically created RadioButtons may have NO_ID on older devices.
        forward.setId(View.generateViewId()); reverse.setId(View.generateViewId());
        group.check(mode == RoutePolicy.Mode.FORWARD ? forward.getId() : reverse.getId());
        group.setOnCheckedChangeListener((g, id) -> {
            mode = id == forward.getId() ? RoutePolicy.Mode.FORWARD : RoutePolicy.Mode.REVERSE;
            save();
        });
        modeCard.addView(group, matchWrap());
        pageHost.addView(modeCard, cardParams());

        LinearLayout buttons = row();
        buttons.addView(primaryButton("添加应用", v -> chooseApps()), weighted());
        Button addDomain = primaryButton("添加网站", v -> addDomain());
        LinearLayout.LayoutParams bp = weighted(); bp.setMargins(dp(8), 0, 0, 0);
        buttons.addView(addDomain, bp);
        pageHost.addView(buttons, matchWrapMargins(0, 4, 0, 8));

        rulesList = column();
        renderRuleRows();
        pageHost.addView(rulesList, matchWrap());
    }

    private void showSettings() {
        clearPage();
        LinearLayout permission = card("权限与系统能力");
        permission.addView(text("网络访问：已声明\n应用列表：已声明（侧载包可用）\n管理员/Root：未请求\n第三方 VPN 注入权限：Android 不提供", 14, INK, false), matchWrap());
        permission.addView(text("为了不破坏现有 VPN，本应用没有声明 VpnService，也不会申请成为系统 VPN。", 13, MUTED, false), matchWrapMargins(0, 10, 0, 0));
        pageHost.addView(permission, cardParams());

        LinearLayout files = card("配置管理");
        files.addView(primaryButton("导出 JSON 配置", v -> exportConfig()), matchWrap());
        files.addView(primaryButton("导入 JSON 配置", v -> importConfig()), matchWrapMargins(0, 8, 0, 0));
        files.addView(primaryButton("打开 Android VPN 设置", v -> startActivity(new Intent(Settings.ACTION_VPN_SETTINGS))), matchWrapMargins(0, 8, 0, 0));
        pageHost.addView(files, cardParams());

        LinearLayout provider = card("VPN 提供商集成");
        provider.addView(text(providerStatusText(), 14, INK, true), matchWrap());
        provider.addView(primaryButton("选择已安装 VPN", v -> chooseProvider()), matchWrapMargins(0, 10, 0, 0));
        provider.addView(primaryButton("复制规则清单", v -> copyRuleSummary()), matchWrapMargins(0, 8, 0, 0));
        pageHost.addView(provider, cardParams());

        LinearLayout note = card("可执行分流条件");
        note.addView(text("要让这些规则真正生效，当前 VPN 应用必须在建立自己的隧道前调用 addAllowedApplication（正向）或 addDisallowedApplication（反向）。独立普通 APK 无法替另一个 VPN 调用这两个接口。", 14, INK, false), matchWrap());
        pageHost.addView(note, cardParams());
    }

    private void updateVpnStatus() {
        boolean active = hasActiveVpn();
        vpnStatus.setText(active ? "● 已检测到活动 VPN（本应用未接管）" : "○ 当前未检测到活动 VPN");
        vpnStatus.setTextColor(active ? Color.rgb(15, 157, 115) : MUTED);
    }

    private boolean hasActiveVpn() {
        ConnectivityManager cm = (ConnectivityManager) getSystemService(CONNECTIVITY_SERVICE);
        for (Network network : cm.getAllNetworks()) {
            NetworkCapabilities caps = cm.getNetworkCapabilities(network);
            if (caps != null && caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN)) return true;
        }
        return false;
    }

    private void refreshIp() {
        currentIp.setText("当前默认出口：检测中…");
        physicalIp.setText("物理网络绑定出口：检测中…");
        executor.submit(() -> {
            try {
                JSONObject data = IpProbe.lookup(null);
                runOnUiThread(() -> currentIp.setText("当前默认出口：\n" + formatIdentity(data)));
            } catch (Exception e) {
                runOnUiThread(() -> currentIp.setText("当前默认出口：失败\n" + e.getMessage()));
            }
        });
        executor.submit(() -> {
            Network physical = findPhysicalNetwork();
            if (physical == null) {
                runOnUiThread(() -> physicalIp.setText("物理网络绑定出口：未找到可用 Wi‑Fi/蜂窝网络"));
                return;
            }
            try {
                JSONObject data = IpProbe.lookup(physical);
                runOnUiThread(() -> physicalIp.setText("物理网络绑定出口：\n" + formatIdentity(data)));
            } catch (Exception e) {
                runOnUiThread(() -> physicalIp.setText("物理网络绑定出口：失败（VPN 可能禁止 bypass）\n" + e.getMessage()));
            }
        });
    }

    private Network findPhysicalNetwork() {
        ConnectivityManager cm = (ConnectivityManager) getSystemService(CONNECTIVITY_SERVICE);
        for (Network network : cm.getAllNetworks()) {
            NetworkCapabilities caps = cm.getNetworkCapabilities(network);
            if (caps == null || caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN)) continue;
            if (!caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)) continue;
            if (caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) || caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) || caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET)) return network;
        }
        return null;
    }

    private String formatIdentity(JSONObject data) {
        JSONObject connection = data.optJSONObject("connection");
        return data.optString("ip") + "\n" + data.optString("country") + " / " + data.optString("region") + " / " + data.optString("city") +
                "\n" + (connection == null ? "" : connection.optString("isp")) + "\n来源：" + data.optString("source") + "\n时间：" + data.optString("checked_at");
    }

    private void openVpnSettingsWithExplanation() {
        new AlertDialog.Builder(this).setTitle("需要当前 VPN 提供商支持")
                .setMessage("Android 不允许本应用修改另一个 VPN 已建立的 allowed/disallowed 应用列表。接下来打开系统 VPN 设置；请在当前 VPN 应用内寻找“分应用代理/绕过应用/路由模式”，并按本应用保存的规则配置。")
                .setNegativeButton("取消", null)
                .setPositiveButton("打开设置", (d, w) -> startActivity(new Intent(Settings.ACTION_VPN_SETTINGS))).show();
    }

    private ProviderIntegration.Provider findSavedProvider() {
        String saved = prefs.getString("provider_package", "");
        if (saved.isEmpty()) return null;
        for (ProviderIntegration.Provider provider : ProviderIntegration.discover(this)) {
            if (provider.packageName.equals(saved)) return provider;
        }
        return null;
    }

    private String providerStatusText() {
        List<ProviderIntegration.Provider> providers = ProviderIntegration.discover(this);
        if (selectedProvider == null) return "已发现 " + providers.size() + " 个 VPN 应用；尚未选择";
        return "已选择：" + selectedProvider.label + "\n" + selectedProvider.packageName +
                (selectedProvider.supportsBridge ? "\n支持 RouteWeaver 直接交接" : "\n需要在提供商应用内粘贴/配置规则");
    }

    private void chooseProvider() {
        List<ProviderIntegration.Provider> providers = ProviderIntegration.discover(this);
        if (providers.isEmpty()) {
            new AlertDialog.Builder(this).setTitle("未发现 VPN 应用")
                    .setMessage("系统中没有可见的 VpnService。请先安装并登录第三方 VPN。")
                    .setPositiveButton("打开 VPN 设置", (d, w) -> startActivity(new Intent(Settings.ACTION_VPN_SETTINGS)))
                    .setNegativeButton("取消", null).show();
            return;
        }
        String[] labels = providers.stream().map(ProviderIntegration.Provider::toString).toArray(String[]::new);
        new AlertDialog.Builder(this).setTitle("选择当前使用的 VPN")
                .setItems(labels, (dialog, which) -> {
                    selectedProvider = providers.get(which);
                    prefs.edit().putString("provider_package", selectedProvider.packageName).apply();
                    if (providerStatus != null) providerStatus.setText(providerStatusText());
                    toast("已选择 " + selectedProvider.label);
                }).show();
    }

    private void applyOrOpenProvider() {
        if (selectedProvider == null) {
            chooseProvider();
            return;
        }
        if (ProviderIntegration.handOff(this, selectedProvider, mode, selectedApps, selectedDomains)) {
            toast("规则已发送给 " + selectedProvider.label + "，请在 VPN 应用内确认状态");
            return;
        }
        copyRuleSummary();
        if (!ProviderIntegration.launch(this, selectedProvider)) {
            startActivity(new Intent(Settings.ACTION_VPN_SETTINGS));
        }
        new AlertDialog.Builder(this).setTitle("已复制规则清单")
                .setMessage("该 VPN 未声明 RouteWeaver 直接交接接口。已复制应用包名和域名，请在其“分应用代理/绕过应用/路由模式”中配置。")
                .setPositiveButton("知道了", null).show();
    }

    private void copyRuleSummary() {
        String summary = ProviderIntegration.ruleSummary(mode, selectedApps, selectedDomains);
        ClipboardManager clipboard = (ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
        clipboard.setPrimaryClip(ClipData.newPlainText("RouteWeaver rules", summary));
        toast("规则清单已复制");
    }

    private void chooseApps() {
        executor.submit(() -> {
            PackageManager pm = getPackageManager();
            List<AppChoice> choices = new ArrayList<>();
            for (ApplicationInfo info : pm.getInstalledApplications(0)) {
                if (pm.getLaunchIntentForPackage(info.packageName) == null || info.packageName.equals(getPackageName())) continue;
                choices.add(new AppChoice(pm.getApplicationLabel(info).toString(), info.packageName));
            }
            choices.sort(Comparator.comparing(choice -> choice.label, String.CASE_INSENSITIVE_ORDER));
            String[] labels = choices.stream().map(AppChoice::toString).toArray(String[]::new);
            boolean[] checked = new boolean[choices.size()];
            for (int i = 0; i < choices.size(); i++) checked[i] = selectedApps.contains(choices.get(i).packageName);
            runOnUiThread(() -> new AlertDialog.Builder(this).setTitle("选择应用")
                    .setMultiChoiceItems(labels, checked, (d, which, yes) -> checked[which] = yes)
                    .setNegativeButton("取消", null)
                    .setPositiveButton("保存", (d, w) -> {
                        selectedApps.clear();
                        for (int i = 0; i < choices.size(); i++) if (checked[i]) selectedApps.add(choices.get(i).packageName);
                        save(); renderRuleRows();
                    }).show());
        });
    }

    private void addDomain() {
        EditText input = new EditText(this);
        input.setHint("例如 google.com 或 *.google.com");
        input.setSingleLine(true);
        new AlertDialog.Builder(this).setTitle("添加网站").setView(input)
                .setNegativeButton("取消", null)
                .setPositiveButton("添加", (d, w) -> {
                    try {
                        String domain = RoutePolicy.normalizeHost(input.getText().toString());
                        if (!domain.isEmpty()) selectedDomains.add(domain);
                        save(); renderRuleRows();
                    } catch (Exception e) { toast("域名无效：" + e.getMessage()); }
                }).show();
    }

    private void renderRuleRows() {
        if (rulesList == null) return;
        rulesList.removeAllViews();
        List<String> apps = new ArrayList<>(selectedApps); Collections.sort(apps);
        List<String> domains = new ArrayList<>(selectedDomains); Collections.sort(domains);
        for (String app : apps) rulesList.addView(ruleRow("应用", app, () -> { selectedApps.remove(app); save(); renderRuleRows(); }), cardParams());
        for (String domain : domains) rulesList.addView(ruleRow("网站", domain, () -> { selectedDomains.remove(domain); save(); renderRuleRows(); }), cardParams());
        if (apps.isEmpty() && domains.isEmpty()) rulesList.addView(text("尚未添加规则。", 14, MUTED, false), matchWrapMargins(8, 18, 8, 0));
    }

    private LinearLayout ruleRow(String kind, String value, Runnable remove) {
        LinearLayout row = card(kind);
        TextView label = text(value, 14, INK, false);
        row.addView(label, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        Button verify = new Button(this); verify.setText("验证"); verify.setOnClickListener(v -> verifyRule(kind, value));
        row.addView(verify, wrapWrap());
        Button button = new Button(this); button.setText("删除"); button.setOnClickListener(v -> remove.run());
        row.addView(button, wrapWrap());
        return row;
    }

    private void verifyRule(String kind, String value) {
        String probeHost = value.startsWith("*.") ? "routeweaver-probe." + value.substring(2) : value;
        RoutePolicy.Target target = kind.equals("应用")
                ? RoutePolicy.decide(mode, value, "ipwho.is", selectedApps, selectedDomains)
                : RoutePolicy.decide(mode, "com.routeweaver.probe", probeHost, selectedApps, selectedDomains);
        boolean providerCanApply = selectedProvider != null && selectedProvider.supportsBridge;

        if (target == RoutePolicy.Target.VPN && !hasActiveVpn()) {
            new AlertDialog.Builder(this).setTitle("无法验证 VPN 出口")
                    .setMessage("此规则预期走 VPN，但系统当前未检测到活动 VPN。请先连接 VPN 后重试。")
                    .setPositiveButton("知道了", null).show();
            return;
        }

        Network network = target == RoutePolicy.Target.DIRECT ? findPhysicalNetwork() : null;
        if (target == RoutePolicy.Target.DIRECT && network == null) {
            new AlertDialog.Builder(this).setTitle("无法验证直连出口")
                    .setMessage("未找到可绑定的 Wi-Fi、蜂窝或以太网物理网络。当前 VPN 也可能禁止 bypass。")
                    .setPositiveButton("知道了", null).show();
            return;
        }

        toast("正在检测该规则的" + (target == RoutePolicy.Target.VPN ? "VPN" : "直连") + "出口…");
        executor.submit(() -> {
            try {
                JSONObject identity = IpProbe.lookup(network);
                String caution = providerCanApply
                        ? "\n\n提供商已声明直接交接接口；此结果证明目标出口可达。仍请在 VPN 应用中确认规则已接收。"
                        : "\n\n注意：这是该规则的目标出口基线，不代表第三方 VPN 已应用此规则。当前提供商未声明直接交接接口，请在其分应用/绕过设置中确认。";
                String message = "规则：" + kind + " · " + value +
                        "\n模式：" + (mode == RoutePolicy.Mode.FORWARD ? "正向映射" : "反向隔离") +
                        "\n预期走向：" + (target == RoutePolicy.Target.VPN ? "VPN 默认出口" : "物理直连出口") +
                        "\n\n实测出口：\n" + formatIdentity(identity) + caution;
                runOnUiThread(() -> new AlertDialog.Builder(this).setTitle("规则出口验证")
                        .setMessage(message).setPositiveButton("完成", null).show());
            } catch (Exception e) {
                runOnUiThread(() -> new AlertDialog.Builder(this).setTitle("规则出口检测失败")
                        .setMessage("规则：" + kind + " · " + value + "\n" + e.getMessage() +
                                "\n\n检测失败不会修改或关闭当前 VPN。")
                        .setPositiveButton("知道了", null).show());
            }
        });
    }

    private void exportConfig() {
        Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT).setType("application/json").putExtra(Intent.EXTRA_TITLE, "routeweaver-rules.json");
        startActivityForResult(intent, REQ_EXPORT);
    }

    private void importConfig() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("application/json").addCategory(Intent.CATEGORY_OPENABLE);
        startActivityForResult(intent, REQ_IMPORT);
    }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (resultCode != RESULT_OK || data == null || data.getData() == null) return;
        Uri uri = data.getData();
        try {
            if (requestCode == REQ_EXPORT) {
                try (OutputStreamWriter writer = new OutputStreamWriter(getContentResolver().openOutputStream(uri), StandardCharsets.UTF_8)) { writer.write(configJson().toString(2)); }
                toast("配置已导出");
            } else if (requestCode == REQ_IMPORT) {
                StringBuilder json = new StringBuilder();
                try (BufferedReader reader = new BufferedReader(new InputStreamReader(getContentResolver().openInputStream(uri), StandardCharsets.UTF_8))) {
                    String line; while ((line = reader.readLine()) != null) json.append(line);
                }
                loadJson(new JSONObject(json.toString())); save(); toast("配置已导入"); showRules();
            }
        } catch (Exception e) { toast("配置操作失败：" + e.getMessage()); }
    }

    private JSONObject configJson() throws Exception {
        JSONObject data = new JSONObject(); data.put("schema", 1); data.put("mode", mode.name().toLowerCase());
        data.put("apps", new JSONArray(selectedApps)); data.put("domains", new JSONArray(selectedDomains)); return data;
    }

    private void loadJson(JSONObject data) {
        selectedApps.clear(); selectedDomains.clear();
        mode = "reverse".equalsIgnoreCase(data.optString("mode")) ? RoutePolicy.Mode.REVERSE : RoutePolicy.Mode.FORWARD;
        JSONArray apps = data.optJSONArray("apps"); JSONArray domains = data.optJSONArray("domains");
        if (apps != null) for (int i = 0; i < apps.length(); i++) selectedApps.add(apps.optString(i));
        if (domains != null) for (int i = 0; i < domains.length(); i++) selectedDomains.add(RoutePolicy.normalizeHost(domains.optString(i)));
    }

    private void save() {
        prefs.edit().putString("mode", mode.name()).putStringSet("apps", new HashSet<>(selectedApps)).putStringSet("domains", new HashSet<>(selectedDomains)).apply();
    }

    private LinearLayout card(String title) {
        LinearLayout card = column(); card.setPadding(dp(16), dp(14), dp(16), dp(14)); card.setBackgroundColor(Color.WHITE);
        TextView heading = text(title, 17, INK, true); heading.setPadding(0, 0, 0, dp(10)); card.addView(heading, matchWrap()); return card;
    }
    private LinearLayout column() { LinearLayout v = new LinearLayout(this); v.setOrientation(LinearLayout.VERTICAL); return v; }
    private LinearLayout row() { LinearLayout v = new LinearLayout(this); v.setOrientation(LinearLayout.HORIZONTAL); v.setGravity(Gravity.CENTER_VERTICAL); return v; }
    private TextView text(String value, int size, int color, boolean bold) { TextView v = new TextView(this); v.setText(value); v.setTextSize(size); v.setTextColor(color); if (bold) v.setTypeface(Typeface.DEFAULT, Typeface.BOLD); v.setLineSpacing(0, 1.15f); return v; }
    private Button primaryButton(String label, View.OnClickListener listener) { Button b = new Button(this); b.setText(label); b.setTextColor(Color.WHITE); b.setBackgroundColor(BLUE); b.setOnClickListener(listener); b.setAllCaps(false); return b; }
    private Button navButton(String label, View.OnClickListener listener) { Button b = new Button(this); b.setText(label); b.setTextColor(INK); b.setBackgroundColor(Color.TRANSPARENT); b.setOnClickListener(listener); b.setAllCaps(false); return b; }
    private LinearLayout.LayoutParams matchWrap() { return new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT); }
    private LinearLayout.LayoutParams wrapWrap() { return new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT); }
    private LinearLayout.LayoutParams weighted() { return new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1); }
    private LinearLayout.LayoutParams cardParams() { return matchWrapMargins(0, 5, 0, 7); }
    private LinearLayout.LayoutParams matchWrapMargins(int l, int t, int r, int b) { LinearLayout.LayoutParams p = matchWrap(); p.setMargins(dp(l), dp(t), dp(r), dp(b)); return p; }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private void toast(String value) { Toast.makeText(this, value, Toast.LENGTH_LONG).show(); }

    @Override protected void onDestroy() { executor.shutdownNow(); super.onDestroy(); }
}
