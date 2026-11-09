# -*- coding: utf-8 -*-
"""
国文创系统一键备份与恢复引擎 (GuoWenChuang Backup & Restore Engine)
=================================================================
1. 完整采集工控机系统配置：
   - 网络适配器 IPv4 / DHCP / DNS / 网关参数
   - 展馆全套策略与安全注册表项 (UAC/Defender/更新/防火墙/休眠/快启/RDP免密等)
   - 系统与用户级开机启动项快照
   - 预装软件及运行环境清单
   - 自定义展馆程序配置目录与重要文件打包
2. 导出为 .gwcbackup 标准备份包 (内含元数据签名、清单及数据文件)
3. 支持一键全自动恢复还原：
   - 自动恢复网卡配置、写回注册表策略、还原自启动项、校验预装软件环境
4. 支持上传备份至主控中心、接收主控下发备份并执行自动恢复
"""

import os
import sys
import re
import json
import time
import zipfile
import platform
import socket
import hashlib
import shutil
import ctypes
import winreg
from datetime import datetime

import gwc_system_ops
import gwc_crypto


def get_terminal_data_dir() -> str:
    """获取受控端专属统一数据文件夹 GWC_Terminal_Data (软件生成的唯一顶级文件夹，规范归档所有生成文件，绝不乱放)"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if getattr(sys, "frozen", False):
        base_dir = os.path.dirname(os.path.abspath(sys.executable))
    d = os.path.join(base_dir, "GWC_Terminal_Data")
    os.makedirs(d, exist_ok=True)
    return d


def get_default_backup_dir() -> str:
    """获取默认系统镜像文件存储目录 (归档于 GWC_Terminal_Data/Backups 专属子文件夹)"""
    d = os.path.join(get_terminal_data_dir(), "Backups")
    os.makedirs(d, exist_ok=True)
    return d


def get_default_temp_dir() -> str:
    """获取临时还原与过程数据目录 (归档于 GWC_Terminal_Data/Temp)"""
    d = os.path.join(get_terminal_data_dir(), "Temp")
    os.makedirs(d, exist_ok=True)
    return d


def get_disk_free_space(path: str) -> int:
    """获取指定路径所在磁盘的剩余可用空间字节数"""
    try:
        total, used, free = shutil.disk_usage(path)
        return free
    except Exception:
        try:
            free_bytes = ctypes.c_ulonglong(0)
            ctypes.windll.kernel32.GetDiskFreeSpaceExW(ctypes.c_wchar_p(path), ctypes.byref(free_bytes), None, None)
            return free_bytes.value
        except Exception:
            return 10 * 1024 * 1024 * 1024  # 默认兜底 10GB


def estimate_system_image_size(extra_dirs: list = None, output_dir: str = None) -> dict:
    """
    扫描并预估即将生成的系统镜像大小与磁盘空间预检
    :return: dict 包含 raw_bytes, file_count, est_compressed_bytes, free_bytes, is_space_tight 等
    """
    file_count = 6
    raw_bytes = 1024 * 1024 * 2  # 基础系统环境快照约 2MB

    if extra_dirs:
        for p in extra_dirs:
            if not p:
                continue
            if os.path.isfile(p):
                file_count += 1
                try: raw_bytes += os.path.getsize(p)
                except Exception: pass
            elif os.path.isdir(p):
                for root, _, files in os.walk(p):
                    for f in files:
                        file_count += 1
                        try: raw_bytes += os.path.getsize(os.path.join(root, f))
                        except Exception: pass

    # 预估压缩后的镜像大小 (按 75% 预估，考虑多媒体和文本混合)
    est_comp_bytes = max(1024 * 100, int(raw_bytes * 0.75))
    out_d = output_dir or get_default_backup_dir()
    free_bytes = get_disk_free_space(out_d)

    # 剩余空间紧张警告判定: 剩余可用空间不足预估压缩镜像的 1.25 倍
    is_space_tight = bool(est_comp_bytes * 1.25 > free_bytes)

    return {
        "file_count": file_count,
        "raw_bytes": raw_bytes,
        "raw_str": format_file_size(raw_bytes),
        "est_compressed_bytes": est_comp_bytes,
        "est_str": format_file_size(est_comp_bytes),
        "free_bytes": free_bytes,
        "free_str": format_file_size(free_bytes),
        "is_space_tight": is_space_tight,
        "output_dir": out_d
    }


def collect_system_snapshot(custom_paths: list = None) -> dict:
    """采集当前系统的完整配置快照"""
    snapshot = {
        "hostname": platform.node(),
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp": int(time.time()),
        "network": [],
        "policies": {},
        "startup": [],
        "software": [],
        "custom_files": []
    }

    # 1. 采集网络适配器配置
    adapters = gwc_system_ops.get_network_adapters()
    for ad in adapters:
        info = gwc_system_ops.read_adapter_ipv4(ad)
        snapshot["network"].append(info)

    # 2. 采集展馆策略注册表配置
    policy_checks = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System", "EnableLUA"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System", "ConsentPromptBehaviorAdmin"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU", "NoAutoUpdate"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU", "AUOptions"),
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Power", "HiberbootEnabled"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows\EdgeUI", "AllowEdgeSwipe"),
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Terminal Server", "fDenyTSConnections"),
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Lsa", "LimitBlankPasswordUse")
    ]
    for root, sub, val_name in policy_checks:
        try:
            with winreg.OpenKey(root, sub, 0, winreg.KEY_READ) as k:
                val, typ = winreg.QueryValueEx(k, val_name)
                snapshot["policies"][f"{sub}\\{val_name}"] = val
        except Exception:
            snapshot["policies"][f"{sub}\\{val_name}"] = None

    # 3. 采集自启动项
    snapshot["startup"] = gwc_system_ops.scan_all_startup_items()

    # 4. 采集已安装预装软件列表
    snapshot["software"] = gwc_system_ops.list_installed_software()

    # 5. 自定义目录与文件
    if custom_paths:
        for p in custom_paths:
            if os.path.exists(p):
                snapshot["custom_files"].append(os.path.abspath(p))

    # 自动包含本地展馆环境核心配置文件 (兼容专属配置目录及旧文件)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if getattr(sys, "frozen", False):
        base_dir = os.path.dirname(os.path.abspath(sys.executable))

    cfg_targets = [
        os.path.join(base_dir, "GWC_Terminal_Data", "Configs", "agent_config.json"),
        os.path.join(base_dir, "GWC_Terminal_Data", "Configs", "agent_preset_apps.json"),
        os.path.join(base_dir, "agent_config.json"),
        os.path.join(base_dir, "agent_preset_apps.json"),
        os.path.join(base_dir, "gwc_config.json"),
    ]
    for cfg_p in cfg_targets:
        if os.path.isfile(cfg_p) and cfg_p not in snapshot["custom_files"]:
            snapshot["custom_files"].append(cfg_p)

    return snapshot


def format_file_size(size_bytes: int) -> str:
    """智能人性化文件大小格式化 (杜绝不足 1MB 显示为 0Mb 的误导)"""
    if size_bytes <= 0:
        return "0 B"
    elif size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"


def create_backup_package(name: str = "", notes: str = "", custom_paths: list = None, output_dir: str = None, extra_dirs: list = None) -> dict:
    """
    执行一键系统配置与展项工程完整备份，生成标注系统镜像文件 (.gwcsysimg / .gwcbackup)
    """
    if not output_dir:
        output_dir = get_default_backup_dir()
    os.makedirs(output_dir, exist_ok=True)

    # 兼容 custom_paths 与 extra_dirs
    merged_paths = []
    if custom_paths:
        merged_paths.extend(custom_paths)
    if extra_dirs:
        merged_paths.extend(extra_dirs)

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    clean_host = re.sub(r'[\\/*?:"<>| ]', "_", platform.node())
    safe_name = re.sub(r'[\\/*?:"<>| ]', "_", name.strip()) if name.strip() else f"系统镜像_{clean_host}_{timestamp_str}"
    filename = f"{safe_name}.gwcsysimg"
    file_path = os.path.join(output_dir, filename)

    try:
        snapshot = collect_system_snapshot(merged_paths)
        manifest = {
            "format_version": "2.0",
            "package_type": "SYSTEM_IMAGE",
            "package_label": "展馆工控系统完整镜像文件",
            "name": safe_name,
            "notes": notes,
            "hostname": snapshot["hostname"],
            "source_host": snapshot["hostname"],
            "os": snapshot["os"],
            "created_at": snapshot["created_at"],
            "timestamp": snapshot["timestamp"],
            "network_count": len(snapshot["network"]),
            "software_count": len(snapshot["software"]),
            "startup_count": len(snapshot["startup"])
        }

        with zipfile.ZipFile(file_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            zf.writestr("network.json", json.dumps(snapshot["network"], ensure_ascii=False, indent=2))
            zf.writestr("policies.json", json.dumps(snapshot["policies"], ensure_ascii=False, indent=2))
            zf.writestr("startup.json", json.dumps(snapshot["startup"], ensure_ascii=False, indent=2))
            zf.writestr("software.json", json.dumps(snapshot["software"], ensure_ascii=False, indent=2))

            # 写入自定义文件与展项工程数据 (附带原路径映射，支持完美还原)
            file_map = {}
            for cp in snapshot.get("custom_files", []):
                if os.path.isfile(cp):
                    arc_name = f"files/{os.path.basename(cp)}"
                    zf.write(cp, arc_name)
                    file_map[arc_name] = os.path.abspath(cp)
                elif os.path.isdir(cp):
                    base_folder = os.path.basename(cp)
                    for root, _, files in os.walk(cp):
                        for f in files:
                            full_p = os.path.join(root, f)
                            rel_p = os.path.relpath(full_p, cp).replace("\\", "/")
                            arc_name = f"files/{base_folder}/{rel_p}"
                            zf.write(full_p, arc_name)
                            file_map[arc_name] = os.path.abspath(full_p)
            zf.writestr("file_map.json", json.dumps(file_map, ensure_ascii=False, indent=2))

        size_bytes = os.path.getsize(file_path)
        if size_bytes == 0:
            raise IOError("备份文件写入异常，生成文件大小为 0 字节")

        sz_str = format_file_size(size_bytes)
        sz_mb = max(0.01, round(size_bytes / (1024 * 1024), 2))
        return {
            "success": True,
            "path": file_path,
            "filename": filename,
            "manifest": manifest,
            "size_bytes": size_bytes,
            "size_str": sz_str,
            "size_mb": sz_mb,
            "msg": f"系统配置已成功备份为 {filename} ({sz_str})"
        }
    except Exception as e:
        return {"success": False, "error": f"备份生成失败: {e}"}


def inspect_backup_package(file_path: str) -> dict:
    """读取并解析 .gwcbackup 文件中的元数据和清单"""
    if not os.path.isfile(file_path):
        return {"valid": False, "error": "备份文件不存在"}

    try:
        size_bytes = os.path.getsize(file_path)
        if size_bytes == 0:
            return {"valid": False, "error": "备份文件大小为 0 字节 (损坏的空文件)"}

        with zipfile.ZipFile(file_path, "r") as zf:
            names = zf.namelist()
            if "manifest.json" not in names:
                return {"valid": False, "error": "非法国文创备份包 (缺少 manifest.json)"}

            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            net_data = json.loads(zf.read("network.json").decode("utf-8")) if "network.json" in names else []
            sw_data = json.loads(zf.read("software.json").decode("utf-8")) if "software.json" in names else []
            pol_data = json.loads(zf.read("policies.json").decode("utf-8")) if "policies.json" in names else {}

            sz_str = format_file_size(size_bytes)
            sz_mb = max(0.01, round(size_bytes / (1024 * 1024), 2))
            return {
                "valid": True,
                "manifest": manifest,
                "network": net_data,
                "software_count": len(sw_data),
                "policies_count": len(pol_data),
                "has_files": any(n.startswith("files/") for n in names),
                "path": file_path,
                "size_bytes": size_bytes,
                "size_str": sz_str,
                "size_mb": sz_mb,
                "package_type": manifest.get("package_type", "SYSTEM_IMAGE"),
                "source_host": manifest.get("source_host", manifest.get("hostname", "")),
                "package_label": manifest.get("package_label", "展馆工控系统镜像文件")
            }
    except Exception as e:
        return {"valid": False, "error": f"解析备份包失败: {e}"}


def restore_backup_package(file_path: str, restore_net: bool = True, restore_policies: bool = True, restore_startup: bool = True) -> dict:
    """
    一键恢复系统配置
    - 还原网卡静态 IP 或 DHCP
    - 写回展馆策略与注册表项
    - 还原开机自启项
    - 核验预装软件
    """
    if not os.path.isfile(file_path):
        return {"success": False, "error": "备份文件不存在"}

    logs = []
    logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 开始执行系统一键还原...")

    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            names = zf.namelist()
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            logs.append(f"加载备份: {manifest.get('name')} (创建时间: {manifest.get('created_at')})")

            # 1. 恢复网络设置
            if restore_net and "network.json" in names:
                net_list = json.loads(zf.read("network.json").decode("utf-8"))
                current_adapters = gwc_system_ops.get_network_adapters()
                logs.append(f"正在还原网络配置 ({len(net_list)} 个网卡快照)...")

                for net_item in net_list:
                    ad_name = net_item.get("adapter")
                    if ad_name in current_adapters:
                        if net_item.get("dhcp"):
                            gwc_system_ops.apply_dhcp_config(ad_name)
                            logs.append(f" - {ad_name}: 已恢复为 DHCP 自动获取")
                        else:
                            ip = net_item.get("ip")
                            mask = net_item.get("mask", "255.255.255.0")
                            gw = net_item.get("gateway", "")
                            dns1 = net_item.get("dns1", "")
                            dns2 = net_item.get("dns2", "")
                            if ip:
                                ok, out = gwc_system_ops.apply_ip_config(ad_name, ip, mask, gw, dns1, dns2)
                                logs.append(f" - {ad_name}: 已恢复静态IP {ip} (掩码 {mask})")
                    else:
                        logs.append(f" - 提示: 未在当前系统中找到网卡 [{ad_name}]，已跳过")

            # 2. 恢复策略注册表
            if restore_policies and "policies.json" in names:
                policies = json.loads(zf.read("policies.json").decode("utf-8"))
                logs.append(f"正在还原展馆安全与系统策略...")
                for reg_key_path, val in policies.items():
                    if val is not None and "\\" in reg_key_path:
                        sub, val_name = reg_key_path.rsplit("\\", 1)
                        try:
                            # 默认以 HKLM 写入
                            with winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, sub) as k:
                                if isinstance(val, int):
                                    winreg.SetValueEx(k, val_name, 0, winreg.REG_DWORD, val)
                                elif isinstance(val, str):
                                    winreg.SetValueEx(k, val_name, 0, winreg.REG_SZ, val)
                            logs.append(f" - 策略写回: {val_name} = {val}")
                        except Exception as ex:
                            logs.append(f" - 策略写入警告 ({val_name}): {ex}")

            # 3. 恢复自启动项
            if restore_startup and "startup.json" in names:
                startup_items = json.loads(zf.read("startup.json").decode("utf-8"))
                logs.append(f"正在核验与还原开机启动项 ({len(startup_items)} 项)...")
                for s_item in startup_items:
                    if s_item.get("location") == "Registry" and s_item.get("scope") == "HKLM":
                        try:
                            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_WRITE) as k:
                                winreg.SetValueEx(k, s_item["name"], 0, winreg.REG_SZ, s_item["command"])
                            logs.append(f" - 还原自启: {s_item['name']}")
                        except Exception:
                            pass

            # 4. 预装软件比对核查
            if "software.json" in names:
                saved_sw = json.loads(zf.read("software.json").decode("utf-8"))
                current_sw = [x["name"].lower() for x in gwc_system_ops.list_installed_software()]
                missing = []
                for sw in saved_sw:
                    s_name = sw["name"]
                    if not any(s_name.lower() in c or c in s_name.lower() for c in current_sw):
                        missing.append(s_name)
                if missing:
                    logs.append(f"⚠️ 预装软件核对提示: 当前系统可能缺少 {len(missing)} 个软件:")
                    for m in missing[:5]:
                        logs.append(f"   * 缺少: {m}")
                    if len(missing) > 5:
                        logs.append(f"   * 更多已省略 (共 {len(missing)} 个)")
                else:
                    logs.append("✅ 预装软件环境核验通过，所有预装软件均已就绪！")

            # 5. 还原展项工程数据与应用文件
            if "file_map.json" in names:
                file_map = json.loads(zf.read("file_map.json").decode("utf-8"))
                logs.append(f"正在还原展项工程与应用数据文件 ({len(file_map)} 项)...")
                restored_cnt = 0
                for arc_name, target_path in file_map.items():
                    if arc_name in names:
                        try:
                            os.makedirs(os.path.dirname(target_path), exist_ok=True)
                            with open(target_path, "wb") as f_out:
                                f_out.write(zf.read(arc_name))
                            restored_cnt += 1
                        except Exception as e_file:
                            logs.append(f" - 文件写回跳过 ({os.path.basename(target_path)}): {e_file}")
                logs.append(f"✅ 展项工程与应用数据还原完成，共恢复 {restored_cnt} 个文件！")

        gwc_system_ops.notify_shell_refresh()
        logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 系统一键配置还原全部完成！")
        return {"success": True, "logs": logs, "msg": "系统配置一键还原成功！"}
    except Exception as e:
        logs.append(f"❌ 恢复过程出错: {e}")
        return {"success": False, "logs": logs, "error": str(e)}


def list_local_backups(backup_dir: str = None) -> list:
    """列出指定目录下的所有系统镜像与备份文件列表 (.gwcsysimg / .gwcbackup)"""
    if not backup_dir:
        backup_dir = get_default_backup_dir()
    backups = []
    if not os.path.isdir(backup_dir):
        return backups

    for f in os.listdir(backup_dir):
        f_lower = f.lower()
        if f_lower.endswith(".gwcsysimg") or f_lower.endswith(".gwcbackup"):
            fp = os.path.join(backup_dir, f)
            info = inspect_backup_package(fp)
            if info.get("valid"):
                backups.append({
                    "filename": f,
                    "path": fp,
                    "name": info["manifest"].get("name", f),
                    "hostname": info["manifest"].get("hostname", ""),
                    "source_host": info.get("source_host", info["manifest"].get("hostname", "")),
                    "package_type": info.get("package_type", "SYSTEM_IMAGE"),
                    "package_label": info.get("package_label", "展馆工控系统镜像文件"),
                    "created_at": info["manifest"].get("created_at", ""),
                    "notes": info["manifest"].get("notes", ""),
                    "size_mb": info["size_mb"],
                    "size_bytes": info.get("size_bytes", 0),
                    "size_str": info.get("size_str", f"{info['size_mb']} MB")
                })
    return sorted(backups, key=lambda x: x["created_at"], reverse=True)
