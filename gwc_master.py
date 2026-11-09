# -*- coding: utf-8 -*-
"""
国文创展馆主控综合管理集群中心 (GuoWenChuang Master Controller Hub)
================================================================
1. 多工控机 TCP 加密并发监听与长连接会话池 (监听 9888 端口)
2. 实时感知全展馆工控机状态 (CPU/内存/磁盘/网络速率/活动窗口/授权状态)
3. 远程协同控制指令调度中心:
   - 单机/批量远程关机、重启
   - 远程主音量精准数值调节与静音切换
   - 远程应用调用 (路径/参数/工作目录)
   - 远程强杀异常进程
4. 嵌入式远程桌面 VNC 与双向文件传输会话映射
5. 备份中心集中归档与远程下发恢复引擎
6. 国文创商业授权中枢 (远程一键授权签发与下发核销)
"""

import os
import sys
import time
import socket
import select
import threading
import json
import base64
import uuid
import shutil
from datetime import datetime

import gwc_crypto
import gwc_backup
import gwc_discovery

try:
    import universal_license_core
except ImportError:
    universal_license_core = None


def get_master_data_dir() -> str:
    """获取主控端专属顶级数据文件夹 GWC_Master_Data (规范归档所有生成文件，绝不乱放)"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if getattr(sys, "frozen", False):
        base_dir = os.path.dirname(os.path.abspath(sys.executable))
    d = os.path.join(base_dir, "GWC_Master_Data")
    os.makedirs(d, exist_ok=True)
    return d


def get_master_backup_dir() -> str:
    """获取主控端系统镜像与备份存储目录 (归档于 GWC_Master_Data/Backups)"""
    d = os.path.join(get_master_data_dir(), "Backups")
    os.makedirs(d, exist_ok=True)
    return d


def get_master_config_dir() -> str:
    """获取主控端配置目录 (归档于 GWC_Master_Data/Configs)"""
    d = os.path.join(get_master_data_dir(), "Configs")
    os.makedirs(d, exist_ok=True)
    return d

MASTER_DEFAULT_PORT = 9888


class GwcMasterHub:
    def __init__(self, port: int = MASTER_DEFAULT_PORT, backup_store_dir: str = None):
        self.port = port
        self.running = False
        self.server_sock = None
        self._server_thread = None

        # 客户端映射: ip -> {"sock": s, "info": dict, "last_seen": ts, "addr": tuple}
        self.clients = {}
        self.clients_lock = threading.Lock()

        # 局域网在线受控端搜索与发现器
        self.discoverer = gwc_discovery.MasterDiscoverer(port=gwc_discovery.DISCOVERY_PORT)

        # 待响应请求回调映射: req_id -> callback
        self.pending_callbacks = {}
        self.callbacks_lock = threading.Lock()

        # 事件回调钩子 (供外部 GUI 订阅)
        self.on_agent_connected = None
        self.on_agent_disconnected = None
        self.on_status_updated = None
        self.on_backup_saved = None

        # 主控系统镜像与备份归档根目录 (统一收纳于 GWC_Master_Data/Backups，规范收纳不乱放)
        if not backup_store_dir:
            self.backup_store_dir = get_master_backup_dir()
        else:
            self.backup_store_dir = backup_store_dir
        os.makedirs(self.backup_store_dir, exist_ok=True)

        # 自动迁移旧目录中的备份文件至专属目录 (GWC_Master_Backups / master_backups)
        base_d = os.path.dirname(os.path.abspath(__file__))
        if getattr(sys, "frozen", False):
            base_d = os.path.dirname(os.path.abspath(sys.executable))
        for old_dir_name in ["GWC_Master_Backups", "master_backups"]:
            old_d = os.path.join(base_d, old_dir_name)
            if os.path.isdir(old_d) and os.path.abspath(old_d) != os.path.abspath(self.backup_store_dir):
                try:
                    for old_f in os.listdir(old_d):
                        if old_f.lower().endswith((".gwcsysimg", ".gwcbackup")):
                            src = os.path.join(old_d, old_f)
                            dst = os.path.join(self.backup_store_dir, old_f)
                            if not os.path.exists(dst):
                                shutil.copy2(src, dst)
                                try: os.remove(src)
                                except Exception: pass
                    if not os.listdir(old_d):
                        try: os.rmdir(old_d)
                        except Exception: pass
                except Exception:
                    pass

        # 展馆第三方智能中控多协议总线调度监听接口 (UDP:9889 | TCP:9890 | HTTP API:9891 | 串口COM)
        self.udp_control_port = 9889
        self.tcp_control_port = 9890
        self.http_control_port = 9891
        self.serial_port_name = ""
        self.serial_baudrate = 9600

        self.udp_controller = UdpCentralControlListener(self, port=self.udp_control_port)
        self.tcp_controller = TcpCentralControlListener(self, port=self.tcp_control_port)
        self.http_controller = HttpCentralControlServer(self, port=self.http_control_port)
        self.serial_controller = SerialCentralControlListener(self)

        self.on_central_control_event = None
        self.on_udp_command_received = None  # 兼容旧回调属性

    def start(self):
        """启动主控监听服务 (TCP 集群监听 + 外部智能中控全协议 UDP/TCP/HTTP 调度服务)"""
        if self.running:
            return
        self.running = True
        self._server_thread = threading.Thread(target=self._server_listen_loop, daemon=True)
        self._server_thread.start()

        # 启动外部智能中控 UDP/TCP/HTTP 调度总线
        self.udp_controller.start()
        self.tcp_controller.start()
        self.http_controller.start()

        print(f"[*] 展馆智能集群管控中枢已就绪: 集群通信 TCP {self.port} | 中控总线 UDP {self.udp_control_port} | TCP {self.tcp_control_port} | HTTP {self.http_control_port}")

    def stop(self):
        """停止主控服务"""
        self.running = False
        self.udp_controller.stop()
        self.tcp_controller.stop()
        self.http_controller.stop()
        self.serial_controller.stop()
        if self.server_sock:
            try:
                self.server_sock.close()
            except Exception:
                pass
        with self.clients_lock:
            for ip, data in list(self.clients.items()):
                try:
                    data["sock"].close()
                except Exception:
                    pass
            self.clients.clear()

    def get_online_clients(self) -> list:
        """获取所有当前在线的从机列表 (完整携带视频推流监看地址与 API 控制接口)"""
        with self.clients_lock:
            result = []
            for ip, c in self.clients.items():
                info = c.get("info", {})
                result.append({
                    "ip": ip,
                    "hostname": info.get("hostname", "Unknown"),
                    "custom_name": info.get("custom_name", ""),
                    "os": info.get("os", "Windows"),
                    "cpu_percent": info.get("cpu_percent", 0),
                    "gpu_percent": info.get("gpu_percent", 0),
                    "mem_percent": info.get("memory", {}).get("percent", 0),
                    "disks": info.get("disks", []),
                    "fg_window": info.get("foreground_window", ""),
                    "visible_windows": info.get("visible_windows", []),
                    "top_processes": info.get("top_processes", []),
                    "preset_apps": info.get("preset_apps", []),
                    "license": info.get("license", {}),
                    "last_seen": c.get("last_seen", 0),
                    # 视频推流地址与 API 接口规范
                    "vnc_url": f"vnc://{ip}:5900",
                    "webrtc_url": f"webrtc://{ip}:5900/live",
                    "stream_url": f"http://{ip}:5901/stream.mjpg",
                    "rtsp_url": f"rtsp://{ip}:8554/live",
                    "api_url": f"http://{ip}:9891/api/devices"
                })
            return result

    def send_command(self, client_ip: str, cmd_type: str, payload: dict = None, callback=None) -> bool:
        """向指定从机下发加密指令"""
        if payload is None:
            payload = {}

        req_id = str(uuid.uuid4())[:8]
        payload["req_id"] = req_id

        if callback:
            with self.callbacks_lock:
                self.pending_callbacks[req_id] = callback

        with self.clients_lock:
            client = self.clients.get(client_ip)
            if not client:
                return False
            sock = client["sock"]

        try:
            pkt = gwc_crypto.pack_packet(cmd_type, payload)
            sock.sendall(pkt)
            return True
        except Exception as e:
            print(f"[-] 向 {client_ip} 发送指令失败: {e}")
            self._remove_client(client_ip)
            return False

    def broadcast_command(self, cmd_type: str, payload: dict = None):
        """向所有在线从机批量广播指令"""
        with self.clients_lock:
            ips = list(self.clients.keys())
        for ip in ips:
            self.send_command(ip, cmd_type, payload)

    # ==================== 国文创远程授权中枢 ====================
    def remote_authorize_agent(self, client_ip: str, auth_type: str = "permanent", custom_val: int = 1,
                               duration_code: int = 15, runs_code: int = 31, callback=None) -> dict:
        """
        根据终端的 8 位申请码，一键远程签发 16 位专属商业激活码并下发给终端 (支持自定义小时、月、永久)
        """
        with self.clients_lock:
            c = self.clients.get(client_ip)
            if not c:
                return {"success": False, "error": f"终端 {client_ip} 处于离线状态"}
            req_code = c.get("info", {}).get("license", {}).get("request_code", "")

        if not req_code:
            return {"success": False, "error": "该终端尚未上报 8 位设备申请码"}

        act_code = ""
        # 1. 优先使用 2026 展馆控制终端专属授权算法 (支持自定义小时、月、永久)
        try:
            import gwc_license_terminal as lt
            dec = lt.decode_request_code(req_code)
            if dec.get("valid"):
                act_code = lt.generate_terminal_license(dec["hw_hash"], dec["nonce"], auth_type=auth_type, custom_val=custom_val)
        except Exception:
            pass

        # 2. 备用原版 VisualCast 算法兼容
        if not act_code and universal_license_core:
            try:
                dec_leg = universal_license_core.decode_request_code(req_code, "VisualCast")
                if dec_leg.get("valid"):
                    act_code = universal_license_core.encode_license(dec_leg["hw_hash"], dec_leg["nonce"], 31, 31, "VisualCast")
            except Exception:
                pass

        if not act_code:
            return {"success": False, "error": f"申请码格式校验失败，未能识别申请码: {req_code}"}

        # 异步推送给从机
        def on_auth_resp(resp):
            if resp and resp.get("success"):
                with self.clients_lock:
                    if client_ip in self.clients:
                        desc = f"{custom_val} 小时" if auth_type == "hour" else (f"{custom_val} 个月" if auth_type == "month" else "永久有效")
                        self.clients[client_ip]["info"]["license"]["status"] = "ACTIVE"
                        self.clients[client_ip]["info"]["license"]["expire_desc"] = f"已远程商业授权 ({desc})"
                if self.on_status_updated:
                    self.on_status_updated(client_ip, self.clients[client_ip]["info"])
            if callback:
                callback(resp)

        ok = self.send_command(client_ip, "CMD_REMOTE_AUTH", {"code": act_code}, callback=on_auth_resp)
        return {"success": ok, "act_code": act_code, "req_code": req_code, "client_ip": client_ip}

    # ==================== 备份管理与分发下发 ====================
    def request_agent_backup(self, client_ip: str, backup_name: str = "", notes: str = "", callback=None):
        """命令从机立即生成完整系统配置备份并回传给主控存储"""
        def on_resp(resp):
            if resp and resp.get("success"):
                filename = resp.get("filename", f"系统镜像_{client_ip}_{int(time.time())}.gwcsysimg")
                b64_data = resp.get("b64_data", "")
                if b64_data:
                    raw_bytes = base64.b64decode(b64_data)
                    save_path = os.path.join(self.backup_store_dir, filename)
                    with open(save_path, "wb") as f:
                        f.write(raw_bytes)
                        f.flush()
                        os.fsync(f.fileno())
                    info = gwc_backup.inspect_backup_package(save_path)
                    if self.on_backup_saved:
                        self.on_backup_saved(client_ip, save_path, info)
            if callback:
                callback(resp)

        return self.send_command(client_ip, "CMD_CREATE_BACKUP_AND_UPLOAD", {"name": backup_name, "notes": notes}, callback=on_resp)

    def push_backup_to_agent(self, client_ip: str, backup_file_path: str, callback=None):
        """将主控存储的指定备份包下发到从机并触发自动恢复"""
        if not os.path.isfile(backup_file_path):
            if callback:
                callback({"success": False, "error": "主控端备份文件不存在"})
            return False

        chk = gwc_backup.inspect_backup_package(backup_file_path)
        if not chk.get("valid"):
            if callback:
                callback({"success": False, "error": f"备份包无效或损坏: {chk.get('error')}"})
            return False

        with open(backup_file_path, "rb") as f:
            data = f.read()

        b64_str = base64.b64encode(data).decode("ascii")
        filename = os.path.basename(backup_file_path)

        return self.send_command(client_ip, "CMD_RESTORE_BACKUP", {
            "filename": filename,
            "b64_data": b64_str
        }, callback=callback)

    def list_master_backups(self) -> list:
        """列出主控归档库中的所有备份文件"""
        return gwc_backup.list_local_backups(self.backup_store_dir)

    # ==================== 局域网在线受控端主动搜索 ====================
    def scan_online_agents(self, timeout: float = 2.0, auto_connect: bool = False, on_found=None) -> list:
        """向局域网广播探测包，主动搜索所有在线的受控端"""
        return self.discoverer.scan(
            timeout=timeout,
            master_port=self.port,
            auto_connect=auto_connect,
            on_found=on_found
        )

    def start_agent_beacon_listener(self, on_discovered=None):
        """开启后台监听从机上线广播心跳"""
        self.discoverer.on_agent_discovered = on_discovered
        self.discoverer.start_beacon_listener()

    def stop_agent_beacon_listener(self):
        """停止后台从机上线监听"""
        self.discoverer.stop_beacon_listener()

    # ==================== 网络监听与客户端会话管理 ====================
    def _server_listen_loop(self):
        try:
            self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_sock.bind(("0.0.0.0", self.port))
            self.server_sock.listen(128)
            self.server_sock.settimeout(1.0)

            while self.running:
                try:
                    conn, addr = self.server_sock.accept()
                    client_ip = addr[0]
                    t = threading.Thread(target=self._handle_client_conn, args=(conn, addr), daemon=True)
                    t.start()
                except socket.timeout:
                    continue
                except Exception:
                    break
        except Exception as e:
            print(f"[-] 主控监听异常: {e}")

    def _handle_client_conn(self, conn, addr):
        client_ip = addr[0]
        try:
            conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            if hasattr(socket, "SIO_KEEPALIVE_VALS"):
                conn.ioctl(socket.SIO_KEEPALIVE_VALS, (1, 6000, 1000))
        except Exception:
            pass

        with self.clients_lock:
            # 若已存在旧连接，则先优雅关闭旧连接
            if client_ip in self.clients:
                try:
                    self.clients[client_ip]["sock"].close()
                except Exception:
                    pass
            self.clients[client_ip] = {
                "sock": conn,
                "addr": addr,
                "info": {},
                "last_seen": time.time()
            }

        recv_buffer = b""
        try:
            while self.running:
                rlist, _, _ = select.select([conn], [], [], 2.0)
                if not rlist:
                    continue
                chunk = conn.recv(65536)
                if not chunk:
                    break
                recv_buffer += chunk

                while len(recv_buffer) >= 8:
                    if not recv_buffer.startswith(gwc_crypto.MAGIC_HEADER):
                        idx = recv_buffer.find(gwc_crypto.MAGIC_HEADER, 1)
                        if idx != -1:
                            recv_buffer = recv_buffer[idx:]
                        else:
                            recv_buffer = b""
                            break
                    total_len = struct_unpack_len(recv_buffer)
                    if len(recv_buffer) < 8 + total_len:
                        break
                    frame = recv_buffer[:8 + total_len]
                    recv_buffer = recv_buffer[8 + total_len:]

                    try:
                        msg = gwc_crypto.unpack_packet(frame)
                        self._process_agent_message(client_ip, msg)
                    except Exception as ex:
                        print(f"[-] 解密从机 {client_ip} 报文错误: {ex}")

        except Exception:
            pass
        finally:
            self._remove_client(client_ip, conn=conn)

    def _process_agent_message(self, client_ip: str, msg: dict):
        m_type = msg.get("type", "")
        payload = msg.get("payload", {})

        with self.clients_lock:
            if client_ip in self.clients:
                self.clients[client_ip]["last_seen"] = time.time()

        if m_type == "AGENT_ONLINE":
            with self.clients_lock:
                if client_ip in self.clients:
                    self.clients[client_ip]["info"] = payload
            if self.on_agent_connected:
                self.on_agent_connected(client_ip, payload)

        elif m_type == "STATUS_REPORT":
            with self.clients_lock:
                if client_ip in self.clients:
                    self.clients[client_ip]["info"].update(payload)
            if self.on_status_updated:
                self.on_status_updated(client_ip, payload)

        elif m_type.startswith("RESP_"):
            # 响应回调
            req_id = payload.get("req_id")
            cb = None
            if req_id:
                with self.callbacks_lock:
                    cb = self.pending_callbacks.pop(req_id, None)
            if cb:
                cb(payload)

            # 特殊情况: 如果包含图像响应 (VNC_CAPTURE)
            if m_type == "RESP_VNC_CAPTURE" and "b64_image" in payload and cb:
                pass

    def _remove_client(self, client_ip: str, conn=None):
        should_notify = False
        with self.clients_lock:
            client_record = self.clients.get(client_ip)
            if client_record:
                if conn is not None and client_record.get("sock") is not conn:
                    # 避免旧连接退出线程误杀已接管的新连接
                    return
                try:
                    client_record["sock"].close()
                except Exception:
                    pass
                del self.clients[client_ip]
                should_notify = True
        if should_notify and self.on_agent_disconnected:
            self.on_agent_disconnected(client_ip)

    def _on_udp_ctl_received(self, cmd_raw: str, addr: tuple, result: dict):
        if self.on_udp_command_received:
            try:
                self.on_udp_command_received(cmd_raw, addr, result)
            except Exception:
                pass


# ==================== 展馆第三方集中智能中控多协议总线 (UDP/TCP/HTTP/串口) ====================
UDP_CENTRAL_CONTROL_PORT = 9889
TCP_CENTRAL_CONTROL_PORT = 9890
HTTP_CENTRAL_CONTROL_PORT = 9891


class CentralControlDispatcher:
    """
    展馆第三方集中智能中控核心指令解析与调度总线
    统一驱动 UDP、TCP、HTTP REST API、物理串口 (RS232/RS485)
    """
    @staticmethod
    def dispatch(master_hub, cmd_raw: str, protocol_name: str = "UDP", client_addr: str = "") -> dict:
        cmd_raw = (cmd_raw or "").strip()
        if not cmd_raw:
            return {"status": "ERROR", "code": 400, "error": "空指令报文"}

        resp_data = {"status": "SUCCESS", "code": 200, "protocol": protocol_name, "timestamp": int(time.time())}
        cmd_name = ""

        try:
            parsed_json = None
            if (cmd_raw.startswith("{") and cmd_raw.endswith("}")) or (cmd_raw.startswith("[") and cmd_raw.endswith("]")):
                try:
                    parsed_json = json.loads(cmd_raw)
                except Exception:
                    pass

            if parsed_json and isinstance(parsed_json, dict):
                # 兼顾 action 与 cmd 字段
                cmd_name = str(parsed_json.get("action") or parsed_json.get("cmd") or "").upper()
                ip = parsed_json.get("ip", "")
                path = parsed_json.get("path") or parsed_json.get("app_name", "")
                args = parsed_json.get("args", "")
                level = parsed_json.get("level") or parsed_json.get("volume", 50)
                pid = parsed_json.get("pid")
                name = parsed_json.get("name") or parsed_json.get("target", "")

                if cmd_name in ("PING", "STATUS", "HEALTH"):
                    resp_data["msg"] = f"PONG:GWC_MASTER_HUB:ONLINE:{len(master_hub.clients)}"
                    resp_data["online_count"] = len(master_hub.clients)
                elif cmd_name in ("GET_CLIENTS", "GET_DEVICES", "DEVICES"):
                    resp_data["devices"] = master_hub.get_online_clients()
                    resp_data["total"] = len(resp_data["devices"])
                elif cmd_name == "ALL_SHUTDOWN":
                    cnt = master_hub.broadcast_command("CMD_SHUTDOWN", {"force": True, "timeout": 0})
                    resp_data["msg"] = f"已向全馆 {cnt} 台工控机下发关机指令"
                elif cmd_name == "ALL_REBOOT":
                    cnt = master_hub.broadcast_command("CMD_REBOOT", {"force": True, "timeout": 0})
                    resp_data["msg"] = f"已向全馆 {cnt} 台工控机下发重启指令"
                elif cmd_name == "ALL_MUTE":
                    cnt = master_hub.broadcast_command("CMD_VOLUME", {"action": "mute"})
                    resp_data["msg"] = f"已向全馆 {cnt} 台工控机下发静音指令"
                elif cmd_name == "ALL_UNMUTE":
                    cnt = master_hub.broadcast_command("CMD_VOLUME", {"action": "unmute"})
                    resp_data["msg"] = f"已向全馆 {cnt} 台工控机下发解除静音指令"
                elif cmd_name in ("ALL_VOLUME", "SET_ALL_VOLUME"):
                    cnt = master_hub.broadcast_command("CMD_VOLUME", {"action": "set", "level": int(level)})
                    resp_data["msg"] = f"已向全馆 {cnt} 台工控机下发音量设定: {level}%"
                elif cmd_name in ("ALL_RUN", "RUN_ALL", "ALL_LAUNCH"):
                    cnt = master_hub.broadcast_command("CMD_RUN_APP", {"path": path, "args": args})
                    resp_data["msg"] = f"已向全馆 {cnt} 台工控机下发启动指令: {path}"
                elif cmd_name == "DEV_SHUTDOWN":
                    ok = master_hub.send_command(ip, "CMD_SHUTDOWN", {"force": True, "timeout": 0})
                    resp_data["msg"] = f"向设备 [{ip}] 下发关机指令: {'成功' if ok else '失败(离线)'}"
                elif cmd_name == "DEV_REBOOT":
                    ok = master_hub.send_command(ip, "CMD_REBOOT", {"force": True, "timeout": 0})
                    resp_data["msg"] = f"向设备 [{ip}] 下发重启指令: {'成功' if ok else '失败(离线)'}"
                elif cmd_name == "DEV_MUTE":
                    ok = master_hub.send_command(ip, "CMD_VOLUME", {"action": "mute"})
                    resp_data["msg"] = f"向设备 [{ip}] 下发静音指令: {'成功' if ok else '失败(离线)'}"
                elif cmd_name == "DEV_UNMUTE":
                    ok = master_hub.send_command(ip, "CMD_VOLUME", {"action": "unmute"})
                    resp_data["msg"] = f"向设备 [{ip}] 下发解除静音指令: {'成功' if ok else '失败(离线)'}"
                elif cmd_name == "DEV_VOLUME":
                    ok = master_hub.send_command(ip, "CMD_VOLUME", {"action": "set", "level": int(level)})
                    resp_data["msg"] = f"向设备 [{ip}] 设定音量为 {level}%: {'成功' if ok else '失败(离线)'}"
                elif cmd_name in ("DEV_RUN", "DEV_LAUNCH"):
                    ok = master_hub.send_command(ip, "CMD_RUN_APP", {"path": path, "args": args})
                    resp_data["msg"] = f"向设备 [{ip}] 下发启动程序 {path}: {'成功' if ok else '失败(离线)'}"
                elif cmd_name == "DEV_KILL":
                    ok = master_hub.send_command(ip, "CMD_KILL_PROC", {"pid": pid, "name": name})
                    resp_data["msg"] = f"向设备 [{ip}] 下发结束进程: {'成功' if ok else '失败(离线)'}"
                elif cmd_name == "SCAN_AGENTS":
                    threading.Thread(target=lambda: master_hub.scan_online_agents(timeout=1.5, auto_connect=True), daemon=True).start()
                    resp_data["msg"] = "已触发全网段受控端雷达扫描"
                else:
                    resp_data = {"status": "ERROR", "code": 404, "error": f"未支持的 JSON 命令: {cmd_name}"}

            else:
                # 冒号/空格分隔文本指令 (兼容快思聪/AMX/串口纯字符串)
                parts = cmd_raw.split(":")
                cmd_name = parts[0].strip().upper()

                if cmd_name in ("PING", "STATUS", "HEALTH"):
                    resp_data["msg"] = f"PONG:GWC_MASTER_HUB:ONLINE:{len(master_hub.clients)}"
                    resp_data["online_count"] = len(master_hub.clients)
                elif cmd_name in ("GET_DEVICES", "GET_CLIENTS", "DEVICES"):
                    resp_data["devices"] = master_hub.get_online_clients()
                    resp_data["total"] = len(resp_data["devices"])
                elif cmd_name == "ALL_SHUTDOWN":
                    cnt = master_hub.broadcast_command("CMD_SHUTDOWN", {"force": True, "timeout": 0})
                    resp_data["msg"] = f"已向全馆 {cnt} 台工控机下发关机指令"
                elif cmd_name == "ALL_REBOOT":
                    cnt = master_hub.broadcast_command("CMD_REBOOT", {"force": True, "timeout": 0})
                    resp_data["msg"] = f"已向全馆 {cnt} 台工控机下发重启指令"
                elif cmd_name == "ALL_MUTE":
                    cnt = master_hub.broadcast_command("CMD_VOLUME", {"action": "mute"})
                    resp_data["msg"] = f"已向全馆 {cnt} 台工控机下发静音指令"
                elif cmd_name == "ALL_UNMUTE":
                    cnt = master_hub.broadcast_command("CMD_VOLUME", {"action": "unmute"})
                    resp_data["msg"] = f"已向全馆 {cnt} 台工控机下发解除静音指令"
                elif cmd_name in ("ALL_VOLUME", "SET_ALL_VOLUME") and len(parts) >= 2:
                    lvl = int(parts[1].strip())
                    cnt = master_hub.broadcast_command("CMD_VOLUME", {"action": "set", "level": lvl})
                    resp_data["msg"] = f"全馆音量已设定为 {lvl}% (已下发 {cnt} 台)"
                elif cmd_name in ("ALL_RUN", "ALL_LAUNCH") and len(parts) >= 2:
                    p = ":".join(parts[1:]).strip()
                    cnt = master_hub.broadcast_command("CMD_RUN_APP", {"path": p})
                    resp_data["msg"] = f"全馆已批量启动应用: {p} (已下发 {cnt} 台)"
                elif cmd_name == "DEV_SHUTDOWN" and len(parts) >= 2:
                    target_ip = parts[1].strip()
                    ok = master_hub.send_command(target_ip, "CMD_SHUTDOWN", {"force": True, "timeout": 0})
                    resp_data["msg"] = f"向工控机 [{target_ip}] 下发关机指令: {'成功' if ok else '失败(未在线)'}"
                elif cmd_name == "DEV_REBOOT" and len(parts) >= 2:
                    target_ip = parts[1].strip()
                    ok = master_hub.send_command(target_ip, "CMD_REBOOT", {"force": True, "timeout": 0})
                    resp_data["msg"] = f"向工控机 [{target_ip}] 下发重启指令: {'成功' if ok else '失败(未在线)'}"
                elif cmd_name == "DEV_MUTE" and len(parts) >= 2:
                    target_ip = parts[1].strip()
                    ok = master_hub.send_command(target_ip, "CMD_VOLUME", {"action": "mute"})
                    resp_data["msg"] = f"向工控机 [{target_ip}] 下发静音指令: {'成功' if ok else '失败(未在线)'}"
                elif cmd_name == "DEV_UNMUTE" and len(parts) >= 2:
                    target_ip = parts[1].strip()
                    ok = master_hub.send_command(target_ip, "CMD_VOLUME", {"action": "unmute"})
                    resp_data["msg"] = f"向工控机 [{target_ip}] 下发解除静音指令: {'成功' if ok else '失败(未在线)'}"
                elif cmd_name == "DEV_VOLUME" and len(parts) >= 3:
                    target_ip = parts[1].strip()
                    lvl = int(parts[2].strip())
                    ok = master_hub.send_command(target_ip, "CMD_VOLUME", {"action": "set", "level": lvl})
                    resp_data["msg"] = f"工控机 [{target_ip}] 音量设定为 {lvl}%: {'成功' if ok else '失败(未在线)'}"
                elif cmd_name in ("DEV_RUN", "DEV_LAUNCH") and len(parts) >= 3:
                    target_ip = parts[1].strip()
                    run_path = ":".join(parts[2:]).strip()
                    ok = master_hub.send_command(target_ip, "CMD_RUN_APP", {"path": run_path})
                    resp_data["msg"] = f"向工控机 [{target_ip}] 启动程序 {run_path}: {'成功' if ok else '失败(未在线)'}"
                elif cmd_name == "DEV_KILL" and len(parts) >= 3:
                    target_ip = parts[1].strip()
                    target_proc = parts[2].strip()
                    pid_val = int(target_proc) if target_proc.isdigit() else None
                    name_val = None if pid_val else target_proc
                    ok = master_hub.send_command(target_ip, "CMD_KILL_PROC", {"pid": pid_val, "name": name_val})
                    resp_data["msg"] = f"向工控机 [{target_ip}] 强杀进程 {target_proc}: {'成功' if ok else '失败(未在线)'}"
                elif cmd_name == "SCAN_AGENTS":
                    threading.Thread(target=lambda: master_hub.scan_online_agents(timeout=1.5, auto_connect=True), daemon=True).start()
                    resp_data["msg"] = "已触发全网段受控端雷达扫描"
                else:
                    resp_data = {"status": "ERROR", "code": 404, "error": f"未支持的文本命令: {cmd_raw}"}

            # 触发统一事件总线回调
            if getattr(master_hub, "on_central_control_event", None):
                try:
                    master_hub.on_central_control_event(protocol_name, client_addr, cmd_raw, resp_data)
                except Exception:
                    pass

            return resp_data

        except Exception as ex:
            err_dict = {"status": "ERROR", "code": 500, "error": str(ex), "protocol": protocol_name}
            if getattr(master_hub, "on_central_control_event", None):
                try:
                    master_hub.on_central_control_event(protocol_name, client_addr, cmd_raw, err_dict)
                except Exception:
                    pass
            return err_dict


class UdpCentralControlListener:
    """展馆智能中控 UDP 调度监听器 (默认 UDP 9889)"""
    def __init__(self, master_hub, port: int = UDP_CENTRAL_CONTROL_PORT):
        self.master_hub = master_hub
        self.port = port
        self.running = False
        self.sock = None
        self._thread = None
        self.on_command_received = None

    def start(self):
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass

    def _listen_loop(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(("0.0.0.0", self.port))
            self.sock.settimeout(1.0)
            print(f"[*] 智能中控 UDP 调度总线已启动: 监听端口 {self.port}")
        except Exception as e:
            print(f"[-] 绑定中控 UDP 端口 {self.port} 失败: {e}")
            return

        while self.running:
            try:
                data, addr = self.sock.recvfrom(4096)
                if not data:
                    continue
                cmd_raw = data.decode("utf-8", errors="ignore").strip()
                threading.Thread(target=self._handle_req, args=(cmd_raw, addr), daemon=True).start()
            except socket.timeout:
                continue
            except Exception:
                break

    def _handle_req(self, cmd_raw: str, addr: tuple):
        addr_str = f"{addr[0]}:{addr[1]}"
        resp_data = CentralControlDispatcher.dispatch(self.master_hub, cmd_raw, protocol_name="UDP", client_addr=addr_str)
        try:
            ack_bytes = json.dumps(resp_data, ensure_ascii=False).encode("utf-8")
            self.sock.sendto(ack_bytes, addr)
        except Exception:
            pass
        if self.on_command_received:
            try:
                self.on_command_received(cmd_raw, addr, resp_data)
            except Exception:
                pass


class TcpCentralControlListener:
    """展馆智能中控 TCP Socket 监听器 (默认 TCP 9890)"""
    def __init__(self, master_hub, port: int = TCP_CENTRAL_CONTROL_PORT):
        self.master_hub = master_hub
        self.port = port
        self.running = False
        self.server_sock = None
        self._thread = None

    def start(self):
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        if self.server_sock:
            try:
                self.server_sock.close()
            except Exception:
                pass

    def _listen_loop(self):
        try:
            self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_sock.bind(("0.0.0.0", self.port))
            self.server_sock.listen(10)
            self.server_sock.settimeout(1.0)
            print(f"[*] 智能中控 TCP 调度总线已启动: 监听端口 {self.port}")
        except Exception as e:
            print(f"[-] 绑定中控 TCP 端口 {self.port} 失败: {e}")
            return

        while self.running:
            try:
                client_sock, addr = self.server_sock.accept()
                threading.Thread(target=self._handle_client, args=(client_sock, addr), daemon=True).start()
            except socket.timeout:
                continue
            except Exception:
                break

    def _handle_client(self, client_sock: socket.socket, addr: tuple):
        addr_str = f"{addr[0]}:{addr[1]}"
        client_sock.settimeout(10.0)
        buf = ""
        try:
            while self.running:
                data = client_sock.recv(4096)
                if not data:
                    break
                buf += data.decode("utf-8", errors="ignore")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    cmd_line = line.strip()
                    if not cmd_line:
                        continue
                    resp_dict = CentralControlDispatcher.dispatch(self.master_hub, cmd_line, protocol_name="TCP", client_addr=addr_str)
                    ack_str = json.dumps(resp_dict, ensure_ascii=False) + "\n"
                    client_sock.sendall(ack_str.encode("utf-8"))
        except Exception:
            pass
        finally:
            try:
                client_sock.close()
            except Exception:
                pass


class HttpCentralControlServer:
    """展馆智能中控 HTTP RESTful API 服务 (默认 HTTP 9891)"""
    def __init__(self, master_hub, port: int = HTTP_CENTRAL_CONTROL_PORT):
        self.master_hub = master_hub
        self.port = port
        self.running = False
        self.httpd = None
        self._thread = None

    def start(self):
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._run_server, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        if self.httpd:
            try:
                self.httpd.shutdown()
            except Exception:
                pass

    def _run_server(self):
        from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
        from urllib.parse import urlparse, parse_qs

        master_ref = self.master_hub

        class HttpApiHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass  # 静默输出避免刷屏

            def _send_cors_headers(self, code=200, content_type="application/json; charset=utf-8"):
                self.send_response(code)
                self.send_header("Content-Type", content_type)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
                self.end_headers()

            def do_OPTIONS(self):
                self._send_cors_headers(200)

            def do_GET(self):
                pr = urlparse(self.path)
                p = pr.path
                client_addr = f"{self.client_address[0]}:{self.client_address[1]}"

                if p in ("/", "/api", "/api/"):
                    # 帮助与系统概览
                    data = {
                        "name": "展馆智能集群综合管控中心 HTTP RESTful API",
                        "status": "RUNNING",
                        "online_agents": len(master_ref.clients),
                        "ports": {
                            "udp_control": master_ref.udp_control_port,
                            "tcp_control": master_ref.tcp_control_port,
                            "http_api": master_ref.http_control_port
                        },
                        "endpoints": {
                            "GET /api/devices": "获取所有在线工控机清单及视频推流监看地址",
                            "GET /api/status": "获取中控服务器健康状态",
                            "POST /api/control": "下发中控调度指令 (JSON body: {\"action\": \"...\", ...})",
                            "GET /api/control?action=...": "通过 URL 查询参数执行一键调度 (方便浏览器/大屏按钮触发)"
                        }
                    }
                    self._send_cors_headers(200)
                    self.wfile.write(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))

                elif p == "/api/devices":
                    devices = master_ref.get_online_clients()
                    self._send_cors_headers(200)
                    self.wfile.write(json.dumps({"status": "SUCCESS", "count": len(devices), "devices": devices}, ensure_ascii=False).encode("utf-8"))

                elif p == "/api/status":
                    self._send_cors_headers(200)
                    self.wfile.write(json.dumps({"status": "SUCCESS", "online_count": len(master_ref.clients), "time": int(time.time())}).encode("utf-8"))

                elif p == "/api/control":
                    qs = parse_qs(pr.query)
                    payload = {}
                    for k, v in qs.items():
                        payload[k] = v[0] if len(v) == 1 else v
                    res = CentralControlDispatcher.dispatch(master_ref, json.dumps(payload), protocol_name="HTTP", client_addr=client_addr)
                    self._send_cors_headers(200)
                    self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))

                else:
                    self._send_cors_headers(404)
                    self.wfile.write(json.dumps({"status": "ERROR", "error": "Not Found"}).encode("utf-8"))

            def do_POST(self):
                pr = urlparse(self.path)
                client_addr = f"{self.client_address[0]}:{self.client_address[1]}"
                if pr.path == "/api/control":
                    length = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(length).decode("utf-8", errors="ignore")
                    res = CentralControlDispatcher.dispatch(master_ref, body, protocol_name="HTTP", client_addr=client_addr)
                    self._send_cors_headers(200)
                    self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
                else:
                    self._send_cors_headers(404)
                    self.wfile.write(json.dumps({"status": "ERROR", "error": "Endpoint Not Found"}).encode("utf-8"))

        try:
            self.httpd = ThreadingHTTPServer(("0.0.0.0", self.port), HttpApiHandler)
            print(f"[*] 智能中控 HTTP RESTful API 总线已就绪: http://0.0.0.0:{self.port}/api")
            self.httpd.serve_forever()
        except Exception as e:
            print(f"[-] 启动中控 HTTP API 服务失败 (端口 {self.port}): {e}")


class SerialCentralControlListener:
    """展馆智能中控 物理串口 (RS232/RS485) 监听器"""
    def __init__(self, master_hub):
        self.master_hub = master_hub
        self.port_name = ""
        self.baudrate = 9600
        self.running = False
        self.serial_obj = None
        self._thread = None

    @staticmethod
    def list_available_ports() -> list:
        """原生枚举 Windows 可用物理与虚拟串口 (无需依赖第三方库)"""
        ports = []
        # 1. 优先尝试 pyserial
        try:
            import serial.tools.list_ports
            for p in serial.tools.list_ports.comports():
                ports.append(p.device)
            if ports:
                return sorted(list(set(ports)))
        except Exception:
            pass

        # 2. 纯 Windows 注册表原生枚举
        if sys.platform == "win32":
            try:
                import winreg
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\SERIALCOMM")
                for i in range(64):
                    try:
                        _, val, _ = winreg.EnumValue(key, i)
                        if val:
                            ports.append(str(val))
                    except OSError:
                        break
                winreg.CloseKey(key)
            except Exception:
                pass

        if not ports:
            # 常见备选
            ports = ["COM1", "COM2", "COM3", "COM4"]
        return sorted(list(set(ports)))

    def start(self, port_name: str, baudrate: int = 9600) -> tuple:
        """启动指定串口监听"""
        self.stop()
        self.port_name = port_name
        self.baudrate = baudrate
        try:
            import serial
        except ImportError:
            return False, "未安装 pyserial 串口模块，请执行 pip install pyserial"

        try:
            self.serial_obj = serial.Serial(self.port_name, self.baudrate, timeout=1.0)
            self.running = True
            self._thread = threading.Thread(target=self._serial_loop, daemon=True)
            self._thread.start()
            print(f"[*] 智能中控串口监听已启动: {self.port_name} (波特率 {self.baudrate})")
            return True, f"已开启串口 {self.port_name} 监听"
        except Exception as e:
            return False, f"打开串口 {self.port_name} 失败: {e}"

    def stop(self):
        self.running = False
        if self.serial_obj:
            try:
                self.serial_obj.close()
            except Exception:
                pass
            self.serial_obj = None

    def _serial_loop(self):
        buf = ""
        while self.running and self.serial_obj and self.serial_obj.is_open:
            try:
                raw = self.serial_obj.read(128)
                if not raw:
                    continue
                buf += raw.decode("utf-8", errors="ignore")
                while "\n" in buf or "\r" in buf:
                    # 兼容 \r\n 或 \n
                    if "\r\n" in buf:
                        line, buf = buf.split("\r\n", 1)
                    elif "\n" in buf:
                        line, buf = buf.split("\n", 1)
                    elif "\r" in buf:
                        line, buf = buf.split("\r", 1)
                    else:
                        break

                    cmd_line = line.strip()
                    if not cmd_line:
                        continue
                    resp = CentralControlDispatcher.dispatch(self.master_hub, cmd_line, protocol_name="SERIAL", client_addr=self.port_name)
                    ack_line = f"ACK:{resp.get('msg', 'OK')}\r\n"
                    try:
                        self.serial_obj.write(ack_line.encode("utf-8"))
                    except Exception:
                        pass
            except Exception:
                break


def struct_unpack_len(buffer: bytes) -> int:
    import struct
    return struct.unpack(">I", buffer[4:8])[0]
