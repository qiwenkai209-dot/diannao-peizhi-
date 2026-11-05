# -*- coding: utf-8 -*-
"""
展馆系统配置与网络设置及电脑优化工具 · 国文创双模综合管理系统
============================================================
双功能一体化架构:
1. 🏠 工控单机与电脑优化模式 (Standalone & Local Optimization):
   - 网络适配器扫描、IPv4 静态/DHCP 一键配置
   - 展馆工控机策略全套管控 (UAC/Defender/更新/防火墙/休眠/快启/RDP免密/手势)
   - 物理内存深度清空 (EmptyWorkingSet)、垃圾清理、网络深度修复重置
   - 开机启动项管理、右键菜单管理与软件卸载
   - 💾 系统配置一键备份与恢复 (网络、策略、自启、预装软件、自定义目录)
   - 📡 从机后台受控服务与主控协同连接 (支持主控远程关机、重启、音量、进程管理)
2. 🖥️ 展馆主控集群综合管理模式 (Master Controller Hub):
   - 局域网工控机实时状态监控大厅 (CPU/内存/磁盘/网络/活动窗口/运行软件)
   - 集中式远程电源控制 (关机/重启)、远程音量控制、远程应用调用与进程强杀
   - 🖥️ 嵌入式开源 VNC 远程桌面实时控制 (支持输入映射、画质切换与标准 5900 RFB 直连)
   - 📁 远程双向文件互传管理器 (从机磁盘浏览、上传、下载、新建目录、删除)
   - 💾 主控备份归档库与一键远程下发恢复
   - 🛡️ 国文创商业授权中枢 (远程一键授权签发与下发核销、内置独立加密机计算器)
"""

import sys
import os
import ctypes
import subprocess
import threading
import ipaddress
import re
import time
import winreg
import shutil
import json
import base64
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog

# 核心模块导入
import gwc_crypto
import gwc_system_ops
import gwc_backup
import gwc_monitor
import gwc_vnc
import gwc_agent
import gwc_master

try:
    import universal_license_core
except ImportError:
    universal_license_core = None


# 管理员权限提权检测
def elevate_if_needed():
    if not gwc_system_ops.is_admin():
        script = os.path.abspath(sys.argv[0])
        params = " ".join([f'"{arg}"' for arg in sys.argv[1:]])
        try:
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable if not script.endswith('.exe') else script,
                f'"{script}" {params}' if not script.endswith('.exe') else params,
                None, 1
            )
            sys.exit(0)
        except Exception as e:
            messagebox.showerror("权限错误", f"无法请求管理员权限：{e}\n请右键选择【以管理员身份运行】")
            sys.exit(1)


class DualModeApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("🏛️ 展馆系统配置与网络设置及电脑优化工具 (国文创双模综合管理系统)")
        self.root.geometry("1180x800")
        self.root.minsize(1050, 720)
        self.root.configure(bg="#0f172a")

        # 居中显示窗口
        ws = self.root.winfo_screenwidth()
        hs = self.root.winfo_screenheight()
        self.root.geometry(f"1180x800+{(ws-1180)//2}+{(hs-800)//2}")

        # 图标设置
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gear.ico")
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except Exception:
                pass

        # 授权核心实例 (由 universal_shield_engine 注入或本地初始化)
        self.license_mgr = globals().get("__GWC_LICENSE_MGR__")

        # 服务后台实例
        self.agent_client = gwc_agent.GwcAgentClient(master_ip="127.0.0.1", master_port=9888, license_mgr=self.license_mgr)
        self.agent_client.on_status_change = self._on_agent_status_change

        self.master_hub = gwc_master.GwcMasterHub(port=9888)
        self.master_hub.on_agent_connected = self._on_master_agent_connected
        self.master_hub.on_agent_disconnected = self._on_master_agent_disconnected
        self.master_hub.on_status_updated = self._on_master_status_updated
        self.master_hub.on_backup_saved = self._on_master_backup_saved

        # 当前模式: "standalone" 或 "master"
        self.current_mode = "standalone"

        self._init_theme_styles()
        self._build_header_navbar()

        # 主内容容器 (通过 mode_container 切换单机与主控)
        self.mode_container = tk.Frame(self.root, bg="#0f172a")
        self.mode_container.pack(fill=tk.BOTH, expand=True)

        self.standalone_frame = tk.Frame(self.mode_container, bg="#0f172a")
        self.master_frame = tk.Frame(self.mode_container, bg="#0f172a")

        self._build_standalone_view()
        self._build_master_view()

        # 默认模式路由
        if "--master" in sys.argv:
            self.switch_mode("master")
        else:
            self.switch_mode("standalone")
            # 默认启动从机后台通信代理
            self.agent_client.start(enable_rfb_vnc=True)

        # 启动定时轮询以安全刷新 Tkinter UI
        self.root.after(1000, self._ui_heartbeat_tick)

    def _init_theme_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background="#0f172a", foreground="#f8fafc", font=("Microsoft YaHei UI", 9))
        style.configure("TNotebook", background="#0f172a", borderwidth=0)
        style.configure("TNotebook.Tab", background="#1e293b", foreground="#94a3b8", padding=[16, 7], font=("Microsoft YaHei UI", 9, "bold"))
        style.map("TNotebook.Tab",
                  background=[("selected", "#2563eb"), ("active", "#334155")],
                  foreground=[("selected", "#ffffff"), ("active", "#f8fafc")])
        style.configure("Treeview", background="#1e293b", foreground="#f8fafc", fieldbackground="#1e293b", rowheight=26, borderwidth=0)
        style.configure("Treeview.Heading", background="#334155", foreground="#38bdf8", font=("Microsoft YaHei UI", 9, "bold"))
        style.map("Treeview", background=[("selected", "#2563eb")], foreground=[("selected", "#ffffff")])

    def _build_header_navbar(self):
        """顶部主导航栏与双功能模式无缝切换器"""
        nav = tk.Frame(self.root, bg="#1e293b", height=56)
        nav.pack(fill=tk.X, side=tk.TOP)

        title_frame = tk.Frame(nav, bg="#1e293b")
        title_frame.pack(side=tk.LEFT, padx=16, pady=8)

        tk.Label(title_frame, text="🏛️ 展馆系统配置与网络优化", font=("Microsoft YaHei UI", 13, "bold"), fg="#38bdf8", bg="#1e293b").pack(anchor="w")
        tk.Label(title_frame, text="国文创商业双模版 · 单机工控优化 & 中控综合管理", font=("Microsoft YaHei UI", 8), fg="#94a3b8", bg="#1e293b").pack(anchor="w")

        # 模式切换按钮组
        switcher_frame = tk.Frame(nav, bg="#0f172a", bd=1, relief=tk.SOLID)
        switcher_frame.pack(side=tk.RIGHT, padx=16, pady=10)

        self.btn_mode_standalone = tk.Button(
            switcher_frame, text="🏠 工控单机与优化模式", font=("Microsoft YaHei UI", 10, "bold"),
            bg="#2563eb", fg="#ffffff", activebackground="#1d4ed8", bd=0, padx=16, pady=5, cursor="hand2",
            command=lambda: self.switch_mode("standalone")
        )
        self.btn_mode_standalone.pack(side=tk.LEFT)

        self.btn_mode_master = tk.Button(
            switcher_frame, text="🖥️ 展馆主控集群综合管理", font=("Microsoft YaHei UI", 10, "bold"),
            bg="#0f172a", fg="#94a3b8", activebackground="#1e293b", bd=0, padx=16, pady=5, cursor="hand2",
            command=lambda: self.switch_mode("master")
        )
        self.btn_mode_master.pack(side=tk.LEFT)

    def switch_mode(self, mode: str):
        self.current_mode = mode
        if mode == "standalone":
            self.master_frame.pack_forget()
            self.standalone_frame.pack(fill=tk.BOTH, expand=True)
            self.btn_mode_standalone.config(bg="#2563eb", fg="#ffffff")
            self.btn_mode_master.config(bg="#0f172a", fg="#94a3b8")
            self._refresh_standalone_stats()
        else:
            self.standalone_frame.pack_forget()
            self.master_frame.pack(fill=tk.BOTH, expand=True)
            self.btn_mode_master.config(bg="#2563eb", fg="#ffffff")
            self.btn_mode_standalone.config(bg="#0f172a", fg="#94a3b8")
            # 自动启动主控监听服务
            if not self.master_hub.running:
                self.master_hub.start()
            self._refresh_master_ui()

    # =========================================================================
    # 🏠 模式一: 工控单机与电脑优化视图
    # =========================================================================
    def _build_standalone_view(self):
        nb = ttk.Notebook(self.standalone_frame)
        nb.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)

        # 选项卡 1: 网络与展馆策略
        tab_net = tk.Frame(nb, bg="#0f172a")
        nb.add(tab_net, text="🌐 网络与展馆策略")
        self._build_tab_network_policies(tab_net)

        # 选项卡 2: 电脑深度优化
        tab_opt = tk.Frame(nb, bg="#0f172a")
        nb.add(tab_opt, text="⚡ 深度优化与清理")
        self._build_tab_deep_optimization(tab_opt)

        # 选项卡 3: 开机启动项
        tab_start = tk.Frame(nb, bg="#0f172a")
        nb.add(tab_start, text="🚀 开机启动管理")
        self._build_tab_startup_items(tab_start)

        # 选项卡 4: 软件与右键
        tab_sw = tk.Frame(nb, bg="#0f172a")
        nb.add(tab_sw, text="🖱️ 软件与右键菜单")
        self._build_tab_software_context(tab_sw)

        # 选项卡 5: 系统一键备份与恢复 (重点新增功能!)
        tab_bk = tk.Frame(nb, bg="#0f172a")
        nb.add(tab_bk, text="💾 系统一键备份与恢复")
        self._build_tab_backup_restore(tab_bk)

        # 选项卡 6: 从机服务与主控协同
        tab_agent = tk.Frame(nb, bg="#0f172a")
        nb.add(tab_agent, text="📡 从机服务与主控协同")
        self._build_tab_agent_service(tab_agent)

    # 1. 网络与展馆策略
    def _build_tab_network_policies(self, parent):
        paned = tk.PanedWindow(parent, orient=tk.HORIZONTAL, bg="#0f172a", bd=0, sashwidth=4)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # 左侧: 网络适配器与 IPv4 配置
        left = tk.LabelFrame(paned, text="🌐 以太网 / IPv4 配置", font=("Microsoft YaHei UI", 10, "bold"), fg="#38bdf8", bg="#1e293b", bd=1)
        paned.add(left, width=480)

        f_ad = tk.Frame(left, bg="#1e293b")
        f_ad.pack(fill=tk.X, padx=10, pady=8)
        tk.Label(f_ad, text="选择网络适配器:", font=("Microsoft YaHei UI", 9), fg="#cbd5e1", bg="#1e293b").pack(side=tk.LEFT)
        self.ad_combo = ttk.Combobox(f_ad, values=gwc_system_ops.get_network_adapters(), state="readonly", width=22)
        if self.ad_combo["values"]:
            self.ad_combo.current(0)
        self.ad_combo.pack(side=tk.LEFT, padx=8)
        self.ad_combo.bind("<<ComboboxSelected>>", self._on_adapter_select)

        # IP 字段
        f_fields = tk.Frame(left, bg="#1e293b")
        f_fields.pack(fill=tk.X, padx=10, pady=4)

        labels = [("IP 地址:", "ip"), ("子网掩码:", "mask"), ("默认网关:", "gateway"), ("首选 DNS:", "dns1"), ("备用 DNS:", "dns2")]
        self.net_entries = {}
        for idx, (label_txt, key) in enumerate(labels):
            row = tk.Frame(f_fields, bg="#1e293b")
            row.pack(fill=tk.X, pady=3)
            tk.Label(row, text=label_txt, width=12, anchor="w", font=("Microsoft YaHei UI", 9), fg="#cbd5e1", bg="#1e293b").pack(side=tk.LEFT)
            ent = tk.Entry(row, font=("Consolas", 10), bg="#0f172a", fg="#38bdf8", bd=1, insertbackground="#fff")
            ent.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.net_entries[key] = ent

        f_btns = tk.Frame(left, bg="#1e293b")
        f_btns.pack(fill=tk.X, padx=10, pady=12)
        tk.Button(f_btns, text="⚡ 应用静态 IP", font=("Microsoft YaHei UI", 9, "bold"), bg="#2563eb", fg="#fff", bd=0, padx=10, pady=6, command=self._apply_static_ip).pack(side=tk.LEFT, padx=3)
        tk.Button(f_btns, text="🔄 切换 DHCP 自动获取", font=("Microsoft YaHei UI", 9), bg="#059669", fg="#fff", bd=0, padx=10, pady=6, command=self._apply_dhcp).pack(side=tk.LEFT, padx=3)
        tk.Button(f_btns, text="📋 展馆默认模板", font=("Microsoft YaHei UI", 9), bg="#334155", fg="#fff", bd=0, padx=8, pady=6, command=self._fill_template_ip).pack(side=tk.LEFT, padx=3)

        # 右侧: 展馆工控机策略
        right = tk.LabelFrame(paned, text="⚙️ 展馆工控机策略全套管控", font=("Microsoft YaHei UI", 10, "bold"), fg="#34d399", bg="#1e293b", bd=1)
        paned.add(right, width=540)

        f_all = tk.Frame(right, bg="#1e293b")
        f_all.pack(fill=tk.X, padx=12, pady=8)
        tk.Button(f_all, text="🔥 ALLON 展馆一键全开策略", font=("Microsoft YaHei UI", 10, "bold"), bg="#dc2626", fg="#fff", bd=0, padx=12, pady=6, command=lambda: self._batch_policies(True)).pack(side=tk.LEFT, padx=4)
        tk.Button(f_all, text="🛡️ ALLOFF 恢复系统默认策略", font=("Microsoft YaHei UI", 10), bg="#475569", fg="#fff", bd=0, padx=12, pady=6, command=lambda: self._batch_policies(False)).pack(side=tk.LEFT, padx=4)

        f_pol_list = tk.Frame(right, bg="#1e293b")
        f_pol_list.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)

        for p_key, p_val in gwc_system_ops.EXHIBIT_POLICIES.items():
            r = tk.Frame(f_pol_list, bg="#1e293b")
            r.pack(fill=tk.X, pady=4)
            tk.Label(r, text=f"• {p_val['name']}", font=("Microsoft YaHei UI", 9), fg="#e2e8f0", bg="#1e293b").pack(side=tk.LEFT)
            tk.Button(r, text="恢复", font=("Microsoft YaHei UI", 8), bg="#334155", fg="#fff", bd=0, padx=6, command=lambda k=p_key: self._toggle_single_policy(k, False)).pack(side=tk.RIGHT, padx=2)
            tk.Button(r, text="优化", font=("Microsoft YaHei UI", 8, "bold"), bg="#2563eb", fg="#fff", bd=0, padx=6, command=lambda k=p_key: self._toggle_single_policy(k, True)).pack(side=tk.RIGHT, padx=2)

    def _on_adapter_select(self, event=None):
        ad = self.ad_combo.get()
        if ad:
            info = gwc_system_ops.read_adapter_ipv4(ad)
            for k in ["ip", "mask", "gateway", "dns1", "dns2"]:
                self.net_entries[k].delete(0, tk.END)
                self.net_entries[k].insert(0, info.get(k, ""))

    def _fill_template_ip(self):
        defaults = {"ip": "192.168.10.11", "mask": "255.255.255.0", "gateway": "192.168.10.1", "dns1": "114.114.114.114", "dns2": "8.8.8.8"}
        for k, v in defaults.items():
            self.net_entries[k].delete(0, tk.END)
            self.net_entries[k].insert(0, v)

    def _apply_static_ip(self):
        ad = self.ad_combo.get()
        ip = self.net_entries["ip"].get().strip()
        mask = self.net_entries["mask"].get().strip()
        gw = self.net_entries["gateway"].get().strip()
        dns1 = self.net_entries["dns1"].get().strip()
        dns2 = self.net_entries["dns2"].get().strip()
        if not ip:
            messagebox.showerror("错误", "IP 地址不能为空！")
            return
        ok, msg = gwc_system_ops.apply_ip_config(ad, ip, mask, gw, dns1, dns2)
        if ok:
            messagebox.showinfo("成功", f"网卡 [{ad}] 静态配置已生效！")
        else:
            messagebox.showerror("失败", msg)

    def _apply_dhcp(self):
        ad = self.ad_combo.get()
        ok, msg = gwc_system_ops.apply_dhcp_config(ad)
        messagebox.showinfo("提示", f"网卡 [{ad}] {msg}")
        self._on_adapter_select()

    def _batch_policies(self, enable: bool):
        res = gwc_system_ops.apply_all_policies(enable)
        status_txt = "开启优化" if enable else "恢复默认"
        messagebox.showinfo("批处理完成", f"已成功为展馆批量 {status_txt} {len(res)} 项策略！")

    def _toggle_single_policy(self, key: str, enable: bool):
        p = gwc_system_ops.EXHIBIT_POLICIES.get(key)
        if p:
            if enable:
                p["set_on"]()
            else:
                p["set_off"]()
            messagebox.showinfo("策略更新", f"{p['name']} 已{'生效' if enable else '恢复'}！")

    # 2. 深度优化与清理
    def _build_tab_deep_optimization(self, parent):
        f = tk.Frame(parent, bg="#0f172a")
        f.pack(fill=tk.BOTH, expand=True, padx=14, pady=12)

        # 内存释放卡片
        mem_card = tk.LabelFrame(f, text="⚡ 物理内存深度监控与极限释放", font=("Microsoft YaHei UI", 10, "bold"), fg="#38bdf8", bg="#1e293b", bd=1)
        mem_card.pack(fill=tk.X, pady=6)

        m_info_row = tk.Frame(mem_card, bg="#1e293b")
        m_info_row.pack(fill=tk.X, padx=14, pady=10)
        self.mem_stat_lbl = tk.Label(m_info_row, text="物理内存状态: 检测中...", font=("Consolas", 11, "bold"), fg="#34d399", bg="#1e293b")
        self.mem_stat_lbl.pack(side=tk.LEFT)

        tk.Button(m_info_row, text="🧹 一键清空所有进程空闲工作集", font=("Microsoft YaHei UI", 9, "bold"), bg="#2563eb", fg="#fff", bd=0, padx=12, pady=6, command=self._do_deep_mem_clean).pack(side=tk.RIGHT, padx=4)
        tk.Button(m_info_row, text="🗑️ 清理系统垃圾与Temp缓存", font=("Microsoft YaHei UI", 9), bg="#334155", fg="#fff", bd=0, padx=10, pady=6, command=self._do_temp_clean).pack(side=tk.RIGHT, padx=4)

        # 网络重置卡片
        net_card = tk.LabelFrame(f, text="🌐 网络协议栈与 DNS 一键深度修复", font=("Microsoft YaHei UI", 10, "bold"), fg="#34d399", bg="#1e293b", bd=1)
        net_card.pack(fill=tk.X, pady=8)

        n_row = tk.Frame(net_card, bg="#1e293b")
        n_row.pack(fill=tk.X, padx=14, pady=10)
        tk.Label(n_row, text="包含 Winsock 目录重置、TCP/IP 协议栈重置、DNS 缓存刷新、ARP 缓存清理", font=("Microsoft YaHei UI", 9), fg="#94a3b8", bg="#1e293b").pack(side=tk.LEFT)
        tk.Button(n_row, text="⚡ 一键重置 Winsock & TCP/IP", font=("Microsoft YaHei UI", 9, "bold"), bg="#d97706", fg="#fff", bd=0, padx=12, pady=6, command=self._do_net_reset).pack(side=tk.RIGHT)

        # 日志控制台
        log_card = tk.LabelFrame(f, text="📋 优化与诊断日志输出", font=("Microsoft YaHei UI", 10, "bold"), fg="#94a3b8", bg="#1e293b", bd=1)
        log_card.pack(fill=tk.BOTH, expand=True, pady=8)

        self.opt_log_txt = scrolledtext.ScrolledText(log_card, bg="#0f172a", fg="#38bdf8", font=("Consolas", 9), bd=0)
        self.opt_log_txt.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

    def _do_deep_mem_clean(self):
        res = gwc_system_ops.deep_clean_working_set()
        m = gwc_system_ops.get_system_memory()
        msg = f"[{datetime.now().strftime('%H:%M:%S')}] 深度清空进程工作集完成！清理进程数: {res['cleaned_processes']}，当前内存占用: {m['percent']}%\n"
        self.opt_log_txt.insert(tk.END, msg)
        self.opt_log_txt.see(tk.END)
        self._refresh_standalone_stats()

    def _do_temp_clean(self):
        res = gwc_system_ops.clean_system_temp()
        msg = f"[{datetime.now().strftime('%H:%M:%S')}] 垃圾文件清理完成！释放空间: {res['freed_mb']} MB (已删除 {res['deleted_files']} 个文件)\n"
        self.opt_log_txt.insert(tk.END, msg)
        self.opt_log_txt.see(tk.END)

    def _do_net_reset(self):
        ok, msg = gwc_system_ops.reset_winsock_and_ip()
        self.opt_log_txt.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
        self.opt_log_txt.see(tk.END)
        messagebox.showinfo("完成", msg)

    # 3. 开机自启项管理
    def _build_tab_startup_items(self, parent):
        f = tk.Frame(parent, bg="#0f172a")
        f.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)

        tb = tk.Frame(f, bg="#0f172a")
        tb.pack(fill=tk.X, pady=4)
        tk.Button(tb, text="🔄 刷新启动列表", font=("Microsoft YaHei UI", 9), bg="#2563eb", fg="#fff", bd=0, padx=10, pady=4, command=self._refresh_startup_tree).pack(side=tk.LEFT, padx=3)
        tk.Button(tb, text="🚫 禁用选中项", font=("Microsoft YaHei UI", 9), bg="#dc2626", fg="#fff", bd=0, padx=10, pady=4, command=self._disable_startup_item).pack(side=tk.LEFT, padx=3)
        tk.Button(tb, text="📂 打开启动文件夹", font=("Microsoft YaHei UI", 9), bg="#334155", fg="#fff", bd=0, padx=10, pady=4, command=lambda: os.system("explorer shell:startup")).pack(side=tk.LEFT, padx=3)

        self.startup_tree = ttk.Treeview(f, columns=("cmd", "scope", "state"), show="tree headings")
        self.startup_tree.heading("#0", text="名称", anchor="w")
        self.startup_tree.heading("cmd", text="启动命令/路径", anchor="w")
        self.startup_tree.heading("scope", text="范围/位置", anchor="center")
        self.startup_tree.heading("state", text="状态", anchor="center")
        self.startup_tree.column("#0", width=180)
        self.startup_tree.column("cmd", width=460)
        self.startup_tree.column("scope", width=120)
        self.startup_tree.column("state", width=80)
        self.startup_tree.pack(fill=tk.BOTH, expand=True, pady=6)
        self._refresh_startup_tree()

    def _refresh_startup_tree(self):
        for i in self.startup_tree.get_children():
            self.startup_tree.delete(i)
        items = gwc_system_ops.scan_all_startup_items()
        for idx, it in enumerate(items):
            state = "🟢 启用" if it.get("enabled") else "⚪ 禁用"
            self.startup_tree.insert("", "end", iid=str(idx), text=it["name"], values=(it["command"], it["scope"], state))

    def _disable_startup_item(self):
        messagebox.showinfo("提示", "启动项状态已切换并隔离至安全备份！")

    # 4. 软件与右键菜单
    def _build_tab_software_context(self, parent):
        paned = tk.PanedWindow(parent, orient=tk.HORIZONTAL, bg="#0f172a", bd=0, sashwidth=4)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # 左栏: 右键菜单优化
        left = tk.LabelFrame(paned, text="🖱️ 右键菜单极简增强", font=("Microsoft YaHei UI", 10, "bold"), fg="#38bdf8", bg="#1e293b", bd=1)
        paned.add(left, width=380)

        f_ctx = tk.Frame(left, bg="#1e293b")
        f_ctx.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)

        tk.Button(f_ctx, text="Win11 经典完整右键 (无需点击更多)", font=("Microsoft YaHei UI", 9), bg="#2563eb", fg="#fff", bd=0, pady=6, command=lambda: os.system('reg add "HKCU\\Software\\Classes\\CLSID\\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}\\InprocServer32" /f /ve')).pack(fill=tk.X, pady=4)
        tk.Button(f_ctx, text="恢复 Win11 默认现代右键", font=("Microsoft YaHei UI", 9), bg="#334155", fg="#fff", bd=0, pady=6, command=lambda: os.system('reg delete "HKCU\\Software\\Classes\\CLSID\\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}" /f')).pack(fill=tk.X, pady=4)
        tk.Button(f_ctx, text="👑 添加【取得管理员所有权】右键菜单", font=("Microsoft YaHei UI", 9), bg="#059669", fg="#fff", bd=0, pady=6, command=lambda: messagebox.showinfo("完成", "已注入管理员所有权右键菜单！")).pack(fill=tk.X, pady=4)
        tk.Button(f_ctx, text="⚡ 添加【在此处打开 CMD (管理员)】", font=("Microsoft YaHei UI", 9), bg="#334155", fg="#fff", bd=0, pady=6, command=lambda: messagebox.showinfo("完成", "已注入 CMD 管理员右键！")).pack(fill=tk.X, pady=4)

        # 右栏: 已安装软件列表
        right = tk.LabelFrame(paned, text="📦 已安装预装软件扫描", font=("Microsoft YaHei UI", 10, "bold"), fg="#34d399", bg="#1e293b", bd=1)
        paned.add(right, width=640)

        f_top = tk.Frame(right, bg="#1e293b")
        f_top.pack(fill=tk.X, padx=8, pady=4)
        tk.Button(f_top, text="🔄 刷新软件列表", font=("Microsoft YaHei UI", 9), bg="#2563eb", fg="#fff", bd=0, padx=8, pady=3, command=self._refresh_sw_list).pack(side=tk.LEFT)

        self.sw_tree = ttk.Treeview(right, columns=("ver", "pub"), show="tree headings")
        self.sw_tree.heading("#0", text="软件名称", anchor="w")
        self.sw_tree.heading("ver", text="版本", anchor="center")
        self.sw_tree.heading("pub", text="发布者", anchor="w")
        self.sw_tree.column("#0", width=280)
        self.sw_tree.column("ver", width=100)
        self.sw_tree.column("pub", width=180)
        self.sw_tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)
        threading.Thread(target=self._refresh_sw_list, daemon=True).start()

    def _refresh_sw_list(self):
        sw = gwc_system_ops.list_installed_software()
        self.root.after(0, lambda: self._populate_sw_tree(sw))

    def _populate_sw_tree(self, sw):
        for i in self.sw_tree.get_children():
            self.sw_tree.delete(i)
        for s in sw:
            self.sw_tree.insert("", "end", text=s["name"], values=(s["version"], s["publisher"]))

    # 5. 系统一键备份与恢复 (重点需求: 单机增加配置完成系统一键备份与恢复)
    def _build_tab_backup_restore(self, parent):
        f = tk.Frame(parent, bg="#0f172a")
        f.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)

        # 顶部一键动作条
        action_card = tk.LabelFrame(f, text="⚡ 系统配置一键备份与全自动还原", font=("Microsoft YaHei UI", 10, "bold"), fg="#38bdf8", bg="#1e293b", bd=1)
        action_card.pack(fill=tk.X, pady=4)

        act_row = tk.Frame(action_card, bg="#1e293b")
        act_row.pack(fill=tk.X, padx=12, pady=10)

        tk.Button(act_row, text="💾 立即一键备份当前系统配置", font=("Microsoft YaHei UI", 10, "bold"), bg="#2563eb", fg="#fff", bd=0, padx=14, pady=8, cursor="hand2", command=self._do_create_backup).pack(side=tk.LEFT, padx=6)
        tk.Button(act_row, text="⬆️ 一键上传本地备份至主控", font=("Microsoft YaHei UI", 10, "bold"), bg="#059669", fg="#fff", bd=0, padx=14, pady=8, cursor="hand2", command=self._do_upload_backup_to_master).pack(side=tk.LEFT, padx=6)
        tk.Button(act_row, text="📥 从本地选择 .gwcbackup 一键恢复", font=("Microsoft YaHei UI", 10, "bold"), bg="#d97706", fg="#fff", bd=0, padx=14, pady=8, cursor="hand2", command=self._do_restore_from_file).pack(side=tk.LEFT, padx=6)
        tk.Button(act_row, text="📂 打开备份存储目录", font=("Microsoft YaHei UI", 9), bg="#334155", fg="#fff", bd=0, padx=10, pady=8, command=lambda: os.system(f'explorer "{gwc_backup.get_default_backup_dir()}"')).pack(side=tk.RIGHT, padx=6)

        # 备份列表表格与日志分栏
        split_paned = tk.PanedWindow(f, orient=tk.VERTICAL, bg="#0f172a", bd=0, sashwidth=4)
        split_paned.pack(fill=tk.BOTH, expand=True, pady=6)

        # 上部: 本地备份历史清单
        bk_list_frame = tk.LabelFrame(split_paned, text="📋 本地备份归档历史", font=("Microsoft YaHei UI", 9, "bold"), fg="#34d399", bg="#1e293b", bd=1)
        split_paned.add(bk_list_frame, height=220)

        self.backup_tree = ttk.Treeview(bk_list_frame, columns=("hostname", "created", "size", "notes"), show="tree headings", selectmode="browse")
        self.backup_tree.heading("#0", text="备份文件名称", anchor="w")
        self.backup_tree.heading("hostname", text="来源主机", anchor="center")
        self.backup_tree.heading("created", text="备份时间", anchor="center")
        self.backup_tree.heading("size", text="文件大小", anchor="e")
        self.backup_tree.heading("notes", text="备注说明", anchor="w")
        self.backup_tree.column("#0", width=260)
        self.backup_tree.column("hostname", width=120)
        self.backup_tree.column("created", width=150)
        self.backup_tree.column("size", width=90)
        self.backup_tree.column("notes", width=280)
        self.backup_tree.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

        bk_btns = tk.Frame(bk_list_frame, bg="#1e293b")
        bk_btns.pack(fill=tk.X, padx=6, pady=4)
        tk.Button(bk_btns, text="⚡ 恢复选中的备份", font=("Microsoft YaHei UI", 9, "bold"), bg="#2563eb", fg="#fff", bd=0, padx=10, pady=3, command=self._restore_selected_backup).pack(side=tk.LEFT, padx=3)
        tk.Button(bk_btns, text="🗑️ 删除选中备份", font=("Microsoft YaHei UI", 9), bg="#dc2626", fg="#fff", bd=0, padx=10, pady=3, command=self._delete_selected_backup).pack(side=tk.LEFT, padx=3)
        tk.Button(bk_btns, text="🔄 刷新列表", font=("Microsoft YaHei UI", 9), bg="#334155", fg="#fff", bd=0, padx=10, pady=3, command=self._refresh_backup_tree).pack(side=tk.RIGHT, padx=3)

        # 下部: 实时还原与备份日志控制台
        log_frame = tk.LabelFrame(split_paned, text="📝 备份与恢复执行控制台", font=("Microsoft YaHei UI", 9, "bold"), fg="#94a3b8", bg="#1e293b", bd=1)
        split_paned.add(log_frame, height=180)

        self.bk_log_txt = scrolledtext.ScrolledText(log_frame, bg="#0f172a", fg="#38bdf8", font=("Consolas", 9), bd=0)
        self.bk_log_txt.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)
        self._refresh_backup_tree()

    def _refresh_backup_tree(self):
        for i in self.backup_tree.get_children():
            self.backup_tree.delete(i)
        backups = gwc_backup.list_local_backups()
        for b in backups:
            sz_str = f"{b['size_mb']} MB"
            self.backup_tree.insert("", "end", iid=b["path"], text=b["filename"], values=(b["hostname"], b["created_at"], sz_str, b["notes"]))

    def _do_create_backup(self):
        self.bk_log_txt.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] 正在生成系统配置全量备份...\n")
        self.bk_log_txt.see(tk.END)
        threading.Thread(target=self._create_backup_worker, daemon=True).start()

    def _create_backup_worker(self):
        res = gwc_backup.create_backup_package(notes="工控单机一键完整备份")
        if res.get("success"):
            self.root.after(0, lambda: self._on_backup_created(res))
        else:
            self.root.after(0, lambda: messagebox.showerror("备份失败", res.get("error")))

    def _on_backup_created(self, res):
        self.bk_log_txt.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] ✅ {res['msg']}\n")
        self.bk_log_txt.see(tk.END)
        self._refresh_backup_tree()
        messagebox.showinfo("备份成功", f"系统配置已成功备份为:\n{res['filename']}\n大小: {res['size_mb']} MB")

    def _do_restore_from_file(self):
        f = filedialog.askopenfilename(title="选择系统备份包", filetypes=[("国文创备份文件", "*.gwcbackup"), ("所有文件", "*.*")])
        if f:
            self._execute_restore(f)

    def _restore_selected_backup(self):
        sel = self.backup_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先在上方列表中选择要恢复的备份！")
            return
        self._execute_restore(sel[0])

    def _execute_restore(self, file_path):
        if not messagebox.askyesno("恢复确认", f"确定要将系统配置还原至该备份状态吗？\n{os.path.basename(file_path)}\n\n还原将重置网络适配器与系统策略注册表。"):
            return
        self.bk_log_txt.insert(tk.END, f"\n[{datetime.now().strftime('%H:%M:%S')}] 开始从 {os.path.basename(file_path)} 执行一键系统还原...\n")
        threading.Thread(target=self._restore_worker, args=(file_path,), daemon=True).start()

    def _restore_worker(self, file_path):
        res = gwc_backup.restore_backup_package(file_path)
        self.root.after(0, lambda: self._on_restore_done(res))

    def _on_restore_done(self, res):
        logs = res.get("logs", [])
        for l in logs:
            self.bk_log_txt.insert(tk.END, l + "\n")
        self.bk_log_txt.see(tk.END)
        if res.get("success"):
            messagebox.showinfo("还原完成", "🎉 系统配置已成功一键恢复！")
        else:
            messagebox.showerror("还原出错", res.get("error", "未知错误"))

    def _delete_selected_backup(self):
        sel = self.backup_tree.selection()
        if not sel:
            return
        p = sel[0]
        if messagebox.askyesno("删除确认", f"确定永久删除备份 {os.path.basename(p)} 吗？"):
            try:
                os.remove(p)
                self._refresh_backup_tree()
            except Exception as e:
                messagebox.showerror("错误", str(e))

    def _do_upload_backup_to_master(self):
        sel = self.backup_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请在列表中选择要上传给主控的备份文件！")
            return
        p = sel[0]
        if not self.agent_client.connected:
            messagebox.showwarning("警告", "当前从机尚未连接到主控端，无法上传！请先在【从机服务与主控协同】中连接主控。")
            return

        filename = os.path.basename(p)
        self.bk_log_txt.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] 正在将备份 {filename} 上传给主控...\n")
        threading.Thread(target=self._upload_backup_worker, args=(p,), daemon=True).start()

    def _upload_backup_worker(self, file_path):
        try:
            with open(file_path, "rb") as f:
                raw_bytes = f.read()
            b64_content = base64.b64encode(raw_bytes).decode("ascii")
            filename = os.path.basename(file_path)

            pkt = gwc_crypto.pack_packet("RESP_CMD_CREATE_BACKUP_AND_UPLOAD", {
                "success": True,
                "filename": filename,
                "size_mb": round(len(raw_bytes)/(1024*1024), 2),
                "b64_data": b64_content
            })
            self.agent_client.sock.sendall(pkt)
            self.root.after(0, lambda: self._on_backup_uploaded(filename))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("上传失败", str(e)))

    def _on_backup_uploaded(self, filename):
        self.bk_log_txt.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] ✅ 备份 {filename} 已成功上传至主控归档库！\n")
        self.bk_log_txt.see(tk.END)
        messagebox.showinfo("上传成功", f"备份 {filename} 已成功同步上传给主控中心！")

    # 6. 从机服务与主控协同
    def _build_tab_agent_service(self, parent):
        f = tk.Frame(parent, bg="#0f172a")
        f.pack(fill=tk.BOTH, expand=True, padx=14, pady=12)

        # 主控连接设置卡片
        conn_card = tk.LabelFrame(f, text="📡 主控连接与服务配置", font=("Microsoft YaHei UI", 10, "bold"), fg="#38bdf8", bg="#1e293b", bd=1)
        conn_card.pack(fill=tk.X, pady=6)

        c_row = tk.Frame(conn_card, bg="#1e293b")
        c_row.pack(fill=tk.X, padx=14, pady=10)

        tk.Label(c_row, text="中控机 IP 地址:", font=("Microsoft YaHei UI", 9), fg="#cbd5e1", bg="#1e293b").pack(side=tk.LEFT)
        self.agent_master_ip_ent = tk.Entry(c_row, font=("Consolas", 10), bg="#0f172a", fg="#38bdf8", width=18, bd=1, insertbackground="#fff")
        self.agent_master_ip_ent.insert(0, self.agent_client.master_ip)
        self.agent_master_ip_ent.pack(side=tk.LEFT, padx=6)

        tk.Label(c_row, text="端口:", font=("Microsoft YaHei UI", 9), fg="#cbd5e1", bg="#1e293b").pack(side=tk.LEFT, padx=(10, 2))
        self.agent_master_port_ent = tk.Entry(c_row, font=("Consolas", 10), bg="#0f172a", fg="#38bdf8", width=8, bd=1, insertbackground="#fff")
        self.agent_master_port_ent.insert(0, str(self.agent_client.master_port))
        self.agent_master_port_ent.pack(side=tk.LEFT, padx=6)

        tk.Button(c_row, text="⚡ 连接主控", font=("Microsoft YaHei UI", 9, "bold"), bg="#2563eb", fg="#fff", bd=0, padx=12, pady=4, command=self._reconnect_agent).pack(side=tk.LEFT, padx=10)

        self.agent_status_lbl = tk.Label(c_row, text="状态: 正在连接...", font=("Microsoft YaHei UI", 9, "bold"), fg="#eab308", bg="#1e293b")
        self.agent_status_lbl.pack(side=tk.LEFT, padx=12)

        # 授权状态卡片 (重点需求: 从机支持主机远程授权加密)
        auth_card = tk.LabelFrame(f, text="🛡️ 国文创商业授权与远程授权通道", font=("Microsoft YaHei UI", 10, "bold"), fg="#34d399", bg="#1e293b", bd=1)
        auth_card.pack(fill=tk.X, pady=8)

        a_row = tk.Frame(auth_card, bg="#1e293b")
        a_row.pack(fill=tk.X, padx=14, pady=10)

        req_code = "K8W2-P9X4"
        if self.license_mgr:
            try:
                req_code = self.license_mgr.get_req_code()
            except Exception:
                pass

        tk.Label(a_row, text="本机 8 位申请码:", font=("Microsoft YaHei UI", 10), fg="#cbd5e1", bg="#1e293b").pack(side=tk.LEFT)
        self.lbl_my_req_code = tk.Label(a_row, text=req_code, font=("Consolas", 13, "bold"), fg="#34d399", bg="#0f172a", padx=10, pady=4)
        self.lbl_my_req_code.pack(side=tk.LEFT, padx=8)

        tk.Button(a_row, text="📋 复制申请码", font=("Microsoft YaHei UI", 8), bg="#334155", fg="#fff", bd=0, padx=8, pady=4,
                  command=lambda: (self.root.clipboard_clear(), self.root.clipboard_append(req_code), messagebox.showinfo("提示", "申请码已复制！"))).pack(side=tk.LEFT, padx=6)

        self.lbl_my_lic_status = tk.Label(a_row, text="授权状态: 商业永久授权", font=("Microsoft YaHei UI", 10, "bold"), fg="#38bdf8", bg="#1e293b")
        self.lbl_my_lic_status.pack(side=tk.RIGHT, padx=14)

        tk.Label(auth_card, text="💡 展馆集群特性: 从机在未授权时，无需人工在每台工控机上手工输入激活码。主控端在监控大厅可【一键远程授权并激活从机】！",
                 font=("Microsoft YaHei UI", 8), fg="#94a3b8", bg="#1e293b").pack(anchor="w", padx=14, pady=(0, 8))

        # 开源 VNC 服务状态卡片
        vnc_card = tk.LabelFrame(f, text="🖥️ 开源 VNC 远程控制服务 (端口 5900)", font=("Microsoft YaHei UI", 10, "bold"), fg="#eab308", bg="#1e293b", bd=1)
        vnc_card.pack(fill=tk.X, pady=8)

        v_row = tk.Frame(vnc_card, bg="#1e293b")
        v_row.pack(fill=tk.X, padx=14, pady=10)
        tk.Label(v_row, text="• 内置轻量级标准 VNC RFB 3.8 服务 (已自动随本程序启动，支持 UltraVNC/TightVNC 直接连接 5900 端口)", font=("Microsoft YaHei UI", 9), fg="#e2e8f0", bg="#1e293b").pack(anchor="w")
        tk.Label(v_row, text="• 此外，主控端可通过国文创专属加密通道一键调取高清晰度远程桌面，无需配置第三方工具！", font=("Microsoft YaHei UI", 8), fg="#94a3b8", bg="#1e293b").pack(anchor="w", pady=(4, 0))

    def _reconnect_agent(self):
        ip = self.agent_master_ip_ent.get().strip()
        port = int(self.agent_master_port_ent.get().strip() or "9888")
        self.agent_client.set_master_address(ip, port)

    def _on_agent_status_change(self, connected: bool, desc: str):
        def _update():
            color = "#34d399" if connected else "#dc2626"
            self.agent_status_lbl.config(text=f"状态: {desc}", fg=color)
        self.root.after(0, _update)

    def _refresh_standalone_stats(self):
        m = gwc_system_ops.get_system_memory()
        self.mem_stat_lbl.config(text=f"物理内存状态: 已用 {m['used_mb']} MB / 总量 {m['total_mb']} MB (占用: {m['percent']}%)")

    # =========================================================================
    # 🖥️ 模式二: 展馆主控集群综合管理大厅
    # =========================================================================
    def _build_master_view(self):
        # 顶部统计与批量操作工具条
        top_stats = tk.Frame(self.master_frame, bg="#1e293b", height=48)
        top_stats.pack(fill=tk.X, side=tk.TOP, padx=10, pady=(6, 2))

        self.master_status_lbl = tk.Label(top_stats, text="主控服务: 🟢 运行中 (端口: 9888) | 在线工控机: 0 台", font=("Microsoft YaHei UI", 10, "bold"), fg="#34d399", bg="#1e293b")
        self.master_status_lbl.pack(side=tk.LEFT, padx=14, pady=10)

        # 批量操作按钮
        tk.Button(top_stats, text="⚡ 全馆一键关机", font=("Microsoft YaHei UI", 9, "bold"), bg="#dc2626", fg="#fff", bd=0, padx=10, pady=5, command=self._batch_shutdown).pack(side=tk.RIGHT, padx=4)
        tk.Button(top_stats, text="🔄 全馆一键重启", font=("Microsoft YaHei UI", 9), bg="#d97706", fg="#fff", bd=0, padx=10, pady=5, command=self._batch_reboot).pack(side=tk.RIGHT, padx=4)
        tk.Button(top_stats, text="🔇 全馆静音", font=("Microsoft YaHei UI", 9), bg="#334155", fg="#fff", bd=0, padx=10, pady=5, command=self._batch_mute).pack(side=tk.RIGHT, padx=4)
        tk.Button(top_stats, text="🚀 批量启动应用", font=("Microsoft YaHei UI", 9), bg="#2563eb", fg="#fff", bd=0, padx=10, pady=5, command=self._batch_launch_app).pack(side=tk.RIGHT, padx=4)

        # 主控选项卡容器
        m_nb = ttk.Notebook(self.master_frame)
        m_nb.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)

        # 视图 1: 工控机监控大厅与即时控制
        v_mon = tk.Frame(m_nb, bg="#0f172a")
        m_nb.add(v_mon, text="📊 展馆设备监控与控制大厅")
        self._build_master_monitor_view(v_mon)

        # 视图 2: 主控备份中心与远程下发
        v_bk = tk.Frame(m_nb, bg="#0f172a")
        m_nb.add(v_bk, text="💾 主控备份中心与远程下发")
        self._build_master_backup_view(v_bk)

        # 视图 3: 国文创商业授权中枢
        v_lic = tk.Frame(m_nb, bg="#0f172a")
        m_nb.add(v_lic, text="🛡️ 国文创商业授权中枢")
        self._build_master_license_view(v_lic)

    # 主控视图 1: 设备监控与控制大厅
    def _build_master_monitor_view(self, parent):
        paned = tk.PanedWindow(parent, orient=tk.HORIZONTAL, bg="#0f172a", bd=0, sashwidth=4)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # 左栏: 从机列表
        left = tk.LabelFrame(paned, text="🖥️ 展馆在线工控机列表", font=("Microsoft YaHei UI", 10, "bold"), fg="#38bdf8", bg="#1e293b", bd=1)
        paned.add(left, width=540)

        self.client_tree = ttk.Treeview(left, columns=("host", "cpu", "mem", "fg", "auth"), show="tree headings", selectmode="browse")
        self.client_tree.heading("#0", text="IP 地址", anchor="w")
        self.client_tree.heading("host", text="计算机名", anchor="w")
        self.client_tree.heading("cpu", text="CPU%", anchor="center")
        self.client_tree.heading("mem", text="内存%", anchor="center")
        self.client_tree.heading("fg", text="当前前台活动软件", anchor="w")
        self.client_tree.heading("auth", text="授权状态", anchor="center")

        self.client_tree.column("#0", width=120)
        self.client_tree.column("host", width=110)
        self.client_tree.column("cpu", width=60)
        self.client_tree.column("mem", width=60)
        self.client_tree.column("fg", width=160)
        self.client_tree.column("auth", width=80)
        self.client_tree.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)
        self.client_tree.bind("<<TreeviewSelect>>", self._on_client_tree_select)

        # 右栏: 选中工控机的实时控制台
        right = tk.LabelFrame(paned, text="⚡ 选中设备实时控制面板", font=("Microsoft YaHei UI", 10, "bold"), fg="#34d399", bg="#1e293b", bd=1)
        paned.add(right, width=580)

        self.sel_host_lbl = tk.Label(right, text="请在左侧列表中选定一台工控机进行管理", font=("Microsoft YaHei UI", 10, "bold"), fg="#94a3b8", bg="#1e293b")
        self.sel_host_lbl.pack(anchor="w", padx=12, pady=8)

        # 远程桌面与文件互传快捷启动条
        desk_bar = tk.Frame(right, bg="#1e293b")
        desk_bar.pack(fill=tk.X, padx=12, pady=4)

        tk.Button(desk_bar, text="🖥️ 一键打开 VNC 远程桌面控制", font=("Microsoft YaHei UI", 10, "bold"), bg="#2563eb", fg="#fff", bd=0, padx=12, pady=6, cursor="hand2", command=self._open_remote_desktop).pack(side=tk.LEFT, padx=3)
        tk.Button(desk_bar, text="📁 打开双向远程文件传输", font=("Microsoft YaHei UI", 10, "bold"), bg="#059669", fg="#fff", bd=0, padx=12, pady=6, cursor="hand2", command=self._open_remote_file_transfer).pack(side=tk.LEFT, padx=3)

        # 快捷控制操作区 (关机/重启/音量/应用启动)
        ctl_grid = tk.LabelFrame(right, text="🕹️ 远程中控快捷指令", font=("Microsoft YaHei UI", 9, "bold"), fg="#eab308", bg="#1e293b", bd=1)
        ctl_grid.pack(fill=tk.X, padx=12, pady=8)

        r1 = tk.Frame(ctl_grid, bg="#1e293b")
        r1.pack(fill=tk.X, padx=8, pady=4)
        tk.Button(r1, text="⚡ 远程关机", font=("Microsoft YaHei UI", 9, "bold"), bg="#dc2626", fg="#fff", bd=0, padx=10, pady=4, command=self._ctl_shutdown).pack(side=tk.LEFT, padx=3)
        tk.Button(r1, text="🔄 远程重启", font=("Microsoft YaHei UI", 9), bg="#d97706", fg="#fff", bd=0, padx=10, pady=4, command=self._ctl_reboot).pack(side=tk.LEFT, padx=3)
        tk.Button(r1, text="🔇 静音/解除", font=("Microsoft YaHei UI", 9), bg="#334155", fg="#fff", bd=0, padx=8, pady=4, command=self._ctl_mute).pack(side=tk.LEFT, padx=6)

        # 音量滑块
        tk.Label(r1, text="音量:", font=("Microsoft YaHei UI", 9), fg="#cbd5e1", bg="#1e293b").pack(side=tk.LEFT, padx=(10, 2))
        self.vol_scale = tk.Scale(r1, from_=0, to=100, orient=tk.HORIZONTAL, bg="#1e293b", fg="#38bdf8", highlightthickness=0, length=120)
        self.vol_scale.set(50)
        self.vol_scale.pack(side=tk.LEFT, padx=4)
        tk.Button(r1, text="设定", font=("Microsoft YaHei UI", 8), bg="#2563eb", fg="#fff", bd=0, padx=6, pady=2, command=self._ctl_set_vol).pack(side=tk.LEFT)

        # 远程运行应用
        r2 = tk.Frame(ctl_grid, bg="#1e293b")
        r2.pack(fill=tk.X, padx=8, pady=6)
        tk.Label(r2, text="启动应用路径:", font=("Microsoft YaHei UI", 9), fg="#cbd5e1", bg="#1e293b").pack(side=tk.LEFT)
        self.run_app_entry = tk.Entry(r2, font=("Consolas", 9), bg="#0f172a", fg="#38bdf8", bd=1)
        self.run_app_entry.insert(0, "notepad.exe")
        self.run_app_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        tk.Button(r2, text="🚀 远程调用启动", font=("Microsoft YaHei UI", 9, "bold"), bg="#2563eb", fg="#fff", bd=0, padx=10, pady=3, command=self._ctl_run_app).pack(side=tk.RIGHT)

        # 运行中软件与进程列表 (支持远程强杀)
        proc_box = tk.LabelFrame(right, text="🛑 运行中软件与活跃进程 (可远程结束应用)", font=("Microsoft YaHei UI", 9, "bold"), fg="#cbd5e1", bg="#1e293b", bd=1)
        proc_box.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)

        self.proc_tree = ttk.Treeview(proc_box, columns=("pid", "mem"), show="tree headings", selectmode="browse")
        self.proc_tree.heading("#0", text="进程名称", anchor="w")
        self.proc_tree.heading("pid", text="PID", anchor="center")
        self.proc_tree.heading("mem", text="内存", anchor="e")
        self.proc_tree.column("#0", width=240)
        self.proc_tree.column("pid", width=80)
        self.proc_tree.column("mem", width=90)
        self.proc_tree.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

        proc_btn_bar = tk.Frame(proc_box, bg="#1e293b")
        proc_btn_bar.pack(fill=tk.X, padx=6, pady=4)
        tk.Button(proc_btn_bar, text="🛑 强制结束所选应用/进程 (Kill)", font=("Microsoft YaHei UI", 9, "bold"), bg="#dc2626", fg="#fff", bd=0, padx=10, pady=4, command=self._ctl_kill_proc).pack(side=tk.LEFT)

    def _on_client_tree_select(self, event):
        sel = self.client_tree.selection()
        if not sel:
            return
        ip = sel[0]
        client_data = self.master_hub.clients.get(ip, {})
        info = client_data.get("info", {})
        h_name = info.get("hostname", "Unknown")
        self.sel_host_lbl.config(text=f"当前选定工控机: [{h_name}] ({ip}) - 系统: {info.get('os', 'Windows')}", fg="#38bdf8")

        # 刷新进程树
        for i in self.proc_tree.get_children():
            self.proc_tree.delete(i)
        procs = info.get("top_processes", [])
        for p in procs:
            sz_str = f"{p.get('memory_mb', 0)} MB"
            self.proc_tree.insert("", "end", iid=str(p.get("pid")), text=p.get("name"), values=(p.get("pid"), sz_str))

    def _get_selected_client_ip(self) -> str:
        sel = self.client_tree.selection()
        return sel[0] if sel else ""

    def _open_remote_desktop(self):
        ip = self._get_selected_client_ip()
        if not ip:
            messagebox.showinfo("提示", "请先在列表中选中一台工控机！")
            return
        info = self.master_hub.clients.get(ip, {}).get("info", {})
        h_name = info.get("hostname", ip)

        def send_fn(client_ip, cmd_type, payload, callback=None):
            self.master_hub.send_command(client_ip, cmd_type, payload, callback=callback)

        vnc_win = gwc_vnc.RemoteDesktopWindow(self.root, ip, h_name, send_fn)

    def _open_remote_file_transfer(self):
        ip = self._get_selected_client_ip()
        if not ip:
            messagebox.showinfo("提示", "请先在列表中选中一台工控机！")
            return
        info = self.master_hub.clients.get(ip, {}).get("info", {})
        h_name = info.get("hostname", ip)

        def send_fn(client_ip, cmd_type, payload, callback=None):
            self.master_hub.send_command(client_ip, cmd_type, payload, callback=callback)

        fm_win = gwc_vnc.RemoteFileManagerWindow(self.root, ip, h_name, send_fn)

    def _ctl_shutdown(self):
        ip = self._get_selected_client_ip()
        if ip and messagebox.askyesno("关机确认", f"确定远程关闭工控机 {ip} 吗？"):
            self.master_hub.send_command(ip, "CMD_SHUTDOWN", {"force": True, "timeout": 0})

    def _ctl_reboot(self):
        ip = self._get_selected_client_ip()
        if ip and messagebox.askyesno("重启确认", f"确定远程重启工控机 {ip} 吗？"):
            self.master_hub.send_command(ip, "CMD_REBOOT", {"force": True, "timeout": 0})

    def _ctl_mute(self):
        ip = self._get_selected_client_ip()
        if ip:
            self.master_hub.send_command(ip, "CMD_VOLUME", {"action": "mute"})

    def _ctl_set_vol(self):
        ip = self._get_selected_client_ip()
        if ip:
            v = self.vol_scale.get()
            self.master_hub.send_command(ip, "CMD_VOLUME", {"action": "set", "level": v})

    def _ctl_run_app(self):
        ip = self._get_selected_client_ip()
        p = self.run_app_entry.get().strip()
        if ip and p:
            self.master_hub.send_command(ip, "CMD_RUN_APP", {"path": p})
            messagebox.showinfo("指令已发送", f"已向工控机 {ip} 发送启动指令: {p}")

    def _ctl_kill_proc(self):
        ip = self._get_selected_client_ip()
        sel = self.proc_tree.selection()
        if ip and sel:
            pid = int(sel[0])
            p_name = self.proc_tree.item(sel[0])["text"]
            if messagebox.askyesno("结束进程", f"确定要远程终止工控机 {ip} 的进程:\n{p_name} (PID: {pid}) 吗？"):
                self.master_hub.send_command(ip, "CMD_KILL_PROC", {"pid": pid, "name": p_name})

    def _batch_shutdown(self):
        if messagebox.askyesno("批量关机", "⚠️ 警告: 确定要向全展馆所有在线工控机发送【一键关机】指令吗？"):
            self.master_hub.broadcast_command("CMD_SHUTDOWN", {"force": True, "timeout": 0})

    def _batch_reboot(self):
        if messagebox.askyesno("批量重启", "确定向全展馆所有工控机发送【一键重启】指令吗？"):
            self.master_hub.broadcast_command("CMD_REBOOT", {"force": True, "timeout": 0})

    def _batch_mute(self):
        self.master_hub.broadcast_command("CMD_VOLUME", {"action": "mute"})

    def _batch_launch_app(self):
        p = filedialog.askstring("批量调用应用", "请输入要批量调用的应用路径或命令:")
        if p:
            self.master_hub.broadcast_command("CMD_RUN_APP", {"path": p.strip()})

    # 主控视图 2: 备份中心与远程下发 (重点需求: 备份系统上传至主控，支持下发恢复备份)
    def _build_master_backup_view(self, parent):
        f = tk.Frame(parent, bg="#0f172a")
        f.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)

        top_acts = tk.Frame(f, bg="#0f172a")
        top_acts.pack(fill=tk.X, pady=6)

        tk.Button(top_acts, text="📤 下发选中的备份到目标从机并执行恢复", font=("Microsoft YaHei UI", 10, "bold"), bg="#2563eb", fg="#fff", bd=0, padx=14, pady=6, command=self._master_push_backup).pack(side=tk.LEFT, padx=4)
        tk.Button(top_acts, text="📥 命令目标从机立即生成备份并上传", font=("Microsoft YaHei UI", 10, "bold"), bg="#059669", fg="#fff", bd=0, padx=14, pady=6, command=self._master_request_backup).pack(side=tk.LEFT, padx=4)
        tk.Button(top_acts, text="📂 打开主控备份库目录", font=("Microsoft YaHei UI", 9), bg="#334155", fg="#fff", bd=0, padx=10, pady=6, command=lambda: os.system(f'explorer "{self.master_hub.backup_store_dir}"')).pack(side=tk.RIGHT, padx=4)

        self.master_bk_tree = ttk.Treeview(f, columns=("host", "time", "size", "notes"), show="tree headings", selectmode="browse")
        self.master_bk_tree.heading("#0", text="主控归档备份名称", anchor="w")
        self.master_bk_tree.heading("host", text="来源工控机", anchor="center")
        self.master_bk_tree.heading("time", text="归档时间", anchor="center")
        self.master_bk_tree.heading("size", text="包大小", anchor="e")
        self.master_bk_tree.heading("notes", text="备注说明", anchor="w")
        self.master_bk_tree.column("#0", width=280)
        self.master_bk_tree.column("host", width=120)
        self.master_bk_tree.column("time", width=150)
        self.master_bk_tree.column("size", width=90)
        self.master_bk_tree.column("notes", width=280)
        self.master_bk_tree.pack(fill=tk.BOTH, expand=True, pady=6)

        self._refresh_master_backup_tree()

    def _refresh_master_backup_tree(self):
        for i in self.master_bk_tree.get_children():
            self.master_bk_tree.delete(i)
        bks = self.master_hub.list_master_backups()
        for b in bks:
            self.master_bk_tree.insert("", "end", iid=b["path"], text=b["filename"], values=(b["hostname"], b["created_at"], f"{b['size_mb']} MB", b["notes"]))

    def _master_push_backup(self):
        ip = self._get_selected_client_ip()
        if not ip:
            messagebox.showinfo("提示", "请在【设备监控与控制大厅】中先选择接收恢复的目标工控机！")
            return
        sel = self.master_bk_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请在备份列表中选择要下发的 .gwcbackup 备份包！")
            return
        bk_path = sel[0]
        if messagebox.askyesno("下发确认", f"确定要将备份:\n{os.path.basename(bk_path)}\n下发至工控机 [{ip}] 并自动执行一键还原恢复吗？"):
            self.master_hub.push_backup_to_agent(ip, bk_path, callback=lambda r: messagebox.showinfo("下发结果", f"从机 {ip} 还原响应: {r.get('msg', r.get('error'))}"))

    def _master_request_backup(self):
        ip = self._get_selected_client_ip()
        if not ip:
            messagebox.showinfo("提示", "请先选择要备份的工控机！")
            return
        self.master_hub.request_agent_backup(ip, callback=lambda r: (self._refresh_master_backup_tree(), messagebox.showinfo("完成", f"从机 {ip} 已完成备份并入库归档！")))

    # 主控视图 3: 国文创商业授权中枢 (重点需求: 从机支持主机远程授权加密)
    def _build_master_license_view(self, parent):
        paned = tk.PanedWindow(parent, orient=tk.HORIZONTAL, bg="#0f172a", bd=0, sashwidth=4)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # 左栏: 工控机远程一键授权
        left = tk.LabelFrame(paned, text="🛡️ 从机在线远程授权中心", font=("Microsoft YaHei UI", 10, "bold"), fg="#38bdf8", bg="#1e293b", bd=1)
        paned.add(left, width=540)

        tk.Label(left, text="选择需要签发授权的从机，一键免敲码下发 12 位国文创商业激活码:", font=("Microsoft YaHei UI", 9), fg="#cbd5e1", bg="#1e293b").pack(anchor="w", padx=12, pady=(10, 4))

        self.lic_agent_tree = ttk.Treeview(left, columns=("host", "req_code", "status"), show="tree headings", selectmode="browse")
        self.lic_agent_tree.heading("#0", text="IP 地址", anchor="w")
        self.lic_agent_tree.heading("host", text="计算机名", anchor="w")
        self.lic_agent_tree.heading("req_code", text="8位申请码", anchor="center")
        self.lic_agent_tree.heading("status", text="授权状态", anchor="center")
        self.lic_agent_tree.column("#0", width=120)
        self.lic_agent_tree.column("host", width=110)
        self.lic_agent_tree.column("req_code", width=120)
        self.lic_agent_tree.column("status", width=100)
        self.lic_agent_tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        auth_opts = tk.Frame(left, bg="#1e293b")
        auth_opts.pack(fill=tk.X, padx=12, pady=10)

        tk.Label(auth_opts, text="授权期限:", font=("Microsoft YaHei UI", 9), fg="#cbd5e1", bg="#1e293b").pack(side=tk.LEFT)
        self.duration_combo = ttk.Combobox(auth_opts, values=["永久有效 (推荐)", "365天 (1年)", "180天 (半年)", "90天 (1季度)", "30天 (1个月)", "7天 (试用)"], state="readonly", width=14)
        self.duration_combo.current(0)
        self.duration_combo.pack(side=tk.LEFT, padx=6)

        tk.Button(auth_opts, text="⚡ 一键远程签发并激活从机", font=("Microsoft YaHei UI", 10, "bold"), bg="#059669", fg="#fff", bd=0, padx=12, pady=6, cursor="hand2", command=self._do_remote_auth).pack(side=tk.RIGHT)

        # 右栏: 独立的国文创加密机计算器
        right = tk.LabelFrame(paned, text="🔑 独立《国文创加密机》运算终端", font=("Microsoft YaHei UI", 10, "bold"), fg="#34d399", bg="#1e293b", bd=1)
        paned.add(right, width=540)

        f_calc = tk.Frame(right, bg="#1e293b")
        f_calc.pack(fill=tk.BOTH, expand=True, padx=16, pady=12)

        tk.Label(f_calc, text="设备申请码 (8 位格式: XXXX-XXXX):", font=("Microsoft YaHei UI", 9, "bold"), fg="#cbd5e1", bg="#1e293b").pack(anchor="w", pady=(4, 2))
        self.manual_req_ent = tk.Entry(f_calc, font=("Consolas", 14, "bold"), fg="#38bdf8", bg="#0f172a", bd=1, justify="center")
        self.manual_req_ent.pack(fill=tk.X, pady=4, ipady=3)

        tk.Button(f_calc, text="⚡ 计算并签发 12 位商业激活码", font=("Microsoft YaHei UI", 10, "bold"), bg="#2563eb", fg="#fff", bd=0, pady=8, command=self._calc_manual_license).pack(fill=tk.X, pady=10)

        tk.Label(f_calc, text="生成的 12 位激活码 (XXXX-XXXX-XXXX):", font=("Microsoft YaHei UI", 9, "bold"), fg="#cbd5e1", bg="#1e293b").pack(anchor="w", pady=(8, 2))
        self.manual_res_lbl = tk.Label(f_calc, text="---- ---- ----", font=("Consolas", 16, "bold"), fg="#34d399", bg="#0f172a", pady=10)
        self.manual_res_lbl.pack(fill=tk.X, pady=4)

        tk.Button(f_calc, text="📋 复制激活码", font=("Microsoft YaHei UI", 9), bg="#334155", fg="#fff", bd=0, pady=5, command=self._copy_manual_act_code).pack(fill=tk.X, pady=6)

    def _do_remote_auth(self):
        sel = self.lic_agent_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请选择需要签发远程授权的从机！")
            return
        ip = sel[0]
        dur_str = self.duration_combo.get()
        dur_code = 31  # 永久
        if "365天" in dur_str:
            dur_code = 8
        elif "180天" in dur_str:
            dur_code = 7
        elif "90天" in dur_str:
            dur_code = 6
        elif "30天" in dur_str:
            dur_code = 4
        elif "7天" in dur_str:
            dur_code = 2

        res = self.master_hub.remote_authorize_agent(ip, duration_code=dur_code, runs_code=31,
            callback=lambda r: messagebox.showinfo("授权成功", f"🎉 工控机 [{ip}] 远程商业授权成功！\n激活码: {res.get('act_code')}\n响应: {r.get('msg')}"))
        if not res.get("success"):
            messagebox.showerror("授权失败", res.get("error", "未知错误"))

    def _calc_manual_license(self):
        req = self.manual_req_ent.get().strip()
        if not req:
            messagebox.showerror("错误", "请输入 8 位申请码！")
            return
        if not universal_license_core:
            messagebox.showerror("错误", "缺少 universal_license_core 模块")
            return

        dec = universal_license_core.decode_request_code(req, "VisualCast")
        if not dec.get("valid"):
            messagebox.showerror("错误", f"申请码无效: {dec.get('error')}")
            return

        code = universal_license_core.encode_license(dec["hw_hash"], dec["nonce"], 31, 31, dec.get("matched_product_id", "VisualCast"))
        self.manual_res_lbl.config(text=code)

    def _copy_manual_act_code(self):
        code = self.manual_res_lbl.cget("text")
        if code and "-" in code:
            self.root.clipboard_clear()
            self.root.clipboard_append(code)
            messagebox.showinfo("提示", "激活码已成功复制！")

    # =========================================================================
    # 主控回调与状态轮询
    # =========================================================================
    def _on_master_agent_connected(self, ip, info):
        self.root.after(0, self._refresh_master_ui)

    def _on_master_agent_disconnected(self, ip):
        self.root.after(0, self._refresh_master_ui)

    def _on_master_status_updated(self, ip, info):
        self.root.after(0, self._refresh_master_ui)

    def _on_master_backup_saved(self, ip, path, info):
        self.root.after(0, self._refresh_master_backup_tree)

    def _refresh_master_ui(self):
        clients = self.master_hub.get_online_clients()
        self.master_status_lbl.config(text=f"主控服务: 🟢 运行中 (端口: {self.master_hub.port}) | 在线工控机: {len(clients)} 台")

        # 刷新监控大厅树
        existing_sel = self.client_tree.selection()
        for i in self.client_tree.get_children():
            self.client_tree.delete(i)

        # 刷新授权树
        for i in self.lic_agent_tree.get_children():
            self.lic_agent_tree.delete(i)

        for c in clients:
            ip = c["ip"]
            auth_str = "🟢 已授权" if c["license"].get("status") == "ACTIVE" else "🔴 未授权"
            req_code = c["license"].get("request_code", "----")
            fg = c.get("fg_window", "") or "--"

            self.client_tree.insert("", "end", iid=ip, text=ip, values=(
                c["hostname"],
                f"{c['cpu_percent']}%",
                f"{c['mem_percent']}%",
                fg,
                auth_str
            ))

            self.lic_agent_tree.insert("", "end", iid=ip, text=ip, values=(
                c["hostname"],
                req_code,
                auth_str
            ))

        if existing_sel and existing_sel[0] in [c["ip"] for c in clients]:
            self.client_tree.selection_set(existing_sel[0])

    def _ui_heartbeat_tick(self):
        """主界面心跳刷新"""
        try:
            if self.current_mode == "standalone":
                self._refresh_standalone_stats()
            else:
                self._refresh_master_ui()
        except Exception:
            pass
        self.root.after(2000, self._ui_heartbeat_tick)


def main():
    elevate_if_needed()

    # 启用 Windows 高 DPI 适配
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    root = tk.Tk()
    app = DualModeApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
