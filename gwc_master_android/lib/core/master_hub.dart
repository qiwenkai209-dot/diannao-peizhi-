import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import '../models/agent_device.dart';
import 'crypto.dart';

/// 国文创展馆主控综合集群管理中心 (Dart 核心实现)
class GwcMasterHub {
  static const int defaultMasterPort = 9888;

  ServerSocket? _serverSocket;
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

  /// 启动 TCP 9888 服务端监听
  Future<void> start({int port = defaultMasterPort}) async {
    if (_running) return;
    try {
      _serverSocket = await ServerSocket.bind(InternetAddress.anyIPv4, port);
      _running = true;
      onLogMessage?.call('🏛️ 主控端集群通信总线已启动: TCP 端口 $port');

      _serverSocket?.listen(
        _handleClientConnection,
        onError: (e) {
          onLogMessage?.call('[-] 集群监听套接字异常: $e');
        },
      );
    } catch (e) {
      onLogMessage?.call('[-] 绑定 TCP $port 端口失败: $e');
    }
  }

  void stop() {
    _running = false;
    for (final s in _clientSockets.values) {
      try {
        s.destroy();
      } catch (_) {}
    }
    _clientSockets.clear();
    _recvBuffers.clear();
    _serverSocket?.close();
    _serverSocket = null;
    onLogMessage?.call('[-] 主控端服务已停止');
  }

  /// 接收并处理工控受控端的 TCP 接入
  void _handleClientConnection(Socket client) {
    final remoteIp = client.remoteAddress.address;
    onLogMessage?.call('[+] 受控工控机接入: $remoteIp');

    _clientSockets[remoteIp] = client;
    _recvBuffers[remoteIp] = BytesBuilder();

    // 确保设备注册到列表
    if (!_devices.containsKey(remoteIp)) {
      _devices[remoteIp] = AgentDevice(ip: remoteIp, source: 'tcp');
    } else {
      _devices[remoteIp]!.source = 'tcp';
    }
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

    // 循环提取解包 GWCC 完整封包
    while (bytes.length >= 8) {
      // 寻找 MAGIC_HEADER
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
        // 数据包尚未完整接收
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
    onLogMessage?.call('[-] 工控机断开长连接: $ip');
    onDevicesChanged?.call();
  }

  /// 向单个指定 IP 下发指令
  bool sendCommand(String ip, String cmd, Map<String, dynamic> payload) {
    final socket = _clientSockets[ip];
    if (socket == null) return false;

    try {
      final packet = GwcCrypto.packPacket(cmd, payload);
      socket.add(packet);
      return true;
    } catch (e) {
      return false;
    }
  }

  /// 向全馆所有在线工控机广播下发指令
  int broadcastCommand(String cmd, Map<String, dynamic> payload) {
    var count = 0;
    for (final entry in _clientSockets.entries) {
      try {
        final packet = GwcCrypto.packPacket(cmd, payload);
        entry.value.add(packet);
        count++;
      } catch (_) {}
    }
    return count;
  }

  /// 纳管新扫描到的设备
  void registerDiscoveredDevice(AgentDevice device) {
    if (_devices.containsKey(device.ip)) {
      _devices[device.ip]!.updateFromReport(device.toJson());
    } else {
      _devices[device.ip] = device;
    }
    onDevicesChanged?.call();
  }
}

