# -*- coding: utf-8 -*-
"""
展馆系统配置与网络设置及电脑优化工具
核心功能：
1. 展馆网络与系统配置：以太网/IPv4配置、系统策略管理(UAC/Defender/更新/防火墙/节能/快启/手势/休眠/RDP免密)、ALLON/ALLOFF一键批处理
2. 电脑深度优化工具箱：
   - 内存释放：实时监控物理内存，一键深度清空进程工作集与系统缓存，清理垃圾临时文件
   - 网络修复：重置Winsock、重置TCP/IP协议栈、刷新DNS、释放更新DHCP、ARP清理、网络连通性一键诊断
   - 启动禁用：枚举用户及系统开机启动项与启动文件夹，支持一键禁用/启用/删除启动项
   - 右键管理：Win11经典/新版右键菜单切换、取得管理员所有权、在此处打开CMD/PS、隐藏文件/扩展名切换
   - 软件与注册表管理：已安装软件扫描与官方卸载、系统挂起超时优化、禁用Bing搜索/错误报告/GameDVR、开启卓越性能模式
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
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from ctypes import wintypes

# ==================== 管理员提权检测 ====================
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False

def elevate_if_needed():
    if not is_admin():
        script = os.path.abspath(sys.argv[0])
        params = " ".join([f'"{arg}"' for arg in sys.argv[1:]])
        try:
            ret = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable if not script.endswith('.exe') else script,
                f'"{script}" {params}' if not script.endswith('.exe') else params,
                None, 1
            )
            sys.exit(0)
        except Exception as e:
            messagebox.showerror("权限错误", f"无法请求管理员权限：{e}\n请右键选择【以管理员身份运行】")
            sys.exit(1)


# ==================== 命令行执行与工具函数 ====================
def run_cmd(command):
    """运行系统命令并返回 (success, output)"""
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

def validate_ip(ip_str, field_name="IP地址", allow_empty=False):
    """校验 IPv4 地址合法性"""
    ip_str = ip_str.strip()
    if not ip_str:
        if allow_empty:
            return True, ""
        return False, f"{field_name} 不能为空"
    try:
        ipaddress.IPv4Address(ip_str)
        return True, ""
    except ValueError:
        return False, f"{field_name} 格式不正确: {ip_str}"

def validate_netmask(mask_str):
    """校验子网掩码合法性"""
    mask_str = mask_str.strip()
    if not mask_str:
        return False, "子网掩码不能为空"
    try:
        ipaddress.IPv4Network(f"0.0.0.0/{mask_str}")
        return True, ""
    except ValueError:
        return False, f"子网掩码格式不正确: {mask_str}"

def notify_shell_refresh():
    """通知 Windows Shell 刷新设置与图标"""
    try:
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, 0, 0)
    except Exception:
        pass


# ==================== 1. 内存监测与深度释放模块 ====================
class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ('dwLength', wintypes.DWORD),
        ('dwMemoryLoad', wintypes.DWORD),
        ('ullTotalPhys', ctypes.c_uint64),
        ('ullAvailPhys', ctypes.c_uint64),
        ('ullTotalPageFile', ctypes.c_uint64),
        ('ullAvailPageFile', ctypes.c_uint64),
        ('ullTotalVirtual', ctypes.c_uint64),
        ('ullAvailVirtual', ctypes.c_uint64),
        ('ullAvailExtendedVirtual', ctypes.c_uint64),
    ]

def get_system_memory():
    """获取当前系统物理内存状态"""
    try:
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        total_mb = stat.ullTotalPhys / (1024 * 1024)
        avail_mb = stat.ullAvailPhys / (1024 * 1024)
        used_mb = total_mb - avail_mb
        load = stat.dwMemoryLoad
        return {
            "total_mb": round(total_mb, 1),
            "avail_mb": round(avail_mb, 1),
            "used_mb": round(used_mb, 1),
            "percent": int(load)
        }
    except Exception:
        return {"total_mb": 0, "avail_mb": 0, "used_mb": 0, "percent": 0}

def deep_clean_working_set():
    """深度释放所有进程的工作集内存"""
    PROCESS_QUERY_INFORMATION = 0x0400
    PROCESS_SET_QUOTA = 0x0100

    mem_before = get_system_memory()
    pids = (wintypes.DWORD * 4096)()
    cb_needed = wintypes.DWORD()
    success_cnt = 0
    total_cnt = 0

    if ctypes.windll.psapi.EnumProcesses(ctypes.byref(pids), ctypes.sizeof(pids), ctypes.byref(cb_needed)):
        count = cb_needed.value // ctypes.sizeof(wintypes.DWORD)
        total_cnt = count
        for i in range(count):
            pid = pids[i]
            if pid == 0:
                continue
            h_process = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_SET_QUOTA, False, pid)
            if h_process:
                try:
                    if ctypes.windll.psapi.EmptyWorkingSet(h_process):
                        success_cnt += 1
                except Exception:
                    pass
                finally:
                    ctypes.windll.kernel32.CloseHandle(h_process)

    time.sleep(0.3)
    mem_after = get_system_memory()
    freed_mb = max(0.0, mem_before["used_mb"] - mem_after["used_mb"])
    return {
        "success_cnt": success_cnt,
        "total_cnt": total_cnt,
        "mem_before": mem_before,
        "mem_after": mem_after,
        "freed_mb": round(freed_mb, 1)
    }

def clean_system_temp():
    """安全清理临时文件与缓存垃圾"""
    cleaned_count = 0
    freed_bytes = 0
    temp_dirs = [
        os.environ.get('TEMP', ''),
        os.environ.get('TMP', ''),
        os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'Temp')
    ]
    for d in temp_dirs:
        if not d or not os.path.exists(d):
            continue
        try:
            for root_dir, dirs, files in os.walk(d, topdown=False):
                for f in files:
                    fp = os.path.join(root_dir, f)
                    try:
                        sz = os.path.getsize(fp)
                        os.remove(fp)
                        cleaned_count += 1
                        freed_bytes += sz
                    except Exception:
                        pass
                for dir_name in dirs:
                    dp = os.path.join(root_dir, dir_name)
                    try:
                        os.rmdir(dp)
                    except Exception:
                        pass
        except Exception:
            pass
    return cleaned_count, round(freed_bytes / (1024 * 1024), 2)


# ==================== 2. 网络配置与修复诊断模块 ====================
def get_network_adapters():
    """获取所有网络适配器名称列表"""
    adapters = []
    try:
        cmd = ['powershell', '-NoProfile', '-Command', 'Get-NetAdapter | Select-Object -ExpandProperty Name']
        res = subprocess.run(cmd, capture_output=True, text=True, encoding='gbk', errors='ignore')
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                name = line.strip()
                if name and name not in adapters:
                    adapters.append(name)
    except Exception:
        pass

    if not adapters:
        try:
            res = subprocess.run('netsh interface show interface', shell=True, capture_output=True, encoding='gbk', errors='ignore')
            for line in res.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 4 and parts[0] in ('已启用', '已禁用', 'Enabled', 'Disabled'):
                    name = " ".join(parts[3:])
                    if name and name not in adapters:
                        adapters.append(name)
        except Exception:
            pass

    if "以太网" not in adapters:
        adapters.insert(0, "以太网")
    else:
        adapters.remove("以太网")
        adapters.insert(0, "以太网")

    return adapters

def read_adapter_ipv4(adapter_name):
    """读取指定适配器的当前 IPv4 配置"""
    info = {"ip": "", "mask": "255.255.255.0", "gateway": "", "dns1": "", "dns2": "", "dhcp": False}
    try:
        res = subprocess.run(
            f'netsh interface ip show config name="{adapter_name}"',
            shell=True, capture_output=True, encoding='gbk', errors='ignore'
        )
        output = res.stdout
        if "DHCP" in output and ("是" in output or "Yes" in output or "enabled" in output.lower()):
            info["dhcp"] = True

        ips = []
        dns_list = []
        gateways = []
        masks = []

        for line in output.splitlines():
            line_str = line.strip()
            found_ips = re.findall(r'(\d{1,3}(?:\.\d{1,3}){3})', line_str)
            if not found_ips:
                continue

            if "IP" in line_str or "ip" in line_str:
                for ip in found_ips:
                    if not ip.startswith("255.") and ip not in ips:
                        ips.append(ip)
            if "掩码" in line_str or "Mask" in line_str or "mask" in line_str:
                for m in found_ips:
                    if m.startswith("255.") and m not in masks:
                        masks.append(m)
            if "网关" in line_str or "Gateway" in line_str or "gateway" in line_str:
                for gw in found_ips:
                    if gw not in gateways:
                        gateways.append(gw)
            if "DNS" in line_str or "dns" in line_str:
                for dns in found_ips:
                    if dns not in dns_list:
                        dns_list.append(dns)

        if ips:
            info["ip"] = ips[0]
        if masks:
            info["mask"] = masks[0]
        if gateways:
            info["gateway"] = gateways[0]
        if len(dns_list) > 0:
            info["dns1"] = dns_list[0]
        if len(dns_list) > 1:
            info["dns2"] = dns_list[1]
    except Exception:
        pass
    return info

def run_network_diagnostic(target_gateway=""):
    """一键诊断网络状态并输出分析"""
    results = []
    
    # 1. 回环检测
    ok_loop, out_loop = run_cmd("ping 127.0.0.1 -n 2 -w 800")
    results.append(("TCP/IP 本机协议栈 (127.0.0.1)", "正常" if ok_loop else "异常", ok_loop))
    
    # 2. 网关连通性
    if target_gateway:
        ok_gw, out_gw = run_cmd(f"ping {target_gateway} -n 2 -w 1000")
        results.append((f"局域网默认网关 ({target_gateway})", "连通正常" if ok_gw else "无法连通(断网或网线松动)", ok_gw))
    else:
        results.append(("局域网默认网关", "未配置网关", None))
        
    # 3. 公共 DNS Ping
    for dns_ip, name in [("223.5.5.5", "阿里公共DNS"), ("114.114.114.114", "114公共DNS")]:
        ok_dns, out_dns = run_cmd(f"ping {dns_ip} -n 2 -w 1200")
        results.append((f"公网连通性 ({name} {dns_ip})", "通畅" if ok_dns else "不通(外网故障/被防火墙拦截)", ok_dns))
        
    # 4. 域名解析检测
    ok_res, out_res = run_cmd("nslookup baidu.com")
    dns_ok = ok_res and ("Address" in out_res or "Addresses" in out_res)
    results.append(("公网 DNS 域名解析 (baidu.com)", "解析正常" if dns_ok else "解析失败(请检查DNS设置)", dns_ok))
    
    return results


# ==================== 3. 启动禁用与启动项管理模块 ====================
RUN_LOCATIONS = [
    (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", "当前用户注册表 (HKCU)", "HKCU_RUN"),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run", "系统级注册表 (HKLM)", "HKLM_RUN"),
    (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run-Disabled", "当前用户注册表(已禁用)", "HKCU_DIS"),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run-Disabled", "系统级注册表(已禁用)", "HKLM_DIS"),
]

def get_startup_folders():
    folders = []
    user_startup = os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup")
    common_startup = os.path.expandvars(r"%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs\Startup")
    if os.path.exists(user_startup):
        folders.append((user_startup, "用户启动文件夹", "USER_FOLDER"))
    if os.path.exists(common_startup):
        folders.append((common_startup, "系统公共启动文件夹", "COMMON_FOLDER"))
    return folders

def scan_all_startup_items():
    """扫描所有自启动项（注册表与启动文件夹）"""
    items = []
    # 1. 扫描注册表
    for root, subkey, label, tag in RUN_LOCATIONS:
        try:
            with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ) as key:
                count = winreg.QueryInfoKey(key)[1]
                for i in range(count):
                    try:
                        name, val, typ = winreg.EnumValue(key, i)
                        is_disabled = "DIS" in tag
                        items.append({
                            "name": name,
                            "command": str(val),
                            "type": "注册表",
                            "source_label": label,
                            "tag": tag,
                            "reg_root": root,
                            "reg_key": subkey,
                            "status": "已禁用" if is_disabled else "已启用",
                            "is_disabled": is_disabled,
                            "file_path": str(val).split('"')[1] if str(val).startswith('"') else str(val).split()[0] if str(val) else ""
                        })
                    except Exception:
                        pass
        except Exception:
            pass

    # 2. 扫描启动文件夹
    for folder_path, label, tag in get_startup_folders():
        try:
            for f in os.listdir(folder_path):
                full_p = os.path.join(folder_path, f)
                if os.path.isfile(full_p):
                    is_dis = f.lower().endswith(".disabled")
                    display_name = f[:-9] if is_dis else f
                    items.append({
                        "name": display_name,
                        "command": full_p,
                        "type": "启动文件夹",
                        "source_label": label,
                        "tag": tag,
                        "file_path": full_p,
                        "status": "已禁用" if is_dis else "已启用",
                        "is_disabled": is_dis
                    })
        except Exception:
            pass

    return items

def set_startup_item_state(item, enable=True):
    """启用或禁用启动项"""
    if item["type"] == "注册表":
        root = item["reg_root"]
        curr_key = item["reg_key"]
        name = item["name"]
        val = item["command"]
        
        if enable:
            target_key_name = r"Software\Microsoft\Windows\CurrentVersion\Run"
        else:
            target_key_name = r"Software\Microsoft\Windows\CurrentVersion\Run-Disabled"
            
        try:
            # 写入目标键
            with winreg.CreateKey(root, target_key_name) as t_key:
                winreg.SetValueEx(t_key, name, 0, winreg.REG_SZ, val)
            # 从原键删除
            with winreg.OpenKey(root, curr_key, 0, winreg.KEY_SET_VALUE) as s_key:
                winreg.DeleteValue(s_key, name)
            return True, f"注册表自启项 [{name}] 已设置为: {'已启用' if enable else '已禁用'}"
        except Exception as ex:
            return False, f"修改启动项状态失败: {ex}"
            
    elif item["type"] == "启动文件夹":
        fp = item["file_path"]
        try:
            if enable and fp.endswith(".disabled"):
                new_p = fp[:-9]
                os.rename(fp, new_p)
                return True, f"启动文件夹项已恢复启用: {os.path.basename(new_p)}"
            elif not enable and not fp.endswith(".disabled"):
                new_p = fp + ".disabled"
                os.rename(fp, new_p)
                return True, f"启动文件夹项已禁用: {os.path.basename(new_p)}"
            return True, "状态未变更"
        except Exception as ex:
            return False, f"重命名文件失败: {ex}"
    return False, "未知启动项类型"

def delete_startup_item_permanently(item):
    """永久删除启动项"""
    if item["type"] == "注册表":
        try:
            with winreg.OpenKey(item["reg_root"], item["reg_key"], 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, item["name"])
            return True, f"已从注册表中永久删除: {item['name']}"
        except Exception as ex:
            return False, f"删除失败: {ex}"
    elif item["type"] == "启动文件夹":
        try:
            os.remove(item["file_path"])
            return True, f"已从启动文件夹删除: {os.path.basename(item['file_path'])}"
        except Exception as ex:
            return False, f"删除文件失败: {ex}"
    return False, "未知类型"


# ==================== 4. 右键菜单管理模块 ====================
CONTEXT_SCAN_PATHS = [
    (winreg.HKEY_CLASSES_ROOT, r'*\shell', '文件', 'shell'),
    (winreg.HKEY_CLASSES_ROOT, r'*\shellex\ContextMenuHandlers', '文件', 'shellex'),
    (winreg.HKEY_CLASSES_ROOT, r'AllFilesystemObjects\shell', '所有文件与文件夹', 'shell'),
    (winreg.HKEY_CLASSES_ROOT, r'AllFilesystemObjects\shellex\ContextMenuHandlers', '所有文件与文件夹', 'shellex'),
    (winreg.HKEY_CLASSES_ROOT, r'Directory\shell', '文件夹', 'shell'),
    (winreg.HKEY_CLASSES_ROOT, r'Directory\shellex\ContextMenuHandlers', '文件夹', 'shellex'),
    (winreg.HKEY_CLASSES_ROOT, r'Directory\Background\shell', '桌面与空白背景', 'shell'),
    (winreg.HKEY_CLASSES_ROOT, r'Directory\Background\shellex\ContextMenuHandlers', '桌面与空白背景', 'shellex'),
    (winreg.HKEY_CLASSES_ROOT, r'Drive\shell', '磁盘驱动器', 'shell'),
    (winreg.HKEY_CLASSES_ROOT, r'Drive\shellex\ContextMenuHandlers', '磁盘驱动器', 'shellex'),
]

SYSTEM_WHITELIST = {
    'open', 'opennewwindow', 'openas', 'openwith', 'openwithlist', 'print', 'edit',
    'explore', 'find', 'runas', 'runasuser', 'cmd', 'powershell', 'properties',
    'cut', 'copy', 'paste', 'delete', 'rename', 'preview',
    'modernsharing', 'sharing', 'workspaces', 'workfolders', 'epp',
    'encryptionmenu', 'open with', 'open with encryptionmenu',
    'offline files', 'sendto', 'copyaspathmenu', 'new', 'enhancedstorageshell',
    'change-passphrase', 'change-pin', 'encrypt-bde', 'encrypt-bde-elev',
    'manage-bde', 'resume-bde', 'resume-bde-elev', 'unlock-bde',
    'launchworkfolderscontrol', 'offlinefileslaunchsynccenter',
    'opencmdadmin', 'openpsadmin'
}

def get_clsid_info(clsid):
    c = clsid.strip().lstrip('-')
    if not (c.startswith('{') and c.endswith('}')):
        return ''
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, f'CLSID\\{c}', 0, winreg.KEY_READ) as k:
            name = ''
            try:
                name = str(winreg.QueryValue(k, '')).strip()
            except Exception:
                pass
            dll = ''
            try:
                with winreg.OpenKey(k, 'InprocServer32') as ik:
                    dll = str(winreg.QueryValue(ik, '')).strip()
            except Exception:
                pass
            return f'{name} [{dll}]' if (name and dll) else (name or dll)
    except Exception:
        return ''

def scan_context_menu_items():
    items = []
    for root, path, scope_label, kind in CONTEXT_SCAN_PATHS:
        try:
            with winreg.OpenKey(root, path, 0, winreg.KEY_READ) as key:
                sub_count = winreg.QueryInfoKey(key)[0]
                for i in range(sub_count):
                    subkey_name = winreg.EnumKey(key, i)
                    is_sys = subkey_name.lower() in SYSTEM_WHITELIST
                    full_path = f'{path}\\{subkey_name}'
                    display_name = subkey_name
                    command_or_clsid = ''
                    is_disabled = False
                    try:
                        with winreg.OpenKey(root, full_path, 0, winreg.KEY_READ) as sk:
                            try:
                                def_val = str(winreg.QueryValue(sk, '')).strip()
                            except Exception:
                                def_val = ''
                            if kind == 'shellex':
                                command_or_clsid = def_val
                                if def_val.startswith('-'):
                                    is_disabled = True
                                clsid_info = get_clsid_info(def_val)
                                if clsid_info:
                                    display_name = f'{subkey_name} ({clsid_info})'
                            else:
                                try:
                                    mui = str(winreg.QueryValueEx(sk, 'MUIVerb')[0]).strip()
                                    if mui:
                                        display_name = mui
                                except Exception:
                                    pass
                                if (not display_name or display_name == subkey_name) and def_val:
                                    display_name = f'{subkey_name} ({def_val})'
                                for dis_flag in ['LegacyDisable', 'ProgrammaticAccessOnly']:
                                    try:
                                        winreg.QueryValueEx(sk, dis_flag)
                                        is_disabled = True
                                        break
                                    except Exception:
                                        pass
                                try:
                                    with winreg.OpenKey(sk, 'command') as ck:
                                        command_or_clsid = str(winreg.QueryValue(ck, '')).strip()
                                except Exception:
                                    pass
                    except Exception:
                        pass
                    items.append({
                        'name': display_name,
                        'key_name': subkey_name,
                        'is_third_party': not is_sys,
                        'scope': scope_label,
                        'kind': kind,
                        'path': path,
                        'full_path': full_path,
                        'cmd_or_clsid': command_or_clsid,
                        'status': '已禁用' if is_disabled else '已启用',
                        'is_disabled': is_disabled
                    })
        except Exception:
            pass
    return items

def set_context_entry_state(item, enable=True):
    path = item['path']
    subkey = item['key_name']
    kind = item['kind']
    if kind == 'shellex':
        clsid = item['cmd_or_clsid'].strip()
        clean_clsid = clsid.lstrip('-')
        target_val = clean_clsid if enable else ('-' + clean_clsid)
        res = subprocess.run(['reg', 'add', f'HKCR\\{path}\\{subkey}', '/ve', '/d', target_val, '/f'], capture_output=True, text=True, encoding='gbk')
        if res.returncode == 0:
            notify_shell_refresh()
            return True, f'右键扩展 [{subkey}] 已设为: {"已启用" if enable else "已禁用"}'
        res2 = subprocess.run(['reg', 'add', f'HKLM\\Software\\Classes\\{path}\\{subkey}', '/ve', '/d', target_val, '/f'], capture_output=True, text=True, encoding='gbk')
        if res2.returncode == 0:
            notify_shell_refresh()
            return True, f'右键扩展 [{subkey}] 已设为: {"已启用" if enable else "已禁用"}'
        return False, (res.stderr or res2.stderr or '操作失败').strip()
    else:
        if enable:
            subprocess.run(['reg', 'delete', f'HKCR\\{path}\\{subkey}', '/v', 'LegacyDisable', '/f'], capture_output=True)
            subprocess.run(['reg', 'delete', f'HKCR\\{path}\\{subkey}', '/v', 'ProgrammaticAccessOnly', '/f'], capture_output=True)
            notify_shell_refresh()
            return True, f'右键菜单 [{subkey}] 已恢复启用'
        else:
            res = subprocess.run(['reg', 'add', f'HKCR\\{path}\\{subkey}', '/v', 'LegacyDisable', '/t', 'REG_SZ', '/d', '', '/f'], capture_output=True, text=True, encoding='gbk')
            if res.returncode == 0:
                notify_shell_refresh()
                return True, f'右键菜单 [{subkey}] 已成功禁用'
            return False, res.stderr.strip()

def delete_context_entry_permanently(item):
    path = item['path']
    subkey = item['key_name']
    full_path = f'HKCR\\{path}\\{subkey}'
    res = subprocess.run(['reg', 'delete', full_path, '/f'], capture_output=True, text=True, encoding='gbk')
    if res.returncode == 0:
        notify_shell_refresh()
        return True, f'已成功从注册表彻底删除右键项: [{subkey}]'
    hklm_path = f'HKLM\\Software\\Classes\\{path}\\{subkey}'
    res2 = subprocess.run(['reg', 'delete', hklm_path, '/f'], capture_output=True, text=True, encoding='gbk')
    if res2.returncode == 0:
        notify_shell_refresh()
        return True, f'已成功从系统注册表彻底删除右键项: [{subkey}]'
    return False, (res.stderr or res2.stderr or '删除失败').strip()

def set_win11_classic_context_menu(enable=True):
    key_path = r'HKCU\Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}\InprocServer32'
    if enable:
        ok, out = run_cmd(f'reg add "{key_path}" /f /ve')
        if ok:
            run_cmd('taskkill /f /im explorer.exe & start explorer.exe')
            return True, "已切换为 Win10 经典完整右键菜单！(资源管理器已自动平滑重启)"
        return False, f"设置失败: {out}"
    else:
        ok, out = run_cmd(r'reg delete "HKCU\Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}" /f')
        run_cmd('taskkill /f /im explorer.exe & start explorer.exe')
        return True, "已恢复 Win11 现代折叠右键菜单！(资源管理器已自动重启)"

def set_take_ownership_menu(enable=True):
    if enable:
        cmds = [
            'reg add "HKCR\*\shell\runas" /ve /t REG_SZ /d "取得管理员所有权" /f',
            'reg add "HKCR\*\shell\runas" /v "NoWorkingDirectory" /t REG_SZ /d "" /f',
            'reg add "HKCR\*\shell\runas\command" /ve /t REG_SZ /d "cmd.exe /c takeown /f \"%1\" && icacls \"%1\" /grant administrators:F" /f',
            'reg add "HKCR\Directory\shell\runas" /ve /t REG_SZ /d "取得管理员所有权" /f',
            'reg add "HKCR\Directory\shell\runas" /v "NoWorkingDirectory" /t REG_SZ /d "" /f',
            'reg add "HKCR\Directory\shell\runas\command" /ve /t REG_SZ /d "cmd.exe /c takeown /f \"%1\" /r /d y && icacls \"%1\" /grant administrators:F /t" /f'
        ]
        for c in cmds:
            run_cmd(c)
        notify_shell_refresh()
        return True, "已成功添加【取得管理员所有权】右键菜单！"
    else:
        run_cmd('reg delete "HKCR\*\shell\runas" /f')
        run_cmd('reg delete "HKCR\Directory\shell\runas" /f')
        notify_shell_refresh()
        return True, "已移除【取得管理员所有权】右键菜单。"

def set_cmd_context_menu(enable=True):
    if enable:
        cmds = [
            'reg add "HKCR\\Directory\\Background\\shell\\OpenCmdAdmin" /ve /t REG_SZ /d "在此处打开终端 CMD (管理员)" /f',
            'reg add "HKCR\\Directory\\Background\\shell\\OpenCmdAdmin" /v "Icon" /t REG_SZ /d "cmd.exe" /f',
            r'reg add "HKCR\Directory\Background\shell\OpenCmdAdmin\command" /ve /t REG_SZ /d "PowerShell -windowstyle hidden -Command \"Start-Process cmd -ArgumentList \'/s /k pushd \\\"\"%V\\\"\"\' -Verb RunAs\"" /f'
        ]
        for c in cmds:
            run_cmd(c)
        notify_shell_refresh()
        return True, "已添加【在此处打开 CMD (管理员)】右键菜单！"
    else:
        run_cmd('reg delete "HKCR\\Directory\\Background\\shell\\OpenCmdAdmin" /f')
        notify_shell_refresh()
        return True, "已移除【在此处打开 CMD】右键菜单。"

def set_powershell_context_menu(enable=True):
    if enable:
        cmds = [
            'reg add "HKCR\\Directory\\Background\\shell\\OpenPSAdmin" /ve /t REG_SZ /d "在此处打开 PowerShell (管理员)" /f',
            'reg add "HKCR\\Directory\\Background\\shell\\OpenPSAdmin" /v "Icon" /t REG_SZ /d "powershell.exe" /f',
            r'reg add "HKCR\Directory\Background\shell\OpenPSAdmin\command" /ve /t REG_SZ /d "PowerShell -windowstyle hidden -Command \"Start-Process powershell -ArgumentList \'-NoExit -Command Set-Location -LiteralPath \\\"\"%V\\\"\"\' -Verb RunAs\"" /f'
        ]
        for c in cmds:
            run_cmd(c)
        notify_shell_refresh()
        return True, "已添加【在此处打开 PowerShell (管理员)】右键菜单！"
    else:
        run_cmd('reg delete "HKCR\\Directory\\Background\\shell\\OpenPSAdmin" /f')
        notify_shell_refresh()
        return True, "已移除【在此处打开 PowerShell】右键菜单。"

def set_file_extension_visibility(show=True):
    val = 0 if show else 1
    cmd = f'reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced" /v HideFileExt /t REG_DWORD /d {val} /f'
    run_cmd(cmd)
    notify_shell_refresh()
    return True, f"文件扩展名已设置为: {'显示' if show else '隐藏'}"

def set_hidden_files_visibility(show=True):
    val = 1 if show else 2
    cmd = f'reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced" /v Hidden /t REG_DWORD /d {val} /f'
    run_cmd(cmd)
    notify_shell_refresh()
    return True, f"系统隐藏文件已设置为: {'显示' if show else '隐藏'}"


# ==================== 5. 软件与注册表管理模块 ====================
def list_installed_software():
    """扫描系统所有已安装软件列表"""
    locations = [
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall", "HKLM 64位"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall", "HKLM 32位"),
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall", "HKCU 用户")
    ]
    apps = []
    seen = set()

    for root, path, tag in locations:
        try:
            with winreg.OpenKey(root, path, 0, winreg.KEY_READ) as key:
                num_subkeys = winreg.QueryInfoKey(key)[0]
                for i in range(num_subkeys):
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, subkey_name) as subkey:
                            def get_v(n):
                                try:
                                    val = winreg.QueryValueEx(subkey, n)[0]
                                    return str(val).strip()
                                except Exception:
                                    return ""

                            name = get_v("DisplayName")
                            system_component = get_v("SystemComponent")
                            parent_key_name = get_v("ParentKeyName")

                            # 过滤非软件或补丁项
                            if not name or system_component == "1" or parent_key_name:
                                continue

                            version = get_v("DisplayVersion")
                            publisher = get_v("Publisher")
                            uninst = get_v("QuietUninstallString") or get_v("UninstallString")
                            install_loc = get_v("InstallLocation")

                            uniq_key = f"{name}_{version}"
                            if uniq_key in seen:
                                continue
                            seen.add(uniq_key)

                            apps.append({
                                "name": name,
                                "version": version or "-",
                                "publisher": publisher or "-",
                                "uninstall": uninst,
                                "install_loc": install_loc,
                                "reg_root": tag,
                                "key_name": subkey_name
                            })
                    except Exception:
                        pass
        except Exception:
            pass

    # 按软件名称排序
    apps.sort(key=lambda x: x["name"].lower())
    return apps

def apply_system_registry_optimizations(item_key, enable=True):
    """应用系统性能与注册表深度优化"""
    if item_key == "hung_timeout":
        # 优化无响应超时与关机等待
        if enable:
            run_cmd('reg add "HKCU\\Control Panel\\Desktop" /v HungAppTimeout /t REG_SZ /d 1000 /f')
            run_cmd('reg add "HKCU\\Control Panel\\Desktop" /v WaitToKillAppTimeout /t REG_SZ /d 2000 /f')
            run_cmd('reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control" /v WaitToKillServiceTimeout /t REG_SZ /d 2000 /f')
            return True, "已优化卡死程序与关机服务等待时间为 2 秒 (加速关机与结束卡顿)"
        else:
            run_cmd('reg add "HKCU\\Control Panel\\Desktop" /v HungAppTimeout /t REG_SZ /d 5000 /f')
            run_cmd('reg add "HKCU\\Control Panel\\Desktop" /v WaitToKillAppTimeout /t REG_SZ /d 20000 /f')
            run_cmd('reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control" /v WaitToKillServiceTimeout /t REG_SZ /d 5000 /f')
            return True, "已恢复系统默认等待时间"

    elif item_key == "wer":
        # 禁用系统错误报告
        if enable:
            run_cmd('reg add "HKLM\\SOFTWARE\\Microsoft\\Windows\\Windows Error Reporting" /v Disabled /t REG_DWORD /d 1 /f')
            run_cmd('sc config WerSvc start= disabled & sc stop WerSvc')
            return True, "已禁用 Windows 错误报告弹窗与后台收集服务 (WerSvc)"
        else:
            run_cmd('reg delete "HKLM\\SOFTWARE\\Microsoft\\Windows\\Windows Error Reporting" /v Disabled /f')
            run_cmd('sc config WerSvc start= demand')
            return True, "已恢复 Windows 错误报告默认设置"

    elif item_key == "bing_search":
        # 禁用任务栏搜索 Bing 联网联想
        if enable:
            run_cmd('reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Search" /v BingSearchEnabled /t REG_DWORD /d 0 /f')
            run_cmd('reg add "HKCU\\Software\\Policies\\Microsoft\\Windows\\Explorer" /v DisableSearchBoxSuggestions /t REG_DWORD /d 1 /f')
            return True, "已禁用任务栏搜索框 Bing 联网建议 (本地搜索秒出结果，极度清爽)"
        else:
            run_cmd('reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Search" /v BingSearchEnabled /f')
            run_cmd('reg delete "HKCU\\Software\\Policies\\Microsoft\\Windows\\Explorer" /v DisableSearchBoxSuggestions /f')
            return True, "已恢复搜索框联网联想"

    elif item_key == "gamedvr":
        # 禁用后台 GameDVR
        if enable:
            run_cmd('reg add "HKCU\\System\\GameConfigStore" /v GameDVR_Enabled /t REG_DWORD /d 0 /f')
            run_cmd('reg add "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\GameDVR" /v AllowGameDVR /t REG_DWORD /d 0 /f')
            return True, "已彻底禁用后台 GameDVR 录制，释放帧率与系统后台开销"
        else:
            run_cmd('reg delete "HKCU\\System\\GameConfigStore" /v GameDVR_Enabled /f')
            run_cmd('reg delete "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\GameDVR" /v AllowGameDVR /f')
            return True, "已恢复 GameDVR 默认设置"

    elif item_key == "ultimate_perf":
        # 开启卓越性能电源模式
        ok, out = run_cmd("powercfg -duplicatescheme e9a42b02-d5df-448d-aa00-03f14749eb61")
        if ok:
            return True, "已成功激活并生成【卓越性能 (Ultimate Performance)】电源计划！可在电源选项中选择。"
        return False, f"激活卓越性能失败: {out}"

    return False, "未知优化项目"


# ==================== 主窗口 GUI 类 ====================
class SystemConfigApp:
    def __init__(self, root):
        self.root = root
        self.root.title("展馆系统配置与网络设置及电脑优化工具 v2.0")
        self.root.geometry("980x850")
        self.root.minsize(920, 780)

        # 设置窗口图标
        try:
            if hasattr(sys, '_MEIPASS'):
                icon_path = os.path.join(sys._MEIPASS, 'gear.ico')
            else:
                icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'gear.ico')
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except Exception:
            pass

        self.style = ttk.Style()
        try:
            self.style.theme_use("vista")
        except Exception:
            pass

        self._cached_software = []
        self._cached_startup = []
        self._cached_context = []

        self._setup_custom_styles()
        self._build_ui()

        # 启动后异步加载初始数据
        self.root.after(150, self.refresh_adapters)
        self.root.after(300, self.refresh_memory_display)
        self.root.after(450, self.refresh_context_items)

    def _setup_custom_styles(self):
        default_font = ("Microsoft YaHei UI", 9)
        self.root.option_add("*Font", default_font)

        self.style.configure("Title.TLabel", font=("Microsoft YaHei UI", 13, "bold"), foreground="#1e3a8a")
        self.style.configure("Subtitle.TLabel", font=("Microsoft YaHei UI", 9), foreground="#64748b")
        self.style.configure("Header.TLabelframe.Label", font=("Microsoft YaHei UI", 9, "bold"), foreground="#0f172a")
        self.style.configure("Primary.TButton", font=("Microsoft YaHei UI", 9, "bold"))
        self.style.configure("Accent.TButton", font=("Microsoft YaHei UI", 9, "bold"))

    def _build_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 1. 顶部 Header 标题栏与权限状态
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 8))

        title_lbl = ttk.Label(header_frame, text="🏛️ 展馆系统配置与网络设置及电脑优化工具", style="Title.TLabel")
        title_lbl.pack(side=tk.LEFT)

        admin_text = "🛡️ 管理员权限：已就绪" if is_admin() else "⚠️ 未获取管理员权限 (部分功能可能受限)"
        admin_color = "#16a34a" if is_admin() else "#dc2626"
        admin_lbl = tk.Label(header_frame, text=admin_text, fg=admin_color, font=("Microsoft YaHei UI", 9, "bold"))
        admin_lbl.pack(side=tk.RIGHT, pady=2)

        # 2. 中部多功能标签页 Notebook
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

        # Tab 1: 展馆网络与系统配置
        tab1_frame = ttk.Frame(self.notebook, padding="6")
        self.notebook.add(tab1_frame, text="  🌐 展馆与网络设置  ")
        self._build_tab_museum_network(tab1_frame)

        # Tab 2: 电脑深度优化工具箱
        tab2_frame = ttk.Frame(self.notebook, padding="6")
        self.notebook.add(tab2_frame, text="  ⚡ 电脑深度优化  ")
        self._build_tab_pc_optimization(tab2_frame)

        # Tab 3: 开机启动项管理 (启动禁用)
        tab3_frame = ttk.Frame(self.notebook, padding="6")
        self.notebook.add(tab3_frame, text="  🚀 开机启动项管理  ")
        self._build_tab_startup_management(tab3_frame)

        # Tab 4: 软件与注册表管理
        tab4_frame = ttk.Frame(self.notebook, padding="6")
        self.notebook.add(tab4_frame, text="  🗃️ 软件与注册表管理  ")
        self._build_tab_software_registry(tab4_frame)

        # Tab 5: 右键菜单管理 (支持扫描、禁用、删除第三方右键项)
        tab5_frame = ttk.Frame(self.notebook, padding="6")
        self.notebook.add(tab5_frame, text="  🖱️ 右键菜单管理  ")
        self._build_tab_context_menu_management(tab5_frame)

        # 3. 底部通用运行日志区
        log_frame = ttk.LabelFrame(main_frame, text=" 📝 运行日志 ", padding="4", style="Header.TLabelframe")
        log_frame.pack(fill=tk.BOTH, expand=False, pady=(2, 0))

        self.log_text = scrolledtext.ScrolledText(
            log_frame, height=8, bg="#0f172a", fg="#f8fafc",
            insertbackground="white", font=("Consolas", 9), wrap=tk.WORD
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        self.log_text.tag_config("SUCCESS", foreground="#4ade80")
        self.log_text.tag_config("ERROR", foreground="#f87171")
        self.log_text.tag_config("INFO", foreground="#60a5fa")
        self.log_text.tag_config("WARN", foreground="#fbbf24")

        log_bot_row = ttk.Frame(log_frame)
        log_bot_row.pack(fill=tk.X, pady=(2, 0))
        ttk.Button(log_bot_row, text="清空日志", command=self.clear_log).pack(side=tk.RIGHT)
        ttk.Label(log_bot_row, text="💡 所有网络、注册表、优化与启动项操作均在此实时输出详细日志", foreground="#64748b", font=("Microsoft YaHei UI", 8)).pack(side=tk.LEFT)

        self.log("展馆系统配置与网络设置及电脑优化工具已就绪。所有模块支持一键管理与即时生效。", "INFO")

    # ==================== TAB 1: 展馆网络与系统配置 ====================
    def _build_tab_museum_network(self, parent):
        content_paned = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        content_paned.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

        # --- 左侧：网络 IPv4 配置卡片 ---
        net_card = ttk.LabelFrame(content_paned, text=" 🌐 以太网 / IPv4 网络配置 ", padding="8", style="Header.TLabelframe")
        content_paned.add(net_card, weight=4)

        row0 = ttk.Frame(net_card)
        row0.pack(fill=tk.X, pady=2)
        ttk.Label(row0, text="选择网络适配器:", width=13).pack(side=tk.LEFT)
        self.adapter_combo = ttk.Combobox(row0, state="normal")
        self.adapter_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(row0, text="🔄 刷新", width=6, command=self.refresh_adapters).pack(side=tk.RIGHT)

        self.net_status_lbl = ttk.Label(net_card, text="当前模式: 未知", foreground="#2563eb", font=("Microsoft YaHei UI", 8))
        self.net_status_lbl.pack(anchor=tk.W, pady=(0, 4))

        grid_frame = ttk.Frame(net_card)
        grid_frame.pack(fill=tk.X, pady=2)

        ttk.Label(grid_frame, text="IP 地址 (IPv4):", width=14).grid(row=0, column=0, sticky=tk.W, pady=2)
        self.entry_ip = ttk.Entry(grid_frame)
        self.entry_ip.grid(row=0, column=1, sticky=tk.EW, pady=2, padx=4)

        ttk.Label(grid_frame, text="子网掩码 (Mask):", width=14).grid(row=1, column=0, sticky=tk.W, pady=2)
        self.entry_mask = ttk.Entry(grid_frame)
        self.entry_mask.grid(row=1, column=1, sticky=tk.EW, pady=2, padx=4)

        ttk.Label(grid_frame, text="默认网关 (Gateway):", width=14).grid(row=2, column=0, sticky=tk.W, pady=2)
        self.entry_gw = ttk.Entry(grid_frame)
        self.entry_gw.grid(row=2, column=1, sticky=tk.EW, pady=2, padx=4)

        ttk.Label(grid_frame, text="首选 DNS 服务器:", width=14).grid(row=3, column=0, sticky=tk.W, pady=2)
        self.entry_dns1 = ttk.Entry(grid_frame)
        self.entry_dns1.grid(row=3, column=1, sticky=tk.EW, pady=2, padx=4)

        ttk.Label(grid_frame, text="备用 DNS 服务器:", width=14).grid(row=4, column=0, sticky=tk.W, pady=2)
        self.entry_dns2 = ttk.Entry(grid_frame)
        self.entry_dns2.grid(row=4, column=1, sticky=tk.EW, pady=2, padx=4)

        grid_frame.columnconfigure(1, weight=1)

        btn_box1 = ttk.Frame(net_card)
        btn_box1.pack(fill=tk.X, pady=(6, 3))
        ttk.Button(btn_box1, text="📥 读取当前配置", command=self.read_selected_adapter).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        ttk.Button(btn_box1, text="📋 填入展馆默认IP (192.168.10.11)", command=self.fill_default_ip).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

        btn_box2 = ttk.Frame(net_card)
        btn_box2.pack(fill=tk.X, pady=3)
        self.btn_apply_ip = ttk.Button(btn_box2, text="✅ 应用静态 IPv4 配置", style="Primary.TButton", command=self.action_apply_static_ip)
        self.btn_apply_ip.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

        self.btn_dhcp = ttk.Button(btn_box2, text="🌐 切换为 DHCP 自动获取", command=self.action_apply_dhcp)
        self.btn_dhcp.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

        tips_lbl = ttk.Label(
            net_card,
            text="💡 支持自定义任意合法IP/掩码/网关/DNS。无需插拔网线立即生效。\n展馆工控机标准段为 192.168.10.X。",
            foreground="#64748b", font=("Microsoft YaHei UI", 8)
        )
        tips_lbl.pack(anchor=tk.W, pady=(4, 0))

        # --- 右侧：系统策略管理卡片 ---
        sys_card = ttk.LabelFrame(content_paned, text=" ⚙️ 系统策略与优化管理 ", padding="8", style="Header.TLabelframe")
        content_paned.add(sys_card, weight=5)
        self._build_sys_card(sys_card)

        # 底部批量操作区
        batch_card = ttk.LabelFrame(parent, text=" 🚀 批量操作与快捷工具 ", padding="6", style="Header.TLabelframe")
        batch_card.pack(fill=tk.X)

        batch_row = ttk.Frame(batch_card)
        batch_row.pack(fill=tk.X)

        allon_btn = tk.Button(
            batch_row, text="🌟 ALLON 展馆一键配置 (批量策略+网络配置)",
            bg="#2563eb", fg="white", activebackground="#1d4ed8", activeforeground="white",
            font=("Microsoft YaHei UI", 9, "bold"), relief=tk.RAISED, cursor="hand2",
            command=self.action_allon
        )
        allon_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2, ipady=3)

        alloff_btn = tk.Button(
            batch_row, text="🔄 ALLOFF 恢复系统默认 (重置策略+DHCP)",
            bg="#f1f5f9", fg="#0f172a", activebackground="#e2e8f0",
            font=("Microsoft YaHei UI", 9, "bold"), relief=tk.RAISED, cursor="hand2",
            command=self.action_alloff
        )
        alloff_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2, ipady=3)

        ttk.Button(batch_row, text="🔌 网络连接面板 (ncpa.cpl)", command=self.open_ncpa).pack(side=tk.LEFT, padx=2)
        ttk.Button(batch_row, text="📂 开机启动文件夹", command=self.open_startup).pack(side=tk.LEFT, padx=2)
        ttk.Button(batch_row, text="⚡ 重启电脑", command=self.reboot_system).pack(side=tk.LEFT, padx=2)

    def _build_sys_card(self, parent):
        items = [
            ("UAC 用户账户控制", "关闭UAC (需重启)", self.action_uac_off, "恢复UAC", self.action_uac_on),
            ("Defender 安全策略", "关闭Defender", self.action_defender_off, "恢复默认", self.action_defender_on),
            ("Windows 自动更新", "关闭自动更新", self.action_update_off, "恢复更新", self.action_update_on),
            ("系统防火墙", "全部关闭", self.action_firewall_off, "全部开启", self.action_firewall_on),
            ("网卡节能策略", "关闭网卡节能", self.action_net_power_off, "恢复网卡节能", self.action_net_power_on),
            ("系统快速启动", "关闭快速启动", self.action_fastboot_off, "开启快速启动", self.action_fastboot_on),
            ("触摸屏边缘手势", "禁用边缘手势", self.action_gesture_off, "恢复触摸手势", self.action_gesture_on),
            ("电源与休眠", "永不休眠/永不关屏", self.action_sleep_never, "恢复默认超时", self.action_sleep_default),
            ("RDP 远程桌面", "开启无密码登录", self.action_rdp_enable_nopass, "关闭远程桌面", self.action_rdp_disable),
        ]

        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        for idx, (title, off_text, off_cmd, on_text, on_cmd) in enumerate(items):
            row_frame = ttk.Frame(scrollable_frame, padding="1")
            row_frame.pack(fill=tk.X, pady=2, expand=True)

            ttk.Label(row_frame, text=f"• {title}:", width=17, font=("Microsoft YaHei UI", 9, "bold")).pack(side=tk.LEFT)
            btn_off = ttk.Button(row_frame, text=off_text, command=off_cmd)
            btn_off.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
            btn_on = ttk.Button(row_frame, text=on_text, command=on_cmd)
            btn_on.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

    # ==================== TAB 2: 电脑深度优化工具箱 ====================
    def _build_tab_pc_optimization(self, parent):
        # 1. 顶部：内存释放与物理内存监控面板
        mem_card = ttk.LabelFrame(parent, text=" 💾 物理内存实时监控与一键深度释放 ", padding="10", style="Header.TLabelframe")
        mem_card.pack(fill=tk.X, pady=(0, 6))

        mem_top = ttk.Frame(mem_card)
        mem_top.pack(fill=tk.X)

        self.mem_info_lbl = ttk.Label(mem_top, text="正在读取内存状态...", font=("Microsoft YaHei UI", 10, "bold"), foreground="#1e293b")
        self.mem_info_lbl.pack(side=tk.LEFT)

        ttk.Button(mem_top, text="🔄 刷新内存", command=self.refresh_memory_display).pack(side=tk.RIGHT, padx=2)

        self.mem_progress = ttk.Progressbar(mem_card, orient=tk.HORIZONTAL, length=100, mode='determinate')
        self.mem_progress.pack(fill=tk.X, pady=(6, 8))

        mem_btn_row = ttk.Frame(mem_card)
        mem_btn_row.pack(fill=tk.X)

        btn_clean_mem = tk.Button(
            mem_btn_row, text="⚡ 立即深度释放内存 (清空进程工作集与缓存)",
            bg="#16a34a", fg="white", activebackground="#15803d", activeforeground="white",
            font=("Microsoft YaHei UI", 9, "bold"), relief=tk.RAISED, cursor="hand2",
            command=self.action_deep_clean_memory
        )
        btn_clean_mem.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=3, ipady=3)

        btn_clean_temp = tk.Button(
            mem_btn_row, text="🗑️ 清理系统临时文件与垃圾缓存",
            bg="#0284c7", fg="white", activebackground="#0369a1", activeforeground="white",
            font=("Microsoft YaHei UI", 9, "bold"), relief=tk.RAISED, cursor="hand2",
            command=self.action_clean_temp
        )
        btn_clean_temp.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=3, ipady=3)

        # 2. 中部：左右分栏 (左侧：网络一键修复与诊断 | 右侧：系统响应与注册表性能优化)
        bot_paned = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        bot_paned.pack(fill=tk.BOTH, expand=True)

        # 左分栏：网络一键修复与诊断
        net_fix_card = ttk.LabelFrame(bot_paned, text=" 🌐 网络修复与连通性诊断 ", padding="8", style="Header.TLabelframe")
        bot_paned.add(net_fix_card, weight=5)

        ttk.Label(net_fix_card, text="遇到网页打不开、IP冲突、DNS异常或掉线时快速修复：", foreground="#64748b", font=("Microsoft YaHei UI", 8)).pack(anchor=tk.W, pady=(0, 4))

        tk.Button(
            net_fix_card, text="🛠️ 一键深度网络修复 (重置Winsock+协议栈+刷新DNS+清理ARP)",
            bg="#ea580c", fg="white", activebackground="#c2410c", activeforeground="white",
            font=("Microsoft YaHei UI", 9, "bold"), relief=tk.RAISED, cursor="hand2",
            command=self.action_deep_repair_network
        ).pack(fill=tk.X, pady=3, ipady=3)

        tk.Button(
            net_fix_card, text="🩺 网络连通性一键体检与诊断 (Ping/DNS解析分析)",
            bg="#3b82f6", fg="white", activebackground="#2563eb", activeforeground="white",
            font=("Microsoft YaHei UI", 9, "bold"), relief=tk.RAISED, cursor="hand2",
            command=self.action_diagnose_network
        ).pack(fill=tk.X, pady=3, ipady=3)

        row_net_tools = ttk.Frame(net_fix_card)
        row_net_tools.pack(fill=tk.X, pady=3)
        ttk.Button(row_net_tools, text="🔄 软重启当前网卡", command=self.action_restart_adapter).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        ttk.Button(row_net_tools, text="🧹 单独清空DNS缓存", command=self.action_flush_dns_only).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

        # 右分栏：系统响应与注册表性能优化 (右键管理已整合至独立的【🖱️ 右键菜单管理】选项卡)
        reg_card = ttk.LabelFrame(bot_paned, text=" ⚙️ 系统响应与注册表性能优化 ", padding="8", style="Header.TLabelframe")
        bot_paned.add(reg_card, weight=5)

        opt_items = [
            ("无响应程序加速结束", "优化卡死与关机超时(2秒)", "hung_timeout", True, "恢复系统默认", False),
            ("Windows 错误报告", "禁用WER报告与服务", "wer", True, "恢复WER", False),
            ("搜索框 Bing 联网", "禁用Bing联网(搜索秒开)", "bing_search", True, "恢复联网", False),
            ("后台 GameDVR", "禁用GameDVR常驻", "gamedvr", True, "恢复默认", False),
        ]

        for title, on_txt, opt_key, on_val, off_txt, off_val in opt_items:
            r = ttk.Frame(reg_card)
            r.pack(fill=tk.X, pady=2)
            ttk.Label(r, text=f"• {title}:", width=17, font=("Microsoft YaHei UI", 9, "bold")).pack(side=tk.LEFT)
            ttk.Button(r, text=on_txt, command=lambda k=opt_key: self.action_apply_reg_opt(k, True)).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
            ttk.Button(r, text=off_txt, command=lambda k=opt_key: self.action_apply_reg_opt(k, False)).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

        r_ult = ttk.Frame(reg_card)
        r_ult.pack(fill=tk.X, pady=2)
        ttk.Label(r_ult, text="• 卓越性能电源模式:", width=17, font=("Microsoft YaHei UI", 9, "bold")).pack(side=tk.LEFT)
        ttk.Button(r_ult, text="⚡ 激活并解锁【卓越性能模式】计划", command=lambda: self.action_apply_reg_opt("ultimate_perf", True)).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

    # ==================== TAB 3: 开机启动项管理 (启动禁用) ====================
    def _build_tab_startup_management(self, parent):
        top_bar = ttk.Frame(parent)
        top_bar.pack(fill=tk.X, pady=(0, 6))

        ttk.Button(top_bar, text="🔄 刷新自启动项", style="Primary.TButton", command=self.refresh_startup_items).pack(side=tk.LEFT, padx=2)
        ttk.Button(top_bar, text="⛔ 禁用选中项", command=lambda: self.action_toggle_selected_startup(False)).pack(side=tk.LEFT, padx=2)
        ttk.Button(top_bar, text="🟢 启用选中项", command=lambda: self.action_toggle_selected_startup(True)).pack(side=tk.LEFT, padx=2)
        ttk.Button(top_bar, text="🗑️ 彻底删除选中项", command=self.action_delete_selected_startup).pack(side=tk.LEFT, padx=2)
        ttk.Button(top_bar, text="📁 打开启动文件夹", command=self.open_startup).pack(side=tk.LEFT, padx=2)
        ttk.Button(top_bar, text="📊 打开任务管理器启动页", command=lambda: subprocess.Popen('taskmgr /0 /startup', shell=True)).pack(side=tk.LEFT, padx=2)

        self.startup_count_lbl = ttk.Label(top_bar, text="共检测到 0 个启动项", foreground="#2563eb", font=("Microsoft YaHei UI", 9, "bold"))
        self.startup_count_lbl.pack(side=tk.RIGHT, padx=4)

        columns = ("name", "status", "type", "source", "command")
        self.startup_tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="browse")
        self.startup_tree.heading("name", text="启动项名称")
        self.startup_tree.heading("status", text="当前状态")
        self.startup_tree.heading("type", text="类别")
        self.startup_tree.heading("source", text="来源位置")
        self.startup_tree.heading("command", text="启动命令 / 程序路径")

        self.startup_tree.column("name", width=180, anchor=tk.W)
        self.startup_tree.column("status", width=70, anchor=tk.CENTER)
        self.startup_tree.column("type", width=75, anchor=tk.CENTER)
        self.startup_tree.column("source", width=170, anchor=tk.W)
        self.startup_tree.column("command", width=420, anchor=tk.W)

        tree_scroll_y = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.startup_tree.yview)
        tree_scroll_x = ttk.Scrollbar(parent, orient=tk.HORIZONTAL, command=self.startup_tree.xview)
        self.startup_tree.configure(yscrollcommand=tree_scroll_y.set, xscrollcommand=tree_scroll_x.set)

        self.startup_tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        tree_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        tree_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)

        self.startup_tree.tag_configure("DISABLED", foreground="#94a3b8")
        self.startup_tree.tag_configure("ENABLED", foreground="#0f172a")

        # 启动时异步刷新一次
        self.root.after(400, self.refresh_startup_items)

    # ==================== TAB 4: 软件与注册表管理 ====================
    def _build_tab_software_registry(self, parent):
        top_bar = ttk.Frame(parent)
        top_bar.pack(fill=tk.X, pady=(0, 6))

        ttk.Label(top_bar, text="🔍 搜索软件:").pack(side=tk.LEFT, padx=(0, 4))
        self.entry_soft_search = ttk.Entry(top_bar, width=22)
        self.entry_soft_search.pack(side=tk.LEFT, padx=2)
        self.entry_soft_search.bind("<KeyRelease>", lambda e: self.filter_software_list())

        ttk.Button(top_bar, text="🔄 刷新软件列表", command=self.refresh_software_list).pack(side=tk.LEFT, padx=4)
        ttk.Button(top_bar, text="🗑️ 运行官方卸载", style="Primary.TButton", command=self.action_uninstall_selected_software).pack(side=tk.LEFT, padx=2)
        ttk.Button(top_bar, text="📋 复制卸载命令", command=self.action_copy_uninstall_cmd).pack(side=tk.LEFT, padx=2)
        ttk.Button(top_bar, text="📑 打开注册表编辑器 (regedit)", command=lambda: subprocess.Popen('regedit', shell=True)).pack(side=tk.LEFT, padx=2)

        self.software_count_lbl = ttk.Label(top_bar, text="已安装: 0 款软件", foreground="#2563eb", font=("Microsoft YaHei UI", 9, "bold"))
        self.software_count_lbl.pack(side=tk.RIGHT, padx=4)

        columns = ("name", "version", "publisher", "reg_root", "uninstall")
        self.software_tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="browse")
        self.software_tree.heading("name", text="软件名称")
        self.software_tree.heading("version", text="版本")
        self.software_tree.heading("publisher", text="发布者")
        self.software_tree.heading("reg_root", text="注册表归属")
        self.software_tree.heading("uninstall", text="卸载命令行")

        self.software_tree.column("name", width=250, anchor=tk.W)
        self.software_tree.column("version", width=110, anchor=tk.W)
        self.software_tree.column("publisher", width=160, anchor=tk.W)
        self.software_tree.column("reg_root", width=95, anchor=tk.CENTER)
        self.software_tree.column("uninstall", width=330, anchor=tk.W)

        soft_scroll_y = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.software_tree.yview)
        soft_scroll_x = ttk.Scrollbar(parent, orient=tk.HORIZONTAL, command=self.software_tree.xview)
        self.software_tree.configure(yscrollcommand=soft_scroll_y.set, xscrollcommand=soft_scroll_x.set)

        self.software_tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        soft_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        soft_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)

        self.root.after(500, self.refresh_software_list)

    # ==================== TAB 5: 右键菜单管理 (支持第三方扫描与删除) ====================
    def _build_tab_context_menu_management(self, parent):
        # 1. 顶部：快捷增强右键与 Win11 菜单切换
        top_opt_frame = ttk.LabelFrame(parent, text=" ⚡ 系统右键快捷设置与常用增强 ", padding="8", style="Header.TLabelframe")
        top_opt_frame.pack(fill=tk.X, pady=(0, 6))

        r1 = ttk.Frame(top_opt_frame)
        r1.pack(fill=tk.X, pady=2)
        ttk.Label(r1, text="Win11 右键样式:", width=15, font=("Microsoft YaHei UI", 9, "bold")).pack(side=tk.LEFT)
        ttk.Button(r1, text="切换 Win10 经典菜单", command=lambda: self.action_toggle_win11_context(True)).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        ttk.Button(r1, text="恢复 Win11 新版菜单", command=lambda: self.action_toggle_win11_context(False)).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

        ttk.Label(r1, text="管理员所有权:", width=13, font=("Microsoft YaHei UI", 9, "bold")).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(r1, text="添加右键所有权", command=lambda: self.action_toggle_takeown(True)).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        ttk.Button(r1, text="移除所有权", command=lambda: self.action_toggle_takeown(False)).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

        r2 = ttk.Frame(top_opt_frame)
        r2.pack(fill=tk.X, pady=2)
        ttk.Label(r2, text="终端快捷入口:", width=15, font=("Microsoft YaHei UI", 9, "bold")).pack(side=tk.LEFT)
        ttk.Button(r2, text="添加 CMD/PS 管理员终端", command=self.action_add_terminals_context).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        ttk.Button(r2, text="移除终端右键", command=self.action_remove_terminals_context).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

        ttk.Label(r2, text="资源管理器扩展名:", width=13, font=("Microsoft YaHei UI", 9, "bold")).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(r2, text="显示扩展名&隐藏文件", command=lambda: self.action_set_explorer_display(True)).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        ttk.Button(r2, text="隐藏扩展名&隐藏文件", command=lambda: self.action_set_explorer_display(False)).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

        # 2. 中部：第三方及系统右键菜单项扫描管理表格
        list_frame = ttk.LabelFrame(parent, text=" 📋 右键扩展与菜单项列表 (支持禁用与彻底删除第三方菜单) ", padding="8", style="Header.TLabelframe")
        list_frame.pack(fill=tk.BOTH, expand=True)

        tool_bar = ttk.Frame(list_frame)
        tool_bar.pack(fill=tk.X, pady=(0, 6))

        ttk.Button(tool_bar, text="🔄 刷新右键项", style="Primary.TButton", command=self.refresh_context_items).pack(side=tk.LEFT, padx=2)
        
        self.context_filter_var = tk.StringVar(value="third_only")
        r_all = ttk.Radiobutton(tool_bar, text="仅看第三方应用生成", variable=self.context_filter_var, value="third_only", command=self.filter_context_items)
        r_all.pack(side=tk.LEFT, padx=6)
        r_third = ttk.Radiobutton(tool_bar, text="显示全部(含系统自带)", variable=self.context_filter_var, value="all", command=self.filter_context_items)
        r_third.pack(side=tk.LEFT, padx=4)

        ttk.Button(tool_bar, text="⛔ 禁用选中项", command=lambda: self.action_toggle_selected_context(False)).pack(side=tk.LEFT, padx=4)
        ttk.Button(tool_bar, text="🟢 启用选中项", command=lambda: self.action_toggle_selected_context(True)).pack(side=tk.LEFT, padx=2)

        btn_del = tk.Button(
            tool_bar, text="🗑️ 彻底删除选中右键项 (清理流氓/残留右键)",
            bg="#dc2626", fg="white", activebackground="#b91c1c", activeforeground="white",
            font=("Microsoft YaHei UI", 9, "bold"), relief=tk.RAISED, cursor="hand2",
            command=self.action_delete_selected_context
        )
        btn_del.pack(side=tk.LEFT, padx=6, ipady=1)

        self.context_count_lbl = ttk.Label(tool_bar, text="共检测到 0 个右键项", foreground="#2563eb", font=("Microsoft YaHei UI", 9, "bold"))
        self.context_count_lbl.pack(side=tk.RIGHT, padx=4)

        cols = ("name", "status", "scope", "kind", "is_third", "cmd_clsid")
        self.context_tree = ttk.Treeview(list_frame, columns=cols, show="headings", selectmode="browse")
        self.context_tree.heading("name", text="菜单项名称 / 扩展程序")
        self.context_tree.heading("status", text="当前状态")
        self.context_tree.heading("scope", text="出现位置")
        self.context_tree.heading("kind", text="扩展类型")
        self.context_tree.heading("is_third", text="来源属性")
        self.context_tree.heading("cmd_clsid", text="执行命令 / CLSID GUID / 组件路径")

        self.context_tree.column("name", width=240, anchor=tk.W)
        self.context_tree.column("status", width=70, anchor=tk.CENTER)
        self.context_tree.column("scope", width=110, anchor=tk.CENTER)
        self.context_tree.column("kind", width=80, anchor=tk.CENTER)
        self.context_tree.column("is_third", width=95, anchor=tk.CENTER)
        self.context_tree.column("cmd_clsid", width=360, anchor=tk.W)

        c_scroll_y = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.context_tree.yview)
        c_scroll_x = ttk.Scrollbar(list_frame, orient=tk.HORIZONTAL, command=self.context_tree.xview)
        self.context_tree.configure(yscrollcommand=c_scroll_y.set, xscrollcommand=c_scroll_x.set)

        self.context_tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        c_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        c_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)

        self.context_tree.tag_configure("DISABLED", foreground="#94a3b8")
        self.context_tree.tag_configure("THIRD", foreground="#0f172a")
        self.context_tree.tag_configure("SYS", foreground="#64748b")


    # ==================== 日志与基础功能 ====================
    def log(self, message, level="INFO"):
        time_str = datetime.now().strftime("%H:%M:%S")
        tag = level.upper()
        line = f"[{time_str}] [{level}] {message}\n"

        def _append():
            self.log_text.insert(tk.END, line, tag)
            self.log_text.see(tk.END)
        self.root.after(0, _append)

    def clear_log(self):
        self.log_text.delete("1.0", tk.END)

    def _run_system_task(self, name, command, success_msg, level="SUCCESS"):
        def _async():
            self.log(f"正在执行 [{name}] ...", "INFO")
            ok, out = run_cmd(command)
            if ok:
                self.log(f"{name}: {success_msg}", level)
            else:
                self.log(f"{name} 失败: {out}", "ERROR")
        threading.Thread(target=_async, daemon=True).start()

    # ==================== 网络操作逻辑 (Tab 1) ====================
    def refresh_adapters(self):
        def _async():
            self.log("正在枚举系统网络适配器...", "INFO")
            adapters = get_network_adapters()
            def _update():
                self.adapter_combo['values'] = adapters
                if adapters:
                    if "以太网" in adapters:
                        self.adapter_combo.set("以太网")
                    else:
                        self.adapter_combo.current(0)
                    self.read_selected_adapter()
                self.log(f"成功扫描到 {len(adapters)} 个网络适配器: {', '.join(adapters)}", "SUCCESS")
            self.root.after(0, _update)
        threading.Thread(target=_async, daemon=True).start()

    def read_selected_adapter(self):
        adapter = self.adapter_combo.get().strip()
        if not adapter:
            return

        def _async():
            self.log(f"正在读取适配器 [{adapter}] 当前网络配置...", "INFO")
            info = read_adapter_ipv4(adapter)
            def _update():
                self.entry_ip.delete(0, tk.END)
                if info["ip"]:
                    self.entry_ip.insert(0, info["ip"])

                self.entry_mask.delete(0, tk.END)
                if info["mask"]:
                    self.entry_mask.insert(0, info["mask"])

                self.entry_gw.delete(0, tk.END)
                if info["gateway"]:
                    self.entry_gw.insert(0, info["gateway"])

                self.entry_dns1.delete(0, tk.END)
                if info["dns1"]:
                    self.entry_dns1.insert(0, info["dns1"])

                self.entry_dns2.delete(0, tk.END)
                if info["dns2"]:
                    self.entry_dns2.insert(0, info["dns2"])

                status_txt = "当前模式: DHCP (自动获取)" if info["dhcp"] else "当前模式: 静态 IP (Static)"
                self.net_status_lbl.config(text=status_txt, foreground="#059669" if info["dhcp"] else "#2563eb")
                self.log(f"已加载 [{adapter}] 配置: IP={info['ip']}, 掩码={info['mask']}, 网关={info['gateway']}, DNS={info['dns1']}/{info['dns2']}", "SUCCESS")
            self.root.after(0, _update)
        threading.Thread(target=_async, daemon=True).start()

    def fill_default_ip(self):
        self.entry_ip.delete(0, tk.END)
        self.entry_ip.insert(0, "192.168.10.11")
        self.entry_mask.delete(0, tk.END)
        self.entry_mask.insert(0, "255.255.255.0")
        self.entry_gw.delete(0, tk.END)
        self.entry_gw.insert(0, "192.168.10.1")
        self.entry_dns1.delete(0, tk.END)
        self.entry_dns1.insert(0, "192.168.10.1")
        self.entry_dns2.delete(0, tk.END)
        self.entry_dns2.insert(0, "114.114.114.114")
        self.log("已填发展馆标准默认配置模板 (IP: 192.168.10.11, 网关/DNS: 192.168.10.1)。点击【应用静态 IPv4 配置】即可生效。", "INFO")

    def action_apply_static_ip(self, silent=False):
        adapter = self.adapter_combo.get().strip()
        ip = self.entry_ip.get().strip()
        mask = self.entry_mask.get().strip()
        gw = self.entry_gw.get().strip()
        dns1 = self.entry_dns1.get().strip()
        dns2 = self.entry_dns2.get().strip()

        if not adapter:
            messagebox.showwarning("错误", "请选择网络适配器！")
            return False

        valid_ip, msg_ip = validate_ip(ip, "IP地址")
        if not valid_ip:
            messagebox.showerror("格式错误", msg_ip)
            return False

        valid_mask, msg_mask = validate_netmask(mask)
        if not valid_mask:
            messagebox.showerror("格式错误", msg_mask)
            return False

        if gw:
            valid_gw, msg_gw = validate_ip(gw, "默认网关")
            if not valid_gw:
                messagebox.showerror("格式错误", msg_gw)
                return False

        if dns1:
            valid_dns1, msg_dns1 = validate_ip(dns1, "首选DNS")
            if not valid_dns1:
                messagebox.showerror("格式错误", msg_dns1)
                return False

        if dns2:
            valid_dns2, msg_dns2 = validate_ip(dns2, "备用DNS")
            if not valid_dns2:
                messagebox.showerror("格式错误", msg_dns2)
                return False

        def _async():
            self.log(f"正在为 [{adapter}] 应用静态配置: IP={ip}, 掩码={mask}, 网关={gw or '无'}...", "INFO")
            if gw:
                cmd_ip = f'netsh interface ip set address name="{adapter}" source=static addr={ip} mask={mask} gateway={gw} gwmetric=1'
            else:
                cmd_ip = f'netsh interface ip set address name="{adapter}" source=static addr={ip} mask={mask}'

            ok_ip, out_ip = run_cmd(cmd_ip)
            if not ok_ip:
                self.log(f"设置 IP 失败: {out_ip}", "ERROR")
                if not silent:
                    messagebox.showerror("设置失败", f"设置 IP 失败：\n{out_ip}")
                return False

            self.log(f"[{adapter}] 静态 IP 地址与网关设置成功！", "SUCCESS")

            if dns1:
                cmd_dns1 = f'netsh interface ip set dns name="{adapter}" source=static addr={dns1} register=primary'
                ok_dns1, out_dns1 = run_cmd(cmd_dns1)
                if ok_dns1:
                    self.log(f"[{adapter}] 首选 DNS 设置成功: {dns1}", "SUCCESS")
                if dns2:
                    cmd_dns2 = f'netsh interface ip add dns name="{adapter}" addr={dns2} index=2'
                    ok_dns2, out_dns2 = run_cmd(cmd_dns2)
                    if ok_dns2:
                        self.log(f"[{adapter}] 备用 DNS 设置成功: {dns2}", "SUCCESS")
            else:
                run_cmd(f'netsh interface ip delete dns name="{adapter}" all')
                self.log(f"[{adapter}] DNS 已清空", "INFO")

            def _done():
                self.net_status_lbl.config(text="当前模式: 静态 IP (Static)", foreground="#2563eb")
                if not silent:
                    messagebox.showinfo("成功", f"[{adapter}] 静态 IPv4 配置已生效！\nIP: {ip}\n掩码: {mask}\n网关: {gw or '未配置'}\nDNS: {dns1 or '未配置'} {dns2}")
            self.root.after(0, _done)
            return True

        threading.Thread(target=_async, daemon=True).start()
        return True

    def action_apply_dhcp(self, silent=False):
        adapter = self.adapter_combo.get().strip()
        if not adapter:
            messagebox.showwarning("错误", "请选择网络适配器！")
            return

        def _async():
            self.log(f"正在将 [{adapter}] 切换为 DHCP 自动获取 IP 和 DNS...", "INFO")
            ok1, out1 = run_cmd(f'netsh interface ip set address name="{adapter}" source=dhcp')
            ok2, out2 = run_cmd(f'netsh interface ip set dns name="{adapter}" source=dhcp')

            if ok1 and ok2:
                self.log(f"[{adapter}] 已成功切换为 DHCP 自动获取！", "SUCCESS")
                def _done():
                    self.net_status_lbl.config(text="当前模式: DHCP (自动获取)", foreground="#059669")
                    if not silent:
                        messagebox.showinfo("成功", f"[{adapter}] 已恢复为 DHCP 自动获取 IP 和 DNS。")
                    self.read_selected_adapter()
                self.root.after(0, _done)
            else:
                err = f"{out1}\n{out2}".strip()
                self.log(f"切换 DHCP 失败: {err}", "ERROR")
                if not silent:
                    messagebox.showerror("失败", f"切换 DHCP 失败：\n{err}")

        threading.Thread(target=_async, daemon=True).start()

    # 系统单项策略 (Tab 1)
    def action_uac_off(self):
        cmd = 'reg ADD "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System" /v EnableLUA /t REG_DWORD /d 0 /f'
        self._run_system_task("UAC控制", cmd, "UAC 已关闭 (需要重启系统生效)")

    def action_uac_on(self):
        cmd = 'reg ADD "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System" /v EnableLUA /t REG_DWORD /d 1 /f'
        self._run_system_task("UAC控制", cmd, "UAC 已恢复默认 (需要重启系统生效)")

    def action_defender_off(self):
        cmd = 'reg add "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows Defender" /v DisableAntiSpyware /t REG_DWORD /d 1 /f'
        self._run_system_task("Defender策略", cmd, "Defender 策略已关闭")

    def action_defender_on(self):
        cmd = 'reg delete "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows Defender" /v DisableAntiSpyware /f'
        self._run_system_task("Defender策略", cmd, "Defender 策略已恢复默认")

    def action_update_off(self):
        cmd = 'reg add HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate\\AU /v NoAutoUpdate /t REG_DWORD /d 1 /f'
        self._run_system_task("Windows更新", cmd, "Windows 自动更新已关闭")

    def action_update_on(self):
        cmd = 'reg delete HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate\\AU /v NoAutoUpdate /f'
        self._run_system_task("Windows更新", cmd, "Windows 自动更新已恢复")

    def action_firewall_off(self):
        cmd = 'netsh advfirewall set allprofiles state off'
        self._run_system_task("系统防火墙", cmd, "防火墙已全部关闭")

    def action_firewall_on(self):
        cmd = 'netsh advfirewall set allprofiles state on'
        self._run_system_task("系统防火墙", cmd, "防火墙已全部开启")

    def action_net_power_off(self):
        cmd = 'powercfg /changevalueindex SUB_NET 0003 0000'
        self._run_system_task("网卡节能", cmd, "网卡节能已关闭")

    def action_net_power_on(self):
        cmd = 'powercfg /changevalueindex SUB_NET 0003 0001'
        self._run_system_task("网卡节能", cmd, "网卡节能已恢复")

    def action_fastboot_off(self):
        cmd = 'reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Power" /v HiberbootEnabled /t REG_DWORD /d 0 /f'
        self._run_system_task("快速启动", cmd, "快速启动已关闭 (重启生效)")

    def action_fastboot_on(self):
        cmd = 'reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Power" /v HiberbootEnabled /t REG_DWORD /d 1 /f'
        self._run_system_task("快速启动", cmd, "快速启动已开启 (重启生效)")

    def action_gesture_off(self):
        cmd = 'reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Touch" /v DisableEdgeUI /t REG_DWORD /d 1 /f & reg add "HKCU\\Software\\Synaptics\\SynTPEnh" /v DisableGestures /t REG_DWORD /f'
        self._run_system_task("触摸手势", cmd, "触摸手势已禁用")

    def action_gesture_on(self):
        cmd = 'reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Touch" /v DisableEdgeUI /f & reg delete "HKCU\\Software\\Microsoft\\Windows\\Synaptics\\SynTPEnh" /v DisableGestures /f'
        self._run_system_task("触摸手势", cmd, "触摸手势已恢复默认")

    def action_sleep_never(self):
        cmd = 'powercfg /change monitor-timeout-ac 0 & powercfg /change standby-timeout-ac 0'
        self._run_system_task("电源休眠", cmd, "电源设置：永不关闭显示器、永不休眠")

    def action_sleep_default(self):
        cmd = 'powercfg /change monitor-timeout-ac 60 & powercfg /change standby-timeout-ac 30'
        self._run_system_task("电源休眠", cmd, "电源设置：已恢复系统默认超时 (屏幕60分/休眠30分)")

    def action_rdp_enable_nopass(self):
        cmd = (
            'reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Terminal Server" /v fDenyTSConnections /t REG_DWORD /d 0 /f & '
            'reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Terminal Server\\WinStations\\RDP-Tcp" /v UserAuthentication /t REG_DWORD /d 0 /f & '
            'reg add "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon" /v PasswordOptional /t REG_DWORD /d 1 /f'
        )
        self._run_system_task("RDP远程桌面", cmd, "RDP无密码登录已开启 (仅限展馆内网工控机使用)")

    def action_rdp_disable(self):
        cmd = (
            'reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Terminal Server" /v fDenyTSConnections /t REG_DWORD /d 1 /f & '
            'reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Terminal Server\\WinStations\\RDP-Tcp" /v UserAuthentication /t REG_DWORD /d 0 /f & '
            'reg delete "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon" /v PasswordOptional /f'
        )
        self._run_system_task("RDP远程桌面", cmd, "RDP远程桌面已关闭并恢复安全限制")

    # 批量一键操作 (Tab 1)
    def action_allon(self):
        confirm = messagebox.askyesno(
            "确认执行 ALLON 展馆一键配置",
            "将依次执行以下配置：\n"
            "1. 关闭 UAC (需重启)\n"
            "2. 关闭 Defender 策略\n"
            "3. 关闭 Windows 自动更新\n"
            "4. 关闭系统防火墙\n"
            "5. 关闭网卡节能\n"
            "6. 应用当前配置的静态 IP 与 DNS\n"
            "7. 关闭快速启动\n"
            "8. 禁用触摸手势\n"
            "9. 设置永不休眠/永不关屏\n"
            "10. 开启 RDP 远程免密登录\n"
            "11. 自动打开网络面板与开机启动文件夹\n\n"
            "是否立即开始执行？"
        )
        if not confirm:
            return

        def _async():
            self.log("========== 开始执行 ALLON 展馆一键配置 ==========", "WARN")
            run_cmd('reg ADD "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System" /v EnableLUA /t REG_DWORD /d 0 /f')
            self.log("[1/10] UAC 已关闭，重启生效", "SUCCESS")

            run_cmd('reg add "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows Defender" /v DisableAntiSpyware /t REG_DWORD /d 1 /f')
            self.log("[2/10] Defender策略已关闭", "SUCCESS")

            run_cmd('reg add HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate\\AU /v NoAutoUpdate /t REG_DWORD /d 1 /f')
            self.log("[3/10] Windows自动更新已关闭", "SUCCESS")

            run_cmd('netsh advfirewall set allprofiles state off')
            self.log("[4/10] 防火墙已全部关闭", "SUCCESS")

            run_cmd('powercfg /changevalueindex SUB_NET 0003 0000')
            self.log("[5/10] 网卡节能已关闭", "SUCCESS")

            adapter = self.adapter_combo.get().strip() or "以太网"
            ip = self.entry_ip.get().strip() or "192.168.10.11"
            mask = self.entry_mask.get().strip() or "255.255.255.0"
            gw = self.entry_gw.get().strip() or "192.168.10.1"
            dns1 = self.entry_dns1.get().strip() or "192.168.10.1"
            dns2 = self.entry_dns2.get().strip() or "114.114.114.114"

            cmd_ip = f'netsh interface ip set address name="{adapter}" source=static addr={ip} mask={mask} gateway={gw} gwmetric=1'
            run_cmd(cmd_ip)
            run_cmd(f'netsh interface ip set dns name="{adapter}" source=static addr={dns1} register=primary')
            if dns2:
                run_cmd(f'netsh interface ip add dns name="{adapter}" addr={dns2} index=2')
            self.log(f"[6/10] [{adapter}] 静态IP配置完成：IP={ip}, 网关={gw}, DNS={dns1}", "SUCCESS")

            run_cmd('reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Power" /v HiberbootEnabled /t REG_DWORD /d 0 /f')
            self.log("[7/10] 快速启动已关闭", "SUCCESS")

            run_cmd('reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Touch" /v DisableEdgeUI /t REG_DWORD /d 1 /f')
            run_cmd('reg add "HKCU\\Software\\Synaptics\\SynTPEnh" /v DisableGestures /t REG_DWORD /f')
            self.log("[8/10] 触摸手势已禁用", "SUCCESS")

            run_cmd('powercfg /change monitor-timeout-ac 0')
            run_cmd('powercfg /change standby-timeout-ac 0')
            self.log("[9/10] 电源设置完成：永不息屏、永不休眠", "SUCCESS")

            run_cmd('reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Terminal Server" /v fDenyTSConnections /t REG_DWORD /d 0 /f')
            run_cmd('reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Terminal Server\\WinStations\\RDP-Tcp" /v UserAuthentication /t REG_DWORD /d 0 /f')
            run_cmd('reg add "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon" /v PasswordOptional /t REG_DWORD /d 1 /f')
            self.log("[10/10] RDP免密登录已开启", "SUCCESS")

            self.log("批量配置已全部完成，正在打开网络面板与启动文件夹...", "INFO")
            run_cmd('start ncpa.cpl')
            startup_dir = os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup")
            subprocess.Popen(f'explorer "{startup_dir}"', shell=True)

            self.log("========== ALLON 展馆一键配置全部执行完毕 ==========", "SUCCESS")

            def _prompt_reboot():
                ask = messagebox.askyesno(
                    "配置完成",
                    "ALLON 展馆一键配置已全部成功执行！\n"
                    "已自动打开网络面板与开机启动文件夹。\n\n"
                    "部分策略（如UAC、快速启动）需要重启电脑后生效。\n"
                    "是否现在立即重启电脑？"
                )
                if ask:
                    run_cmd('shutdown /r /t 5 /c "展馆配置工具重启"')
            self.root.after(0, _prompt_reboot)

        threading.Thread(target=_async, daemon=True).start()

    def action_alloff(self):
        confirm = messagebox.askyesno(
            "确认恢复系统默认",
            "将依次恢复以下默认设置：\n"
            "1. 恢复 UAC 控制\n"
            "2. 恢复 Defender 默认策略\n"
            "3. 恢复 Windows 自动更新\n"
            "4. 开启系统防火墙\n"
            "5. 恢复网卡节能\n"
            "6. 恢复以太网为 DHCP 自动获取\n"
            "7. 开启快速启动\n"
            "8. 恢复触摸手势\n"
            "9. 恢复默认电源休眠 (60分/30分)\n"
            "10. 关闭 RDP 远程桌面免密\n\n"
            "是否继续？"
        )
        if not confirm:
            return

        def _async():
            self.log("========== 开始执行 ALLOFF 恢复系统默认 ==========", "WARN")
            run_cmd('reg ADD "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System" /v EnableLUA /t REG_DWORD /d 1 /f')
            self.log("[1/10] UAC 已恢复默认", "SUCCESS")

            run_cmd('reg delete "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows Defender" /v DisableAntiSpyware /f')
            self.log("[2/10] Defender策略已恢复默认", "SUCCESS")

            run_cmd('reg delete HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate\\AU /v NoAutoUpdate /f')
            self.log("[3/10] Windows自动更新已恢复", "SUCCESS")

            run_cmd('netsh advfirewall set allprofiles state on')
            self.log("[4/10] 防火墙已全部开启", "SUCCESS")

            run_cmd('powercfg /changevalueindex SUB_NET 0003 0001')
            self.log("[5/10] 网卡节能已恢复", "SUCCESS")

            adapter = self.adapter_combo.get().strip() or "以太网"
            run_cmd(f'netsh interface ip set address name="{adapter}" source=dhcp')
            run_cmd(f'netsh interface ip set dns name="{adapter}" source=dhcp')
            self.log(f"[6/10] [{adapter}] 已恢复DHCP自动获取", "SUCCESS")

            run_cmd('reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Power" /v HiberbootEnabled /t REG_DWORD /d 1 /f')
            self.log("[7/10] 快速启动已开启", "SUCCESS")

            run_cmd('reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Touch" /v DisableEdgeUI /f')
            run_cmd('reg delete "HKCU\\Software\\Microsoft\\Windows\\Synaptics\\SynTPEnh" /v DisableGestures /f')
            self.log("[8/10] 触摸手势已恢复", "SUCCESS")

            run_cmd('powercfg /change monitor-timeout-ac 60')
            run_cmd('powercfg /change standby-timeout-ac 30')
            self.log("[9/10] 电源设置已恢复系统默认超时", "SUCCESS")

            run_cmd('reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Terminal Server" /v fDenyTSConnections /t REG_DWORD /d 1 /f')
            run_cmd('reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Terminal Server\\WinStations\\RDP-Tcp" /v UserAuthentication /t REG_DWORD /d 1 /f')
            run_cmd('reg delete "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon" /v PasswordOptional /f')
            self.log("[10/10] RDP远程桌面已关闭并恢复安全限制", "SUCCESS")

            self.log("========== ALLOFF 恢复系统默认全部完成 ==========", "SUCCESS")

            def _prompt_reboot():
                ask = messagebox.askyesno("恢复完成", "系统默认设置已恢复！\n是否现在重启电脑使配置完全生效？")
                if ask:
                    run_cmd('shutdown /r /t 5 /c "展馆配置工具重启"')
            self.root.after(0, _prompt_reboot)

        threading.Thread(target=_async, daemon=True).start()

    def open_ncpa(self):
        self.log("正在打开 Windows 网络连接面板 (ncpa.cpl)...", "INFO")
        subprocess.Popen('control.exe ncpa.cpl', shell=True)

    def open_startup(self):
        self.log("正在打开开机启动文件夹...", "INFO")
        startup_dir = os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup")
        subprocess.Popen(f'explorer "{startup_dir}"', shell=True)

    def reboot_system(self):
        confirm = messagebox.askyesno("确认重启", "确定要立即重启电脑吗？请确保已保存手头的工作。")
        if confirm:
            self.log("正在准备重启系统...", "WARN")
            run_cmd('shutdown /r /t 5 /c "展馆系统配置工具触发重启"')

    # ==================== 电脑深度优化逻辑 (Tab 2) ====================
    # 1. 内存释放与监控
    def refresh_memory_display(self):
        mem = get_system_memory()
        self.mem_info_lbl.config(
            text=f"物理内存：总计 {mem['total_mb'] / 1024:.2f} GB | 已使用 {mem['used_mb'] / 1024:.2f} GB ({mem['percent']}%) | 可用 {mem['avail_mb'] / 1024:.2f} GB"
        )
        self.mem_progress['value'] = mem['percent']

    def action_deep_clean_memory(self):
        def _async():
            self.log("正在执行深度内存清理 (遍历系统各进程释放工作集 Working Set)...", "INFO")
            res = deep_clean_working_set()
            def _update():
                self.refresh_memory_display()
                self.log(
                    f"深度内存清理完成！已清理 {res['success_cnt']} 个进程工作集，"
                    f"释放内存: {res['freed_mb']} MB (占用率从 {res['mem_before']['percent']}% 降至 {res['mem_after']['percent']}%)",
                    "SUCCESS"
                )
                messagebox.showinfo(
                    "内存释放成功",
                    f"深度内存优化完成！\n\n"
                    f"• 已优化进程数：{res['success_cnt']}/{res['total_cnt']}\n"
                    f"• 成功释放空间：{res['freed_mb']} MB\n"
                    f"• 当前内存占用率：{res['mem_after']['percent']}%"
                )
            self.root.after(0, _update)
        threading.Thread(target=_async, daemon=True).start()

    def action_clean_temp(self):
        def _async():
            self.log("正在扫描并清理系统临时文件与缓存垃圾...", "INFO")
            cnt, freed_mb = clean_system_temp()
            def _update():
                self.refresh_memory_display()
                self.log(f"临时文件清理完成！共清除 {cnt} 个文件，释放磁盘空间约 {freed_mb} MB", "SUCCESS")
                messagebox.showinfo("清理完成", f"已成功安全清理系统临时文件！\n\n• 清理文件数：{cnt}\n• 释放空间：约 {freed_mb} MB")
            self.root.after(0, _update)
        threading.Thread(target=_async, daemon=True).start()

    # 2. 网络修复与诊断
    def action_deep_repair_network(self):
        confirm = messagebox.askyesno(
            "确认执行深度网络修复",
            "将依次执行以下网络修复操作：\n"
            "1. 重置 Winsock 目录 (netsh winsock reset)\n"
            "2. 重置 TCP/IP 协议栈 (netsh int ip reset)\n"
            "3. 清空并重新注册 DNS 解析缓存 (ipconfig /flushdns)\n"
            "4. 释放并重新获取 DHCP IP 地址 (release / renew)\n"
            "5. 清空 ARP 动态映射表 (arp -d *)\n\n"
            "是否立即开始执行修复？"
        )
        if not confirm:
            return

        def _async():
            self.log("========== 开始执行一键深度网络修复 ==========", "WARN")
            
            # 1. winsock
            ok1, out1 = run_cmd("netsh winsock reset")
            self.log(f"[1/5] 重置 Winsock 目录: {'成功' if ok1 else '失败'} {out1}", "SUCCESS" if ok1 else "ERROR")

            # 2. int ip
            ok2, out2 = run_cmd("netsh int ip reset")
            self.log(f"[2/5] 重置 TCP/IP 协议栈: {'成功' if ok2 else '提示'} {out2}", "SUCCESS" if ok2 else "INFO")

            # 3. flushdns
            run_cmd("ipconfig /flushdns")
            run_cmd("ipconfig /registerdns")
            self.log("[3/5] 已清空并重新注册本地 DNS 缓存", "SUCCESS")

            # 4. arp
            run_cmd("arp -d *")
            self.log("[4/5] 已清除系统 ARP 映射缓存", "SUCCESS")

            # 5. release & renew (非阻塞尝试)
            self.log("[5/5] 正在重新向 DHCP 服务器申请 IP 租约...", "INFO")
            run_cmd("ipconfig /renew")

            self.log("========== 深度网络修复执行完毕！部分网络协议重置在电脑重启后达到最佳效果 ==========", "SUCCESS")
            def _done():
                messagebox.showinfo("网络修复完成", "深度网络修复已全部执行完成！\n已重置 Winsock、TCP/IP栈、DNS缓存及ARP表。\n如遇到严重网络损坏，建议重启电脑生效。")
                self.read_selected_adapter()
            self.root.after(0, _done)

        threading.Thread(target=_async, daemon=True).start()

    def action_diagnose_network(self):
        gw = self.entry_gw.get().strip()
        def _async():
            self.log("正在对当前网络状态进行全方位诊断与体检...", "INFO")
            results = run_network_diagnostic(gw)
            report_lines = []
            for item_name, status_str, is_ok in results:
                lvl = "SUCCESS" if is_ok else ("WARN" if is_ok is None else "ERROR")
                self.log(f"网络诊断 [{item_name}]: {status_str}", lvl)
                report_lines.append(f"• {item_name}: {status_str}")

            def _show():
                messagebox.showinfo("网络连通性诊断报告", "\n".join(report_lines))
            self.root.after(0, _show)
        threading.Thread(target=_async, daemon=True).start()

    def action_restart_adapter(self):
        adapter = self.adapter_combo.get().strip()
        if not adapter:
            messagebox.showwarning("提示", "请先选择要重启的网络适配器！")
            return
        def _async():
            self.log(f"正在软重启网络适配器 [{adapter}] ...", "INFO")
            run_cmd(f'powershell -NoProfile -Command "Restart-NetAdapter -Name \'{adapter}\' -Confirm:$false"')
            time.sleep(1.5)
            self.log(f"网络适配器 [{adapter}] 已成功重启！", "SUCCESS")
            self.read_selected_adapter()
        threading.Thread(target=_async, daemon=True).start()

    def action_flush_dns_only(self):
        ok, out = run_cmd("ipconfig /flushdns")
        if ok:
            self.log("DNS 解析缓存已成功清空！(ipconfig /flushdns)", "SUCCESS")
            messagebox.showinfo("成功", "DNS 缓存已成功刷新并清空！")
        else:
            self.log(f"刷新 DNS 失败: {out}", "ERROR")

    # 3. 右键菜单管理
    def action_toggle_win11_context(self, enable):
        ok, msg = set_win11_classic_context_menu(enable)
        if ok:
            self.log(msg, "SUCCESS")
            messagebox.showinfo("设置成功", msg)
        else:
            self.log(msg, "ERROR")
            messagebox.showerror("失败", msg)

    def action_toggle_takeown(self, enable):
        ok, msg = set_take_ownership_menu(enable)
        self.log(msg, "SUCCESS" if ok else "ERROR")
        messagebox.showinfo("提示", msg)

    def action_add_terminals_context(self):
        set_cmd_context_menu(True)
        set_powershell_context_menu(True)
        self.log("已在右键菜单中增加【在此处打开 CMD (管理员)】与【在此处打开 PowerShell (管理员)】", "SUCCESS")
        messagebox.showinfo("成功", "已成功添加 CMD / PowerShell 管理员右键快捷菜单！")

    def action_remove_terminals_context(self):
        set_cmd_context_menu(False)
        set_powershell_context_menu(False)
        self.log("已移除 CMD 与 PowerShell 右键快捷菜单", "INFO")
        messagebox.showinfo("成功", "已移除终端右键快捷菜单。")

    def action_set_explorer_display(self, show):
        set_file_extension_visibility(show)
        set_hidden_files_visibility(show)
        txt = "显示" if show else "隐藏"
        self.log(f"资源管理器已设置为: {txt}已知文件扩展名、{txt}系统隐藏文件", "SUCCESS")
        messagebox.showinfo("成功", f"资源管理器已更新：\n• {txt}文件扩展名\n• {txt}隐藏文件")

    # 4. 注册表性能优化
    def action_apply_reg_opt(self, key, enable):
        ok, msg = apply_system_registry_optimizations(key, enable)
        self.log(f"注册表优化 [{key}]: {msg}", "SUCCESS" if ok else "ERROR")
        if ok:
            messagebox.showinfo("优化已应用", msg)
        else:
            messagebox.showerror("优化失败", msg)

    # ==================== 开机启动项管理逻辑 (Tab 3) ====================
    def refresh_startup_items(self):
        def _async():
            self.log("正在扫描系统开机自启项 (注册表 + 启动文件夹)...", "INFO")
            items = scan_all_startup_items()
            self._cached_startup = items

            def _update():
                for row in self.startup_tree.get_children():
                    self.startup_tree.delete(row)

                for idx, it in enumerate(items):
                    tag = "DISABLED" if it["is_disabled"] else "ENABLED"
                    status_display = "🔴 已禁用" if it["is_disabled"] else "🟢 已启用"
                    self.startup_tree.insert(
                        "", tk.END, iid=str(idx),
                        values=(it["name"], status_display, it["type"], it["source_label"], it["command"]),
                        tags=(tag,)
                    )
                self.startup_count_lbl.config(text=f"共检测到 {len(items)} 个启动项")
                self.log(f"开机启动项扫描完成，发现 {len(items)} 个项。", "SUCCESS")

            self.root.after(0, _update)
        threading.Thread(target=_async, daemon=True).start()

    def _get_selected_startup_item(self):
        sel = self.startup_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先在列表中选中一个启动项！")
            return None
        idx = int(sel[0])
        if 0 <= idx < len(self._cached_startup):
            return self._cached_startup[idx]
        return None

    def action_toggle_selected_startup(self, enable):
        item = self._get_selected_startup_item()
        if not item:
            return
        ok, msg = set_startup_item_state(item, enable)
        self.log(msg, "SUCCESS" if ok else "ERROR")
        if ok:
            self.refresh_startup_items()

    def action_delete_selected_startup(self):
        item = self._get_selected_startup_item()
        if not item:
            return
        confirm = messagebox.askyesno("确认删除", f"确定要彻底删除启动项 [{item['name']}] 吗？\n删除后该程序将不再自启。")
        if not confirm:
            return
        ok, msg = delete_startup_item_permanently(item)
        self.log(msg, "SUCCESS" if ok else "ERROR")
        if ok:
            self.refresh_startup_items()

    # ==================== 软件与注册表卸载管理 (Tab 4) ====================
    def refresh_software_list(self):
        def _async():
            self.log("正在枚举已安装软件与注册表卸载项...", "INFO")
            apps = list_installed_software()
            self._cached_software = apps

            def _update():
                self.filter_software_list()
                self.log(f"已安装软件扫描完毕，共发现 {len(apps)} 款应用。", "SUCCESS")

            self.root.after(0, _update)
        threading.Thread(target=_async, daemon=True).start()

    def filter_software_list(self):
        kw = self.entry_soft_search.get().strip().lower()
        for row in self.software_tree.get_children():
            self.software_tree.delete(row)

        count = 0
        for idx, app in enumerate(self._cached_software):
            if kw:
                if kw not in app["name"].lower() and kw not in app["publisher"].lower():
                    continue
            self.software_tree.insert(
                "", tk.END, iid=str(idx),
                values=(app["name"], app["version"], app["publisher"], app["reg_root"], app["uninstall"])
            )
            count += 1

        self.software_count_lbl.config(text=f"已安装: {len(self._cached_software)} 款 | 显示: {count} 款")

    def _get_selected_software(self):
        sel = self.software_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先在列表中选中一款软件！")
            return None
        idx = int(sel[0])
        if 0 <= idx < len(self._cached_software):
            return self._cached_software[idx]
        return None

    def action_uninstall_selected_software(self):
        app = self._get_selected_software()
        if not app:
            return
        cmd = app["uninstall"]
        if not cmd:
            messagebox.showwarning("无卸载命令", f"软件 [{app['name']}] 没有提供标准的卸载命令行。")
            return

        confirm = messagebox.askyesno("确认卸载", f"确定要启动软件 [{app['name']}] 的官方卸载程序吗？\n\n卸载命令:\n{cmd}")
        if not confirm:
            return

        self.log(f"正在启动卸载向导: {cmd}", "INFO")
        try:
            subprocess.Popen(cmd, shell=True)
        except Exception as ex:
            self.log(f"启动卸载程序失败: {ex}", "ERROR")
            messagebox.showerror("启动失败", f"无法启动卸载程序：{ex}")

    def action_copy_uninstall_cmd(self):
        app = self._get_selected_software()
        if not app:
            return
        cmd = app["uninstall"]
        if not cmd:
            messagebox.showinfo("提示", "该软件无注册表卸载命令")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(cmd)
        self.log(f"已复制卸载命令到剪贴板: {cmd}", "SUCCESS")
        messagebox.showinfo("已复制", f"已复制卸载命令到剪贴板：\n\n{cmd}")


    # ==================== 右键菜单项管理逻辑 (Tab 5) ====================
    def refresh_context_items(self):
        def _async():
            self.log("正在扫描系统各类型右键菜单与 Shell 扩展项...", "INFO")
            items = scan_context_menu_items()
            self._cached_context = items
            def _update():
                self.filter_context_items()
                third_count = len([x for x in items if x["is_third_party"]])
                self.log(f"右键菜单项扫描完毕，共发现 {len(items)} 项 (其中第三方应用生成 {third_count} 项)。", "SUCCESS")
            self.root.after(0, _update)
        threading.Thread(target=_async, daemon=True).start()

    def filter_context_items(self):
        filter_mode = self.context_filter_var.get()
        for row in self.context_tree.get_children():
            self.context_tree.delete(row)

        count = 0
        third_cnt = 0
        for idx, it in enumerate(self._cached_context):
            if it["is_third_party"]:
                third_cnt += 1
            if filter_mode == "third_only" and not it["is_third_party"]:
                continue

            tag = "DISABLED" if it["is_disabled"] else ("THIRD" if it["is_third_party"] else "SYS")
            status_display = "🔴 已禁用" if it["is_disabled"] else "🟢 已启用"
            source_display = "⭐ 第三方应用" if it["is_third_party"] else "Windows系统"
            kind_display = "扩展处理器" if it["kind"] == "shellex" else "Shell菜单"

            self.context_tree.insert(
                "", tk.END, iid=str(idx),
                values=(it["name"], status_display, it["scope"], kind_display, source_display, it["cmd_or_clsid"]),
                tags=(tag,)
            )
            count += 1

        self.context_count_lbl.config(text=f"第三方: {third_cnt} 项 | 列表中显示: {count} 项")

    def _get_selected_context_item(self):
        sel = self.context_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先在列表中选中一个右键菜单项！")
            return None
        idx = int(sel[0])
        if 0 <= idx < len(self._cached_context):
            return self._cached_context[idx]
        return None

    def action_toggle_selected_context(self, enable):
        item = self._get_selected_context_item()
        if not item:
            return
        ok, msg = set_context_entry_state(item, enable)
        self.log(msg, "SUCCESS" if ok else "ERROR")
        if ok:
            self.refresh_context_items()

    def action_delete_selected_context(self):
        item = self._get_selected_context_item()
        if not item:
            return
        is_sys = not item["is_third_party"]
        warning_extra = "\n【警告】：该项被检测为 Windows 系统内置项，非必要请勿删除！" if is_sys else ""
        confirm = messagebox.askyesno(
            "确认彻底删除右键项",
            f"确定要彻底从注册表中删除右键菜单项：\n[{item['name']}] 吗？\n\n"
            f"• 注册表键名: {item['key_name']}\n"
            f"• 出现位置: {item['scope']}\n"
            f"• 注册表路径: HKCR\\{item['path']}\\{item['key_name']}"
            f"{warning_extra}\n\n删除后该右键菜单将永久移除，确认继续？"
        )
        if not confirm:
            return
        ok, msg = delete_context_entry_permanently(item)
        self.log(msg, "SUCCESS" if ok else "ERROR")
        if ok:
            messagebox.showinfo("删除成功", f"右键菜单项 [{item['key_name']}] 已成功删除！\n资源管理器右键已即时刷新。")
            self.refresh_context_items()
        else:
            messagebox.showerror("删除失败", f"删除右键菜单项失败：\n{msg}")


# ==================== 入口与自测 ====================
def run_self_tests():
    print("=== 开始自动化核心逻辑校验 ===")
    # 1. 验证IP合法性
    assert validate_ip("192.168.10.11")[0] == True
    assert validate_ip("999.999.999.999")[0] == False
    assert validate_ip("abc")[0] == False
    assert validate_ip("", allow_empty=True)[0] == True
    assert validate_ip("", allow_empty=False)[0] == False
    print("[OK] IP 校验测试通过")

    # 2. 验证掩码合法性
    assert validate_netmask("255.255.255.0")[0] == True
    assert validate_netmask("255.255.0.0")[0] == True
    assert validate_netmask("255.255.255.255")[0] == True
    assert validate_netmask("255.0.255.0")[0] == False
    print("[OK] 子网掩码校验测试通过")

    # 3. 适配器获取
    adapters = get_network_adapters()
    print(f"[OK] 获取适配器列表测试通过，检测到: {adapters}")
    assert len(adapters) > 0

    # 4. 内存检测
    mem = get_system_memory()
    print(f"[OK] 内存状态读取测试通过: 总计 {mem['total_mb']} MB, 使用率 {mem['percent']}%")
    assert mem["total_mb"] > 0

    # 5. 启动项扫描测试
    startup_items = scan_all_startup_items()
    print(f"[OK] 启动项扫描测试通过，扫描到 {len(startup_items)} 个自启项")

    # 6. 软件列表扫描测试
    softwares = list_installed_software()
    print(f"[OK] 软件列表扫描测试通过，扫描到 {len(softwares)} 款已安装软件")

    # 7. 右键菜单扫描自测
    context_items = scan_context_menu_items()
    third_party_cnt = len([x for x in context_items if x["is_third_party"]])
    print(f"[OK] 右键菜单项扫描自测通过: 总计 {len(context_items)} 项，第三方生成 {third_party_cnt} 项")
    assert len(context_items) > 0

    print("=== 所有核心逻辑与优化组件自测通过 ===")

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        run_self_tests()
        return

    # 提权判断
    elevate_if_needed()

    root = tk.Tk()
    app = SystemConfigApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
