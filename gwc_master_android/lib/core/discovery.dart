import 'dart:async';
import 'dart:convert';
import 'dart:io';
import '../models/agent_device.dart';

/// 国文创局域网设备自动发现协议 (Dart 实现，兼容 gwc_discovery.py)
class GwcDiscovery {
  static const String discoveryMagic = 'GWCDISCOVER:';
  static const int discoveryPort = 9887;

  RawDatagramSocket? _beaconSocket;
  bool _isListening = false;
  final void Function(AgentDevice device)? onDeviceDiscovered;

  GwcDiscovery({this.onDeviceDiscovered});

  /// 获取手机本地局域网 Wi-Fi IPv4 地址 (优先 wlan / wifi / eth / 192.168 / 10 / 172)
  static Future<String> getLocalIp() async {
    try {
      final interfaces = await NetworkInterface.list(
        type: InternetAddressType.IPv4,
        includeLinkLocal: false,
      );
      // 1. 优先查找明确的 Wi-Fi 或以太网接口
      for (final iface in interfaces) {
        final name = iface.name.toLowerCase();
        if (name.contains('wlan') || name.contains('wifi') || name.contains('eth') || name.contains('en')) {
          for (final addr in iface.addresses) {
            if (!addr.isLoopback) return addr.address;
          }
        }
      }
      // 2. 查找标准私有网段 (排除移动数据网络)
      for (final iface in interfaces) {
        final name = iface.name.toLowerCase();
        if (!name.contains('rmnet') && !name.contains('pdp') && !name.contains('tun')) {
          for (final addr in iface.addresses) {
            if (!addr.isLoopback &&
                (addr.address.startsWith('192.168.') ||
                    addr.address.startsWith('10.') ||
                    addr.address.startsWith('172.'))) {
              return addr.address;
            }
          }
        }
      }
      // 3. 通用兜底
      for (final iface in interfaces) {
        for (final addr in iface.addresses) {
          if (!addr.isLoopback) return addr.address;
        }
      }
    } catch (_) {}
    return '';
  }

  /// 获取包含通用广播与子网定向广播的地址列表 (确保全网段抗弱网全覆盖)
  static List<String> getBroadcastAddresses(String localIp) {
    final list = <String>['255.255.255.255'];
    if (localIp.isNotEmpty && localIp.contains('.')) {
      final parts = localIp.split('.');
      if (parts.length == 4) {
        final subnetBcast = '${parts[0]}.${parts[1]}.${parts[2]}.255';
        if (!list.contains(subnetBcast)) {
          list.add(subnetBcast);
        }
      }
    }
    return list;
  }

  /// 启动后台被动监听上线宣告 (Beacon)
  Future<void> startBeaconListener() async {
    if (_isListening) return;
    try {
      _beaconSocket = await RawDatagramSocket.bind(
        InternetAddress.anyIPv4,
        discoveryPort,
        reuseAddress: true,
        reusePort: true,
      );
      _beaconSocket?.broadcastEnabled = true;
      _isListening = true;

      _beaconSocket?.listen((RawSocketEvent event) {
        if (event == RawSocketEvent.read) {
          final dg = _beaconSocket?.receive();
          if (dg != null) {
            _handleDatagram(dg.data, dg.address.address);
          }
        }
      });
    } catch (e) {
      // 端口可能已被绑定或权限受限
    }
  }

  void stopBeaconListener() {
    _isListening = false;
    _beaconSocket?.close();
    _beaconSocket = null;
  }

