# -*- coding: utf-8 -*-
"""
展馆工控机系统操作与中控控制执行引擎 (GuoWenChuang System Operations Engine)
=====================================================================
1. 展馆网络适配器与 IPv4 静态/DHCP 一键配置
2. 展馆工控机策略全套管控 (UAC/Defender/更新/防火墙/休眠/快启/RDP免密/手势)
3. 电脑深度性能优化 (物理内存 EmptyWorkingSet 释放、网络深度重置、启动项/右键管理)
4. 中控远程指令本地执行 (远程关机、重启、精准音量控制、应用调用、进程结束)
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
from datetime import datetime

# ==================== 管理员权限检测与提权 ====================
def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def run_cmd(command: str) -> tuple:
    """运行系统命令行指令并返回 (success: bool, output: str)"""
    try:
        process = subprocess.run(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='gbk',
            errors='replace'
        )
        out = (process.stdout or "") + (process.stderr or "")
        return process.returncode == 0, out.strip()
    except Exception as ex:
        return False, str(ex)


def notify_shell_refresh():
    """通知 Windows Shell 即时刷新桌面与文件关联"""
    try:
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, 0, 0)
    except Exception:
        pass


# ==================== 物理内存与垃圾清理 ====================
class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def get_system_memory() -> dict:
    """获取当前系统物理内存状态"""
    try:
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            total_mb = stat.ullTotalPhys / (1024 * 1024)
            avail_mb = stat.ullAvailPhys / (1024 * 1024)
            used_mb = total_mb - avail_mb
            pct = stat.dwMemoryLoad
            return {
                "total_mb": round(total_mb, 1),
                "used_mb": round(used_mb, 1),
                "avail_mb": round(avail_mb, 1),
                "percent": pct
            }
    except Exception:
        pass
    return {"total_mb": 0.0, "used_mb": 0.0, "avail_mb": 0.0, "percent": 0}


def deep_clean_working_set() -> dict:
    """深度清空系统所有可访问进程的工作集与空闲内存"""
    cleaned_count = 0
    failed_count = 0
    pids = (ctypes.c_ulong * 1024)()
    cb_needed = ctypes.c_ulong()

    if ctypes.windll.psapi.EnumProcesses(ctypes.byref(pids), ctypes.sizeof(pids), ctypes.byref(cb_needed)):
        count = int(cb_needed.value / ctypes.sizeof(ctypes.c_ulong))
        for i in range(count):
            pid = pids[i]
            if pid <= 4:
                continue
            h_proc = ctypes.windll.kernel32.OpenProcess(0x0100 | 0x0400, False, pid)
            if h_proc:
                try:
                    if ctypes.windll.psapi.EmptyWorkingSet(h_proc):
                        cleaned_count += 1
                    else:
                        failed_count += 1
                finally:
                    ctypes.windll.kernel32.CloseHandle(h_proc)
    return {"cleaned_processes": cleaned_count, "failed_processes": failed_count}


def clean_system_temp() -> dict:
    """扫描并清理 Windows 临时垃圾文件"""
    temp_dirs = []
    user_temp = os.environ.get("TEMP")
    if user_temp and os.path.isdir(user_temp):
        temp_dirs.append(user_temp)
    win_temp = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Temp")
    if os.path.isdir(win_temp):
        temp_dirs.append(win_temp)

    total_bytes = 0
    deleted_files = 0
    for t_dir in temp_dirs:
        try:
            for root, dirs, files in os.walk(t_dir):
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        sz = os.path.getsize(fp)
                        os.remove(fp)
                        total_bytes += sz
                        deleted_files += 1
                    except Exception:
                        pass
        except Exception:
            pass
    return {"deleted_files": deleted_files, "freed_mb": round(total_bytes / (1024 * 1024), 2)}


# ==================== 网络适配器与 IPv4 配置 ====================
def get_network_adapters() -> list:
    """获取本机所有可用网络适配器名称及状态"""
    adapters = []
    try:
        ok, out = run_cmd("netsh interface show interface")
        if ok and out:
            lines = out.splitlines()
            header_idx = -1
            for idx, line in enumerate(lines):
                if "Admin State" in line or "管理状态" in line or "------" in line:
                    header_idx = idx
            if header_idx != -1:
                for line in lines[header_idx + 1:]:
                    line = line.strip()
                    if not line:
                        continue
                    parts = re.split(r"\s{2,}", line)
                    if len(parts) >= 4:
                        adapters.append(parts[3].strip())
    except Exception:
        pass
    if not adapters:
        adapters = ["以太网", "Ethernet", "WLAN", "Wi-Fi"]
    return sorted(list(dict.fromkeys(adapters)))


def read_adapter_ipv4(adapter_name: str) -> dict:
    """读取指定适配器的 IPv4 配置信息"""
    info = {
        "adapter": adapter_name,
        "dhcp": True,
        "ip": "",
        "mask": "255.255.255.0",
        "gateway": "",
        "dns1": "",
        "dns2": ""
    }
    ok, out = run_cmd(f'netsh interface ipv4 show addresses name="{adapter_name}"')
    if ok and out:
        if "DHCP enabled:                         Yes" in out or "DHCP 已启用:                          是" in out:
            info["dhcp"] = True
        elif "DHCP enabled:                         No" in out or "DHCP 已启用:                          否" in out:
            info["dhcp"] = False

        m_ip = re.search(r"(?:IP Address|IP 地址|IPv4 地址)[^\d]*([\d\.]+)", out)
        if m_ip:
            info["ip"] = m_ip.group(1).strip()
        m_mask = re.search(r"(?:Subnet Prefix|子网前缀|子网掩码)[^\d]*([\d\.]+)", out)
        if m_mask:
            info["mask"] = m_mask.group(1).strip()
        m_gw = re.search(r"(?:Default Gateway|默认网关)[^\d]*([\d\.]+)", out)
        if m_gw:
            info["gateway"] = m_gw.group(1).strip()

    ok_dns, out_dns = run_cmd(f'netsh interface ipv4 show dnsservers name="{adapter_name}"')
    if ok_dns and out_dns:
        dns_matches = re.findall(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b", out_dns)
        if dns_matches:
            info["dns1"] = dns_matches[0]
            if len(dns_matches) > 1:
                info["dns2"] = dns_matches[1]
    return info


def apply_ip_config(adapter_name: str, ip: str, mask: str, gateway: str = "", dns1: str = "", dns2: str = "") -> tuple:
    """应用静态 IPv4 及 DNS 配置"""
    if not gateway:
        cmd_ip = f'netsh interface ipv4 set address name="{adapter_name}" source=static address={ip} mask={mask}'
    else:
        cmd_ip = f'netsh interface ipv4 set address name="{adapter_name}" source=static address={ip} mask={mask} gateway={gateway} gwmetric=1'
    ok, out = run_cmd(cmd_ip)
    if not ok:
        return False, f"设置静态IP失败: {out}"

    if dns1:
        run_cmd(f'netsh interface ipv4 set dnsservers name="{adapter_name}" source=static address={dns1} register=primary validate=no')
        if dns2:
            run_cmd(f'netsh interface ipv4 add dnsservers name="{adapter_name}" address={dns2} index=2 validate=no')
    else:
        run_cmd(f'netsh interface ipv4 set dnsservers name="{adapter_name}" source=static address=none')
    return True, "静态 IP 配置已成功应用"


def apply_dhcp_config(adapter_name: str) -> tuple:
    """切换为 DHCP 自动获取 IP 与 DNS"""
    run_cmd(f'netsh interface ipv4 set address name="{adapter_name}" source=dhcp')
    run_cmd(f'netsh interface ipv4 set dnsservers name="{adapter_name}" source=dhcp')
    return True, "已切换为 DHCP 自动获取"


def reset_winsock_and_ip() -> tuple:
    """一键重置 Winsock 目录与 TCP/IP 协议栈"""
    run_cmd("netsh winsock reset")
    run_cmd("netsh int ip reset")
    run_cmd("ipconfig /flushdns")
    run_cmd("arp -d *")
    return True, "Winsock、TCP/IP 与 DNS 缓存已全部重置"


# ==================== 展馆策略全套管控 ====================
EXHIBIT_POLICIES = {
    "uac": {
        "name": "用户账户控制 (UAC)",
        "set_on": lambda: (
            run_cmd(r'reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" /v EnableLUA /t REG_DWORD /d 0 /f'),
            run_cmd(r'reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" /v ConsentPromptBehaviorAdmin /t REG_DWORD /d 0 /f')
        ),
        "set_off": lambda: (
            run_cmd(r'reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" /v EnableLUA /t REG_DWORD /d 1 /f'),
            run_cmd(r'reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" /v ConsentPromptBehaviorAdmin /t REG_DWORD /d 5 /f')
        )
    },
    "defender": {
        "name": "Windows Defender 策略优化",
        "set_on": lambda: (
            run_cmd(r'reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows Defender" /v DisableAntiSpyware /t REG_DWORD /d 1 /f'),
            run_cmd(r'reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows Defender\Real-Time Protection" /v DisableRealtimeMonitoring /t REG_DWORD /d 1 /f')
        ),
        "set_off": lambda: (
            run_cmd(r'reg delete "HKLM\SOFTWARE\Policies\Microsoft\Windows Defender" /v DisableAntiSpyware /f'),
            run_cmd(r'reg delete "HKLM\SOFTWARE\Policies\Microsoft\Windows Defender\Real-Time Protection" /v DisableRealtimeMonitoring /f')
        )
    },
    "update": {
        "name": "Windows 自动更新彻底关闭",
        "set_on": lambda: (
            run_cmd(r'reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU" /v NoAutoUpdate /t REG_DWORD /d 1 /f'),
            run_cmd(r'reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU" /v AUOptions /t REG_DWORD /d 1 /f'),
            run_cmd("sc stop wuauserv"),
            run_cmd("sc config wuauserv start=disabled")
        ),
        "set_off": lambda: (
            run_cmd(r'reg delete "HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU" /v NoAutoUpdate /f'),
            run_cmd(r'reg delete "HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU" /v AUOptions /f'),
            run_cmd("sc config wuauserv start=auto"),
            run_cmd("sc start wuauserv")
        )
    },
    "firewall": {
        "name": "系统防火墙全配置关闭",
        "set_on": lambda: run_cmd("netsh advfirewall set allprofiles state off"),
        "set_off": lambda: run_cmd("netsh advfirewall set allprofiles state on")
    },
    "fastboot": {
        "name": "快速启动关闭 (防止异常断电丢配置)",
        "set_on": lambda: run_cmd(r'reg add "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Power" /v HiberbootEnabled /t REG_DWORD /d 0 /f'),
        "set_off": lambda: run_cmd(r'reg add "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Power" /v HiberbootEnabled /t REG_DWORD /d 1 /f')
    },
    "sleep": {
        "name": "屏幕常亮与永不休眠",
        "set_on": lambda: (
            run_cmd("powercfg /change monitor-timeout-ac 0"),
            run_cmd("powercfg /change standby-timeout-ac 0"),
            run_cmd("powercfg /change hibernate-timeout-ac 0")
        ),
        "set_off": lambda: (
            run_cmd("powercfg /change monitor-timeout-ac 15"),
            run_cmd("powercfg /change standby-timeout-ac 30")
        )
    },
    "edge_swipe": {
        "name": "触摸屏边缘滑动手势禁用",
        "set_on": lambda: run_cmd(r'reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\EdgeUI" /v AllowEdgeSwipe /t REG_DWORD /d 0 /f'),
        "set_off": lambda: run_cmd(r'reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\EdgeUI" /v AllowEdgeSwipe /t REG_DWORD /d 1 /f')
    },
    "rdp_free": {
        "name": "RDP 远程桌面免密登录",
        "set_on": lambda: (
            run_cmd(r'reg add "HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server" /v fDenyTSConnections /t REG_DWORD /d 0 /f'),
            run_cmd(r'reg add "HKLM\SYSTEM\CurrentControlSet\Control\Lsa" /v LimitBlankPasswordUse /t REG_DWORD /d 0 /f')
        ),
        "set_off": lambda: (
            run_cmd(r'reg add "HKLM\SYSTEM\CurrentControlSet\Control\Lsa" /v LimitBlankPasswordUse /t REG_DWORD /d 1 /f')
        )
    }
}


def apply_all_policies(enable: bool = True) -> list:
    """一键批量应用 (ALLON) 或恢复 (ALLOFF) 展馆所有策略"""
    results = []
    for key, p in EXHIBIT_POLICIES.items():
        try:
            if enable:
                p["set_on"]()
                results.append((p["name"], True, "已启用"))
            else:
                p["set_off"]()
                results.append((p["name"], True, "已恢复"))
        except Exception as e:
            results.append((p["name"], False, str(e)))
    return results


# ==================== 开机启动项扫描与管理 ====================
def scan_all_startup_items() -> list:
    """枚举所有开机启动项"""
    items = []
    # 扫描注册表 HKLM 与 HKCU Run 键
    targets = [
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", "HKCU"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run", "HKLM"),
    ]
    for hkey, subkey, scope in targets:
        try:
            with winreg.OpenKey(hkey, subkey, 0, winreg.KEY_READ) as k:
                num_vals = winreg.QueryInfoKey(k)[1]
                for i in range(num_vals):
                    try:
                        name, val, typ = winreg.EnumValue(k, i)
                        items.append({
                            "name": name,
                            "command": str(val),
                            "scope": scope,
                            "location": "Registry",
                            "enabled": True
                        })
                    except Exception:
                        pass
        except Exception:
            pass

    # 扫描启动文件夹
    startup_folders = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        p1 = os.path.join(appdata, r"Microsoft\Windows\Start Menu\Programs\Startup")
        if os.path.isdir(p1):
            startup_folders.append((p1, "User Startup"))
    progdata = os.environ.get("ProgramData")
    if progdata:
        p2 = os.path.join(progdata, r"Microsoft\Windows\Start Menu\Programs\Startup")
        if os.path.isdir(p2):
            startup_folders.append((p2, "Common Startup"))

    for folder, scope in startup_folders:
        try:
            for f in os.listdir(folder):
                fp = os.path.join(folder, f)
                if os.path.isfile(fp) and not f.lower().endswith(".ini"):
                    items.append({
                        "name": f,
                        "command": fp,
                        "scope": scope,
                        "location": "Folder",
                        "enabled": not f.endswith(".disabled")
                    })
        except Exception:
            pass
    return items


# ==================== 软件清单扫描 ====================
def list_installed_software() -> list:
    """扫描系统已安装的第三方软件清单"""
    installed = []
    reg_paths = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall")
    ]
    seen = set()
    for root, sub in reg_paths:
        try:
            with winreg.OpenKey(root, sub, 0, winreg.KEY_READ) as k:
                sub_count = winreg.QueryInfoKey(k)[0]
                for i in range(sub_count):
                    try:
                        sub_name = winreg.EnumKey(k, i)
                        with winreg.OpenKey(k, sub_name, 0, winreg.KEY_READ) as app_k:
                            try:
                                d_name, _ = winreg.QueryValueEx(app_k, "DisplayName")
                                d_name = d_name.strip()
                                if not d_name or d_name in seen:
                                    continue
                                seen.add(d_name)
                                ver, _ = winreg.QueryValueEx(app_k, "DisplayVersion") if "DisplayVersion" in [winreg.EnumValue(app_k, x)[0] for x in range(winreg.QueryInfoKey(app_k)[1])] else ("", 0)
                                pub, _ = winreg.QueryValueEx(app_k, "Publisher") if "Publisher" in [winreg.EnumValue(app_k, x)[0] for x in range(winreg.QueryInfoKey(app_k)[1])] else ("", 0)
                                installed.append({
                                    "name": d_name,
                                    "version": str(ver or ""),
                                    "publisher": str(pub or "")
                                })
                            except Exception:
                                pass
                    except Exception:
                        pass
        except Exception:
            pass
    return sorted(installed, key=lambda x: x["name"].lower())


# ==================== 中控远程控制指令执行器 ====================
def remote_shutdown(force: bool = True, timeout: int = 0) -> tuple:
    """远程关闭计算机"""
    cmd = f"shutdown /s /t {timeout}" + (" /f" if force else "")
    return run_cmd(cmd)


def remote_reboot(force: bool = True, timeout: int = 0) -> tuple:
    """远程重启计算机"""
    cmd = f"shutdown /r /t {timeout}" + (" /f" if force else "")
    return run_cmd(cmd)


def remote_volume_control(action: str = "set", level: int = 50) -> dict:
    """
    远程系统主音量控制
    action: "set" (设置音量 0-100), "mute" (静音/取消静音), "up", "down"
    """
    user32 = ctypes.windll.user32
    VK_VOLUME_MUTE = 0xAD
    VK_VOLUME_DOWN = 0xAE
    VK_VOLUME_UP = 0xAF

    def press_key(vk):
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.002)
        user32.keybd_event(vk, 0, 2, 0)
        time.sleep(0.002)

    try:
        if action == "mute" or action == "toggle_mute":
            press_key(VK_VOLUME_MUTE)
            return {"success": True, "action": "mute", "msg": "已切换静音状态"}
        elif action == "up":
            for _ in range(5):
                press_key(VK_VOLUME_UP)
            return {"success": True, "action": "up", "msg": "音量增加"}
        elif action == "down":
            for _ in range(5):
                press_key(VK_VOLUME_DOWN)
            return {"success": True, "action": "down", "msg": "音量减少"}
        elif action == "set":
            level = max(0, min(100, int(level)))
            # Windows 每次 VOLUME_DOWN/UP 调整 2% 音量
            # 先连续向下归零，再向上提升
            for _ in range(52):
                press_key(VK_VOLUME_DOWN)
            steps_up = level // 2
            for _ in range(steps_up):
                press_key(VK_VOLUME_UP)
            return {"success": True, "action": "set", "level": level, "msg": f"音量已设为 {level}%"}
    except Exception as e:
        return {"success": False, "error": str(e)}
    return {"success": False, "error": "未知音量指令"}


def remote_run_app(app_path: str, args: str = "", workdir: str = "") -> dict:
    """远程启动指定应用程序或命令"""
    app_path = app_path.strip()
    if not app_path:
        return {"success": False, "error": "应用程序路径不能为空"}

    try:
        if workdir and not os.path.isdir(workdir):
            workdir = os.path.dirname(app_path) if os.path.isfile(app_path) else None

        cmd_line = f'"{app_path}" {args}'.strip() if args else f'"{app_path}"'
        proc = subprocess.Popen(
            cmd_line,
            shell=True,
            cwd=workdir if workdir and os.path.isdir(workdir) else None
        )
        return {"success": True, "pid": proc.pid, "msg": f"已成功启动应用: {app_path} (PID: {proc.pid})"}
    except Exception as e:
        return {"success": False, "error": f"启动应用失败: {e}"}


def remote_kill_process(pid: int = None, name: str = None) -> dict:
    """远程终止指定进程 (支持 PID 或进程名)"""
    if pid is not None and int(pid) > 4:
        ok, out = run_cmd(f"taskkill /f /pid {pid}")
        return {"success": ok, "msg": f"终止 PID {pid}: {out}"}
    elif name:
        proc_name = name.strip()
        if not proc_name.lower().endswith(".exe"):
            proc_name += ".exe"
        ok, out = run_cmd(f'taskkill /f /im "{proc_name}"')
        return {"success": ok, "msg": f"终止进程 {proc_name}: {out}"}
    return {"success": False, "error": "未提供有效的 PID 或进程名"}


def list_running_processes() -> list:
    """枚举系统中正在运行的进程列表 (PID, 名称, 内存占用, 窗口标题) - 高性能原生快照 (30ms)"""
    procs = []
    kernel32 = ctypes.windll.kernel32
    psapi = ctypes.windll.psapi

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ('dwSize', ctypes.c_ulong),
            ('cntUsage', ctypes.c_ulong),
            ('th32ProcessID', ctypes.c_ulong),
            ('th32DefaultHeapID', ctypes.c_size_t),
            ('th32ModuleID', ctypes.c_ulong),
            ('cntThreads', ctypes.c_ulong),
            ('th32ParentProcessID', ctypes.c_ulong),
            ('pcPriClassBase', ctypes.c_long),
            ('dwFlags', ctypes.c_ulong),
            ('szExeFile', ctypes.c_char * 260)
        ]

    class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [
            ('cb', ctypes.c_ulong),
            ('PageFaultCount', ctypes.c_ulong),
            ('PeakWorkingSetSize', ctypes.c_size_t),
            ('WorkingSetSize', ctypes.c_size_t),
            ('QuotaPeakPagedPoolUsage', ctypes.c_size_t),
            ('QuotaPagedPoolUsage', ctypes.c_size_t),
            ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t),
            ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
            ('PagefileUsage', ctypes.c_size_t),
            ('PeakPagefileUsage', ctypes.c_size_t)
        ]

    try:
        h_snap = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
        pe = PROCESSENTRY32()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32)
        pmc = PROCESS_MEMORY_COUNTERS()
        pmc.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)

        if kernel32.Process32First(h_snap, ctypes.byref(pe)):
            while True:
                pid = pe.th32ProcessID
                name = pe.szExeFile.decode('gbk', 'ignore')
                mem_mb = 0.0

                if pid > 4:
                    h_proc = kernel32.OpenProcess(0x0400 | 0x0010, False, pid)
                    if h_proc:
                        try:
                            if psapi.GetProcessMemoryInfo(h_proc, ctypes.byref(pmc), pmc.cb):
                                mem_mb = round(pmc.WorkingSetSize / (1024 * 1024), 1)
                        finally:
                            kernel32.CloseHandle(h_proc)

                procs.append({
                    "pid": pid,
                    "name": name,
                    "memory_mb": mem_mb,
                    "title": ""
                })
                if not kernel32.Process32Next(h_snap, ctypes.byref(pe)):
                    break
        kernel32.CloseHandle(h_snap)
    except Exception:
        pass

    return sorted(procs, key=lambda x: x["memory_mb"], reverse=True)
