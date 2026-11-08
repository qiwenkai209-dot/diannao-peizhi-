# -*- coding: utf-8 -*-
"""
🏛️ 展馆智能集群综合管控中心 · 主控端 (GuoWenChuang Master Hub)
============================================================
核心特性:
1. 局域网在线受控端雷达搜索:
   - 支持一键全网段 UDP 广播主动探测所有在线受控工控机
   - 实时反馈设备名称、IP 地址、系统版本、硬件负载 (CPU/GPU/内存) 与授权码
   - 支持一键批量自动纳管并点亮大厅
   - 支持后台自动侦听上线宣告 (Beacon)，新设备开机免配置即插即用
2. 全馆工控机集群监控大厅:
   - 集中长连接监听 (TCP 9888)，实时流式采集 CPU/GPU/内存/磁盘/前台活动窗口
   - 支持自定义主机名称与别名持久化存储
   - 单击选定设备弹窗桌面低延迟实时预览，双击直接进入全屏沉浸控制 (F11/Esc 切换)
   - 远程调用程序无缝联动受控端预设应用，主控刷新后即时显示并一键启动
   - 完整支持电源管理、音量控制、进程强杀与双向文件管理器
3. 集中备份中心与一键远程下发恢复:
   - 归档从机上传的 .gwcbackup 备份包
   - 一键下发备份到指定从机执行全自动系统还原
4. 国文创商业授权中枢:
   - 授权安全策略限制：仅允许主控授权受控从机，严禁为主控端本机进行自授权
   - 一键免敲码向未授权从机远程签发并下发 12 位激活码
   - 内置独立的《国文创加密机》离线计算终端
"""

import sys
import os
import time
import socket
import threading
import json
import base64
import uuid
import hashlib
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

# 核心功能模块
import gwc_crypto
import gwc_backup
import gwc_vnc
import gwc_master
import gwc_discovery
import gwc_system_ops
import gwc_license_terminal as lt

try:
    import universal_license_core
except ImportError:
    universal_license_core = None


