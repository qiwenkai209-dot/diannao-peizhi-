# -*- coding: utf-8 -*-
"""
国文创局域网设备自动发现协议 (GuoWenChuang LAN Discovery Protocol)
================================================================
1. 主控端通过 UDP 广播主动搜索局域网在线受控端 (DISCOVER_PROBE)
2. 受控端监听广播端口并即刻反馈主机基本信息与运行状态 (DISCOVER_REPLY)
3. 受控端上线自动广播心跳宣告 (AGENT_BEACON)，主控端被动监听感知
4. 支持双向快速组网：主控一键搜索发现，受控端一键自动连入主控
"""

import socket
import select
import threading
import json
import time
import platform
import psutil

DISCOVERY_MAGIC = b"GWCDISCOVER:"
DISCOVERY_PORT = 9887


def get_all_broadcast_addresses() -> list:
    """获取本机所有有效网卡的广播地址，保证全网段覆盖广播"""
    broadcasts = ["255.255.255.255"]
    try:
        nics = psutil.net_if_addrs()
        for nic_name, addrs in nics.items():
            for addr in addrs:
                if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                    if addr.broadcast:
                        broadcasts.append(addr.broadcast)
                    elif addr.netmask:
                        # 简易计算广播地址
                        ip_parts = [int(x) for x in addr.address.split(".")]
                        mask_parts = [int(x) for x in addr.netmask.split(".")]
                        bcast_parts = [(ip_parts[i] | (~mask_parts[i] & 0xFF)) for i in range(4)]
                        bcast_ip = ".".join(str(x) for x in bcast_parts)
                        if bcast_ip not in broadcasts:
                            broadcasts.append(bcast_ip)
    except Exception:
        pass
    return list(set(broadcasts))


