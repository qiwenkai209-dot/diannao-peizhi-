import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import '../models/agent_device.dart';
import 'crypto.dart';
import 'discovery.dart';

/// 国文创展馆主控综合集群管理中心 (Dart 核心实现 - 全域双总线直连架构)
class GwcMasterHub {
  static const int defaultMasterPort = 9888;

  ServerSocket? _serverSocket;
  RawDatagramSocket? _udpSocket;
  Timer? _telemetryTimer;
  bool _running = false;

  final Map<String, AgentDevice> _devices = {};
  final Map<String, Socket> _clientSockets = {};
  final Map<String, BytesBuilder> _recvBuffers = {};

  final void Function()? onDevicesChanged;
  final void Function(String eventLog)? onLogMessage;

  GwcMasterHub({this.onDevicesChanged, this.onLogMessage});

  bool get isRunning => _running;
  List<AgentDevice> get devices => _devices.values.toList();
  int get onlineCount => _devices.values.where((d) => d.isOnline).length;

  /// 启动 TCP 9888 服务端监听 + UDP 9887 控制与遥测总线
  Future<void> start({int port = defaultMasterPort}) async {
    if (_running) return;
    _running = true;

    // 1. 启动 TCP 9888 长连接服务
    try {
      _serverSocket = await ServerSocket.bind(InternetAddress.anyIPv4, port);
      onLogMessage?.call('🏛️ 集群 TCP 控制总线已就绪: 端口 $port');

      _serverSocket?.listen(
        _handleClientConnection,
        onError: (e) {
          onLogMessage?.call('[-] TCP 集群监听套接字异常: $e');
        },
      );
    } catch (e) {
      onLogMessage?.call('[-] 绑定 TCP $port 端口异常: $e');
    }

    // 2. 启动 UDP 通信套接字并开启持续心跳与回显接收
    try {
      _udpSocket = await RawDatagramSocket.bind(
        InternetAddress.anyIPv4,
        0,
        reuseAddress: true,
      );
      _udpSocket?.broadcastEnabled = true;

      _udpSocket?.listen((RawSocketEvent event) {
        if (event == RawSocketEvent.read) {
          final dg = _udpSocket?.receive();
          if (dg != null) {
            _handleUdpPacket(dg.address.address, dg.data);
          }
        }
      });

      // 每 2 秒向全馆广播一次状态轮询，实现无缝实时回显
      _telemetryTimer = Timer.periodic(const Duration(milliseconds: 2000), (_) {
        _pollClusterTelemetry();
      });

      // 立即触发一次全馆扫描轮询
      _pollClusterTelemetry();
    } catch (e) {
      onLogMessage?.call('[-] 启动 UDP 遥测总线异常: $e');
    }
  }

  void stop() {
    _running = false;
    _telemetryTimer?.cancel();
    _telemetryTimer = null;

    for (final s in _clientSockets.values) {
      try {
        s.destroy();
      } catch (_) {}
    }
    _clientSockets.clear();
    _recvBuffers.clear();
    _serverSocket?.close();
    _serverSocket = null;

    _udpSocket?.close();
    _udpSocket = null;
    onLogMessage?.call('[-] 主控端服务已安全停止');
  }

  /// 周期性向全馆广播轻量状态查询，驱动毫秒级状态回显
  void _pollClusterTelemetry() {
    if (_udpSocket == null) return;
    try {
      final probe = {
        'cmd': 'CMD_GET_STATUS',
        'token': 'poll_${DateTime.now().millisecondsSinceEpoch}',
        'master_port': defaultMasterPort,
        'timestamp': DateTime.now().millisecondsSinceEpoch / 1000.0,
      };
      final raw = utf8.encode('${GwcDiscovery.discoveryMagic}${jsonEncode(probe)}');

      // 1. 全网广播
      _udpSocket?.send(raw, InternetAddress('255.255.255.255'), GwcDiscovery.discoveryPort);

      // 2. 对已记录的所有设备 IP 精准单播
      for (final dev in _devices.values) {
        try {
          _udpSocket?.send(raw, InternetAddress(dev.ip), GwcDiscovery.discoveryPort);
        } catch (_) {}
      }
    } catch (_) {}
  }

