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
from datetime import datetime

import gwc_crypto
import gwc_backup

try:
    import universal_license_core
except ImportError:
    universal_license_core = None

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

        # 待响应请求回调映射: req_id -> callback
        self.pending_callbacks = {}
        self.callbacks_lock = threading.Lock()

        # 事件回调钩子 (供外部 GUI 订阅)
        self.on_agent_connected = None
        self.on_agent_disconnected = None
        self.on_status_updated = None
        self.on_backup_saved = None

        # 主控备份归档根目录
        if not backup_store_dir:
            base_d = os.path.dirname(os.path.abspath(__file__))
            self.backup_store_dir = os.path.join(base_d, "master_backups")
        else:
            self.backup_store_dir = backup_store_dir
        os.makedirs(self.backup_store_dir, exist_ok=True)

    def start(self):
        """启动主控监听服务"""
        if self.running:
            return
        self.running = True
        self._server_thread = threading.Thread(target=self._server_listen_loop, daemon=True)
        self._server_thread.start()
        print(f"[*] 国文创主控综合管理集群服务已启动: 监听端口 {self.port}")

    def stop(self):
        """停止主控服务"""
        self.running = False
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
        """获取所有当前在线的从机列表"""
        with self.clients_lock:
            result = []
            for ip, c in self.clients.items():
                info = c.get("info", {})
                result.append({
                    "ip": ip,
                    "hostname": info.get("hostname", "Unknown"),
                    "os": info.get("os", "Windows"),
                    "cpu_percent": info.get("cpu_percent", 0),
                    "mem_percent": info.get("memory", {}).get("percent", 0),
                    "disks": info.get("disks", []),
                    "fg_window": info.get("foreground_window", ""),
                    "visible_windows": info.get("visible_windows", []),
                    "top_processes": info.get("top_processes", []),
                    "license": info.get("license", {}),
                    "last_seen": c.get("last_seen", 0)
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
    def remote_authorize_agent(self, client_ip: str, duration_code: int = 31, runs_code: int = 31, callback=None) -> dict:
        """
        根据从机的 8 位申请码，一键远程签发 12 位一次性激活码并下发给从机
        duration_code: 31 表示永久有效, 8 表示1年, 4 表示30天
        """
        if not universal_license_core:
            return {"success": False, "error": "缺少 universal_license_core 授权算法模块"}

        with self.clients_lock:
            c = self.clients.get(client_ip)
            if not c:
                return {"success": False, "error": f"从机 {client_ip} 处于离线状态"}
            req_code = c.get("info", {}).get("license", {}).get("request_code", "")

        if not req_code:
            return {"success": False, "error": "该从机尚未上报 8 位设备申请码"}

        dec = universal_license_core.decode_request_code(req_code, "VisualCast")
        if not dec.get("valid"):
            return {"success": False, "error": f"申请码解码失败: {dec.get('error')}"}

        hw_hash = dec["hw_hash"]
        nonce = dec["nonce"]
        matched_pid = dec.get("matched_product_id", "VisualCast")

        # 生成 12 位激活码
        act_code = universal_license_core.encode_license(hw_hash, nonce, duration_code, runs_code, matched_pid)

        # 异步推送给从机
        def on_auth_resp(resp):
            if resp and resp.get("success"):
                # 更新本地缓存中的授权状态
                with self.clients_lock:
                    if client_ip in self.clients:
                        self.clients[client_ip]["info"]["license"]["status"] = "ACTIVE"
                        self.clients[client_ip]["info"]["license"]["expire_desc"] = "已远程激活 (永久有效)"
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
                filename = resp.get("filename", f"Backup_{client_ip}_{int(time.time())}.gwcbackup")
                b64_data = resp.get("b64_data", "")
                if b64_data:
                    raw_bytes = base64.b64decode(b64_data)
                    save_path = os.path.join(self.backup_store_dir, filename)
                    with open(save_path, "wb") as f:
                        f.write(raw_bytes)
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
        with self.clients_lock:
            # 若已存在旧连接，则关闭旧连接
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
            self._remove_client(client_ip)

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

    def _remove_client(self, client_ip: str):
        with self.clients_lock:
            if client_ip in self.clients:
                try:
                    self.clients[client_ip]["sock"].close()
                except Exception:
                    pass
                del self.clients[client_ip]
        if self.on_agent_disconnected:
            self.on_agent_disconnected(client_ip)


def struct_unpack_len(buffer: bytes) -> int:
    import struct
    return struct.unpack(">I", buffer[4:8])[0]