def get_local_ip() -> str:
    """获取本机最优先的局域网 IP"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


class AgentDiscoveryServer:
    """受控端 UDP 发现响应与上线宣告服务"""

    def __init__(self, agent_client=None, port: int = DISCOVERY_PORT):
        self.port = port
        self.agent_client = agent_client
        self.running = False
        self.sock = None
        self._thread = None

    def start(self):
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        # 启动未连接时的周期性上线宣告守护线程 (每 8 秒一次，连上后自动静默)
        threading.Thread(target=self._beacon_loop, daemon=True).start()

    def _beacon_loop(self):
        while self.running:
            is_connected = False
            if self.agent_client:
                is_connected = getattr(self.agent_client, "connected", False)
            if not is_connected:
                self.send_beacon()
            time.sleep(8.0)

    def stop(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass

    def send_beacon(self):
        """受控端主动发送上线广播宣告"""
        try:
            info = self._get_device_info()
            data = {
                "cmd": "AGENT_BEACON",
                "info": info,
                "timestamp": time.time()
            }
            raw = DISCOVERY_MAGIC + json.dumps(data, ensure_ascii=False).encode("utf-8")
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            for bcast in get_all_broadcast_addresses():
                try:
                    s.sendto(raw, (bcast, self.port))
                except Exception:
                    pass
            s.close()
        except Exception:
            pass

    def _get_device_info(self) -> dict:
        hostname = socket.gethostname()
        local_ip = get_local_ip()
        cpu_usage = 0.0
        gpu_usage = 0.0
        mem_usage = 0.0
        try:
            import gwc_monitor
            cpu_usage = gwc_monitor._collector.get_cpu_percent()
            gpu_usage = gwc_monitor._collector.get_gpu_percent()
            mem_usage = psutil.virtual_memory().percent
        except Exception:
            pass

        connected = False
        master_ip = ""
        req_code = ""
        is_auth = False
        custom_name = ""

        if self.agent_client:
            connected = getattr(self.agent_client, "connected", False)
            master_ip = getattr(self.agent_client, "master_ip", "")
            c_name = getattr(self.agent_client, "custom_name", "")
            if c_name:
                hostname = c_name
                custom_name = c_name
            lm = getattr(self.agent_client, "license_mgr", None)
            if lm:
                try:
                    req_fn = getattr(lm, "get_req_code", getattr(lm, "get_request_code", None))
                    if req_fn:
                        req_code = req_fn()
                    is_auth = getattr(lm, "is_authorized", lambda: lm.check()[0])()
                except Exception:
                    pass

        return {
            "hostname": hostname,
            "custom_name": custom_name,
            "ip": local_ip,
            "os": f"Windows ({platform.release()})",
            "cpu": cpu_usage,
            "gpu": gpu_usage,
            "mem": mem_usage,
            "connected_master": connected,
            "current_master_ip": master_ip,
            "request_code": req_code,
            "authorized": is_auth,
            "agent_port": 9888,
            "vnc_port": 5900,
            "role": "GWC_AGENT"
        }

    def _listen_loop(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            except Exception:
                pass
            self.sock.bind(("0.0.0.0", self.port))
            self.sock.settimeout(1.0)

            while self.running:
                try:
                    data, addr = self.sock.recvfrom(4096)
                    if not data.startswith(DISCOVERY_MAGIC):
                        continue

                    json_str = data[len(DISCOVERY_MAGIC):].decode("utf-8", errors="ignore")
                    msg = json.loads(json_str)

                    if msg.get("cmd") == "DISCOVER_PROBE":
                        sender_master_ip = msg.get("master_ip") or addr[0]
                        master_tcp_port = msg.get("master_port", 9888)
                        auto_connect = msg.get("auto_connect", False)

                        # 回复响应包
                        reply_info = self._get_device_info()
                        resp_data = {
                            "cmd": "DISCOVER_REPLY",
                            "probe_token": msg.get("token", ""),
                            "info": reply_info,
                            "timestamp": time.time()
                        }
                        resp_raw = DISCOVERY_MAGIC + json.dumps(resp_data, ensure_ascii=False).encode("utf-8")

                        # 单播发回给主控端探测端口
                        self.sock.sendto(resp_raw, addr)

                        # 如果主控端要求自动连接，且受控端当前尚未连接任何主控
                        if auto_connect and self.agent_client:
                            if not getattr(self.agent_client, "connected", False):
                                self.agent_client.set_master_address(sender_master_ip, master_tcp_port)
                                if not getattr(self.agent_client, "running", False):
                                    self.agent_client.start()

                except socket.timeout:
                    continue
                except Exception:
                    continue
        except Exception as e:
            print(f"[-] 受控端 UDP 发现服务异常: {e}")
        finally:
            if self.sock:
                try:
                    self.sock.close()
                except Exception:
                    pass


class MasterDiscoverer:
    """主控端局域网受控端搜索与发现器"""

    def __init__(self, port: int = DISCOVERY_PORT):
        self.port = port
        self.sock = None
        self.listening_beacon = False
        self.on_agent_discovered = None  # 回调通知主控 UI: fn(agent_info: dict)
        self._beacon_thread = None

    def start_beacon_listener(self):
        """在后台持续监听受控端上线广播宣告"""
        if self.listening_beacon:
            return
        self.listening_beacon = True
        self._beacon_thread = threading.Thread(target=self._beacon_listen_loop, daemon=True)
        self._beacon_thread.start()

    def stop_beacon_listener(self):
        self.listening_beacon = False

    def _beacon_listen_loop(self):
        b_sock = None
        try:
            b_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            b_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            b_sock.bind(("0.0.0.0", self.port))
            b_sock.settimeout(1.0)

            while self.listening_beacon:
                try:
                    data, addr = b_sock.recvfrom(4096)
                    if not data.startswith(DISCOVERY_MAGIC):
                        continue
                    json_str = data[len(DISCOVERY_MAGIC):].decode("utf-8", errors="ignore")
                    msg = json.loads(json_str)

                    if msg.get("cmd") == "AGENT_BEACON":
                        info = msg.get("info", {})
                        if not info.get("ip"):
                            info["ip"] = addr[0]
                        info["from_addr"] = addr
                        info["source"] = "beacon"
                        if self.on_agent_discovered:
                            self.on_agent_discovered(info)
                except socket.timeout:
                    continue
                except Exception:
                    continue
        except Exception:
            pass
        finally:
            if b_sock:
                try:
                    b_sock.close()
                except Exception:
                    pass

    def scan(self, timeout: float = 2.5, master_port: int = 9888, auto_connect: bool = False, on_found=None) -> list:
        """
        向局域网广播探测包，同步/异步收集所有在线受控设备
        :param timeout: 监听收集时长 (秒)
        :param master_port: 主控端 TCP 监听端口
        :param auto_connect: 是否命令受控端收到探测后直接发起 TCP 连接入网
        :param on_found: 每搜到一台设备时的即时回调函数 fn(device_dict)
        :return: 搜索到的设备字典列表
        """
        local_ip = get_local_ip()
        probe_token = f"probe_{int(time.time() * 1000)}"
        probe_msg = {
            "cmd": "DISCOVER_PROBE",
            "token": probe_token,
            "master_ip": local_ip,
            "master_port": master_port,
            "auto_connect": auto_connect,
            "timestamp": time.time()
        }
        raw_probe = DISCOVERY_MAGIC + json.dumps(probe_msg, ensure_ascii=False).encode("utf-8")

        discovered = {}
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # 绑定随机端口接收回包
        s.bind(("0.0.0.0", 0))
        s.settimeout(0.2)

        # 全网卡广播发送探测包
        broadcasts = get_all_broadcast_addresses()
        for bcast in broadcasts:
            try:
                s.sendto(raw_probe, (bcast, self.port))
            except Exception:
                pass

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                data, addr = s.recvfrom(4096)
                if not data.startswith(DISCOVERY_MAGIC):
                    continue
                json_str = data[len(DISCOVERY_MAGIC):].decode("utf-8", errors="ignore")
                msg = json.loads(json_str)

                if msg.get("cmd") == "DISCOVER_REPLY" and msg.get("probe_token") == probe_token:
                    info = msg.get("info", {})
                    ip = info.get("ip") or addr[0]
                    # 计算大致往返延迟 (ms)
                    latency = max(1, int((time.time() - start_time) * 1000))
                    info["ip"] = ip
                    info["latency_ms"] = latency
                    info["last_seen"] = time.time()

                    if ip not in discovered:
                        discovered[ip] = info
                        if on_found:
                            try:
                                on_found(info)
                            except Exception:
                                pass
                        if self.on_agent_discovered:
                            try:
                                self.on_agent_discovered(info)
                            except Exception:
                                pass
            except socket.timeout:
                continue
            except Exception:
                break

        try:
            s.close()
        except Exception:
            pass

        return list(discovered.values())