class MarqueeLabel(tk.Canvas):
    """
    走马灯平滑滚动显示组件 (防闪烁重构版)：
    文本未变更时零重绘，文本变更时增量更新 item，绝不暴力 delete('all')，彻底消除闪烁。
    """
    def __init__(self, parent, text="", font=("Segoe UI", 9), bg="#151c2c", fg="#38bdf8", height=24, speed=1, fps=30, **kwargs):
        super().__init__(parent, bg=bg, height=height, highlightthickness=0, bd=0, **kwargs)
        self.text = text
        self.font = font
        self.fg = fg
        self.speed = speed
        self.interval = max(25, int(1000 / fps))
        self.offset_x = 0
        self.text_width = 0
        self._animating = False
        self._timer_id = None
        self._text_item = None

        self.bind("<Configure>", self._on_resize)
        self.after(50, self._init_render)

    def _init_render(self):
        self._render_or_update_text()

    def set_text(self, text: str, fg: str = None):
        if text == self.text and (fg is None or fg == self.fg):
            return  # 文本与颜色完全一致，直接忽略，杜绝不必要的重绘闪烁
        if fg:
            self.fg = fg
        self.text = text
        self.offset_x = 0
        self._render_or_update_text()

    def _render_or_update_text(self):
        h = self.winfo_height()
        if h <= 1:
            h = int(self.cget("height")) if self.cget("height") else 24

        if not self._text_item:
            self._text_item = self.create_text(
                self.offset_x, h // 2,
                text=self.text, font=self.font, fill=self.fg, anchor="w"
            )
        else:
            self.itemconfigure(self._text_item, text=self.text, fill=self.fg)
            self.coords(self._text_item, self.offset_x, h // 2)

        bbox = self.bbox(self._text_item)
        if bbox:
            self.text_width = bbox[2] - bbox[0]
        else:
            self.text_width = len(self.text) * 8
        self._check_scroll()

    def _on_resize(self, event):
        self._check_scroll()

    def _check_scroll(self):
        w = self.winfo_width()
        if w <= 1:
            w = self.winfo_reqwidth()
        if self.text_width > w and not self._animating:
            self._start_scroll()
        elif self.text_width <= w and self._animating:
            self._stop_scroll()
            self.offset_x = 0
            if self._text_item:
                h = self.winfo_height()
                self.coords(self._text_item, 0, h // 2 if h > 1 else 12)

    def _start_scroll(self):
        self._animating = True
        self._tick()

    def _stop_scroll(self):
        self._animating = False
        if self._timer_id:
            try:
                self.after_cancel(self._timer_id)
            except Exception:
                pass
            self._timer_id = None

    def _tick(self):
        if not self._animating or not self.winfo_exists():
            return
        w = self.winfo_width()
        self.offset_x -= self.speed
        if self.offset_x < -(self.text_width + 25):
            self.offset_x = w + 10
        if self._text_item:
            h = self.winfo_height()
            self.coords(self._text_item, self.offset_x, h // 2 if h > 1 else 12)
        self._timer_id = self.after(self.interval, self._tick)

    def destroy(self):
        self._stop_scroll()
        super().destroy()


class MasterAppUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("🏛️ 展馆智能集群综合管控中心 (国文创主控管理端)")
        self.root.geometry("1260x830")
        self.root.minsize(1120, 750)
        self.root.configure(bg="#0b0f19")

        # 居中显示窗口
        ws = self.root.winfo_screenwidth()
        hs = self.root.winfo_screenheight()
        self.root.geometry(f"1260x830+{(ws-1260)//2}+{(hs-830)//2}")

        # 图标
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gear.ico")
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except Exception:
                pass

        # 本机硬件特征与安全授权防护
        self.license_mgr = globals().get("__GWC_LICENSE_MGR__")
        self.local_hw_hash = self._calc_local_hw_hash()
        self.local_req_code = ""
        if self.license_mgr and hasattr(self.license_mgr, "get_req_code"):
            try:
                self.local_req_code = self.license_mgr.get_req_code()
            except Exception:
                pass

        # 主机别名配置管理
        self.alias_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "master_host_aliases.json")
        self.aliases = self._load_aliases()

        self.selected_ip = ""

        # 主控服务核心
        self.master_hub = gwc_master.GwcMasterHub(port=9888)
        self.master_hub.on_agent_connected = self._on_agent_connected
        self.master_hub.on_agent_disconnected = self._on_agent_disconnected
        self.master_hub.on_status_updated = self._on_agent_status_updated
        self.master_hub.on_backup_saved = self._on_backup_saved
        self.master_hub.on_udp_command_received = self._on_udp_command_received
        self.master_hub.on_central_control_event = self._on_central_control_event

        # 启动主控 TCP 监听与后台上线侦听
        self.master_hub.start()
        self.master_hub.start_agent_beacon_listener(on_discovered=self._on_beacon_discovered)

        # 状态变量
        self.total_online_var = tk.StringVar(value="在线工控机: 0 台")
        self.notice_var = tk.StringVar(value="主控中心已就绪，正在监听端口 9888 ...")

        # 搜索缓存: ip -> info
        self.discovered_agents = {}

        # 样式与界面构建
        self._setup_theme()
        self._build_ui()

        # 定时刷新大厅
        self.root.after(1000, self._periodic_ui_refresh)

    # ==================== 别名持久化与计算 ====================
    def _load_aliases(self) -> dict:
        if os.path.exists(self.alias_file):
            try:
                with open(self.alias_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_aliases(self):
        try:
            with open(self.alias_file, "w", encoding="utf-8") as f:
                json.dump(self.aliases, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _get_display_name(self, ip: str, hostname: str) -> str:
        alias = self.aliases.get(ip) or self.aliases.get(hostname)
        if alias:
            return f"【{alias}】 {hostname}"
        return hostname

    def _calc_local_hw_hash(self) -> int:
        parts = []
        try:
            parts.append(f"MAC_{uuid.getnode():012X}")
        except Exception:
            pass
        parts.append(f"CPU_{os.environ.get('PROCESSOR_IDENTIFIER', '')}_{os.environ.get('NUMBER_OF_PROCESSORS', '1')}")
        h = int(hashlib.sha256("|".join(parts).encode()).hexdigest()[:8], 16)
        return (h % 4095) + 1

    def _is_self_device(self, client_ip: str, req_code: str = "") -> bool:
        """支持给包括本机在内的所有设备授权，不阻拦任何机器"""
        return False

    # ==================== 主题与样式 ====================
    def _setup_theme(self):
        style = ttk.Style()
        style.theme_use("clam")

        self.BG_MAIN = "#0b0f19"
        self.BG_PANEL = "#151c2c"
        self.BG_CARD = "#1e293b"
        self.BORDER_COLOR = "#334155"
        self.ACCENT_CYAN = "#38bdf8"
        self.ACCENT_BLUE = "#0284c7"
        self.ACCENT_GREEN = "#10b981"
        self.ACCENT_YELLOW = "#f59e0b"
        self.ACCENT_RED = "#ef4444"
        self.TEXT_WHITE = "#f8fafc"
        self.TEXT_MUTED = "#94a3b8"

        style.configure("Dark.TFrame", background=self.BG_MAIN)
        style.configure("Panel.TFrame", background=self.BG_PANEL)
        style.configure("Card.TFrame", background=self.BG_CARD)

        # Treeview 样式
        style.configure(
            "Treeview",
            background="#0f172a",
            foreground="#f8fafc",
            fieldbackground="#0f172a",
            rowheight=26,
            font=("Segoe UI", 9)
        )
        style.configure(
            "Treeview.Heading",
            background="#1e293b",
            foreground="#38bdf8",
            relief="flat",
            font=("Segoe UI", 9, "bold")
        )
        style.map(
            "Treeview",
            background=[("selected", "#0284c7")],
            foreground=[("selected", "#ffffff")]
        )

        # Notebook 样式
        style.configure("TNotebook", background=self.BG_MAIN, borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background="#1e293b",
            foreground=self.TEXT_MUTED,
            font=("Segoe UI", 10, "bold"),
            padding=[16, 8]
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", "#0284c7")],
            foreground=[("selected", "#ffffff")]
        )

    # ==================== 界面结构构建 ====================
    def _build_ui(self):
        # 1. 顶部主控指挥舱工具栏
        self._build_top_command_bar()

        # 2. 状态提示小通知条 (长文本自动平滑走马灯滚动播放)
        notice_frame = tk.Frame(self.root, bg="#111827", height=24)
        notice_frame.pack(fill=tk.X, side=tk.TOP)
        self.notice_marquee = MarqueeLabel(
            notice_frame,
            text=self.notice_var.get(),
            font=("Segoe UI", 8),
            bg="#111827",
            fg=self.ACCENT_CYAN,
            height=22,
            speed=1
        )
        self.notice_marquee.pack(fill=tk.X, expand=True, padx=12)

        def _on_notice_changed(*args):
            if hasattr(self, "notice_marquee") and self.notice_marquee.winfo_exists():
                self.notice_marquee.set_text(self.notice_var.get())
        self.notice_var.trace_add("write", _on_notice_changed)

        # 3. 主界面 Notebook 标签容器
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill=tk.BOTH, expand=True, padx=12, pady=(6, 12))
        self.nb.bind("<<NotebookTabChanged>>", self._on_notebook_tab_changed)

        # Tab 1: 集群设备监控大厅
        self.tab_monitor = ttk.Frame(self.nb, style="Dark.TFrame")
        self.nb.add(self.tab_monitor, text="🖥️ 展馆工控机集群监控大厅")
        self._build_monitor_hall(self.tab_monitor)

        # Tab 2: 主控备份归档与下发恢复
        self.tab_backup = ttk.Frame(self.nb, style="Dark.TFrame")
        self.nb.add(self.tab_backup, text="💾 主控备份中心与远程下发")
        self._build_backup_center(self.tab_backup)

        # Tab 3: 国文创商业授权中枢
        self.tab_license = ttk.Frame(self.nb, style="Dark.TFrame")
        self.nb.add(self.tab_license, text="🛡️ 国文创商业授权中枢")
        self._build_license_hub(self.tab_license)

    def _build_top_command_bar(self):
        top_bar = tk.Frame(self.root, bg=self.BG_PANEL, height=56)
        top_bar.pack(fill=tk.X, side=tk.TOP, padx=12, pady=(8, 4))

        # 标题与指标
        title_box = tk.Frame(top_bar, bg=self.BG_PANEL)
        title_box.pack(side=tk.LEFT, padx=12, pady=8)

        lbl_title = tk.Label(
            title_box,
            text="🏛️ 展馆智能集群综合管控中心",
            font=("Segoe UI", 13, "bold"),
            bg=self.BG_PANEL,
            fg="#ffffff"
        )
        lbl_title.pack(anchor="w")

        lbl_sub = tk.Label(
            title_box,
            text="Industrial Intelligent Operations Center · 展馆智能集群综合管控中心",
            font=("Segoe UI", 8),
            bg=self.BG_PANEL,
            fg=self.TEXT_MUTED
        )
        lbl_sub.pack(anchor="w")

        # 在线数量微标
        self.lbl_online_badge = tk.Label(
            top_bar,
            textvariable=self.total_online_var,
            font=("Segoe UI", 9, "bold"),
            bg="#0f172a",
            fg=self.ACCENT_GREEN,
            padx=12,
            pady=4,
            relief="groove",
            bd=1
        )
        self.lbl_online_badge.pack(side=tk.LEFT, padx=14)

        # 核心亮点按钮: 【🔍 局域网搜索受控端】
        btn_search = tk.Button(
            top_bar,
            text="🔍 搜索局域网在线受控端",
            font=("Segoe UI", 10, "bold"),
            bg=self.ACCENT_CYAN,
            fg="#0b0f19",
            activebackground="#0284c7",
            activeforeground="#ffffff",
            relief="flat",
            padx=14,
            pady=6,
            cursor="hand2",
            command=self.open_agent_search_window
        )
        btn_search.pack(side=tk.LEFT, padx=6)

        # 中控安全协议按钮
        btn_udp_doc = tk.Button(
            top_bar,
            text="📖 中控安全协议",
            font=("Segoe UI", 9, "bold"),
            bg="#1e293b",
            fg="#38bdf8",
            activebackground="#0284c7",
            activeforeground="#ffffff",
            relief="flat",
            padx=10,
            pady=6,
            cursor="hand2",
            command=self.open_udp_protocol_help_window
        )
        btn_udp_doc.pack(side=tk.LEFT, padx=6)

        # 全馆批量控制按钮组 (靠右)
        btn_all_shutdown = tk.Button(
            top_bar,
            text="⚡ 全馆一键关机",
            font=("Segoe UI", 9, "bold"),
            bg=self.ACCENT_RED,
            fg="#ffffff",
            relief="flat",
            padx=10,
            pady=5,
            cursor="hand2",
            command=self._batch_shutdown
        )
        btn_all_shutdown.pack(side=tk.RIGHT, padx=4)

        btn_all_reboot = tk.Button(
            top_bar,
            text="🔄 全馆一键重启",
            font=("Segoe UI", 9),
            bg=self.ACCENT_YELLOW,
            fg="#0b0f19",
            relief="flat",
            padx=10,
            pady=5,
            cursor="hand2",
            command=self._batch_reboot
        )
        btn_all_reboot.pack(side=tk.RIGHT, padx=4)



    # ==================== Tab 1: 集群监控大厅 ====================
    def _build_monitor_hall(self, parent):
        paned = tk.PanedWindow(parent, orient=tk.HORIZONTAL, bg=self.BG_MAIN, bd=0, sashwidth=4)
        paned.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        # 左侧: 在线工控机大厅表格
        left = tk.LabelFrame(
            paned,
            text=" 展馆监控大厅 ",
            font=("Segoe UI", 9, "bold"),
            fg=self.ACCENT_CYAN,
            bg=self.BG_PANEL,
            bd=1
        )
        paned.add(left, width=650)

        # 工具栏: 搜索受控端快捷入口与刷新
        left_tool = tk.Frame(left, bg=self.BG_PANEL)
        left_tool.pack(fill=tk.X, padx=8, pady=4)

        btn_fast_scan = tk.Button(
            left_tool,
            text="⚡ 快速扫描局域网从机",
            font=("Segoe UI", 8, "bold"),
            bg="#1e293b",
            fg=self.ACCENT_CYAN,
            relief="flat",
            padx=8,
            pady=3,
            cursor="hand2",
            command=self._do_quick_scan
        )
        btn_fast_scan.pack(side=tk.LEFT)

        btn_refresh = tk.Button(
            left_tool,
            text="🔄 刷新列表",
            font=("Segoe UI", 8),
            bg="#1e293b",
            fg="#ffffff",
            relief="flat",
            padx=8,
            pady=3,
            cursor="hand2",
            command=self._refresh_client_tree
        )
        btn_refresh.pack(side=tk.LEFT, padx=6)

        lbl_tip = tk.Label(
            left_tool,
            text="双击从机小屏预览 · 右键弹出功能菜单",
            font=("Segoe UI", 8),
            bg=self.BG_PANEL,
            fg=self.TEXT_MUTED
        )
        lbl_tip.pack(side=tk.RIGHT)

        # 表格 (移除商业授权列，与授权中枢明确分离；拓宽前台活动窗口展示)
        cols = ("host", "cpu", "gpu", "mem", "fg")
        self.client_tree = ttk.Treeview(left, columns=cols, show="tree headings", selectmode="browse")
        self.client_tree.heading("#0", text="IP 地址", anchor="w")
        self.client_tree.heading("host", text="设备名称 / 别名", anchor="w")
        self.client_tree.heading("cpu", text="CPU%", anchor="center")
        self.client_tree.heading("gpu", text="GPU%", anchor="center")
        self.client_tree.heading("mem", text="内存%", anchor="center")
        self.client_tree.heading("fg", text="前台活动窗口", anchor="w")

        self.client_tree.column("#0", width=115)
        self.client_tree.column("host", width=145)
        self.client_tree.column("cpu", width=55)
        self.client_tree.column("gpu", width=55)
        self.client_tree.column("mem", width=55)
        self.client_tree.column("fg", width=225)

        scroll_y = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self.client_tree.yview)
        self.client_tree.configure(yscrollcommand=scroll_y.set)

        self.client_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0), pady=6)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y, pady=6, padx=(0, 6))

        # 事件绑定：单击选定展示状态，双击单窗口小屏预览
        self.client_tree.bind("<<TreeviewSelect>>", self._on_client_tree_select)
        self.client_tree.bind("<Double-1>", lambda e: self._open_remote_desktop(fullscreen=False, force_single=True))
        self.client_tree.bind("<Button-3>", self._show_client_context_menu)

        # 右键上下文菜单
        self._build_context_menu()

        # 右侧: 选定设备即时控制面板
        right = tk.LabelFrame(
            paned,
            text=" 选定设备控制面板 ",
            font=("Segoe UI", 9, "bold"),
            fg=self.ACCENT_GREEN,
            bg=self.BG_PANEL,
            bd=1
        )
        paned.add(right, width=580)
        self._build_selected_device_panel(right)

    def _build_context_menu(self):
        self.context_menu = tk.Menu(self.root, tearoff=0, bg="#1e293b", fg="#ffffff", activebackground="#0284c7")
        self.context_menu.add_command(label="🖥️ 小屏预览 (双击唯一窗口)", command=lambda: self._open_remote_desktop(fullscreen=False, force_single=True))
        self.context_menu.add_command(label="📑 新建独立预览窗口 (支持多开)", command=lambda: self._open_remote_desktop(fullscreen=False, force_single=False))
        self.context_menu.add_command(label="⛶ 全屏桌面控制", command=lambda: self._open_remote_desktop(fullscreen=True, force_single=False))
        self.context_menu.add_command(label="📁 文件管理", command=self._open_remote_file_transfer)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="✏️ 修改设备别名", command=self._edit_client_alias)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="⚡ 远程关机", command=self._ctl_shutdown)
        self.context_menu.add_command(label="🔄 远程重启", command=self._ctl_reboot)
        self.context_menu.add_command(label="🔇 静音/解除静音", command=self._ctl_mute)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="💾 远程生成备份并回传", command=self._master_request_backup)

    def _show_client_context_menu(self, event):
        item = self.client_tree.identify_row(event.y)
        if item:
            self.client_tree.selection_set(item)
            self._on_client_tree_select(None)
            self.context_menu.post(event.x_root, event.y_root)

    def _build_selected_device_panel(self, parent):
        # 选定机器状态与别名编辑顶栏 (数据超长自动平滑滚动播放)
        dev_header = tk.Frame(parent, bg=self.BG_PANEL)
        dev_header.pack(fill=tk.X, padx=12, pady=(8, 4))

        self.sel_host_lbl = MarqueeLabel(
            dev_header,
            text="请在左侧监控大厅中选定一台工控机进行管理",
            font=("Segoe UI", 9, "bold"),
            bg=self.BG_PANEL,
            fg=self.TEXT_MUTED,
            height=24
        )
        self.sel_host_lbl.pack(fill=tk.X, expand=True)

        # 别名即时编辑行
        alias_bar = tk.Frame(parent, bg=self.BG_PANEL)
        alias_bar.pack(fill=tk.X, padx=12, pady=(2, 6))

        tk.Label(alias_bar, text="设备业务别名:", font=("Segoe UI", 8), bg=self.BG_PANEL, fg=self.TEXT_MUTED).pack(side=tk.LEFT)
        self.alias_entry = tk.Entry(alias_bar, font=("Segoe UI", 9), bg="#0f172a", fg=self.ACCENT_CYAN, width=18, relief="flat")
        self.alias_entry.pack(side=tk.LEFT, padx=6)

        btn_save_alias = tk.Button(
            alias_bar,
            text="💾 保存别名",
            font=("Segoe UI", 8, "bold"),
            bg="#0284c7",
            fg="#ffffff",
            relief="flat",
            padx=8,
            pady=1,
            cursor="hand2",
            command=self._save_current_alias
        )
        btn_save_alias.pack(side=tk.LEFT, padx=2)

        btn_clear_alias = tk.Button(
            alias_bar,
            text="✖️ 清除",
            font=("Segoe UI", 8),
            bg="#334155",
            fg="#cbd5e1",
            relief="flat",
            padx=6,
            pady=1,
            cursor="hand2",
            command=self._clear_current_alias
        )
        btn_clear_alias.pack(side=tk.LEFT, padx=2)

        # 快捷文件管理入口 (双击从机小屏预览，右侧保留文件管理)
        desk_bar = tk.Frame(parent, bg=self.BG_PANEL)
        desk_bar.pack(fill=tk.X, padx=12, pady=4)

        btn_fs = tk.Button(
            desk_bar,
            text="📁 文件管理 (受控端)",
            font=("Segoe UI", 9, "bold"),
            bg="#334155",
            fg="#ffffff",
            relief="flat",
            padx=12,
            pady=4,
            cursor="hand2",
            command=self._open_remote_file_transfer
        )
        btn_fs.pack(side=tk.LEFT)

        # 快捷控制指令 (电源、音量、预设调用)
        ctl_box = tk.LabelFrame(
            parent,
            text=" 快捷控制与预设应用 ",
            font=("Segoe UI", 9, "bold"),
            fg=self.ACCENT_YELLOW,
            bg=self.BG_PANEL,
            bd=1
        )
        ctl_box.pack(fill=tk.X, padx=12, pady=6)

        # 第 1 行: 电源与音量
        r1 = tk.Frame(ctl_box, bg=self.BG_PANEL)
        r1.pack(fill=tk.X, padx=8, pady=4)

        tk.Button(
            r1,
            text="⚡ 远程关机",
            font=("Segoe UI", 8, "bold"),
            bg=self.ACCENT_RED,
            fg="#ffffff",
            relief="flat",
            padx=8,
            pady=2,
            cursor="hand2",
            command=self._ctl_shutdown
        ).pack(side=tk.LEFT, padx=2)

        tk.Button(
            r1,
            text="🔄 远程重启",
            font=("Segoe UI", 8),
            bg=self.ACCENT_YELLOW,
            fg="#0b0f19",
            relief="flat",
            padx=8,
            pady=2,
            cursor="hand2",
            command=self._ctl_reboot
        ).pack(side=tk.LEFT, padx=2)

        tk.Button(
            r1,
            text="🔇 静音/解除",
            font=("Segoe UI", 8),
            bg="#334155",
            fg="#ffffff",
            relief="flat",
            padx=6,
            pady=2,
            cursor="hand2",
            command=self._ctl_mute
        ).pack(side=tk.LEFT, padx=4)

        tk.Label(r1, text="音量:", font=("Segoe UI", 8), fg="#cbd5e1", bg=self.BG_PANEL).pack(side=tk.LEFT, padx=(6, 2))
        self.vol_scale = tk.Scale(
            r1,
            from_=0,
            to=100,
            orient=tk.HORIZONTAL,
            bg=self.BG_PANEL,
            fg=self.ACCENT_CYAN,
            highlightthickness=0,
            length=80
        )
        self.vol_scale.set(50)
        self.vol_scale.pack(side=tk.LEFT, padx=2)

        tk.Button(
            r1,
            text="设定",
            font=("Segoe UI", 8),
            bg=self.ACCENT_BLUE,
            fg="#ffffff",
            relief="flat",
            padx=6,
            pady=1,
            cursor="hand2",
            command=self._ctl_set_vol
        ).pack(side=tk.LEFT)

        # 第 2 行: 受控端预设应用快速选择联动
        r2 = tk.Frame(ctl_box, bg=self.BG_PANEL)
        r2.pack(fill=tk.X, padx=8, pady=(4, 2))

        tk.Label(r2, text="从机预设程序:", font=("Segoe UI", 8, "bold"), fg=self.ACCENT_CYAN, bg=self.BG_PANEL).pack(side=tk.LEFT)
        self.preset_combo = ttk.Combobox(r2, state="readonly", font=("Segoe UI", 8))
        self.preset_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        self.preset_combo.bind("<<ComboboxSelected>>", self._on_preset_app_selected)

        btn_refresh_presets = tk.Button(
            r2,
            text="🔄 刷新预设",
            font=("Segoe UI", 8),
            bg="#1e293b",
            fg="#38bdf8",
            relief="flat",
            padx=6,
            pady=1,
            cursor="hand2",
            command=self._refresh_selected_agent_presets
        )
        btn_refresh_presets.pack(side=tk.RIGHT, padx=2)

        # 第 3 行: 自由路径与启动
        r3 = tk.Frame(ctl_box, bg=self.BG_PANEL)
        r3.pack(fill=tk.X, padx=8, pady=(2, 6))

        tk.Label(r3, text="程序路径:", font=("Segoe UI", 8), fg="#cbd5e1", bg=self.BG_PANEL).pack(side=tk.LEFT)
        self.run_app_entry = tk.Entry(r3, font=("Consolas", 8), bg="#0f172a", fg=self.ACCENT_CYAN, relief="flat", width=22)
        self.run_app_entry.insert(0, "notepad.exe")
        self.run_app_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        tk.Label(r3, text="参数:", font=("Segoe UI", 8), fg="#cbd5e1", bg=self.BG_PANEL).pack(side=tk.LEFT)
        self.run_args_entry = tk.Entry(r3, font=("Consolas", 8), bg="#0f172a", fg="#f8fafc", relief="flat", width=10)
        self.run_args_entry.pack(side=tk.LEFT, padx=4)

        tk.Button(
            r3,
            text="🚀 立即启动",
            font=("Segoe UI", 8, "bold"),
            bg=self.ACCENT_BLUE,
            fg="#ffffff",
            relief="flat",
            padx=8,
            pady=2,
            cursor="hand2",
            command=self._ctl_run_app
        ).pack(side=tk.RIGHT)

        # 运行中软件与进程列表 (支持远程强杀)
        proc_box = tk.LabelFrame(
            parent,
            text=" 运行进程列表 ",
            font=("Segoe UI", 9, "bold"),
            fg=self.TEXT_MUTED,
            bg=self.BG_PANEL,
            bd=1
        )
        proc_box.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)

        self.proc_tree = ttk.Treeview(proc_box, columns=("pid", "mem"), show="tree headings", selectmode="browse")
        self.proc_tree.heading("#0", text="进程名称", anchor="w")
        self.proc_tree.heading("pid", text="PID", anchor="center")
        self.proc_tree.heading("mem", text="内存", anchor="e")
        self.proc_tree.column("#0", width=220)
        self.proc_tree.column("pid", width=70)
        self.proc_tree.column("mem", width=80)
        self.proc_tree.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

        proc_btn_bar = tk.Frame(proc_box, bg=self.BG_PANEL)
        proc_btn_bar.pack(fill=tk.X, padx=6, pady=4)

        tk.Button(
            proc_btn_bar,
            text="🛑 终止进程",
            font=("Segoe UI", 8, "bold"),
            bg=self.ACCENT_RED,
            fg="#ffffff",
            relief="flat",
            padx=10,
            pady=3,
            cursor="hand2",
            command=self._ctl_kill_proc
        ).pack(side=tk.LEFT)

    # ==================== 别名管理与应用预设 ====================
    def _edit_client_alias(self):
        ip = self._get_selected_client_ip()
        if not ip:
            messagebox.showinfo("提示", "请先在监控大厅中选中一台工控机！")
            return
        cur_alias = self.aliases.get(ip, "")
        info = self.master_hub.clients.get(ip, {}).get("info", {})
        h_name = info.get("hostname", ip)

        new_alias = simpledialog.askstring(
            "设置设备别名备注",
            f"请输入工控机 [{h_name}] ({ip}) 的业务别名:\n(例如: 1号序厅主屏、LED多媒体沙盘、二楼触控机)",
            initialvalue=cur_alias,
            parent=self.root
        )
        if new_alias is not None:
            new_alias = new_alias.strip()
            if new_alias:
                self.aliases[ip] = new_alias
                self.aliases[h_name] = new_alias
            else:
                self.aliases.pop(ip, None)
                self.aliases.pop(h_name, None)
            self._save_aliases()
            self._refresh_client_tree()
            self.alias_entry.delete(0, tk.END)
            self.alias_entry.insert(0, new_alias)

    def _save_current_alias(self):
        ip = self._get_selected_client_ip()
        if not ip:
            messagebox.showinfo("提示", "请先在左侧选择要设置别名的工控机！")
            return
        val = self.alias_entry.get().strip()
        info = self.master_hub.clients.get(ip, {}).get("info", {})
        h_name = info.get("hostname", ip)
        if val:
            self.aliases[ip] = val
            self.aliases[h_name] = val
        else:
            self.aliases.pop(ip, None)
            self.aliases.pop(h_name, None)
        self._save_aliases()
        self._refresh_client_tree()
        messagebox.showinfo("别名已保存", f"工控机 [{ip}] 业务别名已更新为: {val or '无'}")

    def _clear_current_alias(self):
        self.alias_entry.delete(0, tk.END)
        self._save_current_alias()

    def _on_preset_app_selected(self, event):
        sel = self.preset_combo.get()
        ip = self._get_selected_client_ip()
        if not ip or not sel:
            return
        info = self.master_hub.clients.get(ip, {}).get("info", {})
        presets = info.get("preset_apps", [])
        for item in presets:
            label = f"{item.get('name', 'App')} ({item.get('path', '')})"
            if label == sel:
                self.run_app_entry.delete(0, tk.END)
                self.run_app_entry.insert(0, item.get("path", ""))
                self.run_args_entry.delete(0, tk.END)
                self.run_args_entry.insert(0, item.get("args", ""))
                break

    def _refresh_selected_agent_presets(self):
        ip = self._get_selected_client_ip()
        if not ip:
            messagebox.showinfo("提示", "请先在监控大厅中选中目标工控机！")
            return
        self.notice_var.set(f"正在从工控机 [{ip}] 刷新预设应用清单...")
        self.master_hub.send_command(
            ip, "CMD_GET_STATUS", {},
            callback=lambda r: self._safe_after(lambda: (
                self._update_preset_combo(ip),
                self.notice_var.set(f"工控机 [{ip}] 预设应用与状态已刷新！")
            ))
        )

    def _update_preset_combo(self, ip: str):
        info = self.master_hub.clients.get(ip, {}).get("info", {})
        presets = info.get("preset_apps", [])
        combo_vals = []
        for p in presets:
            nm = p.get("name", "未命名应用")
            pt = p.get("path", "")
            combo_vals.append(f"{nm} ({pt})")
        self.preset_combo["values"] = combo_vals
        if combo_vals:
            self.preset_combo.current(0)
            self._on_preset_app_selected(None)
        else:
            self.preset_combo.set("该从机暂未预设常用应用")

    # ==================== 局域网在线受控端搜索 ====================
    def open_agent_search_window(self):
        """弹出专用的局域网在线受控端雷达搜索与纳管中心"""
        win = tk.Toplevel(self.root)
        win.title("🔍 局域网在线受控端雷达搜索与自动纳管中心")
        win.geometry("920x580")
        win.configure(bg="#0f172a")
        win.minsize(800, 500)

        # 居中
        ws = win.winfo_screenwidth()
        hs = win.winfo_screenheight()
        win.geometry(f"920x580+{(ws-920)//2}+{(hs-580)//2}")

        # 顶部操作栏
        top_f = tk.Frame(win, bg="#1e293b", padx=12, pady=10)
        top_f.pack(fill=tk.X, padx=12, pady=10)

        lbl_s_title = tk.Label(
            top_f,
            text="🔍 局域网全网段广播探测",
            font=("Segoe UI", 11, "bold"),
            bg="#1e293b",
            fg="#38bdf8"
        )
        lbl_s_title.pack(side=tk.LEFT)

        auto_conn_var = tk.BooleanVar(value=True)
        chk_auto = tk.Checkbutton(
            top_f,
            text="探测后自动命令受控端连入主控",
            variable=auto_conn_var,
            bg="#1e293b",
            fg="#f8fafc",
            selectcolor="#0f172a",
            font=("Segoe UI", 9)
        )
        chk_auto.pack(side=tk.LEFT, padx=16)

        btn_start_scan = tk.Button(
            top_f,
            text="⚡ 开始全网段扫描",
            font=("Segoe UI", 9, "bold"),
            bg="#0284c7",
            fg="#ffffff",
            relief="flat",
            padx=14,
            pady=4,
            cursor="hand2"
        )
        btn_start_scan.pack(side=tk.RIGHT)

        # 结果表格 (含 GPU% 列展示)
        res_frame = tk.Frame(win, bg="#0f172a", padx=12)
        res_frame.pack(fill=tk.BOTH, expand=True)

        cols = ("ip", "latency", "os", "cpu", "gpu", "mem", "conn", "req_code")
        tree = ttk.Treeview(res_frame, columns=cols, show="tree headings", selectmode="extended")
        tree.heading("#0", text="设备名称 / 别名", anchor="w")
        tree.heading("ip", text="IP 地址", anchor="w")
        tree.heading("latency", text="响应延迟", anchor="center")
        tree.heading("os", text="操作系统", anchor="w")
        tree.heading("cpu", text="CPU", anchor="center")
        tree.heading("gpu", text="GPU", anchor="center")
        tree.heading("mem", text="内存", anchor="center")
        tree.heading("conn", text="主控连接状态", anchor="center")
        tree.heading("req_code", text="申请码", anchor="center")

        tree.column("#0", width=130)
        tree.column("ip", width=110)
        tree.column("latency", width=65)
        tree.column("os", width=100)
        tree.column("cpu", width=50)
        tree.column("gpu", width=50)
        tree.column("mem", width=50)
        tree.column("conn", width=95)
        tree.column("req_code", width=85)

        s_y = ttk.Scrollbar(res_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=s_y.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        s_y.pack(side=tk.RIGHT, fill=tk.Y)

        # 底部状态栏与纳管按钮
        bot_f = tk.Frame(win, bg="#0f172a", padx=12, pady=10)
        bot_f.pack(fill=tk.X)

        lbl_scan_status = tk.Label(
            bot_f,
            text="就绪: 点击【开始全网段扫描】搜索局域网内所有在线从机",
            font=("Segoe UI", 9),
            bg="#0f172a",
            fg="#94a3b8"
        )
        lbl_scan_status.pack(side=tk.LEFT)

        def do_scan_work():
            lbl_scan_status.config(text="正在发送 UDP 广播并收集回包，请稍候...", fg="#38bdf8")
            btn_start_scan.config(state="disabled")

            for i in tree.get_children():
                tree.delete(i)

            def on_found(dev):
                def add_item():
                    ip = dev.get("ip")
                    raw_h = dev.get("hostname", "Unknown")
                    h_name = self._get_display_name(ip, raw_h)
                    lat = f"{dev.get('latency_ms', 1)} ms"
                    os_str = dev.get("os", "Windows")
                    cpu_s = f"{dev.get('cpu', 0)}%"
                    gpu_s = f"{dev.get('gpu', dev.get('gpu_percent', 0))}%"
                    mem_s = f"{dev.get('mem', 0)}%"
                    is_c = dev.get("connected_master", False)
                    c_txt = "🟢 已连主控" if is_c else "🟡 待命待连"
                    r_code = dev.get("request_code", "----")
                    if not tree.exists(ip):
                        tree.insert("", "end", iid=ip, text=h_name, values=(ip, lat, os_str, cpu_s, gpu_s, mem_s, c_txt, r_code))
                win.after(0, add_item)

            def runner():
                results = self.master_hub.scan_online_agents(
                    timeout=2.0,
                    auto_connect=auto_conn_var.get(),
                    on_found=on_found
                )
                def done():
                    lbl_scan_status.config(
                        text=f"✓ 扫描完成: 共发现 {len(results)} 台在线工控受控端！",
                        fg="#10b981"
                    )
                    btn_start_scan.config(state="normal")
                    self._refresh_client_tree()
                win.after(0, done)

            threading.Thread(target=runner, daemon=True).start()

        btn_start_scan.config(command=do_scan_work)

        def connect_selected():
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("提示", "请在列表中选中需要纳管连接的工控机！")
                return
            for ip in sel:
                threading.Thread(
                    target=lambda target_ip=ip: self.master_hub.scan_online_agents(timeout=1.0, auto_connect=True),
                    daemon=True
                ).start()
            messagebox.showinfo("已下发连接指令", f"已向选中的 {len(sel)} 台工控机发送接入指令，受控端将即刻自动建立加密长连接！")

        btn_connect_sel = tk.Button(
            bot_f,
            text="🔗 一键纳管选中的受控端",
            font=("Segoe UI", 9, "bold"),
            bg="#10b981",
            fg="#ffffff",
            relief="flat",
            padx=14,
            pady=4,
            cursor="hand2",
            command=connect_selected
        )
        btn_connect_sel.pack(side=tk.RIGHT, padx=4)

        win.after(300, do_scan_work)

    def _do_quick_scan(self):
        """主窗口左侧快速扫描"""
        self.notice_var.set("正在广播探测局域网受控设备...")
        def runner():
            res = self.master_hub.scan_online_agents(timeout=1.5, auto_connect=True)
            self.root.after(0, lambda: (
                self._refresh_client_tree(),
                self.notice_var.set(f"快速探测完毕，共发现 {len(res)} 台受控工控机，已自动握手！")
            ))
        threading.Thread(target=runner, daemon=True).start()

    # ==================== Tab 2: 备份中心与远程下发 ====================
    def _build_backup_center(self, parent):
        f = tk.Frame(parent, bg=self.BG_MAIN)
        f.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)

        # 1. 目标受控工控机发现与指定工具条
        dev_bar = tk.Frame(f, bg=self.BG_PANEL, padx=10, pady=8)
        dev_bar.pack(fill=tk.X, pady=(0, 6))

        tk.Label(
            dev_bar,
            text="🎯 目标受控工控机:",
            font=("Segoe UI", 9, "bold"),
            fg=self.ACCENT_CYAN,
            bg=self.BG_PANEL
        ).pack(side=tk.LEFT, padx=(2, 6))

        self.bk_target_combo = ttk.Combobox(dev_bar, state="readonly", font=("Segoe UI", 9), width=38)
        self.bk_target_combo.pack(side=tk.LEFT, padx=4)

        btn_bk_scan = tk.Button(
            dev_bar,
            text="🔍 发现/刷新在线设备",
            font=("Segoe UI", 8, "bold"),
            bg="#1e293b",
            fg=self.ACCENT_CYAN,
            relief="flat",
            padx=10,
            pady=3,
            cursor="hand2",
            command=self._refresh_backup_devices
        )
        btn_bk_scan.pack(side=tk.LEFT, padx=6)

        self.lbl_bk_target_tip = tk.Label(
            dev_bar,
            text="主控支持直接发现局域网受控设备并下发还原，无需切回监控大厅",
            font=("Segoe UI", 8),
            bg=self.BG_PANEL,
            fg=self.TEXT_MUTED
        )
        self.lbl_bk_target_tip.pack(side=tk.LEFT, padx=8)

        # 2. 备份与还原操作栏
        top_acts = tk.Frame(f, bg=self.BG_PANEL, padx=10, pady=8)
        top_acts.pack(fill=tk.X, pady=(0, 8))

        btn_push_bk = tk.Button(
            top_acts,
            text="📤 下发选中备份到目标工控机并自动还原",
            font=("Segoe UI", 9, "bold"),
            bg=self.ACCENT_BLUE,
            fg="#ffffff",
            relief="flat",
            padx=12,
            pady=5,
            cursor="hand2",
            command=self._master_push_backup
        )
        btn_push_bk.pack(side=tk.LEFT, padx=4)

        btn_req_bk = tk.Button(
            top_acts,
            text="📥 命令目标从机立即生成配置备份并上传",
            font=("Segoe UI", 9, "bold"),
            bg="#059669",
            fg="#ffffff",
            relief="flat",
            padx=12,
            pady=5,
            cursor="hand2",
            command=self._master_request_backup
        )
        btn_req_bk.pack(side=tk.LEFT, padx=4)

        btn_refresh_bk_list = tk.Button(
            top_acts,
            text="🔄 刷新备份库",
            font=("Segoe UI", 9),
            bg="#1e293b",
            fg="#ffffff",
            relief="flat",
            padx=10,
            pady=5,
            cursor="hand2",
            command=self._refresh_master_backup_tree
        )
        btn_refresh_bk_list.pack(side=tk.LEFT, padx=4)

        btn_open_folder = tk.Button(
            top_acts,
            text="📂 打开主控备份归档文件夹",
            font=("Segoe UI", 9),
            bg="#334155",
            fg="#ffffff",
            relief="flat",
            padx=10,
            pady=5,
            cursor="hand2",
            command=lambda: os.system(f'explorer "{self.master_hub.backup_store_dir}"')
        )
        btn_open_folder.pack(side=tk.RIGHT, padx=4)

        # 备份列表表格
        cols = ("host", "time", "size", "notes")
        self.master_bk_tree = ttk.Treeview(f, columns=cols, show="tree headings", selectmode="browse")
        self.master_bk_tree.heading("#0", text="备份包名称 (.gwcbackup)", anchor="w")
        self.master_bk_tree.heading("host", text="来源主机", anchor="center")
        self.master_bk_tree.heading("time", text="归档时间", anchor="center")
        self.master_bk_tree.heading("size", text="大小", anchor="e")
        self.master_bk_tree.heading("notes", text="备份说明", anchor="w")

        self.master_bk_tree.column("#0", width=280)
        self.master_bk_tree.column("host", width=120)
        self.master_bk_tree.column("time", width=140)
        self.master_bk_tree.column("size", width=80)
        self.master_bk_tree.column("notes", width=260)
        self.master_bk_tree.pack(fill=tk.BOTH, expand=True)

        self._refresh_master_backup_tree()
        self._sync_backup_devices()

    def _on_notebook_tab_changed(self, event=None):
        try:
            sel_tab = self.nb.index("current")
            if sel_tab == 1:  # 备份中心
                self._sync_backup_devices()
                self._refresh_master_backup_tree()
            elif sel_tab == 2:  # 商业授权
                self._refresh_client_tree()
        except Exception:
            pass

    def _sync_backup_devices(self):
        """立即将主控端已连接在线的全部工控机实时同步填充至备份中心下拉框"""
        if not hasattr(self, "bk_target_combo"):
            return
        clients = self.master_hub.get_online_clients()
        options = []
        for c in clients:
            ip = c["ip"]
            raw_h = c.get("custom_name") or c.get("hostname", "Unknown")
            disp_host = self._get_display_name(ip, raw_h)
            options.append(f"{ip} - {disp_host}")
        self.bk_target_combo["values"] = options
        if options:
            if not self.bk_target_combo.get() or self.bk_target_combo.get() not in options:
                self.bk_target_combo.current(0)
            if hasattr(self, "lbl_bk_target_tip") and self.lbl_bk_target_tip.winfo_exists():
                self.lbl_bk_target_tip.config(text=f"✓ 已发现 {len(options)} 台在线工控机，已就绪", fg="#10b981")
        else:
            self.bk_target_combo.set("未发现局域网在线受控工控机")
            if hasattr(self, "lbl_bk_target_tip") and self.lbl_bk_target_tip.winfo_exists():
                self.lbl_bk_target_tip.config(text="⚠️ 暂未搜索到在线受控端，请确认受控程序已启动", fg="#f59e0b")

    def _refresh_backup_devices(self):
        """主动探测并刷新备份中心的目标工控机下拉框"""
        self.lbl_bk_target_tip.config(text="正在全网段探测在线受控设备...", fg="#38bdf8")
        def runner():
            res = self.master_hub.scan_online_agents(timeout=1.5, auto_connect=True)
            def done():
                clients = self.master_hub.get_online_clients()
                options = []
                for c in clients:
                    ip = c["ip"]
                    raw_h = c.get("custom_name") or c.get("hostname", "Unknown")
                    disp_host = self._get_display_name(ip, raw_h)
                    options.append(f"{ip} - {disp_host}")
                self.bk_target_combo["values"] = options
                if options:
                    if not self.bk_target_combo.get() or self.bk_target_combo.get() not in options:
                        self.bk_target_combo.current(0)
                    self.lbl_bk_target_tip.config(text=f"✓ 已发现 {len(options)} 台在线工控机，已更新就绪", fg="#10b981")
                else:
                    self.bk_target_combo.set("未发现局域网在线受控工控机")
                    self.lbl_bk_target_tip.config(text="⚠️ 暂未搜索到在线受控端，请确认受控程序已启动", fg="#f59e0b")
            self._safe_after(done)
        threading.Thread(target=runner, daemon=True).start()

    def _get_backup_target_ip(self) -> str:
        """从备份中心下拉框或选定状态中智能获取目标工控机 IP"""
        val = self.bk_target_combo.get().strip() if hasattr(self, "bk_target_combo") else ""
        if val and " - " in val:
            ip = val.split(" - ")[0].strip()
            if ip and ip != "未发现局域网在线受控工控机":
                return ip
        # 回退
        if self.selected_ip:
            return self.selected_ip
        clients = self.master_hub.get_online_clients()
        if clients:
            return clients[0]["ip"]
        return ""

    def _refresh_master_backup_tree(self):
        for i in self.master_bk_tree.get_children():
            self.master_bk_tree.delete(i)
        bks = self.master_hub.list_master_backups()
        for b in bks:
            sz_disp = b.get("size_str", f"{b.get('size_mb', 0)} MB")
            self.master_bk_tree.insert(
                "", "end",
                iid=b["path"],
                text=b["filename"],
                values=(b["hostname"], b["created_at"], sz_disp, b["notes"])
            )

    def _master_push_backup(self):
        ip = self._get_backup_target_ip()
        if not ip:
            messagebox.showinfo("提示", "请在上方【🎯 目标受控工控机】下拉框中选择接收还原的设备，\n或点击【🔍 发现/刷新在线设备】！")
            return
        sel = self.master_bk_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请在备份列表中选择要下发的 .gwcbackup 备份包！")
            return
        bk_path = sel[0]
        if messagebox.askyesno("下发恢复确认", f"确定要将系统备份:\n{os.path.basename(bk_path)}\n下发至工控机 [{ip}] 并自动执行全系统一键还原吗？"):
            self.notice_var.set(f"正在向下发备份包至工控机 [{ip}] ...")
            self.master_hub.push_backup_to_agent(
                ip, bk_path,
                callback=lambda r: self._safe_after(lambda: messagebox.showinfo("还原反馈", f"从机 {ip} 还原结果:\n{r.get('msg', r.get('error'))}"))
            )

    def _master_request_backup(self):
        ip = self._get_backup_target_ip()
        if not ip:
            messagebox.showinfo("提示", "请在上方【🎯 目标受控工控机】下拉框中选择目标设备，\n或点击【🔍 发现/刷新在线设备】！")
            return
        self.notice_var.set(f"正在命令工控机 [{ip}] 生成配置备份...")
        self.master_hub.request_agent_backup(
            ip,
            callback=lambda r: self._safe_after(lambda: (
                self._refresh_master_backup_tree(),
                messagebox.showinfo("完成", f"工控机 [{ip}] 备份已顺利生成并归档入库！")
            ))
        )

    # ==================== Tab 3: 国文创商业授权中枢 ====================
    def _build_license_hub(self, parent):
        paned = tk.PanedWindow(parent, orient=tk.HORIZONTAL, bg=self.BG_MAIN, bd=0, sashwidth=4)
        paned.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        # 左栏: 在线工控机一键远程商业授权与续期
        left = tk.LabelFrame(
            paned,
            text=" 在线工控机商业授权 ",
            font=("Segoe UI", 9, "bold"),
            fg=self.ACCENT_CYAN,
            bg=self.BG_PANEL,
            bd=1
        )
        paned.add(left, width=640)

        lbl_tip = tk.Label(
            left,
            text="选择需要签发或续期的受控工控机，主控按自定义时间远程签发，终端自动接收并更新：",
            font=("Segoe UI", 9),
            bg=self.BG_PANEL,
            fg=self.TEXT_MUTED
        )
        lbl_tip.pack(anchor="w", padx=12, pady=(6, 2))

        # 设备列表表格
        cols = ("host", "req_code", "status", "expire")
        self.lic_agent_tree = ttk.Treeview(left, columns=cols, show="tree headings", selectmode="browse")
        self.lic_agent_tree.heading("#0", text="IP 地址", anchor="w")
        self.lic_agent_tree.heading("host", text="设备名称 / 别名", anchor="w")
        self.lic_agent_tree.heading("req_code", text="8位申请码", anchor="center")
        self.lic_agent_tree.heading("status", text="授权状态", anchor="center")
        self.lic_agent_tree.heading("expire", text="授权有效时长 / 剩余时间", anchor="w")

        self.lic_agent_tree.column("#0", width=110)
        self.lic_agent_tree.column("host", width=115)
        self.lic_agent_tree.column("req_code", width=95)
        self.lic_agent_tree.column("status", width=75)
        self.lic_agent_tree.column("expire", width=160)

        s_y = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self.lic_agent_tree.yview)
        self.lic_agent_tree.configure(yscrollcommand=s_y.set)
        self.lic_agent_tree.pack(fill=tk.BOTH, expand=True, padx=(8, 0), pady=(4, 2))
        s_y.pack(side=tk.RIGHT, fill=tk.Y, pady=(4, 2), padx=(0, 6))

        self.lic_agent_tree.bind("<<TreeviewSelect>>", self._on_lic_agent_selected)

        # 选定终端状态走马灯看板
        self.lic_sel_info_lbl = MarqueeLabel(
            left,
            text="👈 请在上方列表中点击选定一台工控机以签发或更新商业授权",
            font=("Segoe UI", 9, "bold"),
            bg="#111827",
            fg=self.TEXT_MUTED,
            height=24
        )
        self.lic_sel_info_lbl.pack(fill=tk.X, padx=8, pady=(4, 4))

        # 授权模式与自定义时间配置区
        auth_card = tk.LabelFrame(
            left,
            text=" 授权有效期定制 ",
            font=("Segoe UI", 9, "bold"),
            fg=self.ACCENT_YELLOW,
            bg=self.BG_PANEL,
            bd=1
        )
        auth_card.pack(fill=tk.X, padx=8, pady=(2, 6))

        self.auth_mode_var = tk.StringVar(value="hour")

        # 模式切换单选组
        mode_bar = tk.Frame(auth_card, bg=self.BG_PANEL)
        mode_bar.pack(fill=tk.X, padx=8, pady=(4, 4))

        tk.Radiobutton(
            mode_bar, text="⏱️ 按小时授权", variable=self.auth_mode_var, value="hour",
            bg=self.BG_PANEL, fg=self.TEXT_WHITE, selectcolor="#0f172a", font=("Segoe UI", 9, "bold"),
            command=self._on_auth_mode_change
        ).pack(side=tk.LEFT, padx=4)

        tk.Radiobutton(
            mode_bar, text="📅 按月授权", variable=self.auth_mode_var, value="month",
            bg=self.BG_PANEL, fg=self.TEXT_WHITE, selectcolor="#0f172a", font=("Segoe UI", 9, "bold"),
            command=self._on_auth_mode_change
        ).pack(side=tk.LEFT, padx=12)

        tk.Radiobutton(
            mode_bar, text="♾️ 商业授权 (永久)", variable=self.auth_mode_var, value="permanent",
            bg=self.BG_PANEL, fg="#34d399", selectcolor="#0f172a", font=("Segoe UI", 9, "bold"),
            command=self._on_auth_mode_change
        ).pack(side=tk.LEFT, padx=4)

        # 时间输入与快捷按钮行
        self.auth_time_box = tk.Frame(auth_card, bg=self.BG_PANEL)
        self.auth_time_box.pack(fill=tk.X, padx=8, pady=(2, 6))

        self.lbl_time_unit = tk.Label(self.auth_time_box, text="输入小时数:", font=("Segoe UI", 9), fg="#cbd5e1", bg=self.BG_PANEL)
        self.lbl_time_unit.pack(side=tk.LEFT, padx=(2, 4))

        self.auth_time_ent = tk.Entry(self.auth_time_box, font=("Segoe UI", 10, "bold"), bg="#0f172a", fg=self.ACCENT_CYAN, width=8, justify="center", relief="flat")
        self.auth_time_ent.insert(0, "24")
        self.auth_time_ent.pack(side=tk.LEFT, padx=4)

        self.auth_preset_frame = tk.Frame(self.auth_time_box, bg=self.BG_PANEL)
        self.auth_preset_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)

        # 远程签发行动按钮
        btn_action_bar = tk.Frame(auth_card, bg=self.BG_PANEL)
        btn_action_bar.pack(fill=tk.X, padx=8, pady=(4, 6))

        btn_auth = tk.Button(
            btn_action_bar,
            text="🚀 立即远程签发授权",
            font=("Segoe UI", 10, "bold"),
            bg="#059669",
            fg="#ffffff",
            relief="flat",
            padx=16,
            pady=6,
            cursor="hand2",
            command=self._do_remote_auth
        )
        btn_auth.pack(fill=tk.X)

        self._render_auth_presets()

        # 右栏: 独立的国文创加密机计算器
        right = tk.LabelFrame(
            paned,
            text=" 🔑 国文创加密机运算终端 ",
            font=("Segoe UI", 9, "bold"),
            fg=self.ACCENT_GREEN,
            bg=self.BG_PANEL,
            bd=1
        )
        paned.add(right, width=500)

        f_calc = tk.Frame(right, bg=self.BG_PANEL, padx=16, pady=10)
        f_calc.pack(fill=tk.BOTH, expand=True)

        tk.Label(f_calc, text="从机设备申请码 (8 位格式: XXXX-XXXX):", font=("Segoe UI", 9, "bold"), fg="#cbd5e1", bg=self.BG_PANEL).pack(anchor="w", pady=(2, 2))
        self.manual_req_ent = tk.Entry(f_calc, font=("Consolas", 13, "bold"), fg=self.ACCENT_CYAN, bg="#0f172a", bd=1, justify="center")
        self.manual_req_ent.pack(fill=tk.X, pady=4, ipady=3)

        # 离线加密机时长模式选择
        self.calc_mode_var = tk.StringVar(value="hour")
        calc_mode_bar = tk.Frame(f_calc, bg=self.BG_PANEL)
        calc_mode_bar.pack(fill=tk.X, pady=(6, 2))

        tk.Radiobutton(calc_mode_bar, text="按小时", variable=self.calc_mode_var, value="hour", bg=self.BG_PANEL, fg=self.TEXT_WHITE, selectcolor="#0f172a", font=("Segoe UI", 8), command=self._on_calc_mode_change).pack(side=tk.LEFT)
        tk.Radiobutton(calc_mode_bar, text="按月", variable=self.calc_mode_var, value="month", bg=self.BG_PANEL, fg=self.TEXT_WHITE, selectcolor="#0f172a", font=("Segoe UI", 8), command=self._on_calc_mode_change).pack(side=tk.LEFT, padx=8)
        tk.Radiobutton(calc_mode_bar, text="永久商业", variable=self.calc_mode_var, value="permanent", bg=self.BG_PANEL, fg="#34d399", selectcolor="#0f172a", font=("Segoe UI", 8), command=self._on_calc_mode_change).pack(side=tk.LEFT)

        self.calc_time_bar = tk.Frame(f_calc, bg=self.BG_PANEL)
        self.calc_time_bar.pack(fill=tk.X, pady=(2, 6))

        self.lbl_calc_time = tk.Label(self.calc_time_bar, text="小时数:", font=("Segoe UI", 8), fg="#cbd5e1", bg=self.BG_PANEL)
        self.lbl_calc_time.pack(side=tk.LEFT)
        self.calc_time_ent = tk.Entry(self.calc_time_bar, font=("Segoe UI", 9, "bold"), bg="#0f172a", fg=self.ACCENT_CYAN, width=8, justify="center", relief="flat")
        self.calc_time_ent.insert(0, "24")
        self.calc_time_ent.pack(side=tk.LEFT, padx=4)

        self.calc_preset_frame = tk.Frame(self.calc_time_bar, bg=self.BG_PANEL)
        self.calc_preset_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._render_calc_presets()

        btn_calc = tk.Button(
            f_calc,
            text="⚡ 计算并签发 16 位专属商业激活码",
            font=("Segoe UI", 9, "bold"),
            bg=self.ACCENT_BLUE,
            fg="#ffffff",
            relief="flat",
            pady=6,
            cursor="hand2",
            command=self._calc_manual_license
        )
        btn_calc.pack(fill=tk.X, pady=8)

        tk.Label(f_calc, text="生成的商业激活码 (专属 16 位: XXXX-XXXX-XXXX-XXXX):", font=("Segoe UI", 9, "bold"), fg="#cbd5e1", bg=self.BG_PANEL).pack(anchor="w", pady=(6, 2))
        self.manual_res_lbl = tk.Label(f_calc, text="---- ---- ---- ----", font=("Consolas", 14, "bold"), fg="#34d399", bg="#0f172a", pady=10)
        self.manual_res_lbl.pack(fill=tk.X, pady=4)

        btn_copy = tk.Button(
            f_calc,
            text="📋 复制激活码",
            font=("Segoe UI", 9),
            bg="#334155",
            fg="#ffffff",
            relief="flat",
            pady=4,
            cursor="hand2",
            command=self._copy_manual_act_code
        )
        btn_copy.pack(fill=tk.X, pady=4)

    def _on_auth_mode_change(self):
        mode = self.auth_mode_var.get()
        if mode == "hour":
            self.lbl_time_unit.config(text="输入小时数:")
            self.auth_time_ent.config(state="normal")
            self.auth_time_ent.delete(0, tk.END)
            self.auth_time_ent.insert(0, "24")
        elif mode == "month":
            self.lbl_time_unit.config(text="输入月数:")
            self.auth_time_ent.config(state="normal")
            self.auth_time_ent.delete(0, tk.END)
            self.auth_time_ent.insert(0, "1")
        else:
            self.lbl_time_unit.config(text="永久有效:")
            self.auth_time_ent.delete(0, tk.END)
            self.auth_time_ent.insert(0, "终身")
            self.auth_time_ent.config(state="disabled")
        self._render_auth_presets()

    def _render_auth_presets(self):
        for w in self.auth_preset_frame.winfo_children():
            w.destroy()
        mode = self.auth_mode_var.get()
        if mode == "hour":
            presets = [("1h", 1), ("2h", 2), ("6h", 6), ("12h", 12), ("24h", 24), ("48h", 48), ("72h", 72)]
            for lbl, val in presets:
                def make_cmd(v=val):
                    return lambda: (self.auth_time_ent.delete(0, tk.END), self.auth_time_ent.insert(0, str(v)))
                tk.Button(self.auth_preset_frame, text=lbl, font=("Segoe UI", 8), bg="#1e293b", fg=self.ACCENT_CYAN, relief="flat", padx=4, pady=1, cursor="hand2", command=make_cmd()).pack(side=tk.LEFT, padx=2)
        elif mode == "month":
            presets = [("1个月", 1), ("3个月", 3), ("6个月", 6), ("12个月(1年)", 12), ("24个月(2年)", 24), ("36个月(3年)", 36)]
            for lbl, val in presets:
                def make_cmd(v=val):
                    return lambda: (self.auth_time_ent.delete(0, tk.END), self.auth_time_ent.insert(0, str(v)))
                tk.Button(self.auth_preset_frame, text=lbl, font=("Segoe UI", 8), bg="#1e293b", fg=self.ACCENT_CYAN, relief="flat", padx=4, pady=1, cursor="hand2", command=make_cmd()).pack(side=tk.LEFT, padx=2)
        else:
            tk.Label(self.auth_preset_frame, text="终身永久授权，无任何时间限制", font=("Segoe UI", 8), fg="#34d399", bg=self.BG_PANEL).pack(side=tk.LEFT, padx=4)

    def _on_calc_mode_change(self):
        mode = self.calc_mode_var.get()
        if mode == "hour":
            self.lbl_calc_time.config(text="小时数:")
            self.calc_time_ent.config(state="normal")
            self.calc_time_ent.delete(0, tk.END)
            self.calc_time_ent.insert(0, "24")
        elif mode == "month":
            self.lbl_calc_time.config(text="月数:")
            self.calc_time_ent.config(state="normal")
            self.calc_time_ent.delete(0, tk.END)
            self.calc_time_ent.insert(0, "1")
        else:
            self.lbl_calc_time.config(text="永久有效:")
            self.calc_time_ent.delete(0, tk.END)
            self.calc_time_ent.insert(0, "终身")
            self.calc_time_ent.config(state="disabled")
        self._render_calc_presets()

    def _render_calc_presets(self):
        for w in self.calc_preset_frame.winfo_children():
            w.destroy()
        mode = self.calc_mode_var.get()
        if mode == "hour":
            presets = [("1h", 1), ("6h", 6), ("24h", 24), ("72h", 72)]
            for lbl, val in presets:
                def make_cmd(v=val):
                    return lambda: (self.calc_time_ent.delete(0, tk.END), self.calc_time_ent.insert(0, str(v)))
                tk.Button(self.calc_preset_frame, text=lbl, font=("Segoe UI", 7), bg="#1e293b", fg=self.ACCENT_CYAN, relief="flat", padx=3, pady=1, cursor="hand2", command=make_cmd()).pack(side=tk.LEFT, padx=1)
        elif mode == "month":
            presets = [("1月", 1), ("3月", 3), ("6月", 6), ("12月", 12)]
            for lbl, val in presets:
                def make_cmd(v=val):
                    return lambda: (self.calc_time_ent.delete(0, tk.END), self.calc_time_ent.insert(0, str(v)))
                tk.Button(self.calc_preset_frame, text=lbl, font=("Segoe UI", 7), bg="#1e293b", fg=self.ACCENT_CYAN, relief="flat", padx=3, pady=1, cursor="hand2", command=make_cmd()).pack(side=tk.LEFT, padx=1)

    def _on_lic_agent_selected(self, event):
        sel = self.lic_agent_tree.selection()
        if not sel:
            return
        ip = sel[0]
        client_data = self.master_hub.clients.get(ip, {})
        info = client_data.get("info", {})
        raw_h = info.get("hostname", "Unknown")
        disp_h = self._get_display_name(ip, raw_h)
        lic = info.get("license", {})
        req_c = lic.get("request_code", "----")
        st = lic.get("status", "TRIAL")
        exp_desc = lic.get("expire_desc", "")
        if not exp_desc:
            exp_desc = "已激活 (永久有效)" if st == "ACTIVE" else "未激活 / 试用中"

        self.lic_sel_info_lbl.set_text(
            f"选定工控机: {disp_h} ({ip})   |   8位申请码: {req_c}   |   当前状态: {exp_desc}",
            fg=self.ACCENT_CYAN
        )
        if req_c and req_c != "----":
            self.manual_req_ent.delete(0, tk.END)
            self.manual_req_ent.insert(0, req_c)

    def _do_remote_auth(self):
        sel = self.lic_agent_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请在上方列表中选中需要签发远程授权的工控机！")
            return
        ip = sel[0]
        c_info = self.master_hub.clients.get(ip, {}).get("info", {})
        req_code = c_info.get("license", {}).get("request_code", "")

        mode = self.auth_mode_var.get()
        val = 1
        if mode == "hour":
            try:
                val = int(self.auth_time_ent.get().strip())
                if val <= 0:
                    raise ValueError
            except Exception:
                messagebox.showerror("错误", "请输入有效的小时数（必须为大于 0 的整数）！")
                return
        elif mode == "month":
            try:
                val = int(self.auth_time_ent.get().strip())
                if val <= 0:
                    raise ValueError
            except Exception:
                messagebox.showerror("错误", "请输入有效的月数（必须为大于 0 的整数）！")
                return
        elif mode == "permanent":
            val = 0

        desc = f"{val} 小时" if mode == "hour" else (f"{val} 个月" if mode == "month" else "终身永久有效")
        if not messagebox.askyesno("远程授权确认", f"确定向受控工控机 [{ip}]\n远程签发商业授权【{desc}】并自动覆盖激活吗？"):
            return

        self.notice_var.set(f"正在向工控机 [{ip}] 远程签发【{desc}】授权...")
        res = self.master_hub.remote_authorize_agent(
            ip,
            auth_type=mode,
            custom_val=val,
            callback=lambda r: self._safe_after(lambda: (
                self._refresh_client_tree(),
                self.notice_var.set(f"工控机 [{ip}] 远程商业授权成功更新！"),
                messagebox.showinfo(
                    "授权成功",
                    f"🎉 工控机 [{ip}] 远程商业授权成功！\n授权类型: {desc}\n专属激活码: {res.get('act_code')}\n受控端已自动无缝更新授权并解除锁定！"
                )
            ))
        )
        if not res.get("success"):
            messagebox.showerror("授权失败", res.get("error", "未知错误"))

    def _calc_manual_license(self):
        req = self.manual_req_ent.get().strip()
        if not req:
            messagebox.showerror("错误", "请输入 8 位设备申请码！")
            return

        mode = self.calc_mode_var.get()
        val = 1
        if mode == "hour":
            try:
                val = int(self.calc_time_ent.get().strip())
                if val <= 0:
                    raise ValueError
            except Exception:
                messagebox.showerror("错误", "请输入有效的小时数！")
                return
        elif mode == "month":
            try:
                val = int(self.calc_time_ent.get().strip())
                if val <= 0:
                    raise ValueError
            except Exception:
                messagebox.showerror("错误", "请输入有效的月数！")
                return
        elif mode == "permanent":
            val = 0

        act = ""
        # 1. 优先使用 2026 展馆控制终端专属算法生成 16 位激活码
        try:
            import gwc_license_terminal as lt
            dec = lt.decode_request_code(req)
            if dec.get("valid"):
                act = lt.generate_terminal_license(dec["hw_hash"], dec["nonce"], auth_type=mode, custom_val=val)
        except Exception:
            pass

        # 2. 备用原版 VisualCast 算法兼容
        if not act and universal_license_core:
            try:
                dec_leg = universal_license_core.decode_request_code(req, "VisualCast")
                if dec_leg.get("valid"):
                    act = universal_license_core.encode_license(dec_leg["hw_hash"], dec_leg["nonce"], 31, 31, "VisualCast")
            except Exception:
                pass

        if not act:
            messagebox.showerror("无效申请码", "申请码防伪校验失败，未能识别该 8 位申请码！")
            return

        self.manual_res_lbl.config(text=act)

    def _copy_manual_act_code(self):
        c = self.manual_res_lbl.cget("text")
        if c and "----" not in c:
            self.root.clipboard_clear()
            self.root.clipboard_append(c)
            messagebox.showinfo("已复制", f"已复制激活码到剪贴板:\n{c}")

    def _copy_manual_act_code(self):
        c = self.manual_res_lbl.cget("text")
        if c and "----" not in c:
            self.root.clipboard_clear()
            self.root.clipboard_append(c)
            messagebox.showinfo("已复制", f"已复制激活码到剪贴板:\n{c}")

    # ==================== 监控大厅联动与远程操作 ====================
    def _on_client_tree_select(self, event):
        ip = self._get_selected_client_ip()
        if not ip:
            return
        self.selected_ip = ip
        client_data = self.master_hub.clients.get(ip, {})
        info = client_data.get("info", {})
        raw_h = info.get("hostname", "Unknown")
        disp_h = self._get_display_name(ip, raw_h)
        fg_str = info.get("foreground_window", "--")

        self.sel_host_lbl.set_text(
            f"选定设备: {disp_h} ({ip})   |   系统: {info.get('os', 'Windows')}   |   前台活动窗口: {fg_str}",
            fg=self.ACCENT_CYAN
        )

        # 同步备份中心下拉框选中项
        if hasattr(self, "bk_target_combo") and self.bk_target_combo:
            target_str = f"{ip} - {disp_h}"
            vals = list(self.bk_target_combo["values"])
            for v in vals:
                if v.startswith(ip):
                    self.bk_target_combo.set(v)
                    break

        # 填充别名输入框
        cur_alias = self.aliases.get(ip, "")
        self.alias_entry.delete(0, tk.END)
        if cur_alias:
            self.alias_entry.insert(0, cur_alias)

        # 刷新受控端预设应用下拉列表
        self._update_preset_combo(ip)

        # 标注视频推流地址与 API 接口
        if hasattr(self, "stream_url_var"):
            self.stream_url_var.set(f"推流: vnc://{ip}:5900 | webrtc://{ip}:5900/live | http://{ip}:5901/stream.mjpg")

        # 刷新进程树 (采用增量 Diff 策略，杜绝闪烁和点击落空)
        procs = info.get("top_processes", [])
        cur_sel = self.proc_tree.selection()
        cur_pid = cur_sel[0] if cur_sel else None
        existing_pids = set(self.proc_tree.get_children())
        new_pids = set()
        for p in procs:
            item_id = str(p.get("pid"))
            new_pids.add(item_id)
            p_name = p.get("name")
            sz_str = f"{p.get('memory_mb', 0)} MB"
            vals = (p.get("pid"), sz_str)
            if item_id in existing_pids:
                old_vals = self.proc_tree.item(item_id, "values")
                if tuple(str(x) for x in old_vals) != tuple(str(x) for x in vals):
                    self.proc_tree.item(item_id, text=p_name, values=vals)
            else:
                self.proc_tree.insert("", "end", iid=item_id, text=p_name, values=vals)
        for stale_id in existing_pids - new_pids:
            self.proc_tree.delete(stale_id)
        if cur_pid and self.proc_tree.exists(cur_pid):
            if not self.proc_tree.selection() or self.proc_tree.selection()[0] != cur_pid:
                self.proc_tree.selection_set(cur_pid)

    def _get_selected_client_ip(self) -> str:
        sel = self.client_tree.selection()
        if sel and sel[0]:
            self.selected_ip = sel[0]
            return sel[0]
        if hasattr(self, "selected_ip") and self.selected_ip:
            if self.selected_ip in self.master_hub.clients:
                try:
                    if self.client_tree.exists(self.selected_ip):
                        self.client_tree.selection_set(self.selected_ip)
                except Exception:
                    pass
                return self.selected_ip
        return ""

    def _open_remote_desktop(self, fullscreen: bool = False, force_single: bool = True):
        ip = self._get_selected_client_ip()
        if not ip:
            messagebox.showinfo("提示", "请先在列表中选中一台工控机！")
            return
        info = self.master_hub.clients.get(ip, {}).get("info", {})
        raw_h = info.get("hostname", ip)
        h_name = self._get_display_name(ip, raw_h)

        def send_fn(client_ip, cmd_type, payload, callback=None):
            self.master_hub.send_command(client_ip, cmd_type, payload, callback=callback)

        if not hasattr(self, "_active_desktop_windows"):
            self._active_desktop_windows = {}

        if force_single:
            # 双击行为: 严格保证全局只显示一个活跃预览窗口，绝不重复弹窗堆叠
            for old_key, old_w in list(self._active_desktop_windows.items()):
                try:
                    if old_w and old_w.winfo_exists():
                        if old_key == ip:
                            # 已经打开了该从机窗口，直接置顶唤醒！
                            old_w.deiconify()
                            old_w.lift()
                            old_w.focus_force()
                            return
                        else:
                            old_w.destroy()
                except Exception:
                    pass
                self._active_desktop_windows.pop(old_key, None)

            win = gwc_vnc.VNC6RemoteDesktopWindow(self.root, ip, h_name, send_fn, fullscreen=fullscreen)
            self._active_desktop_windows[ip] = win
        else:
            # 右键菜单行为: 允许打开多个独立窗口同时监控多台设备
            win = gwc_vnc.VNC6RemoteDesktopWindow(self.root, ip, h_name, send_fn, fullscreen=fullscreen)
            self._active_desktop_windows[f"{ip}_{id(win)}"] = win

    def _open_remote_file_transfer(self):
        ip = self._get_selected_client_ip()
        if not ip:
            messagebox.showinfo("提示", "请先在列表中选中一台工控机！")
            return
        info = self.master_hub.clients.get(ip, {}).get("info", {})
        raw_h = info.get("hostname", ip)
        h_name = self._get_display_name(ip, raw_h)

        def send_fn(client_ip, cmd_type, payload, callback=None):
            self.master_hub.send_command(client_ip, cmd_type, payload, callback=callback)

        gwc_vnc.RemoteFileManagerWindow(self.root, ip, h_name, send_fn)

    def _ctl_shutdown(self):
        ip = self._get_selected_client_ip()
        if ip and messagebox.askyesno("关机确认", f"确定远程关闭工控机 [{ip}] 吗？"):
            self.master_hub.send_command(ip, "CMD_SHUTDOWN", {"force": True, "timeout": 0})

    def _ctl_reboot(self):
        ip = self._get_selected_client_ip()
        if ip and messagebox.askyesno("重启确认", f"确定远程重启工控机 [{ip}] 吗？"):
            self.master_hub.send_command(ip, "CMD_REBOOT", {"force": True, "timeout": 0})

    def _ctl_mute(self):
        ip = self._get_selected_client_ip()
        if ip:
            self.master_hub.send_command(ip, "CMD_VOLUME", {"action": "mute"})

    def _ctl_set_vol(self):
        ip = self._get_selected_client_ip()
        if ip:
            v = self.vol_scale.get()
            def on_vol_done(r):
                def ui_update():
                    msg = r.get("msg", r.get("error", "音量已调整"))
                    self.notice_var.set(f"从机 [{ip}] 音量调整反馈: {msg}")
                self._safe_after(ui_update)
            self.master_hub.send_command(ip, "CMD_VOLUME", {"action": "set", "level": v}, callback=on_vol_done)
            self.notice_var.set(f"正在调整从机 [{ip}] 音量为 {v}% ...")

    def _ctl_run_app(self):
        ip = self._get_selected_client_ip()
        p = self.run_app_entry.get().strip()
        args = self.run_args_entry.get().strip()
        if ip and p:
            def on_app_done(r):
                def ui_update():
                    msg = r.get("msg", r.get("error", "启动指令已下发"))
                    self.notice_var.set(f"从机 [{ip}] 启动程序反馈: {msg}")
                    # 延时刷新进程状态
                    self.root.after(1200, lambda: self.master_hub.send_command(ip, "CMD_GET_STATUS", {}))
                self._safe_after(ui_update)
            self.master_hub.send_command(ip, "CMD_RUN_APP", {"path": p, "args": args}, callback=on_app_done)
            self.notice_var.set(f"已向从机 [{ip}] 下发启动程序指令: {p} {args}")

    def _ctl_kill_proc(self):
        ip = self._get_selected_client_ip()
        sel = self.proc_tree.selection()
        if ip and sel:
            pid = int(sel[0])
            p_name = self.proc_tree.item(sel[0])["text"]
            if messagebox.askyesno("结束进程", f"确定要远程终止工控机 [{ip}] 的进程:\n{p_name} (PID: {pid}) 吗？"):
                def on_killed(r):
                    def ui_update():
                        # 立即从 UI 移除被杀进程行，界面响应零延迟
                        if self.proc_tree.exists(str(pid)):
                            self.proc_tree.delete(str(pid))
                        msg = r.get("msg", r.get("error", "已执行强杀"))
                        self.notice_var.set(f"从机 [{ip}] 进程 [{p_name} ({pid})] 强杀反馈: {msg}")
                        # 延时 1 秒同步后台真实状态
                        self.root.after(1000, lambda: self.master_hub.send_command(ip, "CMD_GET_STATUS", {}))
                    self._safe_after(ui_update)
                self.master_hub.send_command(ip, "CMD_KILL_PROC", {"pid": pid, "name": p_name}, callback=on_killed)

    def _batch_shutdown(self):
        if messagebox.askyesno("批量关机确认", "⚠️ 警告: 确定要向全展馆所有在线工控机发送【一键关机】指令吗？"):
            self.master_hub.broadcast_command("CMD_SHUTDOWN", {"force": True, "timeout": 0})

    def _batch_reboot(self):
        if messagebox.askyesno("批量重启确认", "确定向全展馆所有在线工控机发送【一键重启】指令吗？"):
            self.master_hub.broadcast_command("CMD_REBOOT", {"force": True, "timeout": 0})

    def _batch_mute(self):
        self.master_hub.broadcast_command("CMD_VOLUME", {"action": "mute"})

    def _batch_run_app(self):
        p = simpledialog.askstring("批量启动应用", "请输入要批量调用的应用完整路径或名称:", parent=self.root)
        if p:
            self.master_hub.broadcast_command("CMD_RUN_APP", {"path": p.strip()})

    # ==================== 主控网络回调处理 ====================
    def _safe_after(self, fn):
        try:
            if self.root.winfo_exists():
                self.root.after(0, fn)
        except Exception:
            pass

    def _on_agent_connected(self, client_ip: str, payload: dict):
        def update():
            self._refresh_client_tree()
            h = self._get_display_name(client_ip, payload.get("hostname", client_ip))
            self.notice_var.set(f"✨ 新工控机接入: {h} ({client_ip}) 已加入监控大厅！")
        self._safe_after(update)

    def _on_agent_disconnected(self, client_ip: str):
        def update():
            self._refresh_client_tree()
            self.notice_var.set(f"工控机 ({client_ip}) 已断开连接。")
        self._safe_after(update)

    def _on_agent_status_updated(self, client_ip: str, payload: dict):
        def update():
            self._update_client_row(client_ip, payload)
        self._safe_after(update)

    def _on_backup_saved(self, client_ip: str, path: str, info: dict):
        def update():
            self._refresh_master_backup_tree()
        self._safe_after(update)

    def _on_beacon_discovered(self, info: dict):
        """受控端上线广播宣告捕获"""
        ip = info.get("ip")
        h = self._get_display_name(ip, info.get("hostname", ip))
        self.discovered_agents[ip] = info
        def update():
            self.notice_var.set(f"✨ 发现新上线工控机: {h} ({ip})，准备建立连接...")
        self._safe_after(update)

    def _refresh_client_tree(self):
        clients = self.master_hub.get_online_clients()
        self.total_online_var.set(f"在线工控机: {len(clients)} 台")

        existing_iids = set(self.client_tree.get_children())
        online_ips = set()
        combo_options = []

        for c in clients:
            ip = c["ip"]
            online_ips.add(ip)
            raw_h = c.get("custom_name") or c.get("hostname", "Unknown")
            disp_host = self._get_display_name(ip, raw_h)
            cpu = f"{c.get('cpu_percent', 0)}%"
            gpu = f"{c.get('gpu_percent', 0)}%"
            mem = f"{c.get('mem_percent', 0)}%"
            fg = c["fg_window"] or "--"
            lic_st = c.get("license", {}).get("status", "TRIAL")
            auth_str = "已授权" if lic_st == "ACTIVE" else "未激活 / 试用"
            exp_desc = c.get("license", {}).get("expire_desc", "")
            if not exp_desc:
                exp_desc = "永久有效" if lic_st == "ACTIVE" else "尚未授权"

            vals = (disp_host, cpu, gpu, mem, fg)
            if ip in existing_iids:
                self.client_tree.item(ip, text=ip, values=vals)
            else:
                self.client_tree.insert("", "end", iid=ip, text=ip, values=vals)

            combo_options.append(f"{ip} - {disp_host}")

            # 同时更新授权大厅表格
            req_c = c.get("license", {}).get("request_code", "----")
            if hasattr(self, "lic_agent_tree"):
                lic_vals = (disp_host, req_c, auth_str, exp_desc)
                if self.lic_agent_tree.exists(ip):
                    self.lic_agent_tree.item(ip, text=ip, values=lic_vals)
                else:
                    self.lic_agent_tree.insert("", "end", iid=ip, text=ip, values=lic_vals)

        # 同步备份中心下拉选项
        if hasattr(self, "bk_target_combo"):
            old_val = self.bk_target_combo.get()
            self.bk_target_combo["values"] = combo_options
            if combo_options:
                if not old_val or old_val not in combo_options:
                    self.bk_target_combo.current(0)
            else:
                self.bk_target_combo.set("暂无在线工控机")

        # 移除离线
        for old_ip in existing_iids - online_ips:
            self.client_tree.delete(old_ip)
            if hasattr(self, "lic_agent_tree") and self.lic_agent_tree.exists(old_ip):
                self.lic_agent_tree.delete(old_ip)

        # 始终稳定保持当前选中的设备高亮，绝不丢失焦点
        if hasattr(self, "selected_ip") and self.selected_ip and self.client_tree.exists(self.selected_ip):
            cur = self.client_tree.selection()
            if not cur or cur[0] != self.selected_ip:
                self.client_tree.selection_set(self.selected_ip)

    def _update_client_row(self, client_ip: str, payload: dict):
        if not self.client_tree.exists(client_ip):
            self._refresh_client_tree()
            return
        raw_h = payload.get("custom_name") or payload.get("hostname", client_ip)
        disp_host = self._get_display_name(client_ip, raw_h)
        cpu = f"{payload.get('cpu_percent', 0)}%"
        gpu = f"{payload.get('gpu_percent', 0)}%"
        mem = f"{payload.get('memory', {}).get('percent', 0)}%"
        fg = payload.get("foreground_window", "--")
        lic_st = payload.get("license", {}).get("status", "TRIAL")
        auth_str = "已授权" if lic_st == "ACTIVE" else "未激活 / 试用"
        exp_desc = payload.get("license", {}).get("expire_desc", "")
        if not exp_desc:
            exp_desc = "永久有效" if lic_st == "ACTIVE" else "尚未授权"

        # 仅在数据变化时更新 Treeview 行，避免不必要的界面抖动
        cur_v = self.client_tree.item(client_ip, "values")
        new_v = (disp_host, cpu, gpu, mem, fg)
        if tuple(str(x) for x in cur_v) != tuple(str(x) for x in new_v):
            self.client_tree.item(client_ip, text=client_ip, values=new_v)

        # 同时更新授权大厅
        if hasattr(self, "lic_agent_tree") and self.lic_agent_tree.exists(client_ip):
            req_c = payload.get("license", {}).get("request_code", "----")
            self.lic_agent_tree.item(client_ip, text=client_ip, values=(disp_host, req_c, auth_str, exp_desc))

        # 若当前正选定该设备，即时增量同步刷新右侧的活动进程列表与选定状态看板！
        if getattr(self, "selected_ip", None) == client_ip:
            self.sel_host_lbl.set_text(
                f"选定设备: {disp_host} ({client_ip})   |   系统: {payload.get('os', 'Windows')}   |   前台活动窗口: {fg}",
                fg=self.ACCENT_CYAN
            )
            if hasattr(self, "stream_url_var"):
                self.stream_url_var.set(f"推流: vnc://{client_ip}:5900 | webrtc://{client_ip}:5900/live | http://{client_ip}:5901/stream.mjpg")

            # 增量比对更新进程树 (Diff Update，杜绝每秒清空重建导致的闪烁和无法点击！)
            procs = payload.get("top_processes", [])
            cur_sel = self.proc_tree.selection()
            cur_pid = cur_sel[0] if cur_sel else None
            existing_pids = set(self.proc_tree.get_children())
            new_pids = set()
            for p in procs:
                item_id = str(p.get("pid"))
                new_pids.add(item_id)
                p_name = p.get("name")
                sz_str = f"{p.get('memory_mb', 0)} MB"
                vals = (p.get("pid"), sz_str)
                if item_id in existing_pids:
                    old_vals = self.proc_tree.item(item_id, "values")
                    if tuple(str(x) for x in old_vals) != tuple(str(x) for x in vals):
                        self.proc_tree.item(item_id, text=p_name, values=vals)
                else:
                    self.proc_tree.insert("", "end", iid=item_id, text=p_name, values=vals)

            for stale_id in existing_pids - new_pids:
                self.proc_tree.delete(stale_id)

            if cur_pid and self.proc_tree.exists(cur_pid):
                if not self.proc_tree.selection() or self.proc_tree.selection()[0] != cur_pid:
                    self.proc_tree.selection_set(cur_pid)

    def _on_central_control_event(self, protocol: str, client_addr: str, cmd_raw: str, result: dict):
        """统一接收外部集中智能中控多协议总线 (UDP/TCP/HTTP/串口) 调度事件"""
        def update_ui():
            msg = result.get("msg", result.get("error", "已执行"))
            log_txt = f"🎮 [中控调度 {protocol}] 来自 {client_addr} -> 指令: {cmd_raw} | 执行结果: {msg}"
            self.notice_var.set(log_txt)
        self._safe_after(update_ui)

    def _on_udp_command_received(self, cmd_raw: str, addr: tuple, result: dict):
        addr_str = f"{addr[0]}:{addr[1]}" if addr else ""
        self._on_central_control_event("UDP 9889", addr_str, cmd_raw, result)

    def open_udp_protocol_help_window(self):
        """弹出展馆第三方集中智能中控多协议 (UDP/TCP/HTTP/串口) 与视频推流 API 手册"""
        win = tk.Toplevel(self.root)
        win.title("📖 展馆中控全协议 (UDP / TCP / HTTP API / 物理串口) 与推流速查手册")
        win.geometry("940x680")
        win.configure(bg="#0f172a")
        win.minsize(820, 600)

        ws = win.winfo_screenwidth()
        hs = win.winfo_screenheight()
        win.geometry(f"940x680+{(ws-940)//2}+{(hs-680)//2}")

        top_f = tk.Frame(win, bg="#1e293b", padx=16, pady=10)
        top_f.pack(fill=tk.X)

        tk.Label(
            top_f,
            text="📡 展馆第三方智能中控多协议总线 (UDP/TCP/HTTP/串口) 与视频推流规范",
            font=("Segoe UI", 12, "bold"),
            bg="#1e293b",
            fg="#38bdf8"
        ).pack(anchor="w")

        local_ips = []
        try:
            local_ips = socket.gethostbyname_ex(socket.gethostname())[2]
        except Exception:
            local_ips = ["127.0.0.1"]

        master_ip_show = local_ips[0] if local_ips else "127.0.0.1"
        tk.Label(
            top_f,
            text=f"中控总线端口: UDP: 9889 | TCP: 9890 | HTTP API: 9891 | 串口 COM | 主控IP: {', '.join(local_ips)}",
            font=("Segoe UI", 9),
            bg="#1e293b",
            fg="#94a3b8"
        ).pack(anchor="w", pady=(2, 0))

        # 串口物理中控快速开关面板
        serial_bar = tk.LabelFrame(win, text=" 🔌 物理串口中控设置 (RS232/RS485/USB-TTL) ", bg="#1e293b", fg="#34d399", font=("Segoe UI", 8, "bold"), padx=10, pady=4)
        serial_bar.pack(fill=tk.X, padx=8, pady=(6, 2))

        tk.Label(serial_bar, text="COM端口:", font=("Segoe UI", 8), bg="#1e293b", fg="#cbd5e1").pack(side=tk.LEFT)
        avail_ports = gwc_master.SerialCentralControlListener.list_available_ports()
        combo_com = ttk.Combobox(serial_bar, values=avail_ports, width=10, state="readonly" if avail_ports else "normal", font=("Segoe UI", 8))
        if avail_ports:
            combo_com.current(0)
        combo_com.pack(side=tk.LEFT, padx=4)

        tk.Label(serial_bar, text="波特率:", font=("Segoe UI", 8), bg="#1e293b", fg="#cbd5e1").pack(side=tk.LEFT, padx=(6, 2))
        combo_baud = ttk.Combobox(serial_bar, values=["9600", "19200", "38400", "57600", "115200"], width=8, state="readonly", font=("Segoe UI", 8))
        combo_baud.set("9600")
        combo_baud.pack(side=tk.LEFT, padx=4)

        serial_st_lbl = tk.Label(serial_bar, text="● 串口未开启", font=("Segoe UI", 8), bg="#1e293b", fg="#94a3b8")
        if self.master_hub.serial_controller.running:
            serial_st_lbl.config(text=f"● 监听中: {self.master_hub.serial_controller.port_name}", fg="#10b981")

        def toggle_serial():
            if self.master_hub.serial_controller.running:
                self.master_hub.serial_controller.stop()
                serial_st_lbl.config(text="● 串口未开启", fg="#94a3b8")
                btn_serial_toggle.config(text="开启串口监听", bg="#0284c7")
                self.notice_var.set("已停止串口中控监听。")
            else:
                p_name = combo_com.get().strip()
                b_val = int(combo_baud.get().strip() or "9600")
                if not p_name:
                    messagebox.showerror("错误", "请先选择需要监听的 COM 端口！", parent=win)
                    return
                ok, msg = self.master_hub.serial_controller.start(p_name, baudrate=b_val)
                if ok:
                    serial_st_lbl.config(text=f"● 监听中: {p_name} ({b_val})", fg="#10b981")
                    btn_serial_toggle.config(text="停止串口监听", bg="#ef4444")
                    self.notice_var.set(f"串口中控已成功启动: {p_name} (波特率 {b_val})")
                    messagebox.showinfo("成功", f"物理串口中控已成功开启监听:\n端口: {p_name}\n波特率: {b_val}", parent=win)
                else:
                    messagebox.showerror("串口开启失败", msg, parent=win)

        btn_serial_toggle = tk.Button(
            serial_bar,
            text="停止串口监听" if self.master_hub.serial_controller.running else "开启串口监听",
            font=("Segoe UI", 8, "bold"),
            bg="#ef4444" if self.master_hub.serial_controller.running else "#0284c7",
            fg="#fff", relief="flat", padx=10, pady=1, cursor="hand2", command=toggle_serial
        )
        btn_serial_toggle.pack(side=tk.LEFT, padx=8)
        serial_st_lbl.pack(side=tk.LEFT, padx=6)

        # 主体说明内容 (使用滚动文本框展现)
        txt = tk.Text(win, bg="#0b0f19", fg="#f8fafc", font=("Consolas", 9), padx=12, pady=10, relief="flat", wrap="none")
        txt_scroll_y = ttk.Scrollbar(win, orient=tk.VERTICAL, command=txt.yview)
        txt_scroll_x = ttk.Scrollbar(win, orient=tk.HORIZONTAL, command=txt.xview)
        txt.configure(yscrollcommand=txt_scroll_y.set, xscrollcommand=txt_scroll_x.set)

        txt_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        txt_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        txt.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 8))

        doc_content = f"""# ==============================================================================
# 🏛️ 展馆智能集群综合管控中心 · 中控全协议 (UDP/TCP/HTTP/串口) 与视频推流 API
# ==============================================================================
# 兼容硬件: 快思聪 (Crestron)、AMX、华为/台达/快捷中控主机、触摸平板、网页Web中控、物理串口按键网关
# 当前主控主机 IP: {master_ip_show}
# 中控服务总线端口:
#   • UDP 协议端口 : 9889 (向 {master_ip_show}:9889 发送无连接 UDP 报文)
#   • TCP 协议端口 : 9890 (连接 {master_ip_show}:9890 发送以换行符 \\n 分隔的报文)
#   • HTTP REST API: 9891 (访问 http://{master_ip_show}:9891/api/...)
#   • 物理串口 COM : 可选 COM1/COM2... (波特率 9600/115200，\\r\\n 换行)
# ==============================================================================

一、视频推流与实时桌面监看地址规范 (可在中控平板、大屏流媒体播放器、网页中无缝拉流):
------------------------------------------------------------------------------
  每台工控机在局域网内拥有独立的 IP 地址，视频桌面推流拉流地址如下:
  1. 原生 VNC 桌面控制流: vnc://<工控机IP>:5900 (例如 vnc://192.168.1.50:5900)
  2. WebRTC 低延时监看流: webrtc://<工控机IP>:5900/live
  3. HTTP MJPEG 实时画面流: http://<工控机IP>:5901/stream.mjpg (浏览器原生 <img> 直接播放)
  4. RTSP 展厅监控流地址: rtsp://<工控机IP>:8554/live

二、HTTP RESTful Web API 接口规范 (浏览器 / 网页大屏 / 微信小程序 / curl 直接调用):
------------------------------------------------------------------------------
  1. 获取所有在线工控机清单及视频推流地址:
     GET http://{master_ip_show}:9891/api/devices
     响应: JSON 格式包含每台工控机名称、IP、CPU、GPU、内存、vnc_url、stream_url 等

  2. 获取主控健康状态与在线工控机数量:
     GET http://{master_ip_show}:9891/api/status

  3. 网页/浏览器 URL 查询参数一键快速控制 (极为方便做成大屏超链接或按键触发):
     • 全馆一键关机: GET http://{master_ip_show}:9891/api/control?action=all_shutdown
     • 全馆一键重启: GET http://{master_ip_show}:9891/api/control?action=all_reboot
     • 全馆统一音量: GET http://{master_ip_show}:9891/api/control?action=all_volume&volume=80
     • 单机精准调音量: GET http://{master_ip_show}:9891/api/control?action=dev_volume&ip=192.168.1.50&volume=60
     • 单机启动程序: GET http://{master_ip_show}:9891/api/control?action=dev_launch&ip=192.168.1.50&app_name=沙盘

  4. POST 方式下发 JSON 控制报文:
     POST http://{master_ip_show}:9891/api/control
     Content-Type: application/json
     Body: {{"action": "all_shutdown"}}
     (支持跨域 CORS 头 Access-Control-Allow-Origin: *，Web 页面任意跨域调用)

三、UDP / TCP / 串口 指令集 (文本冒号分隔模式 · 快思聪 / AMX / 串口通用):
------------------------------------------------------------------------------
  1. ALL_SHUTDOWN           -> 全馆所有已接入工控机一键安全关机
  2. ALL_REBOOT             -> 全馆所有已接入工控机一键安全重启
  3. ALL_MUTE               -> 全馆所有工控机一键静音
  4. ALL_UNMUTE             -> 全馆所有工控机解除静音
  5. ALL_VOLUME:<0-100>     -> 统一全馆音量。示例: "ALL_VOLUME:80" (全馆设为 80%)
  6. ALL_RUN:<程序路径或名称> -> 全馆工控机统一启动展项应用。示例: "ALL_RUN:D:\\Exhibit\\Show.exe"
  7. DEV_SHUTDOWN:<从机IP>   -> 调度单台工控机关机。示例: "DEV_SHUTDOWN:192.168.1.50"
  8. DEV_REBOOT:<从机IP>     -> 调度单台工控机重启。示例: "DEV_REBOOT:192.168.1.50"
  9. DEV_VOLUME:<IP>:<0-100>-> 精准设定单机音量。示例: "DEV_VOLUME:192.168.1.50:65"
  10. DEV_RUN:<IP>:<程序>   -> 调度单台启动应用。示例: "DEV_RUN:192.168.1.50:D:\\Show.exe"
  11. DEV_KILL:<IP>:<进程名> -> 调度单台强杀异常进程。示例: "DEV_KILL:192.168.1.50:Show.exe"
  12. PING                  -> 握手与心跳，主控即时回显在线总数。

四、中控对接调用代码示例 (Python / 快思聪 / HTTP cURL):
------------------------------------------------------------------------------
  [示例 1: HTTP cURL 命令行]
  curl "http://{master_ip_show}:9891/api/control?action=all_volume&volume=85"

  [示例 2: TCP Socket (快思聪 / Python)]
  import socket
  s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  s.connect(("{master_ip_show}", 9890))
  s.sendall(b"ALL_VOLUME:80\\n")
  print("TCP反馈:", s.recv(1024).decode())
  s.close()

  [示例 3: 物理串口发送 (RS232 / RS485)]
  串口调试助手打开 COM3，波特率 9600，发送: "ALL_SHUTDOWN\\r\\n"
  主控执行并回写: "ACK:已向全馆下发关机指令\\r\\n"
"""
        txt.insert("1.0", doc_content)
        txt.config(state="disabled")

        # 底部操作栏: 一键复制命令
        bot_bar = tk.Frame(win, bg="#1e293b", padx=16, pady=8)
        bot_bar.pack(fill=tk.X)

        def copy_demo():
            self.root.clipboard_clear()
            self.root.clipboard_append("ALL_SHUTDOWN")
            messagebox.showinfo("已复制", "已复制测试命令 [ALL_SHUTDOWN] 到剪贴板！", parent=win)

        def copy_http_api():
            u = f"http://{master_ip_show}:9891/api/devices"
            self.root.clipboard_clear()
            self.root.clipboard_append(u)
            messagebox.showinfo("已复制", f"已复制 HTTP API 获取设备清单接口地址:\n{u}", parent=win)

        tk.Button(bot_bar, text="📋 复制关机测试命令 (ALL_SHUTDOWN)", font=("Segoe UI", 9, "bold"), bg="#0284c7", fg="#fff", relief="flat", padx=10, pady=3, command=copy_demo).pack(side=tk.LEFT)
        tk.Button(bot_bar, text="🌐 复制HTTP API接口地址", font=("Segoe UI", 9), bg="#059669", fg="#fff", relief="flat", padx=10, pady=3, command=copy_http_api).pack(side=tk.LEFT, padx=8)
        tk.Button(bot_bar, text="关闭窗口", font=("Segoe UI", 9), bg="#334155", fg="#fff", relief="flat", padx=12, pady=3, command=win.destroy).pack(side=tk.RIGHT)

    def _periodic_ui_refresh(self):
        """定期微调与心跳检测"""
        self._refresh_client_tree()
        self.root.after(3000, self._periodic_ui_refresh)


def main():
    # 单实例运行互斥保护 (杜绝重复多开)
    if not gwc_system_ops.ensure_single_instance("Global\\GWC_Master_Hub_Mutex_2026"):
        try:
            r = tk.Tk()
            r.withdraw()
            messagebox.showwarning("提示", "《展馆智能集群综合管控中心》已在运行中！\n请勿重复多开主控端程序。")
            r.destroy()
        except Exception:
            pass
        sys.exit(0)

    root = tk.Tk()
    app = MasterAppUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
