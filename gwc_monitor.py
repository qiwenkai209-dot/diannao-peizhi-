# -*- coding: utf-8 -*-
"""
主机实时工作状态监控与采集引擎 (GuoWenChuang Host Monitor Engine)
================================================================
1. 实时采集系统核心资源使用率:
   - CPU 使用率 (0-100%)
   - 物理内存使用率 (总计 / 已用 / 可用 / 百分比)
   - 各磁盘分区占用率 (驱动器号、总容量、已用、剩余、百分比)
   - 网络实时收发带宽速率 (KB/s)
2. 运行中软件与前台活动窗口深度感知:
   - 当前前台活动窗口标题
   - 运行中的前台桌面应用清单
   - Top 活跃进程列表 (PID、名称、内存占用)
3. 授权状态与申请码快照
"""

import os
import sys
import time
import ctypes
import socket
import platform
import subprocess
from datetime import datetime

import gwc_system_ops

# 尝试导入 psutil 以提供最高精度的系统性能指标
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


class HostStatusCollector:
    def __init__(self):
        self._last_net_bytes = None
        self._last_net_time = time.time()
        self._prev_idle_time = 0
        self._prev_kernel_time = 0
        self._prev_user_time = 0

    def get_cpu_percent(self) -> float:
        """获取 CPU 实时使用率 (兼容 psutil 与 ctypes GetSystemTimes)"""
        if HAS_PSUTIL:
            try:
                return round(psutil.cpu_percent(interval=None), 1)
            except Exception:
                pass

        try:
            class FILETIME(ctypes.Structure):
                _fields_ = [("dwLowDateTime", ctypes.c_uint32), ("dwHighDateTime", ctypes.c_uint32)]

            idle_time = FILETIME()
            kernel_time = FILETIME()
            user_time = FILETIME()

            if ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle_time), ctypes.byref(kernel_time), ctypes.byref(user_time)):
                def ft_to_int(ft):
                    return (ft.dwHighDateTime << 32) | ft.dwLowDateTime

                i = ft_to_int(idle_time)
                k = ft_to_int(kernel_time)
                u = ft_to_int(user_time)

                if self._prev_kernel_time > 0:
                    usr = u - self._prev_user_time
                    ker = k - self._prev_kernel_time
                    idl = i - self._prev_idle_time
                    sys_total = usr + ker
                    if sys_total > 0:
                        pct = round(((sys_total - idl) / sys_total) * 100, 1)
                        self._prev_idle_time, self._prev_kernel_time, self._prev_user_time = i, k, u
                        return max(0.0, min(100.0, pct))

                self._prev_idle_time, self._prev_kernel_time, self._prev_user_time = i, k, u
        except Exception:
            pass
        return 0.0

    def get_disks_status(self) -> list:
        """获取所有固定驱动器磁盘占用情况"""
        disks = []
        if HAS_PSUTIL:
            try:
                for part in psutil.disk_partitions(all=False):
                    if 'cdrom' in part.opts or not part.fstype:
                        continue
                    try:
                        usage = psutil.disk_usage(part.mountpoint)
                        disks.append({
                            "device": part.device.rstrip("\\"),
                            "mount": part.mountpoint,
                            "total_gb": round(usage.total / (1024**3), 1),
                            "used_gb": round(usage.used / (1024**3), 1),
                            "free_gb": round(usage.free / (1024**3), 1),
                            "percent": usage.percent
                        })
                    except Exception:
                        pass
                if disks:
                    return disks
            except Exception:
                pass

        # ctypes 降级处理
        user32 = ctypes.windll.kernel32
        drives = []
        bitmask = user32.GetLogicalDrives()
        for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
            if bitmask & 1:
                drives.append(f"{letter}:\\")
            bitmask >>= 1

        for d in drives:
            try:
                free_bytes = ctypes.c_ulonglong(0)
                total_bytes = ctypes.c_ulonglong(0)
                total_free = ctypes.c_ulonglong(0)
                if user32.GetDiskFreeSpaceExW(ctypes.c_wchar_p(d), ctypes.byref(free_bytes), ctypes.byref(total_bytes), ctypes.byref(total_free)):
                    if total_bytes.value > 0:
                        tot_gb = round(total_bytes.value / (1024**3), 1)
                        fre_gb = round(free_bytes.value / (1024**3), 1)
                        usd_gb = round(tot_gb - fre_gb, 1)
                        pct = round((usd_gb / tot_gb) * 100, 1) if tot_gb > 0 else 0
                        disks.append({
                            "device": d.rstrip("\\"),
                            "mount": d,
                            "total_gb": tot_gb,
                            "used_gb": usd_gb,
                            "free_gb": fre_gb,
                            "percent": pct
                        })
            except Exception:
                pass
        return disks

    def get_network_speed(self) -> dict:
        """获取网络实时上下行速率 (KB/s)"""
        now = time.time()
        dt = max(0.1, now - self._last_net_time)

        if HAS_PSUTIL:
            try:
                net_io = psutil.net_io_counters()
                cur_bytes = (net_io.bytes_sent, net_io.bytes_recv)
                if self._last_net_bytes:
                    sent_kbps = round((cur_bytes[0] - self._last_net_bytes[0]) / (1024 * dt), 1)
                    recv_kbps = round((cur_bytes[1] - self._last_net_bytes[1]) / (1024 * dt), 1)
                    self._last_net_bytes = cur_bytes
                    self._last_net_time = now
                    return {"upload_kbps": max(0.0, sent_kbps), "download_kbps": max(0.0, recv_kbps)}
                self._last_net_bytes = cur_bytes
                self._last_net_time = now
            except Exception:
                pass
        return {"upload_kbps": 0.0, "download_kbps": 0.0}

    def get_visible_windows(self) -> list:
        """获取当前可见的用户窗口标题"""
        user32 = ctypes.windll.user32
        hdesk = user32.OpenDesktopW('Default', 0, False, 0x01FF)
        if hdesk:
            user32.SetThreadDesktop(hdesk)

        titles = []
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def enum_cb(hwnd, lparam):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    title = buf.value.strip()
                    if title and title not in ["Program Manager", "Default IME", "MSCTFIME UI"]:
                        titles.append(title)
            return True

        try:
            user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
        except Exception:
            pass
        finally:
            if hdesk:
                user32.CloseDesktop(hdesk)
        return titles

    def get_current_foreground_window(self) -> str:
        """获取当前处于焦点的前台窗口标题"""
        user32 = ctypes.windll.user32
        hdesk = user32.OpenDesktopW('Default', 0, False, 0x01FF)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
        try:
            hwnd = user32.GetForegroundWindow()
            if hwnd:
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    return buf.value.strip()
        except Exception:
            pass
        finally:
            if hdesk:
                user32.CloseDesktop(hdesk)
        return ""

    def collect_full_status(self, license_mgr=None) -> dict:
        """
        全量组装当前主机状态字典
        """
        # 1. 资源状态
        cpu = self.get_cpu_percent()
        mem = gwc_system_ops.get_system_memory()
        disks = self.get_disks_status()
        net_speed = self.get_network_speed()

        # 2. 活动窗口与软件
        fg_window = self.get_current_foreground_window()
        visible_apps = self.get_visible_windows()
        top_procs = gwc_system_ops.list_running_processes()[:15]

        # 3. 授权状态
        lic_info = {
            "status": "ACTIVE",
            "request_code": "",
            "expire_desc": "商业永久授权"
        }
        if license_mgr:
            try:
                ok, msg = license_mgr.check()
                req = license_mgr.get_req_code()
                lic_info["status"] = "ACTIVE" if ok else "UNLICENSED"
                lic_info["request_code"] = req
                exp = license_mgr.data.get("expire_time", 0)
                if exp == -1:
                    lic_info["expire_desc"] = "永久有效"
                elif exp > 0:
                    dt = datetime.fromtimestamp(exp).strftime("%Y-%m-%d %H:%M")
                    lic_info["expire_desc"] = f"到期时间: {dt}"
                else:
                    lic_info["expire_desc"] = "未授权"
            except Exception:
                pass

        # 4. 获取本地主 IP
        local_ip = "127.0.0.1"
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except Exception:
            try:
                local_ip = socket.gethostbyname(socket.gethostname())
            except Exception:
                pass

        return {
            "hostname": platform.node(),
            "ip": local_ip,
            "os": f"{platform.system()} {platform.release()}",
            "timestamp": int(time.time()),
            "cpu_percent": cpu,
            "memory": mem,
            "disks": disks,
            "net_speed": net_speed,
            "foreground_window": fg_window,
            "visible_windows": visible_apps[:8],
            "top_processes": top_procs,
            "license": lic_info
        }


# 全局单例采集器
_collector = HostStatusCollector()

def get_host_status_report(license_mgr=None) -> dict:
    return _collector.collect_full_status(license_mgr)
