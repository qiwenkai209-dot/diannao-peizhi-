# -*- coding: utf-8 -*-
"""
国文创从机服务与受控管理代理 (GuoWenChuang Agent Client)
======================================================
1. 从机后台常驻通信引擎:
   - 自动发现主控 (UDP 局域网广播探测) 或直连指定中控 IP
   - 与主控建立长效国文创强加密通信链路 (GWCC 协议)
   - 定时 2 秒实时推送主机工作状态与授权申请码
2. 远程指令执行与状态反馈:
   - 中控远程关机 / 远程重启
   - 远程系统音量精准控制 (设置数值、静音)
   - 远程应用启动调用 (参数工作目录支持)
   - 远程活跃软件与进程强制结束 (taskkill)
3. 备份协同体系:
   - 接收主控指令生成本地系统一键备份并上传至中控库
   - 接收主控下发的备份包并全自动执行一键还原
4. 远程授权激活核销:
   - 接收主控下发的 12 位激活码并自动完成授权核销与解锁
5. 嵌入式 VNC 远程控制与文件管理支持
"""

import os
import sys
import time
import socket
import select
import threading
import json
import base64

import gwc_crypto
import gwc_monitor
import gwc_system_ops
import gwc_backup
import gwc_vnc

DEFAULT_MASTER_PORT = 9888
UDP_DISCOVERY_PORT = 9887