  /// 解析处理工控机回传的 UDP 报文 (实时回显系统状态、音量、进程)
  void _handleUdpPacket(String remoteIp, Uint8List data) {
    try {
      final text = utf8.decode(data, allowMalformed: true);
      if (!text.startsWith(GwcDiscovery.discoveryMagic)) return;

      final jsonStr = text.substring(GwcDiscovery.discoveryMagic.length);
      final msg = jsonDecode(jsonStr) as Map<String, dynamic>;
      final info = (msg['info'] as Map<String, dynamic>?) ?? msg;

      final ip = (info['ip'] as String?)?.isNotEmpty == true
          ? info['ip'] as String
          : remoteIp;

      final dev = _devices[ip] ?? AgentDevice(ip: ip, source: 'udp');
      dev.updateFromReport(info);
      _devices[ip] = dev;
      onDevicesChanged?.call();
    } catch (_) {}
  }

  /// 接收并处理工控受控端的 TCP 接入
  void _handleClientConnection(Socket client) {
    final remoteIp = client.remoteAddress.address;
    onLogMessage?.call('[+] 受控工控机建立长连接: $remoteIp');

    _clientSockets[remoteIp] = client;
    _recvBuffers[remoteIp] = BytesBuilder();

    final dev = _devices[remoteIp] ?? AgentDevice(ip: remoteIp, source: 'tcp');
    dev.source = 'tcp';
    _devices[remoteIp] = dev;
    onDevicesChanged?.call();

    client.listen(
      (data) {
        _onDataReceived(remoteIp, data);
      },
      onError: (e) {
        _onClientDisconnected(remoteIp);
      },
      onDone: () {
        _onClientDisconnected(remoteIp);
      },
      cancelOnError: true,
    );
  }

  void _onDataReceived(String ip, List<int> chunk) {
    final buffer = _recvBuffers[ip];
    if (buffer == null) return;

    buffer.add(chunk);
    var bytes = buffer.toBytes();

    while (bytes.length >= 8) {
      var magicIdx = -1;
      for (var i = 0; i <= bytes.length - 4; i++) {
        if (bytes[i] == GwcCrypto.magicHeader[0] &&
            bytes[i + 1] == GwcCrypto.magicHeader[1] &&
            bytes[i + 2] == GwcCrypto.magicHeader[2] &&
            bytes[i + 3] == GwcCrypto.magicHeader[3]) {
          magicIdx = i;
          break;
        }
      }

      if (magicIdx < 0) {
        bytes = Uint8List(0);
        break;
      }

      if (magicIdx > 0) {
        bytes = bytes.sublist(magicIdx);
      }

      if (bytes.length < 8) break;

      final totalLen = ByteData.sublistView(
        Uint8List.fromList(bytes.sublist(4, 8)),
      ).getUint32(0, Endian.big);

      if (bytes.length - 8 < totalLen) {
        break;
      }

      final frame = bytes.sublist(0, 8 + totalLen);
      bytes = bytes.sublist(8 + totalLen);

      try {
        final msg = GwcCrypto.unpackPacket(frame);
        _handleAgentMessage(ip, msg);
      } catch (ex) {
        onLogMessage?.call('[-] 报文解密失败 [$ip]: $ex');
      }
    }

    _recvBuffers[ip] = BytesBuilder()..add(bytes);
  }

  void _handleAgentMessage(String ip, Map<String, dynamic> msg) {
    final type = msg['type'];
    final payload = msg['payload'] as Map<String, dynamic>? ?? {};

    if (type == 'STATUS_REPORT') {
      final dev = _devices[ip] ?? AgentDevice(ip: ip);
      dev.updateFromReport(payload);
      _devices[ip] = dev;
      onDevicesChanged?.call();
    }
  }

