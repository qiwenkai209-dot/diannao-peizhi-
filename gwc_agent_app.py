# -*- coding: utf-8 -*-
"""
展馆控制终端 · 轻量守护版 (GuoWenChuang Agent Client 2026 Pro)
============================================================
1. 展馆控制终端专属设计:
   - 全局快捷键 (默认 Ctrl+Q) 秒级呼出/隐藏，支持开机自启与静默后台守护。
   - 本机终端自定义名称，实时同步至局域网广播发现与主控连接中心。
   - 服务端端口明确标注: TCP 9888 (中控通信) | UDP 9887 (广播搜索) | VNC 5900 (远程桌面)。
2. 界面极简大气设计:
   - 预设常用应用清单默认折叠收起。
   - 商业授权放置最下方默认折叠收起，支持随时输入新激活码覆盖更新升级。
   - 工控策略高级微调列表默认折叠收起。
3. 展馆工控系统策略一键设置:
   - “一键设置”执行后按钮状态锁止，持久化记录，下次启动仍保持锁止状态。
4. 网络适配器与子网掩码自动获取:
   - 优先自动精准读取网卡实际掩码，缺失时默认 255.255.255.0。
5. 商业授权体系:
   - 采用专属全新独立算法 (8位申请码 XXXX-XXXX，16位激活码 XXXX-XXXX-XXXX-XXXX)，与国文创加密机区分。
   - 默认首次启动未授权前置模态强提醒弹窗。
"""

import sys
import os
import time
import socket
import json
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import platform
import psutil

import gwc_crypto
import gwc_system_ops
import gwc_monitor
import gwc_agent
import gwc_backup
import gwc_discovery
import gwc_desktop_helper as dh
import gwc_license_terminal as lt


class MarqueeLabel(tk.Canvas):
    """
    走马灯平滑滚动显示组件：
    当文本内容超出可视宽度时自动平滑循环滚动播放，放得下时静态靠左显示。
    """
    def __init__(self, parent, text="", font=("Segoe UI", 9), bg="#151c2c", fg="#38bdf8", height=24, speed=1, fps=30, **kwargs):
        super().__init__(parent, bg=bg, height=height, highlightthickness=0, bd=0, **kwargs)
        self.text = text
        self.font = font
        self.fg = fg
        self.speed = speed
        self.interval = max(20, int(1000 / fps))
        self.offset_x = 0
        self.text_width = 0
        self._animating = False
        self._timer_id = None
        self._text_item = None

        self.bind("<Configure>", self._on_resize)
        self.after(50, self._init_render)

    def _init_render(self):
        self._update_text()

    def set_text(self, text: str, fg: str = None):
        if fg:
            self.fg = fg
        self.text = text
        self.offset_x = 0
        self._update_text()

    def _update_text(self):
        self.delete("all")
        if not self.text:
            return
        h = self.winfo_height()
        if h <= 1:
            h = int(self.cget("height")) if self.cget("height") else 24
        self._text_item = self.create_text(
            self.offset_x, h // 2,
            text=self.text, font=self.font, fill=self.fg, anchor="w"
        )
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


class CollapsibleFrame(tk.Frame):
    """
    优雅的深色折叠卡片容器组件
    - 统一高端工业暗黑风，可折叠/展开
    - 标题文本 + 折叠指示指示箭头 (▶ / ▼)
    - 右侧动态状态提示文字
    - 默认可设为折叠收起，保持主界面极其简洁清爽
    """
    def __init__(self, parent, title: str, status_text: str = "", collapsed: bool = True,
                 bg="#151c2c", header_bg="#1e293b", fg_title="#f8fafc", fg_accent="#38bdf8", **kwargs):
        super().__init__(parent, bg=bg, bd=1, relief="solid", highlightthickness=1, highlightbackground="#1e293b", **kwargs)
        self.bg = bg
        self.collapsed = collapsed
        self.title_text = title
        self.fg_accent = fg_accent

        # 头部栏
        self.header = tk.Frame(self, bg=header_bg, cursor="hand2", padx=10, pady=6)
        self.header.pack(fill=tk.X)

        self.arrow_lbl = tk.Label(
            self.header,
            text="▶" if collapsed else "▼",
            font=("Segoe UI", 9, "bold"),
            bg=header_bg,
            fg=fg_accent
        )
        self.arrow_lbl.pack(side=tk.LEFT, padx=(0, 6))

        self.title_lbl = tk.Label(
            self.header,
            text=title,
            font=("Segoe UI", 9, "bold"),
            bg=header_bg,
            fg=fg_title
        )
        self.title_lbl.pack(side=tk.LEFT)

        self.status_lbl = tk.Label(
            self.header,
            text=status_text,
            font=("Segoe UI", 8),
            bg=header_bg,
            fg="#94a3b8"
        )
        self.status_lbl.pack(side=tk.RIGHT)

        # 绑定点击事件
        for widget in (self.header, self.arrow_lbl, self.title_lbl, self.status_lbl):
            widget.bind("<Button-1>", lambda e: self.toggle())

        # 内容主体
        self.body = tk.Frame(self, bg=bg, padx=10, pady=8)
        if not collapsed:
            self.body.pack(fill=tk.BOTH, expand=True)

    def toggle(self):
        if self.collapsed:
            self.expand()
        else:
            self.collapse()

    def expand(self):
        self.collapsed = False
        self.arrow_lbl.config(text="▼")
        self.body.pack(fill=tk.BOTH, expand=True)

    def collapse(self):
        self.collapsed = True
        self.arrow_lbl.config(text="▶")
        self.body.pack_forget()

    def set_status(self, text: str, fg: str = "#94a3b8"):
        self.status_lbl.config(text=text, fg=fg)


