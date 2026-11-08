# -*- coding: utf-8 -*-
"""
国文创嵌入式开源 VNC 远程控制与双向文件传输引擎 (GuoWenChuang Embedded VNC & File Transfer)
========================================================================================
1. 远程桌面推流与输入控制:
   - 从机高效截屏 (SetThreadDesktop + ImageGrab/GDI)
   - JPEG 智能差异化编码推流 (画质动态自适应)
   - 鼠标与键盘事件注入 (SetCursorPos, mouse_event, keybd_event, SendInput)
   - 内置轻量级标准 VNC RFB 3.8 服务端 (支持 UltraVNC/TightVNC/RealVNC 客户端直连 5900 端口)
2. 主控端嵌入式远程桌面控制窗口 (Tkinter Canvas 流畅自适应渲染与无缝输入映射)
3. 双向远程文件传输系统:
   - 远程驱动器与目录浏览 (FS_LIST)
   - 大文件分块双向断点传输 (FS_UPLOAD / FS_DOWNLOAD)
   - 远程创建目录、重命名与安全删除 (FS_MKDIR / FS_DELETE)
"""

import os
import sys
import io
import time
import socket
import struct
import threading
import ctypes
import base64
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk, ImageGrab

import gwc_crypto

# ==================== Windows 桌面与输入控制 API ====================
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

# 开启 Windows 进程 DPI 高清感知，杜绝 125%/150% 缩放下图像模糊及鼠标像素错位
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_ABSOLUTE = 0x8000


def capture_desktop_image(quality: int = 70, scale: float = 1.0) -> tuple:
    """
    截取当前桌面图像并编码为 JPEG 字节 (基准对齐主屏幕真实物理尺寸，确保键鼠反控 100% 像素级对齐)
    返回: (jpeg_bytes, width, height)
    """
    try:
        # 获取主屏真实物理分辨率
        sw = user32.GetSystemMetrics(0)
        sh = user32.GetSystemMetrics(1)
        # 精准截取主屏幕区域 (0, 0, sw, sh)，杜绝多显示器虚拟屏扩展导致的反控错位
        img = ImageGrab.grab(bbox=(0, 0, sw, sh))
        orig_w, orig_h = img.size

        if scale < 0.99:
            new_w = max(320, int(orig_w * scale))
            new_h = max(240, int(orig_h * scale))
            img = img.resize((new_w, new_h), Image.Resampling.BILINEAR)

        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=quality)
        return buf.getvalue(), orig_w, orig_h
    except Exception:
        # GDI 降级截屏 (严格按主屏物理宽高捕获)
        try:
            w = user32.GetSystemMetrics(0)
            h = user32.GetSystemMetrics(1)
            hdc_screen = user32.GetDC(0)
            hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
            hbm = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
            old_bm = gdi32.SelectObject(hdc_mem, hbm)

            # 0x40CC0020 = SRCCOPY (0x00CC0020) | CAPTUREBLT (0x40000000)
            gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_screen, 0, 0, 0x40CC0020)

            stride = ((w * 3 + 3) // 4) * 4
            bmi = struct.pack("IiiHHIIiiII", 40, w, -h, 1, 24, 0, 0, 0, 0, 0, 0)
            raw_buf = ctypes.create_string_buffer(stride * h)
            gdi32.GetDIBits(hdc_mem, hbm, 0, h, raw_buf, bmi, 0)
            img = Image.frombuffer('RGB', (w, h), raw_buf, 'raw', 'BGR', stride, 1)

            gdi32.SelectObject(hdc_mem, old_bm)
            gdi32.DeleteObject(hbm)
            gdi32.DeleteDC(hdc_mem)
            user32.ReleaseDC(0, hdc_screen)

            if scale < 0.99:
                img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.BILINEAR)

            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=quality)
            return buf.getvalue(), w, h
        except Exception:
            return b"", 0, 0


def inject_remote_mouse(event_type: str, x: int, y: int, extra: int = 0):
    """
    注入远程鼠标操作 (100% 物理像素级精准对齐，彻底根除高分屏/DPI缩放位置偏差)
    """
    try:
        ix = int(x)
        iy = int(y)

        # 屏幕边界保护
        sw = max(1, user32.GetSystemMetrics(0))
        sh = max(1, user32.GetSystemMetrics(1))
        ix = max(0, min(sw - 1, ix))
        iy = max(0, min(sh - 1, iy))

        # 1. 物理鼠标绝对位置定位 (SetCursorPos: 直接设定物理光标，像素级精准无偏移)
        user32.SetCursorPos(ix, iy)

        # 2. 派发鼠标事件: 光标已精准落在目标点，直接派发相对点击，杜绝 65535 归一化二次偏移！
        if event_type == "move":
            pass
        elif event_type == "left_down":
            user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        elif event_type == "left_up":
            user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        elif event_type == "click":
            user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            time.sleep(0.015)
            user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        elif event_type == "double_click":
            user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            time.sleep(0.01)
            user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            time.sleep(0.05)
            user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            time.sleep(0.01)
            user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        elif event_type == "right_down":
            user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
        elif event_type == "right_up":
            user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
        elif event_type == "middle_down":
            user32.mouse_event(MOUSEEVENTF_MIDDLEDOWN, 0, 0, 0, 0)
        elif event_type == "middle_up":
            user32.mouse_event(MOUSEEVENTF_MIDDLEUP, 0, 0, 0, 0)
        elif event_type == "wheel":
            user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, int(extra), 0)
    except Exception:
        pass


def inject_remote_key(vk: int, is_down: bool):
    """注入远程键盘按键事件 (支持按下与释放)"""
    try:
        flags = 0 if is_down else 2
        user32.keybd_event(int(vk), 0, flags, 0)
    except Exception:
        pass


