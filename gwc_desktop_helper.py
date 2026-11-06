# -*- coding: utf-8 -*-
"""
国文创受控端系统辅助支持库 (GuoWenChuang Agent Desktop Helper)
============================================================
1. 全局系统热键注册与事件捕获引擎 (基于 Win32 RegisterHotKey 原生 API，无第三方依赖)
2. 自定义开机自启动管理 (注册表 HKCU Run 项，支持开机静默隐藏参数 --hide)
3. 受控端本地持久化配置读取与保存 (agent_config.json)
"""

import os
import sys
import json
import time
import ctypes
from ctypes import wintypes
import threading
import winreg
import gwc_discovery

# Win32 API 常量
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

# 常见虚拟按键映射
VK_KEY_MAP = {
    "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73,
    "F5": 0x74, "F6": 0x75, "F7": 0x76, "F8": 0x77,
    "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
    "SPACE": 0x20, "TAB": 0x09, "ESC": 0x1B, "ENTER": 0x0D,
    "HOME": 0x24, "END": 0x23, "INSERT": 0x2D, "DELETE": 0x2E,
    "PAGEUP": 0x21, "PAGEDOWN": 0x22,
    "UP": 0x26, "DOWN": 0x28, "LEFT": 0x25, "RIGHT": 0x27,
    "PAUSE": 0x13, "PRINTSCREEN": 0x2C, "BACKSPACE": 0x08,
}
# A-Z, 0-9 键码映射
for c in range(ord('A'), ord('Z') + 1):
    VK_KEY_MAP[chr(c)] = c
for c in range(ord('0'), ord('9') + 1):
    VK_KEY_MAP[chr(c)] = c


def parse_hotkey_string(hotkey_str: str) -> tuple:
    """
    解析快捷键字符串，例如 'Ctrl+Alt+F12'
    返回: (modifiers, vk_code, display_text)
    """
    parts = [p.strip().upper() for p in hotkey_str.replace(" ", "").split("+") if p.strip()]
    modifiers = MOD_NOREPEAT
    key_name = ""
    vk_code = 0

    disp_parts = []
    if "CTRL" in parts or "CONTROL" in parts:
        modifiers |= MOD_CONTROL
        disp_parts.append("Ctrl")
    if "ALT" in parts:
        modifiers |= MOD_ALT
        disp_parts.append("Alt")
    if "SHIFT" in parts:
        modifiers |= MOD_SHIFT
        disp_parts.append("Shift")
    if "WIN" in parts:
        modifiers |= MOD_WIN
        disp_parts.append("Win")

    for p in parts:
        if p not in ("CTRL", "CONTROL", "ALT", "SHIFT", "WIN"):
            key_name = p
            break

    if not key_name:
        key_name = "Q"

    vk_code = VK_KEY_MAP.get(key_name, 0x51)
    disp_parts.append(key_name)
    display_str = " + ".join(disp_parts)
    return modifiers, vk_code, display_str


class GlobalHotkeyManager:
    """Windows 原生全局快捷键管理器"""

    def __init__(self, hotkey_str: str = "Ctrl+Q", on_trigger=None):
        self.hotkey_str = hotkey_str
        self.on_trigger = on_trigger
        self.running = False
        self._thread = None
        self._thread_id = None
        self.registered = False
        self.hotkey_id = 10086
        self.last_display_str = ""

    def start(self):
        if self.running:
            return
        self.running = True
        ready_evt = threading.Event()
        self._thread = threading.Thread(target=self._msg_loop, args=(ready_evt,), daemon=True)
        self._thread.start()
        ready_evt.wait(timeout=2.0)

    def stop(self):
        self.running = False
        if self._thread_id:
            try:
                ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            except Exception:
                pass
        self.registered = False

    def update_hotkey(self, new_hotkey_str: str) -> bool:
        """更新并生效新的快捷键"""
        self.hotkey_str = new_hotkey_str
        self.stop()
        time.sleep(0.1)
        self.start()
        return self.registered

    def _msg_loop(self, ready_evt):
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self._thread_id = kernel32.GetCurrentThreadId()

        mods, vk, disp_text = parse_hotkey_string(self.hotkey_str)
        self.last_display_str = disp_text

        # 注册全局热键
        reg_ok = user32.RegisterHotKey(None, self.hotkey_id, mods, vk)
        self.registered = bool(reg_ok)
        ready_evt.set()

        if not self.registered:
            # 兼容：尝试不带 MOD_NOREPEAT 注册（部分老版系统支持）
            reg_ok = user32.RegisterHotKey(None, self.hotkey_id, mods & ~MOD_NOREPEAT, vk)
            self.registered = bool(reg_ok)

        msg = wintypes.MSG()
        try:
            while self.running:
                # 使用 GetMessage 阻塞监听线程消息，完全不消耗 CPU
                res = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if res <= 0:  # WM_QUIT 或错误
                    break
                if msg.message == WM_HOTKEY:
                    if msg.wParam == self.hotkey_id:
                        if self.on_trigger:
                            try:
                                self.on_trigger()
                            except Exception as ex:
                                print(f"[-] 热键触发异常: {ex}")
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        except Exception:
            pass
        finally:
            user32.UnregisterHotKey(None, self.hotkey_id)
            self.registered = False