  /// 向局域网全网段主动发送探测广播，扫描所有在线受控工控机
  Future<List<AgentDevice>> scan({
    Duration timeout = const Duration(milliseconds: 2500),
    String localMasterIp = '',
    int masterPort = 9888,
    bool autoConnect = true,
  }) async {
    final discoveredMap = <String, AgentDevice>{};
    RawDatagramSocket? scanSocket;

    try {
      if (localMasterIp.isEmpty) {
        localMasterIp = await getLocalIp();
      }

      scanSocket = await RawDatagramSocket.bind(
        InternetAddress.anyIPv4,
        0, // 随机端口
        reuseAddress: true,
      );
      scanSocket.broadcastEnabled = true;

      final token = 'probe_${DateTime.now().millisecondsSinceEpoch}';
      final probeMsg = {
        'cmd': 'DISCOVER_PROBE',
        'token': token,
        'master_ip': localMasterIp,
        'master_port': masterPort,
        'auto_connect': true,
        'force_reconnect': true,
        'timestamp': DateTime.now().millisecondsSinceEpoch / 1000.0,
      };

      final payload = utf8.encode(discoveryMagic + jsonEncode(probeMsg));

      // 发送到全网广播
      final broadcastAddrs = [
        InternetAddress('255.255.255.255'),
      ];

      for (final addr in broadcastAddrs) {
        try {
          scanSocket.send(payload, addr, discoveryPort);
        } catch (_) {}
      }

      final completer = Completer<List<AgentDevice>>();

      scanSocket.listen((RawSocketEvent event) {
        if (event == RawSocketEvent.read) {
          final dg = scanSocket?.receive();
          if (dg != null) {
            final raw = utf8.decode(dg.data, allowMalformed: true);
            if (raw.startsWith(discoveryMagic)) {
              final jsonStr = raw.substring(discoveryMagic.length);
              try {
                final map = jsonDecode(jsonStr) as Map<String, dynamic>;
                if (map['cmd'] == 'DISCOVER_REPLY' &&
                    map['probe_token'] == token) {
                  final info = map['info'] as Map<String, dynamic>? ?? {};
                  final ip = (info['ip'] as String?)?.isNotEmpty == true
                      ? info['ip'] as String
                      : dg.address.address;

                  final dev = AgentDevice(
                    ip: ip,
                    hostname: info['hostname'] ?? '',
                    customName: info['custom_name'] ?? '',
                    cpu: (info['cpu'] as num?)?.toDouble() ?? 0.0,
                    gpu: (info['gpu'] as num?)?.toDouble() ?? 0.0,
                    mem: (info['mem'] as num?)?.toDouble() ?? 0.0,
                    isAuthorized: info['authorized'] == true,
                    requestCode: info['request_code'] ?? '',
                    source: 'probe',
                  );

                  discoveredMap[ip] = dev;
                  onDeviceDiscovered?.call(dev);
                }
              } catch (_) {}
            }
          }
        }
      });

      Future.delayed(timeout, () {
        if (!completer.isCompleted) {
          scanSocket?.close();
          completer.complete(discoveredMap.values.toList());
        }
      });

      return await completer.future;
    } catch (e) {
      scanSocket?.close();
      return discoveredMap.values.toList();
    }
  }

  void _handleDatagram(List<int> data, String remoteIp) {
    try {
      final raw = utf8.decode(data, allowMalformed: true);
      if (!raw.startsWith(discoveryMagic)) return;

      final jsonStr = raw.substring(discoveryMagic.length);
      final map = jsonDecode(jsonStr) as Map<String, dynamic>;
      final cmd = map['cmd'];

      if (cmd == 'AGENT_BEACON') {
        final info = map['info'] as Map<String, dynamic>? ?? {};
        final ip = (info['ip'] as String?)?.isNotEmpty == true
            ? info['ip'] as String
            : remoteIp;

        final dev = AgentDevice(
          ip: ip,
          hostname: info['hostname'] ?? '',
          customName: info['custom_name'] ?? '',
          cpu: (info['cpu'] as num?)?.toDouble() ?? 0.0,
          gpu: (info['gpu'] as num?)?.toDouble() ?? 0.0,
          mem: (info['mem'] as num?)?.toDouble() ?? 0.0,
          isAuthorized: info['authorized'] == true,
          requestCode: info['request_code'] ?? '',
          source: 'beacon',
        );

        onDeviceDiscovered?.call(dev);
      }
    } catch (_) {}
  }
}

