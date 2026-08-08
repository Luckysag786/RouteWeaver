from __future__ import annotations

import json
import queue
import threading
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Callable

from . import __version__
from .activity_rules import activity_candidate, matching_rule_index
from .config import ConfigStore
from .diagnostics import run_diagnostics
from .gateway import SplitProxyGateway
from .ip_geo import lookup_identity
from .models import ActivityRecord, AppConfig, IpIdentity, RouteMode, RouteTarget, Rule, RuleKind
from .platform.windows_catalog import InstalledApplication, RunningProcess, list_installed_applications, list_running_processes
from .platform.windows_proxy import SystemProxyManager, is_admin, relaunch_as_admin
from .platform.windows_startup import initialize_startup, set_startup, startup_enabled
from .platform.windows_single_instance import ensure_single_instance, release_single_instance
from .policy import normalize_app
from .rule_probe import RuleProbeResult, probe_rule
from .rule_values import normalize_rule_value, rule_value_key
from .tray import TrayController, TrayUnavailable
from .upstream import ProxyEndpoint, parse_proxy_setting


BG = "#f4f7fb"
CARD = "#ffffff"
INK = "#14213d"
MUTED = "#5f6b7a"
BLUE = "#2563eb"
GREEN = "#0f9d73"
RED = "#d14343"


def _split_proxy(value: str) -> tuple[str, str, int] | None:
    endpoint = parse_proxy_setting(value)
    return (endpoint.protocol, endpoint.host, endpoint.port) if endpoint else None


class AppPicker(tk.Toplevel):
    """Searchable process/installed-app selector populated off the UI thread."""

    def __init__(self, parent: tk.Misc, source: str, selected: Callable[[str, str], None]) -> None:
        super().__init__(parent)
        self.source = source
        self.selected_callback = selected
        self.items: list[RunningProcess | InstalledApplication] = []
        self.visible_items: list[RunningProcess | InstalledApplication] = []
        self.result_queue: queue.Queue[object] = queue.Queue()
        self.title("选择运行进程" if source == "process" else "选择已安装应用")
        self.geometry("900x560")
        self.minsize(720, 430)
        self.transient(parent)
        self.grab_set()

        heading = "任务管理器进程" if source == "process" else "Windows 已安装应用"
        help_text = (
            "读取当前正在运行的进程。选中后会按程序路径建立规则，路径不可读时按 EXE 名称匹配。"
            if source == "process"
            else "读取 Windows 卸载注册表和应用入口。只有能够定位主程序 EXE 的项目可直接加入规则。"
        )
        ttk.Label(self, text=heading, font=("Microsoft YaHei UI", 14, "bold")).pack(anchor="w", padx=18, pady=(16, 2))
        ttk.Label(self, text=help_text, foreground=MUTED, wraplength=850).pack(anchor="w", padx=18, pady=(0, 10))

        search_row = ttk.Frame(self, padding=(18, 0, 18, 8))
        search_row.pack(fill="x")
        ttk.Label(search_row, text="搜索：").pack(side="left")
        self.search_var = tk.StringVar()
        search = ttk.Entry(search_row, textvariable=self.search_var)
        search.pack(side="left", fill="x", expand=True)
        self.status = ttk.Label(search_row, text="正在读取…", foreground=MUTED)
        self.status.pack(side="right", padx=(12, 0))
        self.search_var.trace_add("write", lambda *_: self._render())

        table = ttk.Frame(self, padding=(18, 0, 18, 0))
        table.pack(fill="both", expand=True)
        if source == "process":
            columns = (("name", "进程名称", 190), ("pid", "PID", 80), ("path", "程序路径", 520))
        else:
            columns = (("name", "应用名称", 250), ("publisher", "发布者", 170), ("path", "主程序路径", 400), ("source", "来源", 120))
        self.tree = ttk.Treeview(table, columns=tuple(item[0] for item in columns), show="headings", selectmode="browse")
        for key, title, width in columns:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, anchor="w")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda _event: self._accept())

        buttons = ttk.Frame(self, padding=18)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="取消", command=self.destroy).pack(side="right")
        self.accept_button = ttk.Button(buttons, text="加入分流规则", style="Primary.TButton", command=self._accept, state="disabled")
        self.accept_button.pack(side="right", padx=8)
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self.accept_button.configure(state="normal"))
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        search.focus_set()
        self._load()

    def _load(self) -> None:
        loader = list_running_processes if self.source == "process" else list_installed_applications

        def worker() -> None:
            try:
                self.result_queue.put(loader())
            except Exception as exc:
                self.result_queue.put(exc)

        threading.Thread(target=worker, daemon=True).start()
        self.after(100, self._poll)

    def _poll(self) -> None:
        try:
            result = self.result_queue.get_nowait()
        except queue.Empty:
            if self.winfo_exists():
                self.after(100, self._poll)
            return
        if isinstance(result, Exception):
            self.status.configure(text="读取失败")
            messagebox.showerror("读取失败", str(result), parent=self)
            return
        self.items = list(result)  # type: ignore[arg-type]
        self.status.configure(text=f"共 {len(self.items)} 项")
        self._render()

    def _render(self) -> None:
        if not hasattr(self, "tree"):
            return
        keyword = self.search_var.get().strip().casefold()
        self.visible_items = []
        self.tree.delete(*self.tree.get_children())
        for item in self.items:
            if isinstance(item, RunningProcess):
                haystack = f"{item.name} {item.pid} {item.executable}".casefold()
            else:
                haystack = f"{item.name} {item.publisher} {item.executable} {item.source}".casefold()
            if keyword and keyword not in haystack:
                continue
            index = len(self.visible_items)
            self.visible_items.append(item)
            if isinstance(item, RunningProcess):
                values = (item.name, item.pid, item.executable or "路径不可读（将按名称匹配）")
            else:
                values = (item.name, item.publisher, item.executable or "未定位到主程序", item.source)
            self.tree.insert("", "end", iid=str(index), values=values)

    def _accept(self) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        item = self.visible_items[int(selection[0])]
        if isinstance(item, RunningProcess):
            value, label = item.executable or item.name, item.name
        else:
            if not item.executable:
                messagebox.showwarning("无法直接添加", "该应用的安装信息没有提供主程序路径。请改用“选择 EXE 文件”或先运行应用后从进程列表选择。", parent=self)
                return
            value, label = item.executable, item.name
        self.selected_callback(value, label)
        self.destroy()