class AutoStartManager:
    """自定义开机自启动管理 (注册表 HKCU Run 模式)"""

    REG_KEY_NAME = "GuoWenChuang_Agent"

    @classmethod
    def get_executable_command(cls, silent: bool = True) -> str:
        """获取当前脚本或 EXE 的完整开机执行命令"""
        if getattr(sys, "frozen", False):
            # 打包后的 EXE 路径
            exe_path = os.path.abspath(sys.executable)
            cmd = f'"{exe_path}"'
        else:
            # Python 脚本调试环境
            py_exe = os.path.abspath(sys.executable)
            # 如果是 pythonw 更好（无控制台）
            pyw_exe = os.path.join(os.path.dirname(py_exe), "pythonw.exe")
            runner = pyw_exe if os.path.exists(pyw_exe) else py_exe
            script = os.path.abspath(sys.argv[0])
            cmd = f'"{runner}" "{script}"'

        if silent:
            cmd += " --hide"
        return cmd

    @classmethod
    def is_auto_start_enabled(cls) -> bool:
        """检查当前是否已注册开机自启"""
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ) as k:
                val, _ = winreg.QueryValueEx(k, cls.REG_KEY_NAME)
                return bool(val)
        except Exception:
            return False

    @classmethod
    def set_auto_start(cls, enable: bool, silent: bool = True) -> tuple:
        """
        开启或关闭开机自启
        :param enable: True 为开启，False 为关闭
        :param silent: True 为静默隐藏启动 (--hide)
        :return: (ok: bool, msg: str)
        """
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as k:
                if enable:
                    cmd = cls.get_executable_command(silent=silent)
                    winreg.SetValueEx(k, cls.REG_KEY_NAME, 0, winreg.REG_SZ, cmd)
                    return True, f"已启用开机自启: {cmd}"
                else:
                    try:
                        winreg.DeleteValue(k, cls.REG_KEY_NAME)
                    except FileNotFoundError:
                        pass
                    return True, "已成功取消开机自启"
        except Exception as e:
            return False, f"配置开机自启失败: {e}"


class ConfigManager:
    """受控端持久化配置文件管理器"""

    DEFAULT_CONFIG = {
        "auto_start": True,
        "silent_boot": True,
        "hotkey": "Ctrl+Q",
        "master_ip": "127.0.0.1",
        "master_port": 9888,
        "agent_port": 9888,
        "enable_vnc": True,
        "auto_connect_on_discover": True,
        "minimize_to_tray": True
    }

    @classmethod
    def get_config_path(cls) -> str:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_dir, "agent_config.json")

    @classmethod
    def load_config(cls) -> dict:
        p = cls.get_config_path()
        cfg = cls.DEFAULT_CONFIG.copy()
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    user_cfg = json.load(f)
                    cfg.update(user_cfg)
            except Exception:
                pass
        return cfg

    @classmethod
    def save_config(cls, cfg: dict) -> bool:
        p = cls.get_config_path()
        try:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False