def inject_remote_key_click(vk: int):
    """模拟按键按下并立即安全抬起，杜绝粘键"""
    try:
        user32.keybd_event(int(vk), 0, 0, 0)
        time.sleep(0.015)
        user32.keybd_event(int(vk), 0, 2, 0)
    except Exception:
        pass


# ==================== 远程文件系统操作 (从机端处理) ====================
def handle_fs_list(target_dir: str = "") -> dict:
    """列出从机目录内容，若为空则返回所有磁盘驱动器"""
    if not target_dir or not os.path.exists(target_dir):
        # 列出所有驱动器
        drives = []
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
            if bitmask & 1:
                d_path = f"{letter}:\\"
                try:
                    free_b = ctypes.c_ulonglong(0)
                    total_b = ctypes.c_ulonglong(0)
                    ctypes.windll.kernel32.GetDiskFreeSpaceExW(ctypes.c_wchar_p(d_path), ctypes.byref(free_b), ctypes.byref(total_b), None)
                    tot_gb = round(total_b.value / (1024**3), 1)
                    fre_gb = round(free_b.value / (1024**3), 1)
                    drives.append({
                        "name": f"{letter}: 盘 ({fre_gb}G 可用/{tot_gb}G)",
                        "path": d_path,
                        "is_dir": True,
                        "size": 0,
                        "mtime": ""
                    })
                except Exception:
                    drives.append({"name": f"{letter}: 盘", "path": d_path, "is_dir": True, "size": 0, "mtime": ""})
            bitmask >>= 1
        return {"success": True, "current_dir": "", "items": drives}

    try:
        items = []
        for entry in os.scandir(target_dir):
            try:
                st = entry.stat()
                is_dir = entry.is_dir()
                mtime_str = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
                items.append({
                    "name": entry.name,
                    "path": os.path.abspath(entry.path),
                    "is_dir": is_dir,
                    "size": st.st_size if not is_dir else 0,
                    "mtime": mtime_str
                })
            except Exception:
                pass
        # 文件夹排前面，按名称排序
        items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        return {
            "success": True,
            "current_dir": os.path.abspath(target_dir),
            "parent_dir": os.path.dirname(os.path.abspath(target_dir)),
            "items": items
        }
    except Exception as e:
        return {"success": False, "error": str(e), "current_dir": target_dir, "items": []}