class RuleEditor(tk.Toplevel):
    def __init__(self, parent: tk.Misc, rule: Rule, save: Callable[[RuleKind, str, str, bool], None]) -> None:
        super().__init__(parent)
        self.save_callback = save
        self.title("修改分流规则")
        self.geometry("620x330")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        body = ttk.Frame(self, style="Card.TFrame", padding=22)
        body.pack(fill="both", expand=True, padx=16, pady=16)
        body.columnconfigure(1, weight=1)
        ttk.Label(body, text="修改分流规则", style="Heading.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(body, text="可修改规则类型、匹配值、备注和启用状态；保存后立即同步到分流网关。", style="Muted.TLabel").grid(row=1, column=0, columnspan=3, sticky="w", pady=(3, 14))

        self.kind_var = tk.StringVar(value=rule.kind.value)
        self.value_var = tk.StringVar(value=rule.value)
        self.label_var = tk.StringVar(value=rule.label)
        self.enabled_var = tk.BooleanVar(value=rule.enabled)
        ttk.Label(body, text="规则类型", style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=7)
        kind = ttk.Combobox(body, textvariable=self.kind_var, values=(RuleKind.APP.value, RuleKind.DOMAIN.value), state="readonly")
        kind.grid(row=2, column=1, sticky="ew", padx=12)
        kind.bind("<<ComboboxSelected>>", lambda _event: self._refresh_browse())
        ttk.Label(body, text="匹配值", style="Card.TLabel").grid(row=3, column=0, sticky="w", pady=7)
        self.value_entry = ttk.Entry(body, textvariable=self.value_var)
        self.value_entry.grid(row=3, column=1, sticky="ew", padx=12)
        self.browse_button = ttk.Button(body, text="选择 EXE", command=self._browse)
        self.browse_button.grid(row=3, column=2)
        ttk.Label(body, text="备注", style="Card.TLabel").grid(row=4, column=0, sticky="w", pady=7)
        ttk.Entry(body, textvariable=self.label_var).grid(row=4, column=1, sticky="ew", padx=12)
        ttk.Checkbutton(body, text="启用此规则", variable=self.enabled_var).grid(row=5, column=1, sticky="w", padx=12, pady=7)

        actions = ttk.Frame(body, style="Card.TFrame")
        actions.grid(row=6, column=0, columnspan=3, sticky="e", pady=(16, 0))
        ttk.Button(actions, text="取消", command=self.destroy).pack(side="right")
        ttk.Button(actions, text="保存修改", style="Primary.TButton", command=self._save).pack(side="right", padx=8)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._refresh_browse()
        self.value_entry.focus_set()
        self.value_entry.selection_range(0, "end")

    def _refresh_browse(self) -> None:
        self.browse_button.configure(state="normal" if self.kind_var.get() == RuleKind.APP.value else "disabled")

    def _browse(self) -> None:
        path = filedialog.askopenfilename(parent=self, title="选择 Windows 程序", filetypes=[("Windows 程序", "*.exe"), ("所有文件", "*.*")])
        if path:
            self.value_var.set(path)

    def _save(self) -> None:
        try:
            kind = RuleKind(self.kind_var.get())
            value = normalize_rule_value(kind, self.value_var.get())
            self.save_callback(kind, value, self.label_var.get().strip(), bool(self.enabled_var.get()))
        except ValueError as exc:
            messagebox.showerror("无法保存", str(exc), parent=self)
            return
        self.destroy()


class RouteWeaverApp(tk.Tk):
    def __init__(self, start_minimized: bool = False) -> None:
        super().__init__()
        self.title(f"路由织网 RouteWeaver {__version__}")
        self.geometry("1040x720")
        self.minsize(920, 640)
        self.configure(bg=BG)

        self.store = ConfigStore()
        self.config_model = self.store.load()
        initialize_startup(self.config_model)
        self.store.save(self.config_model)
        self.proxy_manager = SystemProxyManager()
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.gateway = SplitProxyGateway(self.config_model, self._queue_activity)
        self.active = False
        self._closing = False
        self._tray_notice_shown = False
        self.activity_records: dict[str, ActivityRecord] = {}
        self._activity_counter = 0
        self.tray = TrayController(
            lambda: self.events.put(("tray_show", None)),
            lambda: self.events.put(("tray_toggle", None)),
            lambda: self.events.put(("tray_exit", None)),
        )

        self._configure_styles()
        self._recover_stale_proxy()
        self._autodetect_upstream()
        self._build_ui()
        self._load_rules()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(150, self._drain_events)
        self.after(1000, self._refresh_runtime_status)
        if self.config_model.minimize_to_tray:
            self._ensure_tray()
        if start_minimized and self.config_model.minimize_to_tray:
            self.after(80, self._hide_to_tray)

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD)
        style.configure("TLabel", background=BG, foreground=INK, font=("Microsoft YaHei UI", 10))
        style.configure("Card.TLabel", background=CARD, foreground=INK, font=("Microsoft YaHei UI", 10))
        style.configure("Title.TLabel", background=BG, foreground=INK, font=("Microsoft YaHei UI", 19, "bold"))
        style.configure("PageTitle.TLabel", background=BG, foreground=INK, font=("Microsoft YaHei UI", 14, "bold"))
        style.configure("PageHelp.TLabel", background=BG, foreground=MUTED, font=("Microsoft YaHei UI", 9))
        style.configure("Heading.TLabel", background=CARD, foreground=INK, font=("Microsoft YaHei UI", 12, "bold"))
        style.configure("Muted.TLabel", background=CARD, foreground=MUTED, font=("Microsoft YaHei UI", 9))
        style.configure("Primary.TButton", background=BLUE, foreground="white", padding=(18, 9), font=("Microsoft YaHei UI", 10, "bold"))
        style.map("Primary.TButton", background=[("active", "#1d4ed8"), ("disabled", "#93a8d8")])
        style.configure("Danger.TButton", background=RED, foreground="white", padding=(18, 9))
        style.configure("Treeview", rowheight=28, font=("Microsoft YaHei UI", 9), fieldbackground=CARD)
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 9, "bold"))
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(18, 9), font=("Microsoft YaHei UI", 10))

    def _recover_stale_proxy(self) -> None:
        if self.proxy_manager.is_owned():
            restored = self.proxy_manager.restore()
            if restored:
                self.after(200, lambda: messagebox.showinfo("安全恢复", "检测到上次异常退出，已恢复启用分流前的 Windows 系统代理。"))

    def _autodetect_upstream(self) -> ProxyEndpoint | None:
        try:
            fallback = ProxyEndpoint(
                self.config_model.upstream_protocol,
                self.config_model.upstream_host,
                self.config_model.upstream_port,
            )
            detected = self.proxy_manager.detect_upstream(
                fallback=fallback,
                excluded=(self.config_model.listen_host, self.config_model.listen_port),
            )
            if detected:
                self.config_model.upstream_protocol = detected.protocol
                self.config_model.upstream_host = detected.host
                self.config_model.upstream_port = detected.port
                self.config_model.upstream_source = detected.source or "自动识别"
                self.config_model.upstream_detected_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
                self.store.save(self.config_model)
                self.gateway.update_config(self.config_model)
                if hasattr(self, "upstream_protocol_var"):
                    self.upstream_protocol_var.set(detected.protocol)
                    self.upstream_host_var.set(detected.host)
                    self.upstream_port_var.set(str(detected.port))
                    self.upstream_source_var.set(self._upstream_source_text())
                return detected
        except Exception:
            return None
        return None

    def _upstream_source_text(self) -> str:
        text = f"识别来源：{self.config_model.upstream_source or '手动设置'}"
        if self.config_model.upstream_detected_at:
            text += f"　更新时间：{self.config_model.upstream_detected_at}"
        return text

    def _build_ui(self) -> None:
        header = ttk.Frame(self, padding=(24, 18, 24, 8))
        header.pack(fill="x")
        ttk.Label(header, text="路由织网", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="  在现有第三方 VPN 或本地代理前精确分流", foreground=MUTED).pack(side="left", pady=(8, 0))
        self.status_label = ttk.Label(header, text="● 未启用", foreground=MUTED, font=("Microsoft YaHei UI", 10, "bold"))
        self.status_label.pack(side="right", pady=(8, 0))

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=24, pady=(4, 20))
        self.dashboard_tab = ttk.Frame(self.tabs, padding=14)
        self.rules_tab = ttk.Frame(self.tabs, padding=14)
        self.activity_tab = ttk.Frame(self.tabs, padding=14)
        self.settings_tab = ttk.Frame(self.tabs, padding=14)
        self.diagnostics_tab = ttk.Frame(self.tabs, padding=14)
        self.tabs.add(self.dashboard_tab, text="概览")
        self.tabs.add(self.rules_tab, text="分流规则")
        self.tabs.add(self.activity_tab, text="连接活动")
        self.tabs.add(self.settings_tab, text="设置与权限")
        self.tabs.add(self.diagnostics_tab, text="诊断")
        self._build_dashboard()
        self._build_rules()
        self._build_activity()
        self._build_settings()
        self._build_diagnostics()

    def _card(self, parent: tk.Misc, **grid: object) -> ttk.Frame:
        frame = ttk.Frame(parent, style="Card.TFrame", padding=18)
        frame.grid(**grid)
        return frame

    def _build_dashboard(self) -> None:
        tab = self.dashboard_tab
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=1)
        intro = ttk.Frame(tab)
        intro.grid(row=0, column=0, columnspan=2, sticky="ew", padx=4, pady=(0, 8))
        ttk.Label(intro, text="概览", style="PageTitle.TLabel").pack(anchor="w")
        ttk.Label(intro, text="在这里启用或停用分流，并核对直连与代理出口的真实公网 IP。", style="PageHelp.TLabel").pack(anchor="w", pady=(2, 0))
        action = self._card(tab, row=1, column=0, columnspan=2, sticky="ew", padx=4, pady=4)
        action.columnconfigure(1, weight=1)
        ttk.Label(action, text="分流状态", style="Heading.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(action, text="启用后，符合当前规则的连接会自动选择直连或代理出口。", style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(3, 0))
        self.mode_summary = ttk.Label(action, text="", style="Muted.TLabel")
        self.mode_summary.grid(row=2, column=0, sticky="w", pady=(5, 0))
        self.toggle_button = ttk.Button(action, text="启用分流", style="Primary.TButton", command=self._toggle)
        self.toggle_button.grid(row=0, column=2, rowspan=3, padx=(20, 0))

        direct = self._card(tab, row=2, column=0, sticky="nsew", padx=4, pady=8)
        vpn = self._card(tab, row=2, column=1, sticky="nsew", padx=4, pady=8)
        ttk.Label(direct, text="直连出口", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(direct, text="不经过第三方代理时，网站看到的公网地址。", style="Muted.TLabel").pack(anchor="w", pady=(2, 0))
        self.direct_ip = ttk.Label(direct, text="尚未检测", style="Card.TLabel", font=("Consolas", 13, "bold"))
        self.direct_ip.pack(anchor="w", pady=(12, 3))
        self.direct_geo = ttk.Label(direct, text="", style="Muted.TLabel", wraplength=390)
        self.direct_geo.pack(anchor="w")
        ttk.Label(vpn, text="VPN 上游出口", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(vpn, text="经过当前第三方 VPN 或本地代理时，网站看到的公网地址。", style="Muted.TLabel").pack(anchor="w", pady=(2, 0))
        self.vpn_ip = ttk.Label(vpn, text="尚未检测", style="Card.TLabel", font=("Consolas", 13, "bold"))
        self.vpn_ip.pack(anchor="w", pady=(12, 3))
        self.vpn_geo = ttk.Label(vpn, text="", style="Muted.TLabel", wraplength=390)
        self.vpn_geo.pack(anchor="w")

        info = self._card(tab, row=3, column=0, columnspan=2, sticky="ew", padx=4, pady=4)
        ttk.Label(info, text="检测结果来自远端 IP 情报服务的实时响应，不由本工具推算。", style="Muted.TLabel").pack(side="left")
        self.ip_button = ttk.Button(info, text="刷新双出口", command=self._refresh_ips)
        self.ip_button.pack(side="right")
        self._update_mode_summary()

    def _build_rules(self) -> None:
        ttk.Label(self.rules_tab, text="分流规则", style="PageTitle.TLabel").pack(anchor="w")
        ttk.Label(self.rules_tab, text="选择工作模式，并把需要特殊出口的程序或网站加入列表；规则可随时停用、删除或测试。", style="PageHelp.TLabel").pack(anchor="w", pady=(2, 8))
        top = ttk.Frame(self.rules_tab, style="Card.TFrame", padding=14)
        top.pack(fill="x", pady=(0, 10))
        ttk.Label(top, text="工作模式", style="Heading.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(top, text="正向模式只让列表项目走代理；反向模式让列表项目绕过代理并直连。", style="Muted.TLabel").grid(row=1, column=0, columnspan=3, sticky="w", pady=(3, 0))
        self.mode_var = tk.StringVar(value=self.config_model.mode.value)
        ttk.Radiobutton(top, text="正向映射（命中才走 VPN）", variable=self.mode_var, value="forward", command=self._mode_changed).grid(row=0, column=1, padx=(28, 12))
        ttk.Radiobutton(top, text="反向隔离（命中则直连）", variable=self.mode_var, value="reverse", command=self._mode_changed).grid(row=0, column=2, padx=12)

        source = ttk.Frame(self.rules_tab, style="Card.TFrame", padding=14)
        source.pack(fill="x", pady=(0, 10))
        ttk.Label(source, text="程序选择方式", style="Heading.TLabel").grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(source, text="找不到 EXE 时，可直接从正在运行的进程或 Windows 已安装应用列表中选择。", style="Muted.TLabel").grid(row=1, column=0, columnspan=4, sticky="w", pady=(3, 7))
        self.app_source_var = tk.StringVar(value="file")
        ttk.Radiobutton(source, text="① 选择 EXE 文件", variable=self.app_source_var, value="file").grid(row=2, column=0, sticky="w", padx=(0, 20))
        ttk.Radiobutton(source, text="② 当前运行进程", variable=self.app_source_var, value="process").grid(row=2, column=1, sticky="w", padx=20)
        ttk.Radiobutton(source, text="③ Windows 已安装应用", variable=self.app_source_var, value="installed").grid(row=2, column=2, sticky="w", padx=20)
        ttk.Button(source, text="选择并加入规则", style="Primary.TButton", command=self._add_app).grid(row=2, column=3, padx=(24, 0))

        table = ttk.Frame(self.rules_tab, style="Card.TFrame", padding=12)
        table.pack(fill="both", expand=True)
        self.rule_tree = ttk.Treeview(table, columns=("enabled", "kind", "value", "label"), show="headings", selectmode="extended")
        for key, title, width in (("enabled", "状态", 70), ("kind", "类型", 90), ("value", "匹配值", 500), ("label", "备注", 180)):
            self.rule_tree.heading(key, text=title)
            self.rule_tree.column(key, width=width, anchor="w" if key in ("value", "label") else "center")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.rule_tree.yview)
        self.rule_tree.configure(yscrollcommand=scroll.set)
        self.rule_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.rule_tree.bind("<Double-1>", lambda _event: self._edit_selected_rule())
        self.rule_tree.bind("<Delete>", lambda _event: self._remove_rules())
        buttons = ttk.Frame(self.rules_tab, padding=(0, 10, 0, 0))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="添加网站", command=self._add_domain).pack(side="left")
        ttk.Button(buttons, text="修改选中规则", command=self._edit_selected_rule).pack(side="left", padx=8)
        ttk.Button(buttons, text="删除选中规则", style="Danger.TButton", command=self._remove_rules).pack(side="left")
        ttk.Button(buttons, text="启用/停用", command=self._toggle_rule).pack(side="left", padx=8)
        self.rule_test_button = ttk.Button(buttons, text="测试选中规则", command=self._test_selected_rule)
        self.rule_test_button.pack(side="left", padx=8)
        ttk.Button(buttons, text="导出规则", command=self._export_rules).pack(side="right")
        ttk.Button(buttons, text="导入规则", command=self._import_rules).pack(side="right", padx=8)

    def _build_activity(self) -> None:
        ttk.Label(self.activity_tab, text="连接活动", style="PageTitle.TLabel").pack(anchor="w")
        ttk.Label(self.activity_tab, text="查看实际经过本地网关的连接；选中一行后可按应用或网站直接加入、取消当前模式的规则。", style="PageHelp.TLabel").pack(anchor="w", pady=(2, 8))
        wrapper = ttk.Frame(self.activity_tab, style="Card.TFrame", padding=12)
        wrapper.pack(fill="both", expand=True)
        self.activity_tree = ttk.Treeview(wrapper, columns=("time", "process", "host", "route", "rule", "status"), show="headings")
        for key, title, width in (("time", "时间", 145), ("process", "程序", 150), ("host", "目标", 260), ("route", "出口", 75), ("rule", "命中规则", 170), ("status", "结果", 120)):
            self.activity_tree.heading(key, text=title)
            self.activity_tree.column(key, width=width, anchor="w")
        self.activity_tree.pack(fill="both", expand=True)
        self.activity_tree.bind("<<TreeviewSelect>>", self._activity_selected)

        detail = ttk.Frame(self.activity_tab, style="Card.TFrame", padding=14)
        detail.pack(fill="x", pady=(10, 0))
        detail.columnconfigure(1, weight=1)
        ttk.Label(detail, text="所选连接", style="Heading.TLabel").grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(detail, text="先选择按应用还是按网站操作，右侧按钮会自动显示加入或取消。", style="Muted.TLabel").grid(row=1, column=0, columnspan=4, sticky="w", pady=(2, 7))
        self.activity_target_var = tk.StringVar(value="app")
        ttk.Radiobutton(detail, text="按应用", variable=self.activity_target_var, value="app", command=self._refresh_activity_detail).grid(row=2, column=0, sticky="w")
        ttk.Radiobutton(detail, text="按网站", variable=self.activity_target_var, value="domain", command=self._refresh_activity_detail).grid(row=3, column=0, sticky="w")
        self.activity_name_label = ttk.Label(detail, text="尚未选择连接", style="Card.TLabel", wraplength=620)
        self.activity_name_label.grid(row=2, column=1, rowspan=2, sticky="w", padx=18)
        self.activity_rule_status = ttk.Label(detail, text="规则状态：—", style="Muted.TLabel")
        self.activity_rule_status.grid(row=2, column=2, rowspan=2, sticky="w", padx=12)
        self.activity_rule_button = ttk.Button(detail, text="加入规则", style="Primary.TButton", command=self._toggle_activity_rule, state="disabled")
        self.activity_rule_button.grid(row=2, column=3, rowspan=2, padx=(16, 0))

    def _build_settings(self) -> None:
        ttk.Label(self.settings_tab, text="设置与权限", style="PageTitle.TLabel").pack(anchor="w")
        ttk.Label(self.settings_tab, text="配置第三方代理入口、开机启动、关闭行为和管理员权限；修改网络端口前请先停用分流。", style="PageHelp.TLabel").pack(anchor="w", pady=(2, 8))
        card = ttk.Frame(self.settings_tab, style="Card.TFrame", padding=20)
        card.pack(fill="x")
        card.columnconfigure(1, weight=1)
        ttk.Label(card, text="VPN 上游", style="Heading.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 14))
        ttk.Label(card, text="填写第三方 VPN 或本地代理提供的协议、地址和端口；通常可直接自动识别。", style="Muted.TLabel").grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 8))
        self.upstream_protocol_var = tk.StringVar(value=self.config_model.upstream_protocol)
        self.upstream_host_var = tk.StringVar(value=self.config_model.upstream_host)
        self.upstream_port_var = tk.StringVar(value=str(self.config_model.upstream_port))
        self.listen_port_var = tk.StringVar(value=str(self.config_model.listen_port))
        self.upstream_source_var = tk.StringVar(value=self._upstream_source_text())
        ttk.Label(card, text="上游协议", style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=6)
        ttk.Combobox(card, textvariable=self.upstream_protocol_var, values=("http", "socks5"), state="readonly").grid(row=2, column=1, sticky="ew", padx=12)
        ttk.Label(card, text="上游地址", style="Card.TLabel").grid(row=3, column=0, sticky="w", pady=6)
        ttk.Entry(card, textvariable=self.upstream_host_var).grid(row=3, column=1, sticky="ew", padx=12)
        ttk.Label(card, text="端口", style="Card.TLabel").grid(row=4, column=0, sticky="w", pady=6)
        ttk.Entry(card, textvariable=self.upstream_port_var).grid(row=4, column=1, sticky="ew", padx=12)
        ttk.Button(card, text="自动重新识别", command=self._detect_proxy_clicked).grid(row=2, column=2, rowspan=3)
        ttk.Label(card, text="本地网关端口", style="Card.TLabel").grid(row=5, column=0, sticky="w", pady=6)
        ttk.Entry(card, textvariable=self.listen_port_var).grid(row=5, column=1, sticky="ew", padx=12)
        ttk.Label(card, textvariable=self.upstream_source_var, style="Muted.TLabel").grid(row=6, column=0, columnspan=3, sticky="w", pady=(8, 2))
        ttk.Label(card, text="支持 HTTP CONNECT 与无认证 SOCKS5 上游；启动分流前会再次自动校准。", style="Muted.TLabel").grid(row=7, column=0, columnspan=3, sticky="w", pady=(2, 2))
        ttk.Button(card, text="保存网络设置", style="Primary.TButton", command=self._save_settings).grid(row=8, column=2, pady=(14, 0))

        behavior = ttk.Frame(self.settings_tab, style="Card.TFrame", padding=20)
        behavior.pack(fill="x", pady=12)
        ttk.Label(behavior, text="启动与关闭行为", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(behavior, text="默认随 Windows 启动；点击右上角 × 默认隐藏到托盘并继续工作。", style="Muted.TLabel").pack(anchor="w", pady=(2, 8))
        self.startup_var = tk.BooleanVar(value=self.config_model.start_with_windows)
        self.tray_close_var = tk.BooleanVar(value=self.config_model.minimize_to_tray)
        ttk.Checkbutton(behavior, text="开机自动启动", variable=self.startup_var).pack(side="left", padx=(0, 24))
        ttk.Radiobutton(behavior, text="关闭按钮：隐藏到系统托盘", variable=self.tray_close_var, value=True).pack(side="left", padx=12)
        ttk.Radiobutton(behavior, text="关闭按钮：完全退出软件", variable=self.tray_close_var, value=False).pack(side="left", padx=12)
        ttk.Button(behavior, text="保存行为设置", command=self._save_behavior_settings).pack(side="right")

        perm = ttk.Frame(self.settings_tab, style="Card.TFrame", padding=20)
        perm.pack(fill="x")
        ttk.Label(perm, text="权限与恢复", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(perm, text="通常不需要管理员权限；遇到受限系统配置时可手动提权，恢复按钮用于异常情况下还原原代理。", style="Muted.TLabel").pack(anchor="w", pady=(2, 0))
        self.admin_label = ttk.Label(perm, text="管理员：" + ("已授权" if is_admin() else "未授权（系统代理接管不强制需要）"), style="Card.TLabel")
        self.admin_label.pack(side="left", pady=(14, 0))
        ttk.Button(perm, text="以管理员身份重启", command=self._elevate).pack(side="right", pady=(12, 0))
        ttk.Button(perm, text="立即恢复原系统代理", command=self._force_restore).pack(side="right", padx=8, pady=(12, 0))

    def _build_diagnostics(self) -> None:
        ttk.Label(self.diagnostics_tab, text="诊断", style="PageTitle.TLabel").pack(anchor="w")
        ttk.Label(self.diagnostics_tab, text="检查端口、第三方代理、系统权限和公网出口，帮助判断分流为何没有生效。", style="PageHelp.TLabel").pack(anchor="w", pady=(2, 8))
        bar = ttk.Frame(self.diagnostics_tab)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Label(bar, text="运行环境与链路自检", font=("Microsoft YaHei UI", 12, "bold")).pack(side="left")
        ttk.Button(bar, text="运行全部诊断", style="Primary.TButton", command=self._run_diagnostics).pack(side="right")
        self.diag_tree = ttk.Treeview(self.diagnostics_tab, columns=("result", "name", "detail"), show="headings")
        for key, title, width in (("result", "结果", 80), ("name", "项目", 180), ("detail", "详情", 600)):
            self.diag_tree.heading(key, text=title)
            self.diag_tree.column(key, width=width, anchor="w")
        self.diag_tree.pack(fill="both", expand=True)

    def _mode_changed(self) -> None:
        self.config_model.mode = RouteMode(self.mode_var.get())
        self.gateway.update_config(self.config_model)
        self.store.save(self.config_model)
        self._update_mode_summary()
        if hasattr(self, "activity_rule_button"):
            self._refresh_activity_detail()

    def _update_mode_summary(self) -> None:
        if self.config_model.mode is RouteMode.FORWARD:
            text = f"正向映射：仅 {len([r for r in self.config_model.rules if r.enabled])} 条启用规则命中的流量走 VPN，其余直连"
        else:
            text = f"反向隔离：默认走 VPN，{len([r for r in self.config_model.rules if r.enabled])} 条启用规则命中的流量直连"
        if hasattr(self, "mode_summary"):
            self.mode_summary.configure(text=text)

    def _load_rules(self) -> None:
        for item in self.rule_tree.get_children():
            self.rule_tree.delete(item)
        for index, rule in enumerate(self.config_model.rules):
            kind = "应用" if rule.kind is RuleKind.APP else "网站"
            self.rule_tree.insert("", "end", iid=str(index), values=("启用" if rule.enabled else "停用", kind, rule.value, rule.label))
        self._update_mode_summary()

    def _add_app(self) -> None:
        source = self.app_source_var.get()
        if source == "file":
            path = filedialog.askopenfilename(title="选择要分流的程序", filetypes=[("Windows 程序", "*.exe"), ("所有文件", "*.*")])
            if path:
                self._append_rule(RuleKind.APP, str(Path(path)), Path(path).stem)
        elif source in ("process", "installed"):
            AppPicker(self, source, lambda value, label: self._append_rule(RuleKind.APP, value, label))

    def _append_rule(self, kind: RuleKind, value: str, label: str = "", notify: bool = True) -> bool:
        normalized = normalize_app(value) if kind is RuleKind.APP else value.strip().casefold().rstrip(".")
        for index, rule in enumerate(self.config_model.rules):
            current = normalize_app(rule.value) if kind is RuleKind.APP else rule.value.strip().casefold().rstrip(".")
            if rule.kind is kind and current == normalized:
                if not rule.enabled:
                    rule.enabled = True
                    self._rules_changed()
                self.rule_tree.selection_set(str(index))
                self.rule_tree.see(str(index))
                if notify:
                    messagebox.showinfo("规则已存在", "该项目已经在分流规则中，现已定位到对应规则。")
                return False
        self.config_model.rules.append(Rule(kind, value, True, label))
        self._rules_changed()
        iid = str(len(self.config_model.rules) - 1)
        self.rule_tree.selection_set(iid)
        self.rule_tree.see(iid)
        return True

    def _add_domain(self) -> None:
        domain = simpledialog.askstring("添加网站", "输入域名（例如 google.com 或 *.google.com）：", parent=self)
        if domain:
            domain = domain.strip()
            if "://" in domain:
                domain = domain.split("://", 1)[1].split("/", 1)[0]
            self.config_model.rules.append(Rule(RuleKind.DOMAIN, domain, True, ""))
            self._rules_changed()

    def _toggle_rule(self) -> None:
        selection = self.rule_tree.selection()
        if not selection:
            messagebox.showwarning("请选择规则", "请先在规则列表中选择需要启用或停用的项目。")
            return
        for item in selection:
            self.config_model.rules[int(item)].enabled = not self.config_model.rules[int(item)].enabled
        self._rules_changed()

    def _edit_selected_rule(self) -> None:
        selection = self.rule_tree.selection()
        if len(selection) != 1:
            messagebox.showwarning("请选择一条规则", "修改规则时一次只能选择一条。可双击列表中的规则直接修改。")
            return
        index = int(selection[0])
        rule = self.config_model.rules[index]

        def save(kind: RuleKind, value: str, label: str, enabled: bool) -> None:
            wanted = rule_value_key(kind, value)
            for other_index, other in enumerate(self.config_model.rules):
                if other_index != index and other.kind is kind and rule_value_key(other.kind, other.value) == wanted:
                    raise ValueError("修改后的规则与列表中已有规则重复")
            current = self.config_model.rules[index]
            current.kind = kind
            current.value = value
            current.label = label
            current.enabled = enabled
            self._rules_changed()
            self.rule_tree.selection_set(str(index))
            self.rule_tree.see(str(index))

        RuleEditor(self, rule, save)

    def _remove_rules(self) -> None:
        selected = sorted((int(item) for item in self.rule_tree.selection()), reverse=True)
        if not selected:
            messagebox.showwarning("请选择规则", "请先选择需要删除的规则。")
            return
        if not messagebox.askyesno("确认删除", f"确定删除选中的 {len(selected)} 条规则吗？\n删除后将立即停止使用这些匹配项。"):
            return
        for index in selected:
            del self.config_model.rules[index]
        self._rules_changed()

    def _rules_changed(self) -> None:
        self.store.save(self.config_model)
        self.gateway.update_config(self.config_model)
        self._load_rules()
        if hasattr(self, "activity_rule_button"):
            self._refresh_activity_detail()

    def _test_selected_rule(self) -> None:
        selected = self.rule_tree.selection()
        if len(selected) != 1:
            messagebox.showwarning("请选择一条规则", "逐条出口验证一次只能测试一条启用规则。")
            return
        if not self.active:
            messagebox.showwarning("请先启用分流", "请先单击概览页的“启用分流”，再测试规则出口。")
            return
        rule = self.config_model.rules[int(selected[0])]
        if not rule.enabled:
            messagebox.showwarning("规则已停用", "请先启用所选规则。")
            return
        self.rule_test_button.configure(state="disabled", text="测试中…")
        threading.Thread(target=self._rule_probe_worker, args=(rule,), daemon=True).start()

    def _rule_probe_worker(self, rule: Rule) -> None:
        try:
            result = probe_rule(self.config_model, rule)
            self.events.put(("rule_probe", result))
        except Exception as exc:
            self.events.put(("rule_probe_error", str(exc)))

    def _show_rule_probe(self, result: RuleProbeResult) -> None:
        self.rule_test_button.configure(state="normal", text="测试选中规则")
        identity = result.identity
        route = "VPN 上游" if result.decision.target is RouteTarget.VPN else "直连网络"
        kind = "应用" if result.rule.kind is RuleKind.APP else "网站"
        if identity.error:
            messagebox.showerror("规则出口验证失败", f"{kind}：{result.rule.value}\n计划出口：{route}\n\n{identity.error}")
            return
        context = result.process_context if result.rule.kind is RuleKind.APP else result.host_context
        messagebox.showinfo(
            "规则出口验证",
            f"{kind}规则：{result.rule.value}\n"
            f"匹配上下文：{context}\n"
            f"当前模式出口：{route}\n\n"
            f"真实公网 IP：{identity.ip}\n"
            f"地区：{identity.location}\n"
            f"运营商：{identity.isp or '未知'}\n"
            f"来源：{identity.source}\n"
            f"时间：{identity.checked_at}\n\n"
            "说明：这是按该规则选择的真实出口探测；应用自身是否经过网关，仍以“连接活动”中的进程记录为准。",
        )

    def _export_rules(self) -> None:
        path = filedialog.asksaveasfilename(title="导出规则", defaultextension=".json", filetypes=[("JSON", "*.json")])
        if path:
            Path(path).write_text(json.dumps(self.config_model.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def _import_rules(self) -> None:
        path = filedialog.askopenfilename(title="导入规则", filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            imported = AppConfig.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
            self.config_model.rules = imported.rules
            self._rules_changed()
        except Exception as exc:
            messagebox.showerror("导入失败", str(exc))

    def _save_settings(self, quiet: bool = False) -> bool:
        if self.active:
            if not quiet:
                messagebox.showwarning("请先停用", "修改监听或上游地址前请先停用分流。")
            return False
        try:
            upstream_port = int(self.upstream_port_var.get())
            listen_port = int(self.listen_port_var.get())
            if not (1 <= upstream_port <= 65535 and 1024 <= listen_port <= 65535):
                raise ValueError("端口范围无效")
            if upstream_port == listen_port and self.upstream_host_var.get().strip() in ("127.0.0.1", "localhost"):
                raise ValueError("本地网关端口不能与 VPN 上游端口相同，否则会形成环路")
            protocol = self.upstream_protocol_var.get().strip().lower()
            if protocol not in ("http", "socks5"):
                raise ValueError("上游协议必须是 http 或 socks5")
            host = self.upstream_host_var.get().strip()
            old_endpoint = (
                self.config_model.upstream_protocol,
                self.config_model.upstream_host,
                self.config_model.upstream_port,
            )
            self.config_model.upstream_protocol = protocol
            self.config_model.upstream_host = host
            self.config_model.upstream_port = upstream_port
            self.config_model.listen_port = listen_port
            if (protocol, host, upstream_port) != old_endpoint:
                self.config_model.upstream_source = "手动设置"
                self.config_model.upstream_detected_at = ""
                if hasattr(self, "upstream_source_var"):
                    self.upstream_source_var.set(self._upstream_source_text())
            self.store.save(self.config_model)
            self.gateway.update_config(self.config_model)
            if not quiet:
                messagebox.showinfo("已保存", "设置已保存。")
            return True
        except ValueError as exc:
            messagebox.showerror("设置无效", str(exc))
            return False

    def _save_behavior_settings(self) -> None:
        try:
            self.config_model.start_with_windows = bool(self.startup_var.get())
            self.config_model.startup_configured = True
            self.config_model.minimize_to_tray = bool(self.tray_close_var.get())
            set_startup(self.config_model.start_with_windows)
            if self.config_model.minimize_to_tray:
                self._ensure_tray()
            else:
                self.tray.stop()
            self.store.save(self.config_model)
            state = "已开启" if startup_enabled() else "已关闭"
            close = "隐藏到系统托盘" if self.config_model.minimize_to_tray else "完全退出软件"
            messagebox.showinfo("行为设置已保存", f"开机自动启动：{state}\n点击关闭按钮：{close}")
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))

    def _detect_proxy_clicked(self) -> None:
        before = (
            self.config_model.upstream_protocol,
            self.config_model.upstream_host,
            self.config_model.upstream_port,
        )
        detected = self._autodetect_upstream()
        after = (
            self.config_model.upstream_protocol,
            self.config_model.upstream_host,
            self.config_model.upstream_port,
        )
        if detected is None:
            messagebox.showerror("未识别", "未发现可用的 Windows、PAC、WinHTTP 或本地代理入口。")
            return
        changed = "，已更新" if after != before else "，设置未变化"
        messagebox.showinfo(
            "识别成功",
            f"VPN 上游：{after[0]}://{after[1]}:{after[2]}\n来源：{self.config_model.upstream_source}{changed}",
        )

    def _toggle(self) -> None:
        self._disable() if self.active else self._enable()

    def _enable(self) -> None:
        self._autodetect_upstream()
        if not self._save_settings(quiet=True):
            return
        try:
            self.gateway.start()
            self.proxy_manager.activate(self.config_model.listen_host, self.config_model.listen_port)
            self.active = True
            self.status_label.configure(text="● 已启用", foreground=GREEN)
            self.toggle_button.configure(text="停用并恢复", style="Danger.TButton")
        except Exception as exc:
            self.gateway.stop()
            try:
                self.proxy_manager.restore()
            except Exception:
                pass
            messagebox.showerror("启用失败", str(exc))

    def _disable(self) -> None:
        errors = []
        try:
            self.proxy_manager.restore()
        except Exception as exc:
            errors.append(f"恢复系统代理失败：{exc}")
        try:
            self.gateway.stop()
        except Exception as exc:
            errors.append(f"停止网关失败：{exc}")
        self.active = False
        self.status_label.configure(text="● 未启用", foreground=MUTED)
        self.toggle_button.configure(text="启用分流", style="Primary.TButton")
        if errors and not self._closing:
            messagebox.showerror("停用异常", "\n".join(errors))

    def _force_restore(self) -> None:
        restored = self.proxy_manager.restore()
        if self.active:
            self.gateway.stop()
            self.active = False
        messagebox.showinfo("恢复完成", "已恢复启用前的系统代理。" if restored else "没有发现待恢复的系统代理备份。")

    def _refresh_ips(self) -> None:
        self.ip_button.configure(state="disabled")
        self.direct_ip.configure(text="检测中…")
        self.vpn_ip.configure(text="检测中…")
        for target in (RouteTarget.DIRECT, RouteTarget.VPN):
            threading.Thread(target=self._lookup_worker, args=(target,), daemon=True).start()

    def _lookup_worker(self, target: RouteTarget) -> None:
        identity = lookup_identity(
            target,
            self.config_model.upstream_host,
            self.config_model.upstream_port,
            upstream_protocol=self.config_model.upstream_protocol,
        )
        self.events.put(("identity", identity))

    def _show_identity(self, identity: IpIdentity) -> None:
        ip_label = self.direct_ip if identity.route is RouteTarget.DIRECT else self.vpn_ip
        geo_label = self.direct_geo if identity.route is RouteTarget.DIRECT else self.vpn_geo
        if identity.error:
            ip_label.configure(text="检测失败", foreground=RED)
            geo_label.configure(text=identity.error)
        else:
            ip_label.configure(text=identity.ip, foreground=INK)
            geo_label.configure(text=f"{identity.location}\n{identity.isp}\n来源：{identity.source}\n时间：{identity.checked_at}")
        if self.direct_ip.cget("text") != "检测中…" and self.vpn_ip.cget("text") != "检测中…":
            self.ip_button.configure(state="normal")

    def _queue_activity(self, record: ActivityRecord) -> None:
        self.events.put(("activity", record))

    def _show_activity(self, record: ActivityRecord) -> None:
        timestamp = record.timestamp.replace("T", " ").split("+")[0]
        route = "VPN" if record.target is RouteTarget.VPN else "直连"
        status = record.status + (f"：{record.detail}" if record.detail else "")
        self._activity_counter += 1
        iid = f"activity-{self._activity_counter}"
        self.activity_records[iid] = record
        self.activity_tree.insert("", 0, iid=iid, values=(timestamp, record.process_name, f"{record.host}:{record.port}", route, record.matched_rule, status))
        children = self.activity_tree.get_children()
        if len(children) > 1000:
            expired = children[1000:]
            self.activity_tree.delete(*expired)
            for child in expired:
                self.activity_records.pop(child, None)

    def _selected_activity(self) -> ActivityRecord | None:
        selection = self.activity_tree.selection()
        return self.activity_records.get(selection[0]) if selection else None

    def _activity_selected(self, _event: object | None = None) -> None:
        record = self._selected_activity()
        if record and not (record.process_path or (record.process_name and record.process_name != "未知进程")):
            self.activity_target_var.set("domain")
        self._refresh_activity_detail()

    def _activity_candidate(self, record: ActivityRecord) -> tuple[RuleKind, str, str]:
        kind = RuleKind.DOMAIN if self.activity_target_var.get() == "domain" else RuleKind.APP
        value, label = activity_candidate(record, kind)
        return kind, value, label

    def _matching_activity_rule(self, record: ActivityRecord, kind: RuleKind) -> int | None:
        return matching_rule_index(self.config_model, record, kind)

    def _refresh_activity_detail(self) -> None:
        if not hasattr(self, "activity_rule_button"):
            return
        record = self._selected_activity()
        if record is None:
            self.activity_name_label.configure(text="尚未选择连接")
            self.activity_rule_status.configure(text="规则状态：—")
            self.activity_rule_button.configure(text="加入规则", state="disabled")
            return
        kind, value, _label = self._activity_candidate(record)
        application = record.process_name or "未知进程"
        path = record.process_path or "程序路径不可读"
        self.activity_name_label.configure(text=f"应用：{application}\n路径：{path}\n网站：{record.host}")
        if not value:
            self.activity_rule_status.configure(text="规则状态：无法识别")
            self.activity_rule_button.configure(text="无法操作", state="disabled")
            return
        existing = self._matching_activity_rule(record, kind)
        is_reverse = self.config_model.mode is RouteMode.REVERSE
        if existing is None:
            status = "隔离状态：未隔离" if is_reverse else "映射状态：未加入"
            button = "隔离" if is_reverse else "加入映射"
        else:
            matched = self.config_model.rules[existing].value
            status = ("隔离状态：已隔离" if is_reverse else "映射状态：已加入") + f"（{matched}）"
            button = "取消隔离" if is_reverse else "取消映射"
        self.activity_rule_status.configure(text=status)
        self.activity_rule_button.configure(text=button, state="normal")

    def _toggle_activity_rule(self) -> None:
        record = self._selected_activity()
        if record is None:
            return
        kind, value, label = self._activity_candidate(record)
        existing = self._matching_activity_rule(record, kind)
        if existing is None:
            self._append_rule(kind, value, label, notify=False)
        else:
            del self.config_model.rules[existing]
            self._rules_changed()
        self._refresh_activity_detail()

    def _run_diagnostics(self) -> None:
        for item in self.diag_tree.get_children():
            self.diag_tree.delete(item)
        threading.Thread(target=lambda: self.events.put(("diagnostics", run_diagnostics(self.config_model, self.proxy_manager))), daemon=True).start()

    def _elevate(self) -> None:
        if is_admin():
            messagebox.showinfo("管理员权限", "当前已是管理员权限。")
            return
        # The elevated process must be allowed to acquire the same mutex before
        # this normal-integrity process exits. Reacquire it if UAC launch fails.
        release_single_instance()
        if relaunch_as_admin():
            self._exit_app()
        else:
            ensure_single_instance()

    def _ensure_tray(self) -> bool:
        try:
            self.tray.start()
            return True
        except TrayUnavailable as exc:
            messagebox.showerror("系统托盘不可用", f"{exc}\n\n程序将保持在桌面显示；请重新安装完整版本。")
            return False

    def _hide_to_tray(self) -> None:
        if not self._ensure_tray():
            return
        self.withdraw()
        if not self._tray_notice_shown:
            self._tray_notice_shown = True
            self.tray.notify_hidden()

    def _show_from_tray(self) -> None:
        self.deiconify()
        self.state("normal")
        self.lift()
        self.focus_force()

    def _refresh_runtime_status(self) -> None:
        if self._closing:
            return
        if self.active:
            try:
                enabled, server = self.proxy_manager.current_proxy()
                expected = f"{self.config_model.listen_host}:{self.config_model.listen_port}"
                if not enabled or server != expected:
                    self.status_label.configure(text="● 系统代理被外部程序改写", foreground=RED)
                else:
                    self.status_label.configure(text="● 已启用", foreground=GREEN)
            except Exception:
                pass
        self.after(1500, self._refresh_runtime_status)

    def _drain_events(self) -> None:
        if self._closing:
            return
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "identity":
                    self._show_identity(payload)  # type: ignore[arg-type]
                elif kind == "activity":
                    self._show_activity(payload)  # type: ignore[arg-type]
                elif kind == "diagnostics":
                    for result in payload:  # type: ignore[union-attr]
                        self.diag_tree.insert("", "end", values=("通过" if result.ok else "注意", result.name, result.detail))
                elif kind == "rule_probe":
                    self._show_rule_probe(payload)  # type: ignore[arg-type]
                elif kind == "rule_probe_error":
                    self.rule_test_button.configure(state="normal", text="测试选中规则")
                    messagebox.showerror("规则出口验证失败", str(payload))
                elif kind == "tray_show":
                    self._show_from_tray()
                elif kind == "tray_toggle":
                    self._toggle()
                elif kind == "tray_exit":
                    self._exit_app()
        except queue.Empty:
            pass
        self.after(150, self._drain_events)

    def _on_close(self) -> None:
        if self.config_model.minimize_to_tray:
            self._hide_to_tray()
            return
        self._exit_app()

    def _exit_app(self) -> None:
        if self._closing:
            return
        self._closing = True
        self.tray.stop()
        if self.active or self.proxy_manager.is_owned():
            self._disable()
        self.destroy()


def run_app(start_minimized: bool = False) -> None:
    RouteWeaverApp(start_minimized=start_minimized).mainloop()