class GwcAgentClient:
    def __init__(self, master_ip: str = "127.0.0.1", master_port: int = DEFAULT_MASTER_PORT, license_mgr=None):
        self.master_ip = master_ip
        self.master_port = master_port
        self.license_mgr = license_mgr
        self.running = False
        self.connected = False
        self.sock = None
        self._work_thread = None
        self._vnc_server = None
        self.on_status_change = None  # 回调通知 UI

    def start(self, enable_rfb_vnc: bool = True):
        """启动从机通信与受控代理"""
        if self.running:
            return
        self.running = True

        if enable_rfb_vnc:
            try:
                self._vnc_server = gwc_vnc.StandaloneRfbVncServer(port=5900)
                self._vnc_server.start()
            except Exception:
                pass

        self._work_thread = threading.Thread(target=self._connection_loop, daemon=True)
        self._work_thread.start()

    def stop(self):
        """停止从机服务"""
        self.running = False
        self.connected = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        if self._vnc_server:
            self._vnc_server.stop()
        if self.on_status_change:
            self.on_status_change(False, "服务已停止")

    def set_master_address(self, ip: str, port: int = DEFAULT_MASTER_PORT):
        self.master_ip = ip.strip()
        self.master_port = int(port)
        # 强制断开重连
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass

    def _connection_loop(self):
        while self.running:
            try:
                if self.on_status_change:
                    self.on_status_change(False, f"正在连接主控 {self.master_ip}:{self.master_port} ...")

                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(5.0)
                self.sock.connect((self.master_ip, self.master_port))
                self.sock.settimeout(None)
                self.connected = True

                if self.on_status_change:
                    self.on_status_change(True, f"已连接主控 {self.master_ip}:{self.master_port}")

                # 发送首次上线注册包
                first_status = gwc_monitor.get_host_status_report(self.license_mgr)
                reg_pkt = gwc_crypto.pack_packet("AGENT_ONLINE", first_status)
                self.sock.sendall(reg_pkt)

                last_report_time = time.time()
                recv_buffer = b""

                while self.running and self.connected:
                    rlist, _, _ = select.select([self.sock], [], [], 0.5)
                    if rlist:
                        chunk = self.sock.recv(65536)
                        if not chunk:
                            break
                        recv_buffer += chunk

                        # 拆包处理
                        while len(recv_buffer) >= 8:
                            if not recv_buffer.startswith(gwc_crypto.MAGIC_HEADER):
                                # 寻找下一个 Magic
                                idx = recv_buffer.find(gwc_crypto.MAGIC_HEADER, 1)
                                if idx != -1:
                                    recv_buffer = recv_buffer[idx:]
                                else:
                                    recv_buffer = b""
                                    break
                            total_len = struct_unpack_len(recv_buffer)
                            if len(recv_buffer) < 8 + total_len:
                                break  # 等待剩余包体
                            frame = recv_buffer[:8 + total_len]
                            recv_buffer = recv_buffer[8 + total_len:]

                            try:
                                msg = gwc_crypto.unpack_packet(frame)
                                self._dispatch_master_command(msg)
                            except Exception as ex:
                                print(f"[-] 报文解密处理错误: {ex}")

                    # 每 2 秒上报一次状态心跳
                    now = time.time()
                    if now - last_report_time >= 2.0:
                        last_report_time = now
                        status = gwc_monitor.get_host_status_report(self.license_mgr)
                        heartbeat = gwc_crypto.pack_packet("STATUS_REPORT", status)
                        self.sock.sendall(heartbeat)

            except Exception as e:
                self.connected = False
                if self.on_status_change:
                    self.on_status_change(False, f"未连接: {e}")
                time.sleep(3.0)
            finally:
                if self.sock:
                    try:
                        self.sock.close()
                    except Exception:
                        pass
                self.connected = False

    def _dispatch_master_command(self, msg: dict):
        """分发执行来自主控的加密指令"""
        m_type = msg.get("type")
        payload = msg.get("payload", {})
        req_id = payload.get("req_id", "")

        resp_payload = {"req_id": req_id, "success": True}

        try:
            if m_type == "CMD_SHUTDOWN":
                ok, out = gwc_system_ops.remote_shutdown(force=payload.get("force", True), timeout=payload.get("timeout", 0))
                resp_payload.update({"success": ok, "msg": out})

            elif m_type == "CMD_REBOOT":
                ok, out = gwc_system_ops.remote_reboot(force=payload.get("force", True), timeout=payload.get("timeout", 0))
                resp_payload.update({"success": ok, "msg": out})

            elif m_type == "CMD_VOLUME":
                action = payload.get("action", "set")
                level = payload.get("level", 50)
                res = gwc_system_ops.remote_volume_control(action, level)
                resp_payload.update(res)

            elif m_type == "CMD_RUN_APP":
                path = payload.get("path", "")
                args = payload.get("args", "")
                workdir = payload.get("workdir", "")
                res = gwc_system_ops.remote_run_app(path, args, workdir)
                resp_payload.update(res)

            elif m_type == "CMD_KILL_PROC":
                pid = payload.get("pid")
                name = payload.get("name")
                res = gwc_system_ops.remote_kill_process(pid=pid, name=name)
                resp_payload.update(res)

            elif m_type == "CMD_REMOTE_AUTH":
                # 主控远程下发国文创激活码
                act_code = payload.get("code", "")
                if self.license_mgr:
                    ok, msg_txt = self.license_mgr.activate(act_code)
                    resp_payload.update({"success": ok, "msg": msg_txt})
                else:
                    # 尝试动态加载并核销
                    try:
                        from universal_license_core import decode_license
                        dec = decode_license(act_code)
                        resp_payload.update({"success": dec["valid"], "msg": dec.get("error", "激活码校验成功")})
                    except Exception as ex:
                        resp_payload.update({"success": False, "error": str(ex)})

            elif m_type == "CMD_CREATE_BACKUP_AND_UPLOAD":
                # 从机一键生成备份并上传回主控
                b_name = payload.get("name", "")
                b_notes = payload.get("notes", "中控远程触发备份")
                res = gwc_backup.create_backup_package(name=b_name, notes=b_notes)
                if res.get("success"):
                    with open(res["path"], "rb") as f:
                        b_bytes = f.read()
                    b64_content = base64.b64encode(b_bytes).decode("ascii")
                    resp_payload.update({
                        "success": True,
                        "filename": res["filename"],
                        "size_mb": res["size_mb"],
                        "manifest": res["manifest"],
                        "b64_data": b64_content
                    })
                else:
                    resp_payload.update({"success": False, "error": res.get("error")})

            elif m_type == "CMD_RESTORE_BACKUP":
                # 接收主控下发的备份包并在从机执行一键恢复
                b64_data = payload.get("b64_data", "")
                filename = payload.get("filename", "remote_restore.gwcbackup")
                backup_bytes = base64.b64decode(b64_data)

                save_p = os.path.join(gwc_backup.get_default_backup_dir(), filename)
                with open(save_p, "wb") as f:
                    f.write(backup_bytes)

                res = gwc_backup.restore_backup_package(save_p)
                resp_payload.update(res)

            elif m_type == "VNC_CAPTURE":
                quality = payload.get("quality", 65)
                scale = payload.get("scale", 0.85)
                img_bytes, ow, oh = gwc_vnc.capture_desktop_image(quality=quality, scale=scale)
                resp_payload.update({
                    "success": True,
                    "orig_w": ow,
                    "orig_h": oh,
                    "b64_image": base64.b64encode(img_bytes).decode("ascii") if img_bytes else ""
                })

            elif m_type == "VNC_INPUT":
                act = payload.get("action")
                x = payload.get("x", 0)
                y = payload.get("y", 0)
                if act in ["move", "left_down", "left_up", "right_down", "right_up"]:
                    gwc_vnc.inject_remote_mouse(act, x, y)
                elif act == "wheel":
                    gwc_vnc.inject_remote_mouse("wheel", x, y, extra=payload.get("extra", 0))
                elif act == "key_press":
                    gwc_vnc.inject_remote_key(payload.get("vk", 0), True)
                elif act == "key_release":
                    gwc_vnc.inject_remote_key(payload.get("vk", 0), False)
                return  # 输入事件不回传大响应，降低开销

            elif m_type == "FS_LIST":
                res = gwc_vnc.handle_fs_list(payload.get("path", ""))
                resp_payload.update(res)

            elif m_type == "FS_MKDIR":
                res = gwc_vnc.handle_fs_mkdir(payload.get("path", ""))
                resp_payload.update(res)

            elif m_type == "FS_DELETE":
                res = gwc_vnc.handle_fs_delete(payload.get("path", ""))
                resp_payload.update(res)

            elif m_type == "FS_DOWNLOAD":
                p = payload.get("path", "")
                if os.path.isfile(p):
                    with open(p, "rb") as f:
                        b_data = f.read()
                    resp_payload.update({"success": True, "b64_content": base64.b64encode(b_data).decode("ascii")})
                else:
                    resp_payload.update({"success": False, "error": "文件不存在"})

            elif m_type == "FS_UPLOAD":
                dest = payload.get("dest", "")
                b64_data = payload.get("b64_content", "")
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, "wb") as f:
                    f.write(base64.b64decode(b64_data))
                resp_payload.update({"success": True, "msg": f"文件已保存至: {dest}"})

            else:
                resp_payload.update({"success": False, "error": f"未知指令: {m_type}"})

        except Exception as e:
            resp_payload.update({"success": False, "error": str(e)})

        # 发送响应给主控
        if self.sock and self.connected:
            try:
                pkt = gwc_crypto.pack_packet(f"RESP_{m_type}", resp_payload)
                self.sock.sendall(pkt)
            except Exception:
                pass


def struct_unpack_len(buffer: bytes) -> int:
    import struct
    return struct.unpack(">I", buffer[4:8])[0]
