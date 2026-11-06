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
import threading
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
        self._cached_cpu = 0.0
        self._cached_gpu = 0.0
        self._has_nvidia = None
        self._nvidia_last_check = 0
        self._pdh_query = None
        self._pdh_counter = None

        # 内存与 I/O 缓存 (大幅降低工控机磁盘读写与进程枚举开销)
        self._cached_preset_apps = []
        self._preset_apps_mtime = 0
        self._cached_top_procs = []
        self._procs_last_sample = 0

        # 启动常驻高精度后台采样守护线程 (完全独立运行，彻底杜绝主网络循环阻塞)
        self._sampler_thread = threading.Thread(target=self._bg_sampler_loop, daemon=True)
        self._sampler_thread.start()

    def _init_pdh_gpu(self):
        """初始化 Windows 原生 PDH 性能计数器 (DirectX/3D 显卡利用率)"""
        try:
            pdh = ctypes.windll.pdh
            h_query = ctypes.wintypes.HANDLE()
            if pdh.PdhOpenQueryW(None, 0, ctypes.byref(h_query)) == 0:
                h_counter = ctypes.wintypes.HANDLE()
                # 监测 Windows 3D 引擎使用率
                if pdh.PdhAddEnglishCounterW(h_query, r'\GPU Engine(*_engtype_3D)\Utilization Percentage', 0, ctypes.byref(h_counter)) == 0:
                    self._pdh_query = h_query
                    self._pdh_counter = h_counter
                    pdh.PdhCollectQueryData(self._pdh_query)
        except Exception:
            self._pdh_query = None
            self._pdh_counter = None

    def _sample_gpu_pdh(self) -> float:
        """通过 Windows PDH 毫秒级原生读取 GPU 实时占用 (免创建子进程，零延迟)"""
        if not self._pdh_query:
            self._init_pdh_gpu()
        if not self._pdh_query:
            return 0.0

        try:
            pdh = ctypes.windll.pdh
            pdh.PdhCollectQueryData(self._pdh_query)

            buf_sz = ctypes.wintypes.DWORD(0)
            item_cnt = ctypes.wintypes.DWORD(0)
            status = pdh.PdhGetFormattedCounterArrayW(self._pdh_counter, 0x00000200, ctypes.byref(buf_sz), ctypes.byref(item_cnt), None)
            if (status == -2147481646 or status == 0x800007D2) and buf_sz.value > 0:
                buf = ctypes.create_string_buffer(buf_sz.value)
                status2 = pdh.PdhGetFormattedCounterArrayW(self._pdh_counter, 0x00000200, ctypes.byref(buf_sz), ctypes.byref(item_cnt), buf)
                if status2 == 0 and item_cnt.value > 0:
                    class PDH_FMT_COUNTERVALUE(ctypes.Structure):
                        _fields_ = [('CStatus', ctypes.wintypes.DWORD), ('doubleValue', ctypes.c_double)]

                    class PDH_FMT_COUNTERVALUE_ITEM_W(ctypes.Structure):
                        _fields_ = [('szName', ctypes.wintypes.LPWSTR), ('FmtValue', PDH_FMT_COUNTERVALUE)]

                    total_gpu = 0.0
                    items = ctypes.cast(buf, ctypes.POINTER(PDH_FMT_COUNTERVALUE_ITEM_W))
                    for i in range(item_cnt.value):
                        v = items[i].FmtValue.doubleValue
                        if v > 0:
                            total_gpu += v
                    return round(min(100.0, total_gpu), 1)
        except Exception:
            pass
        return 0.0

    def _sample_gpu_nvidia(self) -> float:
        """针对配备 NVIDIA 独立显卡的展馆主机进行精准探测 (增加探测冷却，彻底杜绝无卡机器频繁拉起子进程消耗 CPU)"""
        now = time.time()
        if self._has_nvidia is False:
            if now - self._nvidia_last_check < 60.0:
                return -1.0
        self._nvidia_last_check = now
        try:
            out = subprocess.check_output(
                ['nvidia-smi', '--query-gpu=utilization.gpu', '--format=csv,noheader,nounits'],
                timeout=0.3, stderr=subprocess.DEVNULL, creationflags=0x08000000
            ).decode().strip()
            if out:
                self._has_nvidia = True
                val = float(out.split('\n')[0].strip())
                return round(val, 1)
        except Exception:
            self._has_nvidia = False
        return -1.0

    def _bg_sampler_loop(self):
        """后台独立周期性精准采样 (1.0 秒标准窗口计算，完全匹配任务管理器)"""
        if HAS_PSUTIL:
            try:
                psutil.cpu_percent(interval=None)
            except Exception:
                pass

        while True:
            try:
                # 1. 采集 CPU 使用率 (psutil 1.0 秒滑动窗口，精度 0.1%)
                if HAS_PSUTIL:
                    cpu_val = psutil.cpu_percent(interval=1.0)
                    self._cached_cpu = round(max(0.0, min(100.0, float(cpu_val))), 1)
                else:
                    time.sleep(1.0)

                # 2. 采集 GPU 使用率 (优先 NVIDIA，若无则使用原生 PDH 3D 利用率)
                gpu_nv = self._sample_gpu_nvidia()
                if gpu_nv >= 0.0:
                    self._cached_gpu = gpu_nv
                else:
                    self._cached_gpu = self._sample_gpu_pdh()

            except Exception:
                time.sleep(1.0)

    def get_gpu_percent(self) -> float:
        """获取系统 GPU 实时使用率 (直接返回后台采样值，0 延迟)"""
        return self._cached_gpu

    def get_cpu_percent(self) -> float:
        """获取 CPU 实时使用率 (直接返回后台采样值，精准对应任务管理器)"""
        return self._cached_cpu

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

    def collect_full_status(self, license_mgr=None, custom_name: str = "") -> dict:
        """
        全量组装当前主机状态字典
        """
        if not custom_name:
            try:
                import gwc_desktop_helper as dh
                cfg = dh.ConfigManager.load_config()
                custom_name = cfg.get("custom_name", "")
            except Exception:
                pass
        # 1. 资源状态
        cpu = self.get_cpu_percent()
        gpu = self.get_gpu_percent()
        mem = gwc_system_ops.get_system_memory()
        disks = self.get_disks_status()
        net_speed = self.get_network_speed()

        # 读取受控端本地预设调用应用 (带 mtime 缓存，仅在修改时重新加载，避免心跳频繁读盘)
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            p_file = os.path.join(base_dir, "agent_preset_apps.json")
            if os.path.exists(p_file):
                mtime = os.path.getmtime(p_file)
                if mtime != self._preset_apps_mtime:
                    import json
                    with open(p_file, "r", encoding="utf-8") as pf:
                        self._cached_preset_apps = json.load(pf)
                    self._preset_apps_mtime = mtime
            else:
                self._cached_preset_apps = []
        except Exception:
            pass
        preset_apps = self._cached_preset_apps

        # 2. 活动窗口与软件
        fg_window = self.get_current_foreground_window()
        visible_apps = self.get_visible_windows()
        # 采集前 50 项运行进程 (2 秒动态快照缓存，大幅减轻 CPU 负载)
        now_t = time.time()
        if now_t - self._procs_last_sample >= 2.0 or not self._cached_top_procs:
            self._cached_top_procs = gwc_system_ops.list_running_processes()[:50]
            self._procs_last_sample = now_t
        top_procs = self._cached_top_procs

        # 3. 授权状态
        lic_info = {
            "status": "ACTIVE",
            "request_code": "",
            "expire_desc": "商业永久授权"
        }
        if license_mgr:
            try:
                ok, msg = license_mgr.check()
                req_fn = getattr(license_mgr, "get_req_code", getattr(license_mgr, "get_request_code", None))
                req = req_fn() if req_fn else ""
                lic_info["status"] = "ACTIVE" if ok else "UNLICENSED"
                lic_info["request_code"] = req
                exp = getattr(license_mgr, "data", {}).get("expire_time", 0)
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
            "hostname": custom_name or platform.node(),
            "custom_name": custom_name,
            "ip": local_ip,
            "os": f"{platform.system()} {platform.release()}",
            "timestamp": int(time.time()),
            "cpu_percent": cpu,
            "gpu_percent": gpu,
            "memory": mem,
            "disks": disks,
            "net_speed": net_speed,
            "foreground_window": fg_window,
            "visible_windows": visible_apps[:8],
            "top_processes": top_procs,
            "preset_apps": preset_apps,
            "license": lic_info
        }


# 全局单例采集器
_collector = HostStatusCollector()

def get_host_status_report(license_mgr=None, custom_name: str = "") -> dict:
    return _collector.collect_full_status(license_mgr, custom_name=custom_name)