class AgentAppUI:
    def __init__(self, root: tk.Tk, silent_startup: bool = False):
        self.root = root
        self.root.title("展馆控制终端")
        self.root.geometry("880x720")
        self.root.minsize(800, 640)
        self.root.configure(bg="#0b0f19")

        # 居中显示
        ws = self.root.winfo_screenwidth()
        hs = self.root.winfo_screenheight()
        self.root.geometry(f"880x720+{(ws-880)//2}+{(hs-720)//2}")

        # 窗口图标
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gear.ico")
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except Exception:
                pass

        # 加载持久化配置
        self.config = dh.ConfigManager.load_config()

        # 商业授权实例 (专属展馆控制终端全新算法引擎)
        self.license_mgr = lt.TerminalLicenseManager()

        # 预设常用应用清单持久化
        self.preset_apps_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_preset_apps.json")
        self.preset_apps = self._load_preset_apps()

        # 本机自定义终端名称与中控连接
        master_ip = self.config.get("master_ip", "127.0.0.1")
        master_port = self.config.get("master_port", 9888)
        self.custom_name = self.config.get("custom_name", socket.gethostname()).strip()
        if not self.custom_name:
            self.custom_name = socket.gethostname()

        # 受控端后台通信代理
        self.agent_client = gwc_agent.GwcAgentClient(
            master_ip=master_ip,
            master_port=master_port,
            license_mgr=self.license_mgr,
            custom_name=self.custom_name
        )
        self.agent_client.on_status_change = self._on_agent_status_change
        self.agent_client.on_remote_authorized = self._on_remote_authorized_sync

        # 全局热键管理器 (默认 Ctrl+Q)
        self.current_hotkey = self.config.get("hotkey", "Ctrl+Q")
        self.hotkey_mgr = dh.GlobalHotkeyManager(
            hotkey_str=self.current_hotkey,
            on_trigger=self._on_hotkey_triggered
        )

        # 界面动态数据绑定变量
        self.status_text_var = tk.StringVar(value="正在初始化受控服务...")
        self.conn_badge_var = tk.StringVar(value="● 待命中")
        self.master_ip_var = tk.StringVar(value=master_ip)
        self.master_port_var = tk.StringVar(value=str(master_port))
        self.custom_name_var = tk.StringVar(value=self.custom_name)
        self.backup_dir_var = tk.StringVar(value=self.config.get("backup_dir", gwc_backup.get_default_backup_dir()))
        self.opt_status_var = tk.StringVar(value="当前就绪：网卡配置就绪 | 策略优化待命 | 内存监控正常")
        self.hotkey_display_var = tk.StringVar(value=self.current_hotkey)
        self.autostart_var = tk.BooleanVar(value=dh.AutoStartManager.is_auto_start_enabled())
        self.silent_boot_var = tk.BooleanVar(value=self.config.get("silent_boot", True))

        # 网络设置输入映射
        self.net_entries = {}

        # 样式与界面搭建
        self._setup_styles()
        self._build_ui()

        # 默认首先隐藏主窗口，严格执行未授权不显示终端菜单策略
        self.root.withdraw()

        # 拦截窗口关闭事件 -> 转入后台守护运行
        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_background)

        # 启动热键监听与受控后台通信服务 (支持主控端远程扫描与激活)
        self.hotkey_mgr.start()
        self.agent_client.start(enable_rfb_vnc=self.config.get("enable_vnc", True))

        # 启动常驻授权守护检测器 (运行中若授权到期即时锁定终端菜单)
        self._start_license_guardian()

        # 前置授权检测与强提醒 (若未授权或已到期，弹出最前置不可关闭弹窗，不显示终端菜单)
        self._check_license_and_enforce(silent_startup)

        # 启动预设应用开机自启与延时调度器 (延时 1 秒启动，保证网络及核心服务就绪)
        self.root.after(1000, self._run_autostart_preset_apps)

    # ==================== 商业授权检测、到期守护与最前置锁止弹窗 ====================
    def _check_license_and_enforce(self, silent_startup: bool = False):
        """前置授权检测与执行 (未授权或授权到期最前置弹窗，无法关闭，不显示终端菜单)"""
        is_active = False
        reason = "软件未获得官方商业授权"
        if self.license_mgr:
            try:
                ok, msg = self.license_mgr.check()
                if ok:
                    is_active = True
                else:
                    reason = msg
            except Exception:
                pass

        self._update_auth_ui_display(is_active)
        if not is_active:
            # 严格锁止：隐藏主窗口，不显示终端菜单，弹出最前置不可关闭弹窗
            self.root.withdraw()
            self._show_license_dialog(reason)
        else:
            # 授权有效且正常
            if silent_startup:
                self.root.withdraw()
            else:
                self.root.deiconify()

    def _start_license_guardian(self):
        """后台运行中定期核验授权 (到期即刻锁定终端菜单)"""
        def _check_tick():
            ok, msg = self.license_mgr.check()
            if not ok:
                # 授权到期或失效：立即锁定终端
                if not (hasattr(self, "_license_modal_win") and self._license_modal_win and self._license_modal_win.winfo_exists()):
                    self.root.withdraw()
                    self._show_license_dialog(msg)
            else:
                self._update_auth_ui_display(True)
            self.root.after(3000, _check_tick)
        self.root.after(3000, _check_tick)

    def _update_auth_ui_display(self, is_active: bool = False):
        ok, msg = self.license_mgr.check() if self.license_mgr else (False, "未授权")
        status_txt = f"● {msg}" if ok else f"● {msg}"
        status_color = "#10b981" if ok else "#f59e0b"

        if hasattr(self, "lbl_auth_status_card") and self.lbl_auth_status_card:
            self.lbl_auth_status_card.config(text=status_txt, fg=status_color)

        if hasattr(self, "card_license") and self.card_license:
            badge = "已激活" if ok else "未激活 (点击展开授权)"
            self.card_license.set_status(f"{status_txt} [{badge}]", fg=status_color)

    def _on_remote_authorized_sync(self, act_code: str, msg: str):
        """当主控中心通过网络远程下发并激活商业授权时的同步回调"""
        def update():
            if hasattr(self, "_license_modal_win") and self._license_modal_win and self._license_modal_win.winfo_exists():
                try:
                    self._license_modal_win.destroy()
                except Exception:
                    pass
                self._license_modal_win = None
            self._update_auth_ui_display(True)
            self.status_text_var.set("🎉 已接收到主控中心远程签发的商业许可证，终端菜单已成功解锁！")
            # 激活成功后解锁展现终端主窗口与菜单
            self.root.deiconify()
            self.root.lift()
            messagebox.showinfo(
                "授权成功",
                f"🎉 已成功接收到主控中心远程签发的商业授权！\n激活码: {act_code}\n终端菜单已解锁并激活。"
            )
        try:
            if self.root.winfo_exists():
                self.root.after(0, update)
        except Exception:
            pass

    def _show_license_dialog(self, reason: str = "软件未获得官方商业授权"):
        """前置授权验证对话框 (最前置、无法关闭、不显示终端菜单)"""
        # 强制隐藏主窗口和终端菜单，绝对不显示
        self.root.withdraw()

        if hasattr(self, "_license_modal_win") and self._license_modal_win and self._license_modal_win.winfo_exists():
            try:
                self._license_modal_win.lift()
                self._license_modal_win.attributes("-topmost", True)
                self._license_modal_win.focus_force()
            except Exception:
                pass
            return

        win = tk.Toplevel(self.root)
        self._license_modal_win = win
        win.title("商业授权验证 · 展馆控制终端")
        win.geometry("540x440")
        win.configure(bg="#0f172a")
        win.resizable(False, False)

        ws = win.winfo_screenwidth()
        hs = win.winfo_screenheight()
        win.geometry(f"540x440+{(ws-540)//2}+{(hs-440)//2}")

        try:
            win.attributes("-topmost", True)
            win.focus_force()
        except Exception:
            pass

        # 最前置持续守护: 定时刷新保持全屏最顶层，杜绝被遮挡
        def _keep_modal_topmost():
            if hasattr(self, "_license_modal_win") and self._license_modal_win and self._license_modal_win.winfo_exists():
                try:
                    self._license_modal_win.lift()
                    self._license_modal_win.attributes("-topmost", True)
                except Exception:
                    pass
                self.root.after(400, _keep_modal_topmost)
        self.root.after(400, _keep_modal_topmost)

        # 拦截关闭行为: 无法关闭弹窗！
        def _on_close_attempt():
            messagebox.showwarning(
                "授权锁定",
                "⚠️ 展馆控制终端未获得授权或商业授权已到期！\n终端菜单已锁定，无法关闭此窗口。\n请输入 16 位有效商业激活码激活，或点击【彻底退出软件】关闭程序。",
                parent=win
            )
        win.protocol("WM_DELETE_WINDOW", _on_close_attempt)

        tk.Label(win, text="🔒 展馆控制终端 · 商业授权锁定", font=("Segoe UI", 13, "bold"), bg="#0f172a", fg="#f59e0b").pack(pady=(18, 4))
        tk.Label(win, text=f"状态提醒: {reason} (终端菜单已锁定)", font=("Segoe UI", 9), bg="#0f172a", fg="#ef4444").pack(pady=(0, 10))

        card = tk.Frame(win, bg="#1e293b", padx=16, pady=12)
        card.pack(fill=tk.BOTH, expand=True, padx=24, pady=4)

        req_code = self.license_mgr.get_req_code()

        tk.Label(card, text="本机专属设备申请码 (8 位格式: XXXX-XXXX):", font=("Segoe UI", 9), bg="#1e293b", fg="#cbd5e1").pack(anchor="w")

        r_code = tk.Frame(card, bg="#1e293b")
        r_code.pack(fill=tk.X, pady=4)
        tk.Label(r_code, text=req_code, font=("Consolas", 16, "bold"), bg="#0f172a", fg="#34d399", padx=14, pady=4).pack(side=tk.LEFT)

        def copy_c():
            self.root.clipboard_clear()
            self.root.clipboard_append(req_code)
            messagebox.showinfo("已复制", f"设备申请码已成功复制到剪贴板:\n{req_code}", parent=win)

        tk.Button(r_code, text="📋 复制申请码", font=("Segoe UI", 9, "bold"), bg="#059669", fg="#fff", relief="flat", padx=10, pady=3, cursor="hand2", command=copy_c).pack(side=tk.LEFT, padx=10)

        tk.Label(card, text="输入 16 位专属商业激活码 (支持自定义小时、月、永久):", font=("Segoe UI", 9), bg="#1e293b", fg="#cbd5e1").pack(anchor="w", pady=(12, 2))
        ent_code = tk.Entry(card, font=("Consolas", 12, "bold"), bg="#0f172a", fg="#38bdf8", justify="center", relief="flat")
        ent_code.pack(fill=tk.X, ipady=4)

        tk.Label(card, text="提示: 联网状态下中控室主控端亦可一键免密远程签发并自动解锁", font=("Segoe UI", 8), bg="#1e293b", fg="#94a3b8").pack(anchor="w", pady=(4, 0))

        def do_act():
            code = ent_code.get().strip()
            if not code:
                messagebox.showerror("错误", "请输入 16 位商业激活码！", parent=win)
                return
            ok, m = self.license_mgr.activate(code, force_overwrite=True)
            if ok:
                self._update_auth_ui_display(True)
                messagebox.showinfo("成功", f"商业授权验证通过！\n{m}", parent=win)
                try:
                    win.destroy()
                except Exception:
                    pass
                self._license_modal_win = None
                # 解锁并展示主窗口终端菜单
                self.root.deiconify()
                self.root.lift()
            else:
                messagebox.showerror("激活失败", f"激活失败: {m}", parent=win)

        btn_box = tk.Frame(win, bg="#0f172a")
        btn_box.pack(fill=tk.X, padx=24, pady=12)

        tk.Button(btn_box, text="⚡ 立即核销激活并解锁", font=("Segoe UI", 9, "bold"), bg="#0284c7", fg="#fff", relief="flat", padx=14, pady=6, cursor="hand2", command=do_act).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        tk.Button(btn_box, text="❌ 彻底退出软件", font=("Segoe UI", 9), bg="#475569", fg="#ef4444", relief="flat", padx=12, pady=6, cursor="hand2", command=self.quit_app).pack(side=tk.RIGHT)

    # ==================== 界面主题与样式 ====================
    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        self.BG_DARK = "#0b0f19"
        self.CARD_BG = "#151c2c"
        self.CARD_BORDER = "#1e293b"
        self.ACCENT_BLUE = "#0284c7"
        self.ACCENT_CYAN = "#38bdf8"
        self.ACCENT_GREEN = "#10b981"
        self.ACCENT_YELLOW = "#f59e0b"
        self.ACCENT_RED = "#ef4444"
        self.TEXT_WHITE = "#f8fafc"
        self.TEXT_MUTED = "#94a3b8"

        style.configure("Dark.TFrame", background=self.BG_DARK)
        style.configure("Card.TFrame", background=self.CARD_BG)
        style.configure("Inner.TFrame", background=self.CARD_BG)
        style.configure("TLabel", background=self.CARD_BG, foreground=self.TEXT_WHITE, font=("Segoe UI", 9))
        style.configure("Title.TLabel", background=self.BG_DARK, foreground=self.TEXT_WHITE, font=("Segoe UI", 13, "bold"))
        style.configure("Subtitle.TLabel", background=self.BG_DARK, foreground=self.TEXT_MUTED, font=("Segoe UI", 8))
        style.configure("Dark.TCheckbutton", background=self.CARD_BG, foreground=self.TEXT_WHITE, font=("Segoe UI", 9))
        style.map("Dark.TCheckbutton", background=[("active", self.CARD_BG)])

        # Treeview 表格
        style.configure("Treeview", background="#0f172a", foreground="#f8fafc", fieldbackground="#0f172a", rowheight=24, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", background="#1e293b", foreground="#38bdf8", relief="flat", font=("Segoe UI", 9, "bold"))
        style.map("Treeview", background=[("selected", "#0284c7")], foreground=[("selected", "#ffffff")])

        # Notebook 选项卡
        style.configure("TNotebook", background=self.BG_DARK, borderwidth=0)
        style.configure("TNotebook.Tab", background="#1e293b", foreground=self.TEXT_MUTED, font=("Segoe UI", 9, "bold"), padding=[16, 7])
        style.map("TNotebook.Tab", background=[("selected", "#0284c7")], foreground=[("selected", "#ffffff")])

    # ==================== 主窗口搭建 ====================
    def _build_ui(self):
        main_box = ttk.Frame(self.root, style="Dark.TFrame", padding="14 10 14 10")
        main_box.pack(fill=tk.BOTH, expand=True)

        # 顶部标题栏
        header = ttk.Frame(main_box, style="Dark.TFrame")
        header.pack(fill=tk.X, pady=(0, 8))

        t_box = ttk.Frame(header, style="Dark.TFrame")
        t_box.pack(side=tk.LEFT)

        ttk.Label(t_box, text="🏛️ 展馆控制终端", style="Title.TLabel").pack(anchor="w")
        ttk.Label(t_box, text="后台轻量守护 · 快捷键 Ctrl+Q 唤出 · 支持中控远程管理与单机深度配置", style="Subtitle.TLabel").pack(anchor="w", pady=(1, 0))

        self.lbl_badge = tk.Label(
            header,
            textvariable=self.conn_badge_var,
            font=("Segoe UI", 9, "bold"),
            bg="#1e293b",
            fg=self.ACCENT_YELLOW,
            padx=10,
            pady=3,
            relief="flat"
        )
        self.lbl_badge.pack(side=tk.RIGHT)

        # 选项卡容器
        self.nb = ttk.Notebook(main_box)
        self.nb.pack(fill=tk.BOTH, expand=True, pady=(2, 6))

        # Tab 1: 受控守护与运行设置
        tab_service = ttk.Frame(self.nb, style="Dark.TFrame")
        self.nb.add(tab_service, text="📡 受控守护与运行设置")
        self._build_tab_service(tab_service)

        # Tab 2: ⚙️ 配置 (网络与策略优化设置 + 状态实时反馈)
        tab_opt = ttk.Frame(self.nb, style="Dark.TFrame")
        self.nb.add(tab_opt, text="⚙️ 配置")
        self._build_tab_optimization(tab_opt)

        # Tab 3: 本地系统一键备份与恢复
        tab_bk = ttk.Frame(self.nb, style="Dark.TFrame")
        self.nb.add(tab_bk, text="💾 本地系统备份与恢复")
        self._build_tab_backup(tab_bk)

        # 底部操作栏: 隐藏运行与退出
        self._build_bottom_bar(main_box)

    # ==================== Tab 1: 受控守护与运行设置 ====================
    def _build_tab_service(self, parent):
        box = tk.Frame(parent, bg=self.BG_DARK)
        box.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # 1. 本机常用预设应用清单 (常驻展开，不折叠，置于最顶层，支持开机自启与延时启动)
        self.preset_box = tk.LabelFrame(
            box,
            text=" 💻 本机预设常用应用清单 (支持开机自启 · 延时启动 · 中控联动调用) ",
            bg=self.CARD_BG,
            fg=self.ACCENT_GREEN,
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=6,
            bd=1
        )
        self.preset_box.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

        app_tool = tk.Frame(self.preset_box, bg=self.CARD_BG)
        app_tool.pack(fill=tk.X, pady=(0, 4))

        tk.Button(app_tool, text="➕ 添加预设应用", font=("Segoe UI", 8, "bold"), bg="#0284c7", fg="#fff", relief="flat", padx=8, pady=2, cursor="hand2", command=self._add_preset_app).pack(side=tk.LEFT)
        tk.Button(app_tool, text="✏️ 编辑配置", font=("Segoe UI", 8, "bold"), bg="#059669", fg="#fff", relief="flat", padx=8, pady=2, cursor="hand2", command=self._edit_preset_app).pack(side=tk.LEFT, padx=4)
        tk.Button(app_tool, text="🚀 立即启动测试", font=("Segoe UI", 8), bg="#334155", fg="#38bdf8", relief="flat", padx=8, pady=2, cursor="hand2", command=self._test_run_preset_app).pack(side=tk.LEFT, padx=4)
        tk.Button(app_tool, text="❌ 移除选中项", font=("Segoe UI", 8), bg="#334155", fg="#ef4444", relief="flat", padx=8, pady=2, cursor="hand2", command=self._delete_preset_app).pack(side=tk.LEFT, padx=4)
        tk.Label(app_tool, text="提示: 勾选自启项将在终端开机启动时按设定秒数自动延时拉起", font=("Segoe UI", 8), bg=self.CARD_BG, fg=self.TEXT_MUTED).pack(side=tk.RIGHT)

        cols = ("autostart", "delay", "path", "args")
        self.app_tree = ttk.Treeview(self.preset_box, columns=cols, show="tree headings", selectmode="browse", height=5)
        self.app_tree.heading("#0", text="应用名称", anchor="w")
        self.app_tree.heading("autostart", text="开机自启", anchor="center")
        self.app_tree.heading("delay", text="延时启动", anchor="center")
        self.app_tree.heading("path", text="执行文件完整路径", anchor="w")
        self.app_tree.heading("args", text="启动参数", anchor="w")

        self.app_tree.column("#0", width=140)
        self.app_tree.column("autostart", width=85, anchor="center")
        self.app_tree.column("delay", width=85, anchor="center")
        self.app_tree.column("path", width=340)
        self.app_tree.column("args", width=120)

        app_scroll = ttk.Scrollbar(self.preset_box, orient=tk.VERTICAL, command=self.app_tree.yview)
        self.app_tree.configure(yscrollcommand=app_scroll.set)

        self.app_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        app_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.app_tree.bind("<Double-1>", lambda e: self._edit_preset_app())
        self._refresh_app_tree()

        # 2. 其他功能统筹放入折叠面板 (运行模式/中控设置/商业授权，保持主界面极简清爽)
        self.card_other_settings = CollapsibleFrame(
            box,
            title="🛡️ 终端核心守护与网络授权综合设置 (热键/中控/商业授权)",
            status_text="点击展开设置详情 ▶",
            collapsed=True,
            fg_accent=self.ACCENT_CYAN
        )
        self.card_other_settings.pack(fill=tk.X, pady=(2, 2))

        other_body = self.card_other_settings.body

        # 子板块 1: 运行模式与全局热键
        c1 = tk.LabelFrame(other_body, text=" 运行模式与全局热键 ", bg=self.CARD_BG, fg=self.ACCENT_CYAN, font=("Segoe UI", 9, "bold"), padx=12, pady=5, bd=1)
        c1.pack(fill=tk.X, pady=(0, 4))

        r_hk = tk.Frame(c1, bg=self.CARD_BG)
        r_hk.pack(fill=tk.X, pady=2)

        tk.Label(r_hk, text="呼出/隐藏快捷键:", bg=self.CARD_BG, fg="#cbd5e1", font=("Segoe UI", 9)).pack(side=tk.LEFT)
        self.badge_hotkey = tk.Label(r_hk, textvariable=self.hotkey_display_var, font=("Consolas", 10, "bold"), bg="#0284c7", fg="#fff", padx=8, pady=1)
        self.badge_hotkey.pack(side=tk.LEFT, padx=(8, 10))

        tk.Button(r_hk, text="自定义快捷键", font=("Segoe UI", 8, "bold"), bg="#334155", fg="#fff", relief="flat", padx=8, pady=1, cursor="hand2", command=self._prompt_change_hotkey).pack(side=tk.LEFT)
        tk.Label(r_hk, text="(默认 Ctrl+Q，任意全屏应用下按下均可瞬间唤起/隐藏本终端)", font=("Segoe UI", 8), bg=self.CARD_BG, fg=self.TEXT_MUTED).pack(side=tk.LEFT, padx=(10, 0))

        r_st = tk.Frame(c1, bg=self.CARD_BG)
        r_st.pack(fill=tk.X, pady=(3, 0))

        ttk.Checkbutton(r_st, text="开机自启 (写入注册表 Run)", variable=self.autostart_var, style="Dark.TCheckbutton", command=self._on_toggle_autostart).pack(side=tk.LEFT)
        ttk.Checkbutton(r_st, text="开机静默隐藏运行 (--hide)", variable=self.silent_boot_var, style="Dark.TCheckbutton", command=self._on_toggle_silent_boot).pack(side=tk.LEFT, padx=(20, 0))

        # 子板块 2: 终端名称与中控连接设置 (服务端端口明确标注: TCP/UDP/WebRTC)
        c2 = tk.LabelFrame(other_body, text=" 终端名称与中控连接设置 ", bg=self.CARD_BG, fg=self.ACCENT_CYAN, font=("Segoe UI", 9, "bold"), padx=12, pady=5, bd=1)
        c2.pack(fill=tk.X, pady=(0, 4))

        r_name = tk.Frame(c2, bg=self.CARD_BG)
        r_name.pack(fill=tk.X, pady=2)

        local_ip = gwc_discovery.get_local_ip()
        tk.Label(r_name, text="本机终端名称:", font=("Segoe UI", 9, "bold"), bg=self.CARD_BG, fg="#cbd5e1").pack(side=tk.LEFT)
        ent_cname = tk.Entry(r_name, textvariable=self.custom_name_var, font=("Segoe UI", 9, "bold"), bg="#0f172a", fg=self.ACCENT_CYAN, width=18, relief="flat")
        ent_cname.pack(side=tk.LEFT, padx=(6, 8))

        tk.Button(r_name, text="💾 保存名称", font=("Segoe UI", 8, "bold"), bg=self.ACCENT_BLUE, fg="#fff", relief="flat", padx=8, pady=1, cursor="hand2", command=self._save_custom_name).pack(side=tk.LEFT, padx=(0, 10))
        tk.Label(r_name, text=f"本机 IP: {local_ip}  (系统主机名: {socket.gethostname()})", font=("Segoe UI", 8), bg=self.CARD_BG, fg="#94a3b8").pack(side=tk.LEFT)

        r_port_tag = tk.Frame(c2, bg="#0f172a", padx=8, pady=3)
        r_port_tag.pack(fill=tk.X, pady=(4, 3))
        tk.Label(
            r_port_tag,
            text="📌 服务端端口标注:  TCP: 9888 (中控通信链路)  |  WebRTC: 5900 (极速桌面视讯回传)  |  UDP: 9887 (广播雷达探测)",
            font=("Segoe UI", 8, "bold"),
            bg="#0f172a",
            fg="#38bdf8"
        ).pack(side=tk.LEFT)

        r_conn = tk.Frame(c2, bg=self.CARD_BG)
        r_conn.pack(fill=tk.X, pady=(3, 2))

        tk.Label(r_conn, text="主控端 IP:", font=("Segoe UI", 9), bg=self.CARD_BG, fg="#cbd5e1").pack(side=tk.LEFT)
        ent_ip = tk.Entry(r_conn, textvariable=self.master_ip_var, font=("Consolas", 9), bg="#0f172a", fg="#f8fafc", width=16, relief="flat")
        ent_ip.pack(side=tk.LEFT, padx=(6, 8))

        tk.Label(r_conn, text="端口:", font=("Segoe UI", 9), bg=self.CARD_BG, fg="#cbd5e1").pack(side=tk.LEFT)
        ent_port = tk.Entry(r_conn, textvariable=self.master_port_var, font=("Consolas", 9), bg="#0f172a", fg="#f8fafc", width=6, relief="flat")
        ent_port.pack(side=tk.LEFT, padx=(6, 10))

        tk.Button(r_conn, text="保存并重连", font=("Segoe UI", 8, "bold"), bg=self.ACCENT_BLUE, fg="#fff", relief="flat", padx=10, pady=2, cursor="hand2", command=self._apply_master_address).pack(side=tk.LEFT)

        r_stat = tk.Frame(c2, bg=self.CARD_BG)
        r_stat.pack(fill=tk.X, pady=(3, 0))
        tk.Label(r_stat, text="通信状态:", font=("Segoe UI", 8), bg=self.CARD_BG, fg=self.TEXT_MUTED).pack(side=tk.LEFT)
        tk.Label(r_stat, textvariable=self.status_text_var, font=("Segoe UI", 9), bg=self.CARD_BG, fg="#e2e8f0").pack(side=tk.LEFT, padx=(6, 0))

        # 子板块 3: 展馆控制终端专属商业授权 (支持新激活码随时覆盖升级)
        is_lic_ok, lic_desc = self.license_mgr.check()
        c3 = tk.LabelFrame(other_body, text=" 🔑 展馆控制终端商业授权与申请码 ", bg=self.CARD_BG, fg=self.ACCENT_YELLOW, font=("Segoe UI", 9, "bold"), padx=12, pady=5, bd=1)
        c3.pack(fill=tk.X, pady=(0, 2))

        r_l1 = tk.Frame(c3, bg=self.CARD_BG)
        r_l1.pack(fill=tk.X, pady=2)

        self.lbl_auth_status_card = tk.Label(
            r_l1,
            text=f"● {lic_desc}" if is_lic_ok else "● 软件尚未获得商业授权 (未激活)",
            font=("Segoe UI", 9, "bold"),
            bg=self.CARD_BG,
            fg="#10b981" if is_lic_ok else "#f59e0b"
        )
        self.lbl_auth_status_card.pack(side=tk.LEFT)

        req_code = self.license_mgr.get_req_code()
        tk.Label(r_l1, text=f"专属申请码: {req_code}", font=("Consolas", 9, "bold"), bg="#0f172a", fg="#34d399", padx=8, pady=1).pack(side=tk.RIGHT, padx=6)

        def copy_c_tab():
            self.root.clipboard_clear()
            self.root.clipboard_append(req_code)
            messagebox.showinfo("已复制", f"设备申请码已复制到剪贴板:\n{req_code}")

        tk.Button(r_l1, text="📋 复制申请码", font=("Segoe UI", 8), bg="#334155", fg="#cbd5e1", relief="flat", padx=6, pady=1, cursor="hand2", command=copy_c_tab).pack(side=tk.RIGHT)

        r_l2 = tk.Frame(c3, bg=self.CARD_BG)
        r_l2.pack(fill=tk.X, pady=(6, 2))

        tk.Label(r_l2, text="输入 16 位新激活码 (支持新授权随时覆盖升级写入):", font=("Segoe UI", 9), bg=self.CARD_BG, fg="#cbd5e1").pack(side=tk.LEFT)
        self.ent_new_lic = tk.Entry(r_l2, font=("Consolas", 10, "bold"), bg="#0f172a", fg="#38bdf8", justify="center", width=28, relief="flat")
        self.ent_new_lic.pack(side=tk.LEFT, padx=(8, 8))

        def do_overwrite_act():
            code = self.ent_new_lic.get().strip()
            if not code:
                messagebox.showerror("错误", "请输入 16 位专属商业激活码！")
                return
            ok, m = self.license_mgr.activate(code, force_overwrite=True)
            if ok:
                self._update_auth_ui_display(True)
                messagebox.showinfo("授权成功", f"🎉 新商业授权已成功覆盖写入并生效！\n{m}")
                self.ent_new_lic.delete(0, tk.END)
            else:
                messagebox.showerror("激活失败", f"授权验证失败: {m}")

        tk.Button(r_l2, text="⚡ 覆盖更新/立即核销激活", font=("Segoe UI", 8, "bold"), bg="#059669", fg="#fff", relief="flat", padx=10, pady=2, cursor="hand2", command=do_overwrite_act).pack(side=tk.LEFT)

        r_l3 = tk.Frame(c3, bg=self.CARD_BG)
        r_l3.pack(fill=tk.X, pady=(3, 0))
        tk.Label(r_l3, text="※ 提示: 采用展馆专属算法 (XXXX-XXXX-XXXX-XXXX)，与国文创加密机区分。支持随时输入更高权限激活码无缝覆盖升级。", font=("Segoe UI", 8), bg=self.CARD_BG, fg=self.TEXT_MUTED).pack(anchor="w")

    # ==================== Tab 2: ⚙️ 配置 (网络与策略优化设置 + 状态实时反馈) ====================
    def _build_tab_optimization(self, parent):
        # 底部配置状态动态看板 (放不下自动平滑走马灯滚动播放)
        f_st_bar = tk.Frame(parent, bg="#0f172a", padx=8, pady=4)
        f_st_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=4, pady=(2, 4))

        tk.Label(f_st_bar, text="⚙️ 配置状态:", font=("Segoe UI", 8, "bold"), bg="#0f172a", fg=self.ACCENT_CYAN).pack(side=tk.LEFT)
        self.opt_marquee = MarqueeLabel(
            f_st_bar,
            text=self.opt_status_var.get(),
            font=("Segoe UI", 8),
            bg="#0f172a",
            fg="#f8fafc",
            height=20
        )
        self.opt_marquee.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        def _on_opt_st_changed(*args):
            if hasattr(self, "opt_marquee") and self.opt_marquee.winfo_exists():
                self.opt_marquee.set_text(self.opt_status_var.get())
        self.opt_status_var.trace_add("write", _on_opt_st_changed)

        paned = tk.PanedWindow(parent, orient=tk.HORIZONTAL, bg=self.BG_DARK, bd=0, sashwidth=4)
        paned.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # 左栏: 网络适配器配置 (子网掩码自动获取，没有默认 255.255.255.0)
        left = tk.LabelFrame(paned, text=" 🌐 网络适配器 IPv4 配置 ", bg=self.CARD_BG, fg=self.ACCENT_CYAN, font=("Segoe UI", 9, "bold"), padx=10, pady=6, bd=1)
        paned.add(left, width=380)

        # 网卡选择行
        r_ad = tk.Frame(left, bg=self.CARD_BG)
        r_ad.pack(fill=tk.X, pady=(2, 6))

        tk.Label(r_ad, text="网卡:", font=("Segoe UI", 9), bg=self.CARD_BG, fg="#cbd5e1").pack(side=tk.LEFT)
        self.ad_combo = ttk.Combobox(r_ad, state="readonly", width=22)
        self.ad_combo.pack(side=tk.LEFT, padx=6)
        self.ad_combo.bind("<<ComboboxSelected>>", self._on_adapter_select)

        tk.Button(r_ad, text="扫描", font=("Segoe UI", 8), bg="#334155", fg="#fff", relief="flat", padx=6, pady=1, cursor="hand2", command=self._refresh_adapters).pack(side=tk.LEFT)

        # IP 字段输入框
        fields = [("IP 地址:", "ip"), ("子网掩码:", "mask"), ("默认网关:", "gateway"), ("首选 DNS:", "dns1"), ("备用 DNS:", "dns2")]
        f_in = tk.Frame(left, bg=self.CARD_BG)
        f_in.pack(fill=tk.X, pady=2)

        for label_txt, key in fields:
            r = tk.Frame(f_in, bg=self.CARD_BG)
            r.pack(fill=tk.X, pady=2)
            tk.Label(r, text=label_txt, width=10, anchor="w", font=("Segoe UI", 8), bg=self.CARD_BG, fg="#cbd5e1").pack(side=tk.LEFT)
            ent = tk.Entry(r, font=("Consolas", 9), bg="#0f172a", fg="#38bdf8", relief="flat")
            ent.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.net_entries[key] = ent

        btn_net_f = tk.Frame(left, bg=self.CARD_BG)
        btn_net_f.pack(fill=tk.X, pady=(8, 4))

        tk.Button(btn_net_f, text="⚡ 应用静态 IP", font=("Segoe UI", 8, "bold"), bg=self.ACCENT_BLUE, fg="#fff", relief="flat", padx=8, pady=3, cursor="hand2", command=self._apply_static_ip).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_net_f, text="🔄 切换 DHCP 自动获取", font=("Segoe UI", 8), bg="#059669", fg="#fff", relief="flat", padx=8, pady=3, cursor="hand2", command=self._apply_dhcp).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_net_f, text="重置网络栈", font=("Segoe UI", 8), bg="#334155", fg="#fff", relief="flat", padx=6, pady=3, cursor="hand2", command=self._do_reset_network).pack(side=tk.LEFT, padx=2)

        # 右栏: 展馆工控系统策略一键设置与深度优化 (执行后按钮锁止，下次打开保持锁止)
        right = tk.LabelFrame(paned, text=" ⚙️ 展馆工控系统策略一键设置与优化 ", bg=self.CARD_BG, fg=self.ACCENT_GREEN, font=("Segoe UI", 9, "bold"), padx=10, pady=6, bd=1)
        paned.add(right, width=460)

        # 核心一键设置区域
        f_oneclick = tk.Frame(right, bg=self.CARD_BG)
        f_oneclick.pack(fill=tk.X, pady=(2, 8))

        # 读取持久化锁止状态
        is_locked = self.config.get("one_click_set_locked", False)

        self.btn_one_click = tk.Button(
            f_oneclick,
            text="🔒 已一键设置 (全套策略已锁止生效)" if is_locked else "🔥 一键设置 (全套展馆工控策略即刻生效)",
            font=("Segoe UI", 10, "bold"),
            bg="#334155" if is_locked else self.ACCENT_RED,
            fg="#94a3b8" if is_locked else "#ffffff",
            activebackground="#1e293b" if is_locked else "#dc2626",
            activeforeground="#ffffff",
            state="disabled" if is_locked else "normal",
            cursor="arrow" if is_locked else "hand2",
            relief="flat",
            padx=14,
            pady=6,
            command=self._do_one_click_setting
        )
        self.btn_one_click.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        # 辅助功能与解锁重设
        f_helpers = tk.Frame(right, bg=self.CARD_BG)
        f_helpers.pack(fill=tk.X, pady=(0, 8))

        tk.Button(f_helpers, text="🧹 清空内存", font=("Segoe UI", 8), bg="#2563eb", fg="#fff", relief="flat", padx=8, pady=3, cursor="hand2", command=self._clean_working_set_memory).pack(side=tk.LEFT, padx=2)
        tk.Button(f_helpers, text="🗑️ 清理垃圾", font=("Segoe UI", 8), bg="#334155", fg="#fff", relief="flat", padx=8, pady=3, cursor="hand2", command=self._clean_temp_files).pack(side=tk.LEFT, padx=2)
        tk.Button(f_helpers, text="🔓 解锁重设", font=("Segoe UI", 8), bg="#1e293b", fg="#94a3b8", relief="flat", padx=6, pady=3, cursor="hand2", command=self._unlock_one_click_setting).pack(side=tk.RIGHT)

        # 单项策略高级微调列表 (默认折叠收起，界面保持简洁大气)
        pol_count = len(gwc_system_ops.EXHIBIT_POLICIES)
        self.card_pol_detail = CollapsibleFrame(
            right,
            title="🛠️ 单项工控策略高级微调",
            status_text=f"共 {pol_count} 项微调策略 ▶ 点击展开",
            collapsed=True,
            fg_accent=self.ACCENT_CYAN
        )
        self.card_pol_detail.pack(fill=tk.BOTH, expand=True, pady=(2, 0))

        # 策略条目装入可滚动或紧凑容器
        f_pol = self.card_pol_detail.body
        for p_key, p_val in gwc_system_ops.EXHIBIT_POLICIES.items():
            r = tk.Frame(f_pol, bg=self.CARD_BG)
            r.pack(fill=tk.X, pady=2)
            tk.Label(r, text=f"• {p_val['name']}", font=("Segoe UI", 8), bg=self.CARD_BG, fg="#e2e8f0").pack(side=tk.LEFT)
            tk.Button(r, text="恢复", font=("Segoe UI", 7), bg="#334155", fg="#fff", relief="flat", padx=5, pady=1, cursor="hand2", command=lambda k=p_key: self._toggle_single_policy(k, False)).pack(side=tk.RIGHT, padx=2)
            tk.Button(r, text="优化", font=("Segoe UI", 7, "bold"), bg=self.ACCENT_BLUE, fg="#fff", relief="flat", padx=5, pady=1, cursor="hand2", command=lambda k=p_key: self._toggle_single_policy(k, True)).pack(side=tk.RIGHT, padx=2)

        # 初始刷新网卡
        self._refresh_adapters()

    # ==================== Tab 3: 本地系统备份与恢复 (支持自定义文件夹) ====================
    def _build_tab_backup(self, parent):
        box = tk.Frame(parent, bg=self.BG_DARK)
        box.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # 自定义存储文件夹栏
        dir_acts = tk.Frame(box, bg=self.CARD_BG, padx=10, pady=6)
        dir_acts.pack(fill=tk.X, pady=(0, 6))

        tk.Label(dir_acts, text="备份存储目录:", font=("Segoe UI", 9, "bold"), bg=self.CARD_BG, fg="#cbd5e1").pack(side=tk.LEFT)
        ent_bdir = tk.Entry(dir_acts, textvariable=self.backup_dir_var, font=("Consolas", 9), bg="#0f172a", fg="#38bdf8", relief="flat")
        ent_bdir.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)

        tk.Button(dir_acts, text="📂 浏览选择...", font=("Segoe UI", 8, "bold"), bg="#334155", fg="#fff", relief="flat", padx=8, pady=2, cursor="hand2", command=self._choose_backup_dir).pack(side=tk.LEFT, padx=2)
        tk.Button(dir_acts, text="🔄 恢复默认", font=("Segoe UI", 8), bg="#1e293b", fg="#94a3b8", relief="flat", padx=6, pady=2, cursor="hand2", command=self._reset_backup_dir).pack(side=tk.LEFT, padx=2)

        top_acts = tk.Frame(box, bg=self.CARD_BG, padx=10, pady=8)
        top_acts.pack(fill=tk.X, pady=(0, 6))

        tk.Button(top_acts, text="💾 一键备份本机当前系统配置", font=("Segoe UI", 9, "bold"), bg="#059669", fg="#fff", relief="flat", padx=12, pady=4, cursor="hand2", command=self._create_local_backup).pack(side=tk.LEFT, padx=3)
        tk.Button(top_acts, text="🔄 还原选中的本地备份", font=("Segoe UI", 9, "bold"), bg=self.ACCENT_BLUE, fg="#fff", relief="flat", padx=12, pady=4, cursor="hand2", command=self._restore_selected_local_backup).pack(side=tk.LEFT, padx=6)
        tk.Button(top_acts, text="📂 打开备份目录", font=("Segoe UI", 8), bg="#334155", fg="#fff", relief="flat", padx=10, pady=4, cursor="hand2", command=self._open_backup_explorer).pack(side=tk.RIGHT)

        # 备份列表表格
        cols = ("time", "size", "notes")
        self.bk_tree = ttk.Treeview(box, columns=cols, show="tree headings", selectmode="browse")
        self.bk_tree.heading("#0", text="备份文件包 (.gwcbackup)", anchor="w")
        self.bk_tree.heading("time", text="创建时间", anchor="center")
        self.bk_tree.heading("size", text="大小", anchor="e")
        self.bk_tree.heading("notes", text="备份说明", anchor="w")

        self.bk_tree.column("#0", width=280)
        self.bk_tree.column("time", width=140)
        self.bk_tree.column("size", width=80)
        self.bk_tree.column("notes", width=240)
        self.bk_tree.pack(fill=tk.BOTH, expand=True)

        self._refresh_local_backup_tree()

    # ==================== 底部通用操作栏 ====================
    def _build_bottom_bar(self, parent):
        # 全局动态综合状态走马灯看板 (所有数据长文本自动滚动播放)
        st_box = tk.Frame(parent, bg="#0f172a", padx=8, pady=4)
        st_box.pack(fill=tk.X, pady=(0, 4))
        tk.Label(st_box, text="📢 终端动态看板:", font=("Segoe UI", 8, "bold"), bg="#0f172a", fg=self.ACCENT_CYAN).pack(side=tk.LEFT)
        self.bottom_marquee = MarqueeLabel(
            st_box,
            text="展馆控制终端就绪 · 局域网服务运行正常 · 快捷键 Ctrl+Q 随叫随到",
            font=("Segoe UI", 8),
            bg="#0f172a",
            fg="#cbd5e1",
            height=20
        )
        self.bottom_marquee.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        b_frame = ttk.Frame(parent, style="Dark.TFrame")
        b_frame.pack(fill=tk.X, pady=(2, 0))

        btn_hide = tk.Button(
            b_frame,
            text="🌙 隐藏到后台静默守护 (随时按快捷键 Ctrl+Q 瞬间唤出)",
            bg="#0369a1",
            fg="#ffffff",
            activebackground="#0284c7",
            activeforeground="#ffffff",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=20,
            pady=6,
            cursor="hand2",
            command=self.hide_to_background
        )
        btn_hide.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        btn_quit = tk.Button(
            b_frame,
            text="彻底退出",
            bg="#334155",
            fg="#ef4444",
            activebackground="#475569",
            activeforeground="#ef4444",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=16,
            pady=6,
            cursor="hand2",
            command=self.quit_app
        )
        btn_quit.pack(side=tk.RIGHT)

        # 启动周期刷新全局状态跑马灯
        self._schedule_marquee_update()

    def _schedule_marquee_update(self):
        self._update_global_marquee_text()
        self.root.after(3000, self._schedule_marquee_update)

    def _update_global_marquee_text(self):
        local_ip = gwc_discovery.get_local_ip()
        ok_lic, lic_msg = self.license_mgr.check() if self.license_mgr else (False, "未授权")
        conn_st = self.conn_badge_var.get()
        pol_locked = "【展馆工控全套策略已一键锁止生效】" if self.config.get("one_click_set_locked") else "【策略优化待命】"
        msg = f"🏛️ 终端: {self.custom_name}   |   本机IP: {local_ip}   |   中控通信: {conn_st} ({self.status_text_var.get()})   |   商业授权: {lic_msg}   |   策略状态: {pol_locked}   |   呼出热键: {self.current_hotkey} (支持后台静默守护)"
        if hasattr(self, "bottom_marquee") and self.bottom_marquee.winfo_exists():
            self.bottom_marquee.set_text(msg)

    # ==================== 一键设置锁止机制 ====================
    def _do_one_click_setting(self):
        """执行全套展馆工控策略一键设置，执行后锁止按钮并持久化"""
        if messagebox.askyesno("一键设置确认", "确定执行【一键设置】全套展馆工控系统策略吗？\n将一键优化电源免休眠、禁用屏保、屏蔽系统错误弹窗、放行核心通信端口等。"):
            res = gwc_system_ops.apply_all_policies(True)
            cur_t = time.strftime("%H:%M:%S")

            # 锁止按钮
            self.btn_one_click.config(
                text="🔒 已一键设置 (全套策略已锁止生效)",
                bg="#334155",
                fg="#94a3b8",
                state="disabled",
                cursor="arrow"
            )

            # 持久化锁止配置
            self.config["one_click_set_locked"] = True
            dh.ConfigManager.save_config(self.config)

            st = f"✅ [{cur_t}] 全套展馆工控策略已成功一键设置并锁止生效！(生效项: {len(res)})"
            self.opt_status_var.set(st)
            messagebox.showinfo("一键设置完成", f"🎉 已成功一键完成全套展馆工控系统策略优化！\n策略已全部生效，按钮已自动锁止保护。")

    def _unlock_one_click_setting(self):
        """运维专用: 解锁一键设置按钮"""
        if messagebox.askyesno("解锁确认", "确定解锁【一键设置】按钮以允许重新配置吗？"):
            self.btn_one_click.config(
                text="🔥 一键设置 (全套展馆工控策略即刻生效)",
                bg=self.ACCENT_RED,
                fg="#ffffff",
                state="normal",
                cursor="hand2"
            )
            self.config["one_click_set_locked"] = False
            dh.ConfigManager.save_config(self.config)
            cur_t = time.strftime("%H:%M:%S")
            self.opt_status_var.set(f"🔓 [{cur_t}] 一键设置按钮已解锁，可重新点击配置策略")
            messagebox.showinfo("已解锁", "一键设置按钮已恢复为可点击状态！")

    # ==================== 预设应用列表增删与自启/延时启动调度 ====================
    def _load_preset_apps(self) -> list:
        if os.path.exists(self.preset_apps_file):
            try:
                with open(self.preset_apps_file, "r", encoding="utf-8") as f:
                    apps = json.load(f)
                    for a in apps:
                        if "autostart" not in a:
                            a["autostart"] = False
                        if "delay_sec" not in a:
                            a["delay_sec"] = 0
                    return apps
            except Exception:
                pass
        return [
            {"name": "记事本示例", "path": "notepad.exe", "args": "", "autostart": False, "delay_sec": 0}
        ]

    def _save_preset_apps(self):
        try:
            with open(self.preset_apps_file, "w", encoding="utf-8") as f:
                json.dump(self.preset_apps, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _refresh_app_tree(self):
        for i in self.app_tree.get_children():
            self.app_tree.delete(i)
        for idx, item in enumerate(self.preset_apps):
            is_auto = item.get("autostart", False)
            auto_str = "✅ 开机自启" if is_auto else "⬜ 否"
            delay_s = int(item.get("delay_sec", 0))
            delay_str = f"⏳ 延时 {delay_s} 秒" if delay_s > 0 else "⚡ 立即 (0s)"
            self.app_tree.insert(
                "", "end", iid=str(idx),
                text=item.get("name", "未命名"),
                values=(auto_str, delay_str, item.get("path", ""), item.get("args", ""))
            )

    def _add_preset_app(self):
        self._open_preset_app_dialog(is_edit=False)

    def _edit_preset_app(self):
        sel = self.app_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先在列表中选中需要编辑的预设应用！")
            return
        idx = int(sel[0])
        self._open_preset_app_dialog(is_edit=True, target_idx=idx)

    def _open_preset_app_dialog(self, is_edit: bool = False, target_idx: int = -1):
        win = tk.Toplevel(self.root)
        win.title("编辑预设应用" if is_edit else "添加预设常用应用")
        win.geometry("520x330")
        win.configure(bg="#0f172a")
        win.transient(self.root)
        win.grab_set()

        ws = win.winfo_screenwidth()
        hs = win.winfo_screenheight()
        win.geometry(f"520x330+{(ws-520)//2}+{(hs-330)//2}")

        init_app = self.preset_apps[target_idx] if (is_edit and 0 <= target_idx < len(self.preset_apps)) else {}

        # 1. 应用名称
        tk.Label(win, text="应用显示名称:", font=("Segoe UI", 9, "bold"), bg="#0f172a", fg="#cbd5e1").pack(anchor="w", padx=24, pady=(14, 2))
        ent_n = tk.Entry(win, font=("Segoe UI", 10), bg="#1e293b", fg="#fff", relief="flat")
        ent_n.insert(0, init_app.get("name", ""))
        ent_n.pack(fill=tk.X, padx=24)

        # 2. 执行文件路径
        tk.Label(win, text="可执行文件完整路径 (exe / bat / cmd / lnk):", font=("Segoe UI", 9, "bold"), bg="#0f172a", fg="#cbd5e1").pack(anchor="w", padx=24, pady=(8, 2))
        r_p = tk.Frame(win, bg="#0f172a")
        r_p.pack(fill=tk.X, padx=24)
        ent_p = tk.Entry(r_p, font=("Consolas", 9), bg="#1e293b", fg="#38bdf8", relief="flat")
        ent_p.insert(0, init_app.get("path", ""))
        ent_p.pack(side=tk.LEFT, fill=tk.X, expand=True)

        def browse():
            f = filedialog.askopenfilename(filetypes=[("可执行或脚本文件", "*.exe;*.bat;*.cmd;*.py;*.lnk"), ("所有文件", "*.*")])
            if f:
                ent_p.delete(0, tk.END)
                ent_p.insert(0, f)
                if not ent_n.get().strip():
                    ent_n.insert(0, os.path.splitext(os.path.basename(f))[0])

        tk.Button(r_p, text="📁 浏览...", font=("Segoe UI", 8, "bold"), bg="#334155", fg="#fff", relief="flat", padx=8, pady=1, cursor="hand2", command=browse).pack(side=tk.LEFT, padx=(4, 0))

        # 3. 运行参数
        tk.Label(win, text="启动参数 (可选):", font=("Segoe UI", 9), bg="#0f172a", fg="#94a3b8").pack(anchor="w", padx=24, pady=(6, 2))
        ent_a = tk.Entry(win, font=("Segoe UI", 9), bg="#1e293b", fg="#fff", relief="flat")
        ent_a.insert(0, init_app.get("args", ""))
        ent_a.pack(fill=tk.X, padx=24)

        # 4. 开机自启与延时启动设置栏
        f_auto = tk.LabelFrame(win, text=" ⚡ 开机自启动与延时策略 ", bg="#1e293b", fg=self.ACCENT_CYAN, font=("Segoe UI", 9, "bold"), padx=12, pady=6, bd=1)
        f_auto.pack(fill=tk.X, padx=24, pady=(10, 8))

        var_autostart = tk.BooleanVar(value=init_app.get("autostart", False))
        chk_auto = tk.Checkbutton(
            f_auto, text="开机自动随本终端启动", variable=var_autostart,
            bg="#1e293b", fg="#fff", selectcolor="#0f172a", font=("Segoe UI", 9, "bold")
        )
        chk_auto.pack(side=tk.LEFT, padx=(0, 10))

        tk.Label(f_auto, text="延时秒数:", font=("Segoe UI", 9), bg="#1e293b", fg="#cbd5e1").pack(side=tk.LEFT)
        ent_delay = tk.Entry(f_auto, font=("Segoe UI", 9, "bold"), bg="#0f172a", fg=self.ACCENT_CYAN, width=5, justify="center", relief="flat")
        ent_delay.insert(0, str(init_app.get("delay_sec", 0)))
        ent_delay.pack(side=tk.LEFT, padx=4)
        tk.Label(f_auto, text="秒", font=("Segoe UI", 9), bg="#1e293b", fg="#cbd5e1").pack(side=tk.LEFT, padx=(0, 8))

        # 延时快捷预设标签按钮
        for sec_v in [0, 5, 10, 20, 30]:
            lbl_t = f"{sec_v}s" if sec_v > 0 else "立即"
            def make_dcmd(v=sec_v):
                return lambda: (ent_delay.delete(0, tk.END), ent_delay.insert(0, str(v)))
            tk.Button(f_auto, text=lbl_t, font=("Segoe UI", 7), bg="#334155", fg="#cbd5e1", relief="flat", padx=3, pady=1, cursor="hand2", command=make_dcmd()).pack(side=tk.LEFT, padx=1)

        # 保存按钮
        def save():
            name = ent_n.get().strip()
            path = ent_p.get().strip()
            args = ent_a.get().strip()
            if not name or not path:
                messagebox.showerror("错误", "应用名称和执行路径不能为空！", parent=win)
                return
            try:
                delay_val = max(0, int(ent_delay.get().strip()))
            except Exception:
                delay_val = 0

            app_data = {
                "name": name,
                "path": path,
                "args": args,
                "autostart": var_autostart.get(),
                "delay_sec": delay_val
            }

            if is_edit and 0 <= target_idx < len(self.preset_apps):
                self.preset_apps[target_idx] = app_data
            else:
                self.preset_apps.append(app_data)

            self._save_preset_apps()
            self._refresh_app_tree()
            win.destroy()

        b_row = tk.Frame(win, bg="#0f172a")
        b_row.pack(fill=tk.X, padx=24, pady=8)
        tk.Button(b_row, text="💾 保存并应用", font=("Segoe UI", 9, "bold"), bg=self.ACCENT_BLUE, fg="#fff", relief="flat", padx=14, pady=4, cursor="hand2", command=save).pack(side=tk.RIGHT)
        tk.Button(b_row, text="取消", font=("Segoe UI", 9), bg="#334155", fg="#fff", relief="flat", padx=10, pady=4, cursor="hand2", command=win.destroy).pack(side=tk.RIGHT, padx=6)

    def _test_run_preset_app(self):
        """立即在受控端本地启动测试所选应用"""
        sel = self.app_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请在列表中选中要测试启动的应用！")
            return
        idx = int(sel[0])
        app = self.preset_apps[idx]
        p = app.get("path", "")
        a = app.get("args", "")
        res = gwc_system_ops.remote_run_app(p, a)
        if res.get("success"):
            messagebox.showinfo("启动成功", f"🎉 已成功拉起应用:\n{app.get('name')}\n路径: {p}")
        else:
            messagebox.showerror("启动失败", f"❌ 无法启动应用:\n{res.get('error')}")

    def _delete_preset_app(self):
        sel = self.app_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请选择需要移除的预设应用！")
            return
        idx = int(sel[0])
        app = self.preset_apps[idx]
        if messagebox.askyesno("移除确认", f"确定从预设清单中移除应用:\n{app.get('name')} 吗？"):
            del self.preset_apps[idx]
            self._save_preset_apps()
            self._refresh_app_tree()

    def _run_autostart_preset_apps(self):
        """开机或启动时自动延时调度所有被勾选的应用"""
        for app in self.preset_apps:
            if app.get("autostart", False):
                name = app.get("name", "未命名")
                p = app.get("path", "")
                a = app.get("args", "")
                delay_s = int(app.get("delay_sec", 0))

                def _do_launch(aname=name, apath=p, aargs=a, d_sec=delay_s):
                    if d_sec > 0:
                        time.sleep(d_sec)
                    try:
                        if hasattr(self, "root") and self.root.winfo_exists():
                            res = gwc_system_ops.remote_run_app(apath, aargs)
                            if res.get("success"):
                                cur_t = time.strftime("%H:%M:%S")
                                self._safe_after(lambda: self.opt_status_var.set(f"🚀 [{cur_t}] 开机自启应用 [{aname}] (延时 {d_sec}s) 启动成功"))
                    except Exception:
                        pass

                threading.Thread(target=_do_launch, daemon=True).start()

    # ==================== 网络适配器操作 (子网掩码自动获取) ====================
    def _refresh_adapters(self):
        names = []
        if hasattr(gwc_system_ops, "get_network_adapters"):
            names = gwc_system_ops.get_network_adapters()
        elif hasattr(gwc_system_ops, "scan_network_adapters"):
            raw = gwc_system_ops.scan_network_adapters()
            names = [a["name"] if isinstance(a, dict) else a for a in raw]
        self.ad_combo["values"] = names
        if names:
            self.ad_combo.current(0)
            self._on_adapter_select()

    def _on_adapter_select(self, event=None):
        ad = self.ad_combo.get()
        if ad:
            info = gwc_system_ops.read_adapter_ipv4(ad)
            # 子网掩码自动获取，若无则默认 255.255.255.0
            if not info.get("mask") or info["mask"] in ["0.0.0.0", ""]:
                info["mask"] = "255.255.255.0"
            for k in ["ip", "mask", "gateway", "dns1", "dns2"]:
                self.net_entries[k].delete(0, tk.END)
                self.net_entries[k].insert(0, info.get(k, ""))

    def _save_custom_name(self):
        name = self.custom_name_var.get().strip()
        if not name:
            name = socket.gethostname()
            self.custom_name_var.set(name)
        self.config["custom_name"] = name
        dh.ConfigManager.save_config(self.config)
        self.agent_client.set_custom_name(name)
        messagebox.showinfo("终端名称已保存", f"本机终端名称已更新为: 【{name}】\n主控端中心及广播探测将优先以此名称显示。")

    def _choose_backup_dir(self):
        cur = self.backup_dir_var.get().strip()
        d = filedialog.askdirectory(initialdir=cur if os.path.exists(cur) else None, title="选择本地备份保存目录")
        if d:
            self.backup_dir_var.set(d)
            self.config["backup_dir"] = d
            dh.ConfigManager.save_config(self.config)
            self._refresh_local_backup_tree()

    def _reset_backup_dir(self):
        d = gwc_backup.get_default_backup_dir()
        self.backup_dir_var.set(d)
        self.config["backup_dir"] = d
        dh.ConfigManager.save_config(self.config)
        self._refresh_local_backup_tree()

    def _open_backup_explorer(self):
        d = self.backup_dir_var.get().strip() or gwc_backup.get_default_backup_dir()
        if not os.path.exists(d):
            os.makedirs(d, exist_ok=True)
        os.system(f'explorer "{d}"')

    def _apply_static_ip(self):
        ad = self.ad_combo.get()
        ip = self.net_entries["ip"].get().strip()
        mask = self.net_entries["mask"].get().strip() or "255.255.255.0"
        gw = self.net_entries["gateway"].get().strip()
        dns1 = self.net_entries["dns1"].get().strip()
        dns2 = self.net_entries["dns2"].get().strip()
        if not ip:
            messagebox.showerror("错误", "IP 地址不能为空！")
            return
        ok, msg = gwc_system_ops.apply_ip_config(ad, ip, mask, gw, dns1, dns2)
        cur_t = time.strftime("%H:%M:%S")
        if ok:
            st = f"✅ [{cur_t}] 网卡 [{ad}] 静态IP已生效: {ip} / {mask}，网关: {gw or '无'}"
            self.opt_status_var.set(st)
            messagebox.showinfo("成功", f"网卡 [{ad}] 静态配置已生效！\nIP: {ip}\n子网掩码: {mask}")
        else:
            st = f"❌ [{cur_t}] 网卡 [{ad}] 静态IP配置失败: {msg}"
            self.opt_status_var.set(st)
            messagebox.showerror("失败", msg)

    def _apply_dhcp(self):
        ad = self.ad_combo.get()
        ok, msg = gwc_system_ops.apply_dhcp_config(ad)
        cur_t = time.strftime("%H:%M:%S")
        st = f"🔄 [{cur_t}] 网卡 [{ad}] 已切换为 DHCP 动态获取: {msg}"
        self.opt_status_var.set(st)
        messagebox.showinfo("提示", f"网卡 [{ad}] {msg}")
        self._on_adapter_select()

    def _do_reset_network(self):
        if messagebox.askyesno("重置确认", "确定重置 Winsock 和 TCP/IP 协议栈并刷新 DNS 缓存吗？"):
            ok, msg = gwc_system_ops.reset_winsock_and_ip()
            cur_t = time.strftime("%H:%M:%S")
            self.opt_status_var.set(f"🌐 [{cur_t}] 网络协议栈重置: {msg}")
            messagebox.showinfo("网络重置", msg)

    # ==================== 工控单项策略微调 ====================
    def _toggle_single_policy(self, key: str, enable: bool):
        p = gwc_system_ops.EXHIBIT_POLICIES.get(key)
        if p:
            if enable:
                p["set_on"]()
            else:
                p["set_off"]()
            cur_t = time.strftime("%H:%M:%S")
            self.opt_status_var.set(f"⚙️ [{cur_t}] 单项策略 [{p['name']}] 已更新为: {'优化生效' if enable else '默认恢复'}")
            messagebox.showinfo("策略更新", f"{p['name']} 已{'生效' if enable else '恢复'}！")

    def _clean_working_set_memory(self):
        cnt = gwc_system_ops.deep_clean_empty_working_set()
        cur_t = time.strftime("%H:%M:%S")
        self.opt_status_var.set(f"🧹 [{cur_t}] 内存深度整理完成，已释放并缩减 {cnt} 个活跃进程物理工作集")
        messagebox.showinfo("内存释放", f"已成功回收 {cnt} 个系统进程物理工作集内存！")

    def _clean_temp_files(self):
        cnt, mb = gwc_system_ops.clean_system_temp_files()
        cur_t = time.strftime("%H:%M:%S")
        self.opt_status_var.set(f"🗑️ [{cur_t}] 垃圾清理完成，已清除 {cnt} 个临时文件，回收磁盘空间 {mb:.1f} MB")
        messagebox.showinfo("清理完成", f"已清理 {cnt} 个临时缓存文件，释放磁盘空间 {mb:.1f} MB！")

    # ==================== 本地系统备份与恢复 ====================
    def _refresh_local_backup_tree(self):
        for i in self.bk_tree.get_children():
            self.bk_tree.delete(i)
        b_dir = self.backup_dir_var.get().strip() or gwc_backup.get_default_backup_dir()
        bks = gwc_backup.list_local_backups(backup_dir=b_dir)
        for b in bks:
            self.bk_tree.insert("", "end", iid=b["path"], text=b["filename"], values=(b["created_at"], f"{b['size_mb']} MB", b["notes"]))

    def _create_local_backup(self):
        b_dir = self.backup_dir_var.get().strip() or gwc_backup.get_default_backup_dir()
        def runner():
            res = gwc_backup.create_backup_package(name="", notes="受控端本地一键备份", output_dir=b_dir)
            if res.get("success"):
                self.root.after(0, lambda: (
                    self._refresh_local_backup_tree(),
                    messagebox.showinfo("备份成功", f"系统配置已成功备份！\n目录: {b_dir}\n文件: {res.get('filename')}\n大小: {res.get('size_mb')} MB")
                ))
            else:
                self.root.after(0, lambda: messagebox.showerror("备份失败", res.get("error", "未知错误")))
        threading.Thread(target=runner, daemon=True).start()

    def _restore_selected_local_backup(self):
        sel = self.bk_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先在列表中选择要还原的备份包！")
            return
        bk_path = sel[0]
        if messagebox.askyesno("还原确认", f"确定使用备份:\n{os.path.basename(bk_path)}\n一键还原恢复本机的网络设置、工控策略与启动项吗？"):
            def runner():
                res = gwc_backup.restore_backup_package(bk_path)
                msg = res.get("msg", res.get("error"))
                self.root.after(0, lambda: messagebox.showinfo("还原结果", f"系统还原完成:\n{msg}"))
            threading.Thread(target=runner, daemon=True).start()

    # ==================== 快捷键与生命周期 ====================
    def _on_hotkey_triggered(self):
        self.root.after(0, self.toggle_visibility)

    def toggle_visibility(self):
        ok, msg = self.license_mgr.check()
        if not ok:
            # 严格拦截：未授权或授权已过期，绝对不显示终端菜单！弹出最前置不可关闭弹窗
            self.root.withdraw()
            self._show_license_dialog(msg)
            return
        if self.root.state() in ("withdrawn", "iconic"):
            self.show_window()
        else:
            self.hide_to_background()

    def show_window(self):
        ok, msg = self.license_mgr.check()
        if not ok:
            self.root.withdraw()
            self._show_license_dialog(msg)
            return
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.root.attributes("-topmost", True)
        self.root.attributes("-topmost", False)

    def hide_to_background(self):
        self.root.withdraw()

    def _prompt_change_hotkey(self):
        win = tk.Toplevel(self.root)
        win.title("自定义呼出快捷键")
        win.geometry("420x220")
        win.configure(bg="#0f172a")
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        ws = win.winfo_screenwidth()
        hs = win.winfo_screenheight()
        win.geometry(f"420x220+{(ws-420)//2}+{(hs-220)//2}")

        tk.Label(win, text="设置呼出/隐藏受控端界面的全局快捷键", font=("Segoe UI", 10, "bold"), bg="#0f172a", fg="#38bdf8").pack(pady=(16, 8))

        val_var = tk.StringVar(value=self.current_hotkey)
        entry = tk.Entry(win, textvariable=val_var, font=("Consolas", 12, "bold"), bg="#1e293b", fg="#f8fafc", justify="center", relief="flat")
        entry.pack(pady=4, ipady=4, fill=tk.X, padx=50)

        rec_frame = tk.Frame(win, bg="#0f172a")
        rec_frame.pack(pady=6)
        for cand in ["Ctrl+Q", "Ctrl+Alt+F12", "Ctrl+Shift+F9", "Ctrl+Alt+A"]:
            tk.Button(rec_frame, text=cand, font=("Segoe UI", 8), bg="#1e293b", fg="#94a3b8", relief="flat", cursor="hand2", command=lambda c=cand: val_var.set(c)).pack(side=tk.LEFT, padx=3)

        btn_row = tk.Frame(win, bg="#0f172a")
        btn_row.pack(pady=(12, 0))

        def on_confirm():
            new_hk = val_var.get().strip()
            if not new_hk: return
            ok = self.hotkey_mgr.update_hotkey(new_hk)
            if ok:
                self.current_hotkey = new_hk
                self.hotkey_display_var.set(self.hotkey_mgr.last_display_str)
                self.config["hotkey"] = new_hk
                dh.ConfigManager.save_config(self.config)
                win.destroy()
                messagebox.showinfo("成功", f"快捷键已生效: {self.hotkey_mgr.last_display_str}")
            else:
                messagebox.showerror("失败", f"快捷键 {new_hk} 注册失败，可能被系统或其他软件占用！")

        tk.Button(btn_row, text="确定", bg=self.ACCENT_BLUE, fg="#fff", font=("Segoe UI", 9, "bold"), relief="flat", padx=14, pady=3, command=on_confirm).pack(side=tk.LEFT, padx=6)
        tk.Button(btn_row, text="取消", bg="#334155", fg="#fff", font=("Segoe UI", 9), relief="flat", padx=14, pady=3, command=win.destroy).pack(side=tk.LEFT, padx=6)

    def _on_toggle_autostart(self):
        enable = self.autostart_var.get()
        silent = self.silent_boot_var.get()
        ok, msg = dh.AutoStartManager.set_auto_start(enable=enable, silent=silent)
        self.config["auto_start"] = enable
        dh.ConfigManager.save_config(self.config)
        if not ok:
            messagebox.showerror("设置失败", msg)
            self.autostart_var.set(not enable)

    def _on_toggle_silent_boot(self):
        silent = self.silent_boot_var.get()
        self.config["silent_boot"] = silent
        dh.ConfigManager.save_config(self.config)
        if self.autostart_var.get():
            dh.AutoStartManager.set_auto_start(enable=True, silent=silent)

    def _apply_master_address(self):
        ip = self.master_ip_var.get().strip()
        port = int(self.master_port_var.get().strip() or "9888")
        self.config["master_ip"] = ip
        self.config["master_port"] = port
        dh.ConfigManager.save_config(self.config)
        self.agent_client.set_master_address(ip, port)
        messagebox.showinfo("提示", f"已更新主控中心地址为: {ip}:{port}")

    def _on_agent_status_change(self, connected: bool, desc: str):
        def update():
            self.status_text_var.set(desc)
            if connected:
                self.conn_badge_var.set("● 已连接主控")
                self.lbl_badge.config(fg="#10b981")
            else:
                self.conn_badge_var.set("● 待命中")
                self.lbl_badge.config(fg="#f59e0b")
        try:
            if self.root.winfo_exists():
                self.root.after(0, update)
        except Exception:
            pass

    def quit_app(self):
        if messagebox.askyesno("退出确认", "确定要完全停止并退出展馆控制终端吗？"):
            self.hotkey_mgr.stop()
            self.agent_client.stop()
            self.root.destroy()
            sys.exit(0)


def main():
    # 单实例运行互斥防护 (杜绝重复多开)
    if not gwc_system_ops.ensure_single_instance("Global\\GWC_Exhibit_Terminal_Mutex_2026"):
        try:
            r = tk.Tk()
            r.withdraw()
            messagebox.showwarning("提示", "《展馆控制终端》已经在后台运行中！\n可直接按下快捷键 Ctrl+Q 唤出主界面。")
            r.destroy()
        except Exception:
            pass
        sys.exit(0)

    silent = False
    if "--hide" in sys.argv or "--silent" in sys.argv:
        silent = True

    root = tk.Tk()
    app = AgentAppUI(root, silent_startup=silent)
    root.mainloop()


if __name__ == "__main__":
    main()