  void _onClientDisconnected(String ip) {
    _clientSockets.remove(ip);
    _recvBuffers.remove(ip);
    onLogMessage?.call('[-] 工控机长连接断开: $ip');
    onDevicesChanged?.call();
  }

  /// 向单个指定工控机下发指令 (双通道并发下发: TCP + UDP 9887 直连单播，毫秒级必达)
  bool sendCommand(String ip, String cmd, Map<String, dynamic> payload) {
    var sentSuccess = false;

    // 1. 本地先行乐观更新，音量与控制即时回显
    if (_devices.containsKey(ip)) {
      if (cmd == 'CMD_VOLUME') {
        if (payload['action'] == 'set' && payload.containsKey('level')) {
          _devices[ip]!.volume = (payload['level'] as num).toInt();
          _devices[ip]!.isMuted = false;
        } else if (payload['action'] == 'mute') {
          _devices[ip]!.isMuted = true;
        } else if (payload['action'] == 'unmute') {
          _devices[ip]!.isMuted = false;
        }
      }
      onDevicesChanged?.call();
    }

    // 2. 通道一：TCP 长连接（若存在）
    final socket = _clientSockets[ip];
    if (socket != null) {
      try {
        final packet = GwcCrypto.packPacket(cmd, payload);
        socket.add(packet);
        sentSuccess = true;
      } catch (_) {}
    }

    // 3. 通道二：UDP 9887 直连单播直达工控机
    try {
      final udpMsg = {
        'cmd': cmd,
        ...payload,
        'timestamp': DateTime.now().millisecondsSinceEpoch / 1000.0,
      };
      final raw = utf8.encode('${GwcDiscovery.discoveryMagic}${jsonEncode(udpMsg)}');
      _udpSocket?.send(raw, InternetAddress(ip), GwcDiscovery.discoveryPort);
      sentSuccess = true;
    } catch (_) {}

    return sentSuccess;
  }

  /// 向全馆所有工控机广播下发指令 (全馆一键关机、一键重启、统一音量拖动调控)
  int broadcastCommand(String cmd, Map<String, dynamic> payload) {
    var targetCount = _devices.length;
    if (targetCount == 0) targetCount = 1;

    // 1. 本地先行乐观批量更新
    if (cmd == 'CMD_VOLUME') {
      final level = (payload['level'] as num?)?.toInt() ?? 50;
      for (final dev in _devices.values) {
        dev.volume = level;
        dev.isMuted = false;
      }
      onDevicesChanged?.call();
    }

    // 2. 通道一：向已建立 TCP 连接的所有工控机发送
    for (final entry in _clientSockets.entries) {
      try {
        final packet = GwcCrypto.packPacket(cmd, payload);
        entry.value.add(packet);
      } catch (_) {}
    }

    // 3. 通道二：向全网广播地址 255.255.255.255 发送 UDP 广播报文
    final udpMsg = {
      'cmd': cmd,
      ...payload,
      'timestamp': DateTime.now().millisecondsSinceEpoch / 1000.0,
    };
    final raw = utf8.encode('${GwcDiscovery.discoveryMagic}${jsonEncode(udpMsg)}');

    try {
      _udpSocket?.send(raw, InternetAddress('255.255.255.255'), GwcDiscovery.discoveryPort);
    } catch (_) {}

    // 4. 通道三：对所有已知工控机 IP 逐一发送 UDP 单播补充
    for (final dev in _devices.values) {
      try {
        _udpSocket?.send(raw, InternetAddress(dev.ip), GwcDiscovery.discoveryPort);
      } catch (_) {}
    }

    return targetCount;
  }

  /// 纳管新扫描或探测到的设备
  void registerDiscoveredDevice(AgentDevice device) {
    if (_devices.containsKey(device.ip)) {
      _devices[device.ip]!.updateFromReport(device.toJson());
    } else {
      _devices[device.ip] = device;
    }
    onDevicesChanged?.call();
  }
}
