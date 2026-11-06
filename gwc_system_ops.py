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


def deep_clean_empty_working_set() -> int:
    """深度清空工作集 (兼容旧接口，返回已清理进程数)"""
    res = deep_clean_working_set()
    return res.get("cleaned_processes", 0)


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


def clean_system_temp_files() -> tuple:
    """清理 Windows 临时垃圾 (兼容接口，返回 (删除文件数, 释放MB))"""
    res = clean_system_temp()
    return res.get("deleted_files", 0), res.get("freed_mb", 0.0)


def scan_network_adapters() -> list:
    """扫描网络适配器列表 (兼容字典格式)"""
    names = get_network_adapters()
    return [{"name": n} for n in names]


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
    """读取指定适配器的 IPv4 配置信息 (优先自动精准获取子网掩码，无则默认 255.255.255.0)"""
    info = {
        "adapter": adapter_name,
        "dhcp": True,
        "ip": "",
        "mask": "255.255.255.0",
        "gateway": "",
        "dns1": "",
        "dns2": ""
    }

    # 1. 优先尝试使用 psutil 获取系统原生底层真实的 IPv4 和子网掩码
    try:
        import psutil
        addrs = psutil.net_if_addrs()
        if adapter_name in addrs:
            for snic in addrs[adapter_name]:
                if getattr(snic, "family", None) == socket.AF_INET:
                    if snic.address and not snic.address.startswith("127."):
                        info["ip"] = snic.address
                    if snic.netmask and snic.netmask not in ["0.0.0.0", ""]:
                        info["mask"] = snic.netmask
    except Exception:
        pass

    # 2. 读取 netsh 配置信息 (补充网关、DHCP状态及 DNS)
    ok, out = run_cmd(f'netsh interface ipv4 show addresses name="{adapter_name}"')
    if ok and out:
        if "DHCP enabled:                         Yes" in out or "DHCP 已启用:                          是" in out:
            info["dhcp"] = True
        elif "DHCP enabled:                         No" in out or "DHCP 已启用:                          否" in out:
            info["dhcp"] = False

        if not info["ip"]:
            m_ip = re.search(r"(?:IP Address|IP 地址|IPv4 地址)[^\d]*([\d\.]+)", out)
            if m_ip:
                info["ip"] = m_ip.group(1).strip()

        # 优先提取括号内的真实子网掩码: (mask 255.255.255.0) 或 (掩码 255.255.255.0)
        m_mask = re.search(r"(?:mask|掩码)[^\d]*([\d\.]+)", out, re.IGNORECASE)
        if m_mask and m_mask.group(1).count(".") == 3:
            info["mask"] = m_mask.group(1).strip()
        elif not info["mask"] or info["mask"] == "0.0.0.0":
            # 兼容 CIDR / 前缀换算
            m_prefix = re.search(r"(?:Subnet Prefix|子网前缀|子网掩码)[^\d]*([\d\.]+)/(\d+)", out)
            if m_prefix:
                prefix_len = int(m_prefix.group(2))
                mask_int = (0xFFFFFFFF << (32 - prefix_len)) & 0xFFFFFFFF
                info["mask"] = f"{(mask_int >> 24) & 0xFF}.{(mask_int >> 16) & 0xFF}.{(mask_int >> 8) & 0xFF}.{mask_int & 0xFF}"
            else:
                info["mask"] = "255.255.255.0"

        m_gw = re.search(r"(?:Default Gateway|默认网关)[^\d]*([\d\.]+)", out)
        if m_gw:
            info["gateway"] = m_gw.group(1).strip()

    # 兜底确保掩码非空
    if not info.get("mask") or info["mask"] == "0.0.0.0":
        info["mask"] = "255.255.255.0"

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
    远程系统主音量控制 (优先使用 Windows CoreAudio 原生接口，毫秒级绝对百分比精确设置)
    """
    try:
        class GUID(ctypes.Structure):
            _fields_ = [
                ('Data1', ctypes.c_ulong),
                ('Data2', ctypes.c_ushort),
                ('Data3', ctypes.c_ushort),
                ('Data4', ctypes.c_byte * 8)
            ]
            def __init__(self, l, w1, w2, b1, b2, b3, b4, b5, b6, b7, b8):
                self.Data1 = l
                self.Data2 = w1
                self.Data3 = w2
                self.Data4 = (ctypes.c_byte * 8)(b1, b2, b3, b4, b5, b6, b7, b8)

        CLSID_MMDeviceEnumerator = GUID(0xBCDE0395, 0xE52F, 0x467C, 0x8E, 0x3D, 0xC4, 0x57, 0x92, 0x91, 0x69, 0x2E)
        IID_IMMDeviceEnumerator = GUID(0xA95664D2, 0x9614, 0x4F35, 0xA7, 0x46, 0xDE, 0x8D, 0xB6, 0x36, 0x17, 0xE6)
        IID_IAudioEndpointVolume = GUID(0x5CDF2C82, 0x841E, 0x4546, 0x97, 0x22, 0x0C, 0xF7, 0x40, 0x78, 0x22, 0x9A)

        ctypes.windll.ole32.CoInitialize(None)
        enumerator = ctypes.c_void_p()
        hr = ctypes.windll.ole32.CoCreateInstance(
            ctypes.byref(CLSID_MMDeviceEnumerator), None, 1,
            ctypes.byref(IID_IMMDeviceEnumerator), ctypes.byref(enumerator)
        )
        if hr == 0 and enumerator.value:
            enum_vtable = ctypes.cast(ctypes.cast(enumerator, ctypes.POINTER(ctypes.c_void_p)).contents, ctypes.POINTER(ctypes.c_void_p))
            GetDefaultAudioEndpoint_fn = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))(enum_vtable[4])

            device = ctypes.c_void_p()
            if GetDefaultAudioEndpoint_fn(enumerator, 0, 1, ctypes.byref(device)) == 0 and device.value:
                dev_vtable = ctypes.cast(ctypes.cast(device, ctypes.POINTER(ctypes.c_void_p)).contents, ctypes.POINTER(ctypes.c_void_p))
                Activate_fn = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.c_ulong, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(dev_vtable[3])

                endpoint_vol = ctypes.c_void_p()
                if Activate_fn(device, ctypes.byref(IID_IAudioEndpointVolume), 23, None, ctypes.byref(endpoint_vol)) == 0 and endpoint_vol.value:
                    vol_vtable = ctypes.cast(ctypes.cast(endpoint_vol, ctypes.POINTER(ctypes.c_void_p)).contents, ctypes.POINTER(ctypes.c_void_p))

                    if action == "set":
                        level = max(0, min(100, int(level)))
                        scalar = float(level) / 100.0
                        SetVol_fn = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_float, ctypes.c_void_p)(vol_vtable[7])
                        SetVol_fn(endpoint_vol, scalar, None)
                        # 设置音量时自动解除静音
                        SetMute_fn = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_bool, ctypes.c_void_p)(vol_vtable[14])
                        SetMute_fn(endpoint_vol, False, None)
                        return {"success": True, "action": "set", "level": level, "msg": f"系统主音量已精准设为 {level}%"}

                    elif action in ("mute", "toggle_mute"):
                        GetMute_fn = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(ctypes.c_bool))(vol_vtable[15])
                        is_muted = ctypes.c_bool()
                        GetMute_fn(endpoint_vol, ctypes.byref(is_muted))
                        new_mute = not is_muted.value
                        SetMute_fn = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_bool, ctypes.c_void_p)(vol_vtable[14])
                        SetMute_fn(endpoint_vol, new_mute, None)
                        return {"success": True, "action": "mute", "is_muted": new_mute, "msg": "已开启静音" if new_mute else "已解除静音"}
    except Exception:
        pass

    # 降级备用方案: 模拟键盘调节
    user32 = ctypes.windll.user32
    VK_VOLUME_MUTE = 0xAD
    VK_VOLUME_DOWN = 0xAE
    VK_VOLUME_UP = 0xAF
    def press_key(vk):
        user32.keybd_event(vk, 0, 0, 0)
        user32.keybd_event(vk, 0, 2, 0)

    try:
        if action in ("mute", "toggle_mute"):
            press_key(VK_VOLUME_MUTE)
            return {"success": True, "action": "mute", "msg": "已切换静音状态"}
        elif action == "set":
            level = max(0, min(100, int(level)))
            for _ in range(50): press_key(VK_VOLUME_DOWN)
            for _ in range(level // 2): press_key(VK_VOLUME_UP)
            return {"success": True, "action": "set", "level": level, "msg": f"音量设为 {level}%"}
    except Exception as e:
        return {"success": False, "error": str(e)}
    return {"success": False, "error": "未知音量指令"}


def remote_run_app(app_path: str, args: str = "", workdir: str = "") -> dict:
    """远程极速启动应用程序 (独立进程组与桌面分离，自动展开环境变量与工作目录，零阻塞即刻返回)"""
    app_path = os.path.expandvars(app_path.strip().strip('"'))
    if not app_path:
        return {"success": False, "error": "应用程序路径不能为空"}

    # 快捷方式 (.lnk) 智能解析与重定向
    if app_path.lower().endswith(".lnk") and os.path.isfile(app_path):
        try:
            # 优先使用 Windows PowerShell 极速解析快捷方式真实物理目标
            ps_cmd = f'(New-Object -COM WScript.Shell).CreateShortcut("{app_path}").TargetPath'
            out = subprocess.check_output(["powershell", "-NoProfile", "-Command", ps_cmd], timeout=1.0, creationflags=0x08000000).decode("gbk", errors="ignore").strip()
            if out and os.path.exists(out):
                app_path = out
        except Exception:
            pass

    # 自动推导工作目录：很多工控播控程序必须在自身目录下才能正确加载资源
    if not workdir or not os.path.isdir(workdir):
        if os.path.isfile(app_path):
            workdir = os.path.dirname(os.path.abspath(app_path))
        else:
            workdir = os.getcwd()

    # 优先使用 Windows 原生 ShellExecuteW 桌面环境独立启动 (完全继承当前桌面交互会话)
    try:
        shell32 = ctypes.windll.shell32
        res = shell32.ShellExecuteW(
            None,
            "open",
            app_path,
            args.strip() if args else None,
            workdir if workdir else None,
            1  # SW_SHOWNORMAL
        )
        if res > 32:
            return {"success": True, "msg": f"已成功启动: {os.path.basename(app_path)}", "path": app_path}
    except Exception:
        pass

    # 方案二：通过独立进程组极速分离启动 (零延迟、不阻塞当前服务通道)
    try:
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        cmd_str = f'"{app_path}" {args}'.strip() if args else f'"{app_path}"'
        p = subprocess.Popen(
            cmd_str,
            cwd=workdir,
            shell=True,
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL
        )
        return {"success": True, "pid": p.pid, "msg": f"已启动: {os.path.basename(app_path)} (PID: {p.pid})"}
    except Exception as e:
        return {"success": False, "error": f"调用应用失败: {e}"}


def remote_kill_process(pid: int = None, name: str = None) -> dict:
    """远程终止指定进程 (psutil 子进程树递归强杀 + Win32 TerminateProcess + taskkill 兜底)"""
    killed = False
    details = []

    # 1. 优先使用 psutil 强杀 PID 及其所有递归子进程树 (毫秒级响应)
    if pid is not None:
        try:
            pid_int = int(pid)
            if pid_int > 4:
                try:
                    import psutil
                    if psutil.pid_exists(pid_int):
                        p = psutil.Process(pid_int)
                        # 递归终结所有派生子进程
                        for child in p.children(recursive=True):
                            try:
                                child.kill()
                            except Exception:
                                pass
                        p.kill()
                        killed = True
                        details.append(f"psutil PID {pid_int}")
                    else:
                        killed = True
                        details.append(f"PID {pid_int} 之前已退出")
                except Exception:
                    pass

                # Win32 TerminateProcess 辅助强杀
                try:
                    kernel32 = ctypes.windll.kernel32
                    h_proc = kernel32.OpenProcess(0x0001, False, pid_int)  # PROCESS_TERMINATE
                    if h_proc:
                        kernel32.TerminateProcess(h_proc, 1)
                        kernel32.CloseHandle(h_proc)
                        killed = True
                        details.append(f"Win32 Terminate PID {pid_int}")
                except Exception:
                    pass
        except Exception:
            pass

    # 2. 如果提供了进程名，按名称全量扫描杀进程
    if name:
        proc_name = name.strip()
        if not proc_name.lower().endswith(".exe"):
            proc_name += ".exe"
        try:
            import psutil
            for p in psutil.process_iter(['pid', 'name']):
                try:
                    if p.name().lower() == proc_name.lower():
                        for child in p.children(recursive=True):
                            try: child.kill()
                            except Exception: pass
                        p.kill()
                        killed = True
                        details.append(f"psutil IM {proc_name}")
                except Exception:
                    pass
        except Exception:
            pass

    # 3. 兜底 taskkill 强杀
    if not killed and (pid or name):
        try:
            if pid:
                run_cmd(f"taskkill /F /T /PID {pid}")
            if name:
                run_cmd(f'taskkill /F /T /IM "{proc_name}"')
            killed = True
            details.append("Taskkill 兜底执行")
        except Exception:
            pass

    if killed:
        return {"success": True, "msg": f"进程已成功终止: {', '.join(details)}"}
    else:
        return {"success": False, "error": f"未能找到或终止进程 (PID: {pid}, Name: {name})"}


def ensure_single_instance(mutex_name: str) -> bool:
    """
    进程单实例互斥保护。
    若已有相同互斥体存在，返回 False。
    """
    kernel32 = ctypes.windll.kernel32
    # 尝试创建命名互斥体
    mutex = kernel32.CreateMutexW(None, False, mutex_name)
    last_error = kernel32.GetLastError()
    # 183 = ERROR_ALREADY_EXISTS
    if last_error == 183:
        if mutex:
            kernel32.CloseHandle(mutex)
        return False
    globals()["__GWC_INSTANCE_MUTEX__"] = mutex
    return True


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