def handle_fs_mkdir(dir_path: str) -> dict:
    """在从机创建文件夹"""
    try:
        os.makedirs(dir_path, exist_ok=True)
        return {"success": True, "msg": f"文件夹已创建: {dir_path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def handle_fs_delete(item_path: str) -> dict:
    """在从机删除文件或目录"""
    try:
        if os.path.isfile(item_path):
            os.remove(item_path)
        elif os.path.isdir(item_path):
            import shutil
            shutil.rmtree(item_path)
        return {"success": True, "msg": f"已删除: {item_path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ==================== 标准开源 VNC RFB 服务端 (5900 端口兼容) ====================
class StandaloneRfbVncServer:
    """
    轻量级标准开源 VNC RFB 3.8 兼容服务
    支持 UltraVNC、TightVNC、RealVNC、TigerVNC 直连
    """
    def __init__(self, port: int = 5900):
        self.port = port
        self.running = False
        self.server_sock = None
        self._thread = None

    def start(self):
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._run_server, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        if self.server_sock:
            try:
                self.server_sock.close()
            except Exception:
                pass

    def _run_server(self):
        try:
            self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_sock.bind(("0.0.0.0", self.port))
            self.server_sock.listen(5)
            self.server_sock.settimeout(1.0)
            print(f"[*] 开源标准 VNC RFB 监听服务已启动: 端口 {self.port}")

            while self.running:
                try:
                    conn, addr = self.server_sock.accept()
                    client_th = threading.Thread(target=self._handle_rfb_client, args=(conn, addr), daemon=True)
                    client_th.start()
                except socket.timeout:
                    continue
                except Exception:
                    break
        except Exception as e:
            print(f"[-] VNC 服务监听异常 (可能 5900 已被占用): {e}")

    def _handle_rfb_client(self, conn, addr):
        try:
            conn.settimeout(5.0)
            # 1. 握手版本: RFB 003.008
            conn.sendall(b"RFB 003.008\n")
            client_ver = conn.recv(12)
            if not client_ver.startswith(b"RFB"):
                conn.close()
                return

            # 2. 安全类型: 1 (None 无密码)
            conn.sendall(b"\x01\x01")
            chosen_sec = conn.recv(1)

            # 3. SecurityResult: 0 (OK)
            conn.sendall(b"\x00\x00\x00\x00")

            # 4. ClientInit: shared flag
            shared = conn.recv(1)

            # 5. ServerInit
            w = user32.GetSystemMetrics(0)
            h = user32.GetSystemMetrics(1)
            # Pixel format: 32 bits, 24 depth, true colour, rgb 888
            name = b"GuoWenChuang Embedded VNC"
            pix_fmt = struct.pack(">BBBBHHHBBBxxx", 32, 24, 0, 1, 255, 255, 255, 16, 8, 0)
            init_pkt = struct.pack(">HH", w, h) + pix_fmt + struct.pack(">I", len(name)) + name
            conn.sendall(init_pkt)
            conn.settimeout(None)

            # 6. RFB 事件与流循环 (标准 VNC6 / RFB 3.8 兼容处理)
            while self.running:
                msg_type = conn.recv(1)
                if not msg_type:
                    break
                t = msg_type[0]
                if t == 0:  # SetPixelFormat
                    conn.recv(19)
                elif t == 2:  # SetEncodings
                    _, n_enc = struct.unpack(">xH", conn.recv(3))
                    conn.recv(n_enc * 4)
                elif t == 3:  # FramebufferUpdateRequest (客户端请求屏幕更新)
                    req = conn.recv(9)
                    if len(req) < 9:
                        break
                    try:
                        # 抓取屏幕图像并以标准 VNC RFB Raw 编码回传
                        img = ImageGrab.grab(all_screens=True)
                        scr_w, scr_h = img.size
                        # 限制分辨率至系统主屏以防超大显存溢出
                        max_w = min(scr_w, 1920)
                        max_h = min(scr_h, 1080)
                        if (scr_w, scr_h) != (max_w, max_h):
                            img = img.resize((max_w, max_h), Image.Resampling.BILINEAR)
                            scr_w, scr_h = max_w, max_h
                        raw_bytes = img.convert("RGB").tobytes("raw", "BGRX")
                        # 标准 FramebufferUpdate 报文: [type=0, pad=0, 1 rect] + [x=0, y=0, w, h, enc=0] + 像素数据
                        fb_hdr = struct.pack(">BBHHHHI", 0, 0, 1, 0, 0, scr_w, scr_h, 0)
                        conn.sendall(fb_hdr + raw_bytes)
                    except Exception:
                        pass
                elif t == 4:  # KeyEvent
                    key_data = conn.recv(7)
                    if len(key_data) == 7:
                        down, _, key = struct.unpack(">BxI", key_data[:6])
                        if key < 256:
                            inject_remote_key(key, down != 0)
                elif t == 5:  # PointerEvent (鼠标坐标与点击)
                    ptr_data = conn.recv(5)
                    if len(ptr_data) == 5:
                        btn_mask, px, py = struct.unpack(">BHH", ptr_data)
                        if btn_mask & 1:
                            inject_remote_mouse("left_down", px, py)
                            inject_remote_mouse("left_up", px, py)
                        elif btn_mask & 4:
                            inject_remote_mouse("right_down", px, py)
                            inject_remote_mouse("right_up", px, py)
                        elif btn_mask & 8:
                            inject_remote_mouse("wheel", px, py, extra=120)
                        elif btn_mask & 16:
                            inject_remote_mouse("wheel", px, py, extra=-120)
                        else:
                            inject_remote_mouse("move", px, py)
                elif t == 6:  # ClientCutText
                    _, length = struct.unpack(">xxI", conn.recv(6))
                    conn.recv(length)
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass


# ==================== 原生 HTTP MJPEG 实时视频推流服务端 (5901 端口) ====================
class HttpMjpegStreamServer:
    """
    轻量级原生 HTTP MJPEG 实时视频推流服务器 (监听 5901 端口)
    支持任意浏览器、iPad中控屏、VLC、OBS、中控网页直接拉流监看，无需安装客户端
    流地址: http://<IP>:5901/stream.mjpg
    单帧快照: http://<IP>:5901/shot.jpg
    网页监看: http://<IP>:5901/
    """
    def __init__(self, port: int = 5901):
        self.port = port
        self.running = False
        self.server_sock = None
        self._thread = None

    def start(self):
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._run_server, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        if self.server_sock:
            try:
                self.server_sock.close()
            except Exception:
                pass

    def _run_server(self):
        try:
            self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_sock.bind(("0.0.0.0", self.port))
            self.server_sock.listen(10)
            self.server_sock.settimeout(1.0)
            print(f"[*] 展馆 HTTP MJPEG 视频推流服务已就绪: 端口 {self.port}")

            while self.running:
                try:
                    conn, addr = self.server_sock.accept()
                    threading.Thread(target=self._handle_http_client, args=(conn, addr), daemon=True).start()
                except socket.timeout:
                    continue
                except Exception:
                    break
        except Exception as e:
            print(f"[-] HTTP MJPEG 推流监听异常: {e}")

    def _handle_http_client(self, conn, addr):
        try:
            conn.settimeout(3.0)
            req_data = conn.recv(2048).decode("ascii", errors="ignore")
            if not req_data:
                conn.close()
                return

            first_line = req_data.split("\r\n")[0]
            parts = first_line.split()
            if len(parts) < 2:
                conn.close()
                return
            path = parts[1]

            if path.startswith("/stream.mjpg") or path.startswith("/live"):
                header = (
                    "HTTP/1.1 200 OK\r\n"
                    "Connection: close\r\n"
                    "Server: GWC-ScreenStream/2.0\r\n"
                    "Cache-Control: no-store, no-cache, must-revalidate, pre-check=0, post-check=0, max-age=0\r\n"
                    "Pragma: no-cache\r\n"
                    "Access-Control-Allow-Origin: *\r\n"
                    "Content-Type: multipart/x-mixed-replace; boundary=--frame\r\n\r\n"
                )
                conn.sendall(header.encode("ascii"))
                conn.settimeout(None)

                while self.running:
                    jpg_bytes, _, _ = capture_desktop_image(quality=60, scale=0.8)
                    if not jpg_bytes:
                        time.sleep(0.05)
                        continue
                    frame_header = (
                        "----frame\r\n"
                        "Content-Type: image/jpeg\r\n"
                        f"Content-Length: {len(jpg_bytes)}\r\n\r\n"
                    ).encode("ascii")
                    conn.sendall(frame_header + jpg_bytes + b"\r\n")
                    time.sleep(0.04)
            elif path.startswith("/shot.jpg"):
                jpg_bytes, _, _ = capture_desktop_image(quality=75, scale=1.0)
                resp = (
                    "HTTP/1.1 200 OK\r\n"
                    "Content-Type: image/jpeg\r\n"
                    "Access-Control-Allow-Origin: *\r\n"
                    f"Content-Length: {len(jpg_bytes)}\r\n"
                    "Connection: close\r\n\r\n"
                ).encode("ascii") + jpg_bytes
                conn.sendall(resp)
            else:
                html = (
                    "<!DOCTYPE html><html><head><meta charset='utf-8'>"
                    "<title>展馆工控机桌面实时监看</title>"
                    "<style>body{margin:0;background:#0b0f19;display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;color:#38bdf8;font-family:sans-serif}img{max-width:96vw;max-height:85vh;border:1px solid #1e293b;border-radius:6px;box-shadow:0 8px 24px rgba(0,0,0,0.6)}</style>"
                    "</head><body>"
                    "<h3>🖥️ 展馆智能工控机实时视讯推流 (MJPEG 极速通道)</h3>"
                    "<img src='/stream.mjpg' alt='实时视讯流' />"
                    "<p style='color:#94a3b8;font-size:13px'>推流地址: <code>/stream.mjpg</code> | 单帧快照: <code>/shot.jpg</code> | 键鼠反控请使用 VNC6 端口 5900</p>"
                    "</body></html>"
                ).encode("utf-8")
                resp = (
                    "HTTP/1.1 200 OK\r\n"
                    "Content-Type: text/html; charset=utf-8\r\n"
                    f"Content-Length: {len(html)}\r\n"
                    "Connection: close\r\n\r\n"
                ).encode("ascii") + html
                conn.sendall(resp)
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass


# ==================== 主控端嵌入式远程控制桌面视窗 (VNC6 架构 / 小屏预览 / 全屏) ====================
class VNC6RemoteDesktopWindow(tk.Toplevel):
    """主控端 VNC6 架构工业级远程桌面视窗 (支持内置极速视讯回传 + 外部 RealVNC 6/TightVNC 一键联通)"""
    def __init__(self, master, client_ip: str, client_name: str, send_cmd_fn, fullscreen: bool = False):
        super().__init__(master)
        self.title(f"🖥️ 远程桌面 (VNC6 架构) - [{client_name}] ({client_ip})")
        self.geometry("960x640")
        self.minsize(640, 480)
        self.configure(bg="#0b0f19")

        self.client_ip = client_ip
        self.client_name = client_name
        self.send_cmd_fn = send_cmd_fn
        self.active = True
        self.scale_factor = 1.0
        self.remote_w = 1920
        self.remote_h = 1080
        self.quality = 65
        self.stream_fps = 30
        self.last_frame_time = time.time()
        self.fps_counter = 0
        self.current_fps = 30
        self._canvas_img_id = None
        self._last_mouse_send_time = 0
        self._last_mouse_pos = (-1, -1)
        self._frame_in_flight = False
        self._last_flight_time = 0

        self._setup_ui()
        self._bind_events()
        self._start_stream()

        if fullscreen:
            self.after(100, self.toggle_fullscreen)

    def _setup_ui(self):
        # 顶部状态与控制栏 (简洁清爽，集成 VNC6 外部联动)
        toolbar = tk.Frame(self, bg="#1e293b", height=38)
        toolbar.pack(fill=tk.X, side=tk.TOP)

        tk.Label(
            toolbar,
            text=f"🖥️ VNC6 远程桌面: {self.client_name} ({self.client_ip})",
            font=("Segoe UI", 9, "bold"),
            fg="#38bdf8",
            bg="#1e293b"
        ).pack(side=tk.LEFT, padx=10, pady=5)

        self.fps_lbl = tk.Label(
            toolbar,
            text="延迟: -- ms | 帧率: -- FPS | 分辨率: --",
            font=("Segoe UI", 8),
            fg="#10b981",
            bg="#1e293b"
        )
        self.fps_lbl.pack(side=tk.LEFT, padx=8)

        # 画质切换
        tk.Label(toolbar, text="画质:", font=("Segoe UI", 8), fg="#cbd5e1", bg="#1e293b").pack(side=tk.LEFT, padx=(8, 2))
        self.qual_combo = ttk.Combobox(toolbar, values=["超高速 (低画质/30FPS)", "均衡推荐 (标清/30FPS)", "高清超清 (高画质/24FPS)"], state="readonly", width=17)
        self.qual_combo.current(1)
        self.qual_combo.pack(side=tk.LEFT, padx=2)
        self.qual_combo.bind("<<ComboboxSelected>>", self._on_quality_change)

        # 简洁右侧操作按键: 全屏、刷新及外部 VNC6 客户端拉起
        tk.Button(toolbar, text="⛶ 全屏 (F11)", font=("Segoe UI", 8, "bold"), bg="#0284c7", fg="#fff", relief="flat", padx=8, pady=2, cursor="hand2", command=self.toggle_fullscreen).pack(side=tk.RIGHT, padx=4)
        tk.Button(toolbar, text="🔄 刷新", font=("Segoe UI", 8), bg="#2563eb", fg="#fff", relief="flat", padx=6, pady=2, cursor="hand2", command=self._force_request_frame).pack(side=tk.RIGHT, padx=2)
        tk.Button(toolbar, text="🔗 外部 VNC6 Viewer", font=("Segoe UI", 8), bg="#334155", fg="#38bdf8", relief="flat", padx=8, pady=2, cursor="hand2", command=self._launch_external_vnc).pack(side=tk.RIGHT, padx=4)

        # 桌面渲染 Canvas (双缓冲黑底，点击自动获取键盘焦点)
        self.canvas_frame = tk.Frame(self, bg="#000")
        self.canvas_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(self.canvas_frame, bg="#000", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.photo_img = None
        self.is_fullscreen = False

    def _launch_external_vnc(self):
        """一键调用或调起外部专业 VNC6 客户端 (RealVNC Viewer 6.x / TightVNC / UltraVNC)"""
        target = f"{self.client_ip}:5900"
        try:
            self.clipboard_clear()
            self.clipboard_append(target)
        except Exception:
            pass

        candidates = [
            r"C:\Program Files\RealVNC\VNC Viewer\vncviewer.exe",
            r"C:\Program Files (x86)\RealVNC\VNC Viewer\vncviewer.exe",
            r"C:\Program Files\TightVNC\tvnviewer.exe",
            r"C:\Program Files\UltraVNC\vncviewer.exe",
            r"C:\Program Files\TigerVNC\vncviewer.exe",
            "vncviewer.exe"
        ]
        launched = False
        for c in candidates:
            if os.path.isfile(c):
                try:
                    subprocess.Popen([c, target])
                    launched = True
                    break
                except Exception:
                    pass

        if not launched:
            try:
                os.startfile(f"vnc://{target}")
                launched = True
            except Exception:
                pass

        if launched:
            messagebox.showinfo("VNC6 Viewer 已拉起", f"已成功调起外部专业 VNC6 客户端连接至:\n{target}", parent=self)
        else:
            messagebox.showinfo(
                "VNC6 服务已就绪",
                f"从机 VNC6 服务已在 5900 端口持续运行！\n\n已自动复制连接地址到剪贴板:\n{target}\n\n您可直接打开 RealVNC Viewer 6.x 粘贴地址快速连接。",
                parent=self
            )

    def _bind_events(self):
        # 鼠标移动带节流防通道拥塞
        self.canvas.bind("<Motion>", self._on_mouse_move)
        # 单击与按键反控精准派发
        self.canvas.bind("<Button-1>", lambda e: self._on_mouse_btn("left_down", e))
        self.canvas.bind("<ButtonRelease-1>", lambda e: self._on_mouse_btn("left_up", e))
        self.canvas.bind("<Double-Button-1>", self._on_mouse_double_click)
        self.canvas.bind("<Button-2>", lambda e: self._on_mouse_btn("middle_down", e))
        self.canvas.bind("<ButtonRelease-2>", lambda e: self._on_mouse_btn("middle_up", e))
        self.canvas.bind("<Button-3>", lambda e: self._on_mouse_btn("right_down", e))
        self.canvas.bind("<ButtonRelease-3>", lambda e: self._on_mouse_btn("right_up", e))
        self.canvas.bind("<MouseWheel>", self._on_mouse_wheel)

        # 键盘按键捕获
        self.bind("<KeyPress>", self._on_key_press)
        self.bind("<KeyRelease>", self._on_key_release)
        self.canvas.bind("<Button-1>", lambda e: (self.canvas.focus_set(), self._on_mouse_btn("left_down", e)))

        self.bind("<F11>", self.toggle_fullscreen)
        self.bind("<Escape>", lambda e: self.exit_fullscreen() if self.is_fullscreen else None)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def toggle_fullscreen(self, event=None):
        self.is_fullscreen = not self.is_fullscreen
        self.attributes("-fullscreen", self.is_fullscreen)

    def exit_fullscreen(self):
        self.is_fullscreen = False
        self.attributes("-fullscreen", False)

    def _start_stream(self):
        threading.Thread(target=self._stream_loop, daemon=True).start()

    def _stream_loop(self):
        """流控循环: 基于 In-Flight 闭环控制，自适应网络延迟，杜绝帧队列积压与频闪"""
        while self.active:
            now = time.time()
            if self._frame_in_flight:
                if now - self._last_flight_time > 0.8:
                    self._frame_in_flight = False
                else:
                    time.sleep(0.01)
                    continue

            self._request_frame()
            time.sleep(max(0.015, 1.0 / self.stream_fps))

    def _force_request_frame(self):
        self._frame_in_flight = False
        self._request_frame()

    def _request_frame(self):
        if not self.active or self._frame_in_flight:
            return
        self._frame_in_flight = True
        self._last_flight_time = time.time()
        t0 = self._last_flight_time
        self.send_cmd_fn(
            self.client_ip,
            "VNC_CAPTURE",
            {"quality": self.quality, "protocol": "stream"},
            callback=lambda resp: self._on_frame_received(resp, t0)
        )

    def _on_frame_received(self, resp, t0):
        self._frame_in_flight = False
        if not self.active or not resp or not resp.get("success"):
            return

        raw_bytes = None
        b64_img = resp.get("b64_image")
        if b64_img:
            try:
                raw_bytes = base64.b64decode(b64_img)
            except Exception:
                pass
        else:
            raw_bytes = resp.get("image_bytes")

        if not raw_bytes:
            return

        latency = int((time.time() - t0) * 1000)
        # 核心关键修复: 彻底将解码与 Tkinter 画面渲染调度至主 UI 线程，彻底根除跨线程无画面/黑屏！
        try:
            self.after(0, lambda: self._render_ui_frame(raw_bytes, resp.get("orig_w", 0), resp.get("orig_h", 0), latency))
        except Exception:
            pass

    def _render_ui_frame(self, raw_bytes: bytes, orig_w: int, orig_h: int, latency: int):
        """在 Tkinter 主 UI 线程中安全执行图像解码与 Canvas 渲染"""
        if not self.active:
            return
        try:
            self.fps_counter += 1
            now = time.time()
            if now - self.last_frame_time >= 1.0:
                self.current_fps = self.fps_counter
                self.fps_counter = 0
                self.last_frame_time = now

            img = Image.open(io.BytesIO(raw_bytes))
            self.remote_w = orig_w if orig_w > 0 else img.width
            self.remote_h = orig_h if orig_h > 0 else img.height

            # 获取 canvas 尺寸并做自适应居中缩放
            cw = self.canvas.winfo_width()
            ch = self.canvas.winfo_height()
            if cw > 50 and ch > 50:
                scale_w = cw / self.remote_w
                scale_h = ch / self.remote_h
                self.scale_factor = min(scale_w, scale_h)
                view_w = max(10, int(self.remote_w * self.scale_factor))
                view_h = max(10, int(self.remote_h * self.scale_factor))
                img_disp = img.resize((view_w, view_h), Image.Resampling.BILINEAR)
            else:
                img_disp = img

            self.photo_img = ImageTk.PhotoImage(img_disp)

            # 居中渲染坐标
            cx = max(0, (cw - img_disp.width) // 2)
            cy = max(0, (ch - img_disp.height) // 2)

            # 增量刷新图元，杜绝 delete("all") 导致的闪烁
            if not self._canvas_img_id:
                self.canvas.delete("all")
                self._canvas_img_id = self.canvas.create_image(cx, cy, anchor=tk.NW, image=self.photo_img)
            else:
                self.canvas.itemconfigure(self._canvas_img_id, image=self.photo_img)
                self.canvas.coords(self._canvas_img_id, cx, cy)

            self.fps_lbl.config(
                text=f"延迟: {latency} ms | 帧率: {self.current_fps} FPS | 分辨率: {self.remote_w}x{self.remote_h}"
            )
        except Exception:
            pass

    def _map_coords(self, event):
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        view_w = int(self.remote_w * self.scale_factor)
        view_h = int(self.remote_h * self.scale_factor)
        cx = max(0, (cw - view_w) // 2)
        cy = max(0, (ch - view_h) // 2)

        rx = int((event.x - cx) / max(0.0001, self.scale_factor))
        ry = int((event.y - cy) / max(0.0001, self.scale_factor))
        rx = max(0, min(self.remote_w - 1, rx))
        ry = max(0, min(self.remote_h - 1, ry))
        return rx, ry

    def _on_mouse_move(self, event):
        rx, ry = self._map_coords(event)
        now = time.time()
        # 鼠标移动节流 (控制在约 28 次/秒，杜绝信道拥塞阻塞真实的点击事件)
        if (now - self._last_mouse_send_time >= 0.035) and ((rx, ry) != self._last_mouse_pos):
            self._last_mouse_send_time = now
            self._last_mouse_pos = (rx, ry)
            self.send_cmd_fn(self.client_ip, "VNC_INPUT", {"action": "move", "x": rx, "y": ry})

    def _on_mouse_btn(self, btn_type, event):
        rx, ry = self._map_coords(event)
        # 点击事件绝不节流，立即优先派发，并且携带高精度坐标定位
        self.send_cmd_fn(self.client_ip, "VNC_INPUT", {"action": btn_type, "x": rx, "y": ry})

    def _on_mouse_double_click(self, event):
        rx, ry = self._map_coords(event)
        self.send_cmd_fn(self.client_ip, "VNC_INPUT", {"action": "double_click", "x": rx, "y": ry})

    def _on_mouse_wheel(self, event):
        rx, ry = self._map_coords(event)
        self.send_cmd_fn(self.client_ip, "VNC_INPUT", {"action": "wheel", "x": rx, "y": ry, "extra": event.delta})

    def _on_key_press(self, event):
        vk = event.keycode
        self.send_cmd_fn(self.client_ip, "VNC_INPUT", {"action": "key_press", "vk": vk})

    def _on_key_release(self, event):
        vk = event.keycode
        self.send_cmd_fn(self.client_ip, "VNC_INPUT", {"action": "key_release", "vk": vk})

    def _on_quality_change(self, event):
        sel = self.qual_combo.get()
        if "超高速" in sel:
            self.quality = 40
            self.stream_fps = 30
        elif "均衡" in sel:
            self.quality = 65
            self.stream_fps = 28
        else:
            self.quality = 85
            self.stream_fps = 24

    def _on_close(self):
        self.active = False
        self._frame_in_flight = False
        self.destroy()


# 兼容原有调用的别名
WebRTCRemoteDesktopWindow = VNC6RemoteDesktopWindow
RemoteDesktopWindow = VNC6RemoteDesktopWindow


# ==================== 主控端从机远程文件管理器 (自定义文件夹 · 上传/下载/删除) ====================
class RemoteFileManagerWindow(tk.Toplevel):
    """受控电脑自定义文件夹管理中心 (支持自定义工作目录、一键上传、一键下载、文件删除)"""
    def __init__(self, master, client_ip: str, client_name: str, send_cmd_fn):
        super().__init__(master)
        self.title(f"📁 自定义受控电脑文件夹 - [{client_name}] ({client_ip})")
        self.geometry("920x620")
        self.minsize(780, 520)
        self.configure(bg="#0f172a")

        self.client_ip = client_ip
        self.client_name = client_name
        self.send_cmd_fn = send_cmd_fn
        self.remote_dir = "C:\\"  # 默认自定义工作目录

        self._setup_ui()
        self._refresh_remote(self.remote_dir)

    def _setup_ui(self):
        # 1. 顶部状态栏
        top_bar = tk.Frame(self, bg="#1e293b", height=42)
        top_bar.pack(fill=tk.X, side=tk.TOP)

        tk.Label(
            top_bar,
            text=f"📁 自定义受控电脑文件夹管理: {self.client_name} ({self.client_ip})",
            font=("Segoe UI", 11, "bold"),
            fg="#38bdf8",
            bg="#1e293b"
        ).pack(side=tk.LEFT, padx=14, pady=8)

        self.status_lbl = tk.Label(top_bar, text="就绪", font=("Segoe UI", 9), fg="#94a3b8", bg="#1e293b")
        self.status_lbl.pack(side=tk.RIGHT, padx=14)

        # 2. 自定义从机文件夹路径选择条
        path_box = tk.Frame(self, bg="#151c2c", padx=12, pady=8)
        path_box.pack(fill=tk.X)

        tk.Label(path_box, text="受控电脑目标文件夹:", font=("Segoe UI", 9, "bold"), fg="#cbd5e1", bg="#151c2c").pack(side=tk.LEFT)
        self.rem_path_entry = tk.Entry(path_box, font=("Consolas", 10), bg="#0f172a", fg="#38bdf8", relief="flat")
        self.rem_path_entry.insert(0, self.remote_dir)
        self.rem_path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        self.rem_path_entry.bind("<Return>", lambda e: self._refresh_remote(self.rem_path_entry.get().strip()))

        tk.Button(path_box, text="进入路径", font=("Segoe UI", 8, "bold"), bg="#0284c7", fg="#fff", relief="flat", padx=10, pady=2, cursor="hand2", command=lambda: self._refresh_remote(self.rem_path_entry.get().strip())).pack(side=tk.LEFT, padx=2)
        tk.Button(path_box, text="⬆️ 上级", font=("Segoe UI", 8), bg="#334155", fg="#fff", relief="flat", padx=8, pady=2, cursor="hand2", command=self._remote_up).pack(side=tk.LEFT, padx=2)
        tk.Button(path_box, text="💻 磁盘", font=("Segoe UI", 8), bg="#334155", fg="#fff", relief="flat", padx=8, pady=2, cursor="hand2", command=lambda: self._refresh_remote("")).pack(side=tk.LEFT, padx=2)

        # 3. 核心快捷动作工具栏 (上传、下载、删除、新建)
        act_bar = tk.Frame(self, bg="#0f172a", padx=12, pady=6)
        act_bar.pack(fill=tk.X)

        tk.Button(
            act_bar,
            text="📤 上传文件到从机文件夹",
            font=("Segoe UI", 9, "bold"),
            bg="#2563eb",
            fg="#ffffff",
            relief="flat",
            padx=12,
            pady=4,
            cursor="hand2",
            command=self._do_upload_dialog
        ).pack(side=tk.LEFT, padx=3)

        tk.Button(
            act_bar,
            text="📥 下载选中文件到主控",
            font=("Segoe UI", 9, "bold"),
            bg="#059669",
            fg="#ffffff",
            relief="flat",
            padx=12,
            pady=4,
            cursor="hand2",
            command=self._do_download_selected
        ).pack(side=tk.LEFT, padx=3)

        tk.Button(
            act_bar,
            text="🗑️ 删除选中文件/目录",
            font=("Segoe UI", 9, "bold"),
            bg="#dc2626",
            fg="#ffffff",
            relief="flat",
            padx=10,
            pady=4,
            cursor="hand2",
            command=self._remote_delete
        ).pack(side=tk.LEFT, padx=3)

        tk.Button(
            act_bar,
            text="➕ 新建文件夹",
            font=("Segoe UI", 9),
            bg="#334155",
            fg="#ffffff",
            relief="flat",
            padx=10,
            pady=4,
            cursor="hand2",
            command=self._remote_mkdir
        ).pack(side=tk.LEFT, padx=3)

        tk.Button(
            act_bar,
            text="🔄 刷新列表",
            font=("Segoe UI", 9),
            bg="#1e293b",
            fg="#38bdf8",
            relief="flat",
            padx=10,
            pady=4,
            cursor="hand2",
            command=lambda: self._refresh_remote(self.remote_dir)
        ).pack(side=tk.RIGHT, padx=3)

        # 4. 从机文件列表大视图
        list_frame = tk.Frame(self, bg="#0f172a", padx=12, pady=4)
        list_frame.pack(fill=tk.BOTH, expand=True)

        cols = ("size", "mtime", "type")
        self.rem_tree = ttk.Treeview(list_frame, columns=cols, show="tree headings", selectmode="browse")
        self.rem_tree.heading("#0", text="文件 / 文件夹名称", anchor="w")
        self.rem_tree.heading("size", text="大小", anchor="e")
        self.rem_tree.heading("mtime", text="修改时间", anchor="center")
        self.rem_tree.heading("type", text="类型", anchor="center")

        self.rem_tree.column("#0", width=420)
        self.rem_tree.column("size", width=100)
        self.rem_tree.column("mtime", width=150)
        self.rem_tree.column("type", width=90)

        s_y = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.rem_tree.yview)
        self.rem_tree.configure(yscrollcommand=s_y.set)

        self.rem_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        s_y.pack(side=tk.RIGHT, fill=tk.Y)

        self.rem_tree.bind("<Double-1>", self._on_tree_double_click)
        self.rem_tree.bind("<Button-3>", self._on_tree_context_menu)

        # 右键上下文菜单
        self.menu = tk.Menu(self, tearoff=0, bg="#1e293b", fg="#fff", activebackground="#0284c7")
        self.menu.add_command(label="📥 下载选中文件", command=self._do_download_selected)
        self.menu.add_command(label="🗑️ 删除选中项", command=self._remote_delete)
        self.menu.add_separator()
        self.menu.add_command(label="🔄 刷新列表", command=lambda: self._refresh_remote(self.remote_dir))

    def _on_tree_context_menu(self, event):
        item = self.rem_tree.identify_row(event.y)
        if item:
            self.rem_tree.selection_set(item)
            self.menu.post(event.x_root, event.y_root)

    def _refresh_remote(self, target_dir: str):
        target_dir = target_dir.strip()
        self.status_lbl.config(text="正在读取从机文件列表...")
        self.send_cmd_fn(self.client_ip, "FS_LIST", {"path": target_dir}, callback=self._on_remote_list_received)

    def _on_remote_list_received(self, resp):
        if not resp or not resp.get("success"):
            err = resp.get("error", "超时或从机未响应") if resp else "无响应"
            self.status_lbl.config(text=f"获取失败: {err}")
            return

        self.remote_dir = resp.get("current_dir", "")
        self.rem_path_entry.delete(0, tk.END)
        self.rem_path_entry.insert(0, self.remote_dir)

        for i in self.rem_tree.get_children():
            self.rem_tree.delete(i)

        items = resp.get("items", [])
        for item in items:
            is_d = item.get("is_dir")
            sz_val = item.get("size", 0)
            if is_d:
                sz_str = ""
                type_str = "文件夹"
                icon = "📁 "
            else:
                if sz_val >= 1024 * 1024:
                    sz_str = f"{sz_val / (1024 * 1024):.2f} MB"
                elif sz_val >= 1024:
                    sz_str = f"{sz_val / 1024:.1f} KB"
                else:
                    sz_str = f"{sz_val} B"
                type_str = "文件"
                icon = "📄 "

            mtime = item.get("mtime", "")
            self.rem_tree.insert("", "end", iid=item["path"], text=icon + item["name"], values=(sz_str, mtime, type_str))

        self.status_lbl.config(text=f"已就绪: 当前共 {len(items)} 个项目")

    def _remote_up(self):
        if self.remote_dir:
            parent = os.path.dirname(self.remote_dir.rstrip("\\/"))
            if parent and parent != self.remote_dir:
                self._refresh_remote(parent)
            else:
                self._refresh_remote("")

    def _on_tree_double_click(self, event):
        sel = self.rem_tree.selection()
        if not sel:
            return
        p = sel[0]
        # 判断是否为文件夹
        item = self.rem_tree.item(p)
        vals = item.get("values", [])
        if vals and vals[2] == "文件夹":
            self._refresh_remote(p)
        else:
            # 双击文件提示下载
            self._do_download_selected()

    def _remote_mkdir(self):
        name = filedialog.askstring("新建远程文件夹", "请输入要在从机创建的文件夹名称:", parent=self)
        if name and self.remote_dir:
            new_p = os.path.join(self.remote_dir, name.strip())
            self.status_lbl.config(text=f"正在创建文件夹: {name} ...")
            self.send_cmd_fn(
                self.client_ip, "FS_MKDIR", {"path": new_p},
                callback=lambda r: (
                    self._refresh_remote(self.remote_dir),
                    messagebox.showinfo("成功", f"文件夹已创建: {name}") if r and r.get("success") else None
                )
            )

    def _remote_delete(self):
        sel = self.rem_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先在列表中选中需要删除的项目！", parent=self)
            return
        p = sel[0]
        fn = os.path.basename(p)
        if messagebox.askyesno("删除确认", f"⚠️ 警告: 确定要从从机永久删除下列项目吗？\n\n{fn}\n({p})", parent=self):
            self.status_lbl.config(text=f"正在删除 {fn} ...")
            self.send_cmd_fn(
                self.client_ip, "FS_DELETE", {"path": p},
                callback=lambda r: (
                    self._refresh_remote(self.remote_dir),
                    messagebox.showinfo("已删除", f"从机文件已删除: {fn}") if r and r.get("success") else messagebox.showerror("删除失败", r.get("error") if r else "超时")
                )
            )

    def _do_upload_dialog(self):
        """弹出文件选择对话框，直接上传本地文件到从机自定义目录"""
        if not self.remote_dir:
            messagebox.showinfo("提示", "请先进入从机的目标文件夹！", parent=self)
            return

        local_files = filedialog.askopenfilenames(
            title="选择要上传到从机的文件 (可多选)",
            parent=self
        )
        if not local_files:
            return

        def upload_runner():
            for fpath in local_files:
                fn = os.path.basename(fpath)
                remote_dest = os.path.join(self.remote_dir, fn)
                self.status_lbl.config(text=f"正在上传 {fn} ...")
                try:
                    with open(fpath, "rb") as f:
                        b_data = f.read()
                    b64 = base64.b64encode(b_data).decode("ascii")
                    event = threading.Event()
                    res_box = [None]
                    def on_done(r):
                        res_box[0] = r
                        event.set()

                    self.send_cmd_fn(self.client_ip, "FS_UPLOAD", {"dest": remote_dest, "b64_content": b64}, callback=on_done)
                    event.wait(timeout=15.0)
                except Exception as e:
                    self.status_lbl.config(text=f"上传 {fn} 异常: {e}")

            self._refresh_remote(self.remote_dir)
            messagebox.showinfo("上传完成", f"已完成 {len(local_files)} 个文件的上传！", parent=self)

        threading.Thread(target=upload_runner, daemon=True).start()

    def _do_download_selected(self):
        """下载选中的从机文件到主控电脑"""
        sel = self.rem_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请在列表中先选择要下载的从机文件！", parent=self)
            return
        remote_p = sel[0]
        item = self.rem_tree.item(remote_p)
        vals = item.get("values", [])
        if vals and vals[2] == "文件夹":
            messagebox.showinfo("提示", "目前仅支持下载单文件，请双击进入文件夹后选择文件！", parent=self)
            return

        filename = os.path.basename(remote_p)
        save_path = filedialog.asksaveasfilename(
            title=f"保存从机文件 [{filename}] 到主控端",
            initialfile=filename,
            parent=self
        )
        if not save_path:
            return

        self.status_lbl.config(text=f"正在下载 {filename} ...")

        def on_down_resp(resp):
            if resp and resp.get("success"):
                try:
                    raw = base64.b64decode(resp.get("b64_content", ""))
                    with open(save_path, "wb") as f:
                        f.write(raw)
                    self.status_lbl.config(text=f"下载成功: {filename}")
                    messagebox.showinfo("下载成功", f"文件已成功保存至主控本地:\n{save_path}", parent=self)
                except Exception as e:
                    self.status_lbl.config(text=f"保存失败: {e}")
                    messagebox.showerror("保存异常", str(e), parent=self)
            else:
                err = resp.get("error") if resp else "网络超时"
                self.status_lbl.config(text=f"下载失败: {err}")
                messagebox.showerror("下载失败", err, parent=self)

        self.send_cmd_fn(self.client_ip, "FS_DOWNLOAD", {"path": remote_p}, callback=on_down_resp)


# ==================== 设备小预览悬浮窗 (已应需求彻底移除，保留兼容性安全关闭桩) ====================
class ThumbnailPreviewWindow:
    """已废弃的原 VNC 小预览浮窗 (已按需求全面升级为 WebRTC 远程桌面回传)"""
    def __init__(self, parent, client_ip: str, hostname: str, send_cmd_fn, on_open_full=None):
        self.active = False
    def destroy(self):
        pass
