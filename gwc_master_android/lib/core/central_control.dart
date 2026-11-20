import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'master_hub.dart';

/// 展馆第三方智能中控多协议总线服务 (UDP 9889 / TCP 9890 / HTTP 9891)
class CentralControlManager {
  final GwcMasterHub masterHub;
  final void Function(String log)? onLog;

  RawDatagramSocket? _udpSocket;
  ServerSocket? _tcpServer;
  HttpServer? _httpServer;

  bool _running = false;
  bool get isRunning => _running;

  CentralControlManager({required this.masterHub, this.onLog});

  Future<void> start({
    int udpPort = 9889,
    int tcpPort = 9890,
    int httpPort = 9891,
  }) async {
    if (_running) return;
    _running = true;

    // 1. 启动 UDP 9889 中控监听
    try {
      _udpSocket = await RawDatagramSocket.bind(InternetAddress.anyIPv4, udpPort);
      onLog?.call('📡 智能中控 UDP 总线已就绪: 端口 $udpPort');
      _udpSocket?.listen((event) {
        if (event == RawSocketEvent.read) {
          final dg = _udpSocket?.receive();
          if (dg != null) {
            final raw = utf8.decode(dg.data, allowMalformed: true).trim();
            final resp = _dispatch(raw, protocol: 'UDP');
            final respBytes = utf8.encode(jsonEncode(resp));
            try {
              _udpSocket?.send(respBytes, dg.address, dg.port);
            } catch (_) {}
          }
        }
      });
    } catch (e) {
      onLog?.call('[-] 启动 UDP 中控失败: $e');
    }

    // 2. 启动 TCP 9890 中控监听
    try {
      _tcpServer = await ServerSocket.bind(InternetAddress.anyIPv4, tcpPort);
      onLog?.call('🔌 智能中控 TCP Socket 总线已就绪: 端口 $tcpPort');
      _tcpServer?.listen((client) {
        client.listen((data) {
          final raw = utf8.decode(data, allowMalformed: true).trim();
          final resp = _dispatch(raw, protocol: 'TCP');
          client.writeln(jsonEncode(resp));
        });
      });
    } catch (e) {
      onLog?.call('[-] 启动 TCP 中控失败: $e');
    }

    // 3. 启动 HTTP 9891 RESTful API 服务
    try {
      _httpServer = await HttpServer.bind(InternetAddress.anyIPv4, httpPort);
      onLog?.call('🌐 智能中控 HTTP RESTful API 已就绪: http://0.0.0.0:$httpPort');
      _httpServer?.listen(_handleHttpRequest);
    } catch (e) {
      onLog?.call('[-] 启动 HTTP API 服务失败: $e');
    }
  }

  void stop() {
    _running = false;
    _udpSocket?.close();
    _udpSocket = null;
    _tcpServer?.close();
    _tcpServer = null;
    _httpServer?.close(force: true);
    _httpServer = null;
    onLog?.call('[-] 智能中控总线已停止');
  }

  void _handleHttpRequest(HttpRequest request) async {
    request.response.headers.add('Access-Control-Allow-Origin', '*');
    request.response.headers.add('Content-Type', 'application/json; charset=utf-8');

    final uri = request.uri;
    final path = uri.path;

    if (path == '/api/status' || path == '/api/ping') {
      final data = {
        'status': 'ONLINE',
        'app': 'GuoWenChuang Master Hub Android',
        'online_devices': masterHub.onlineCount,
        'total_registered': masterHub.devices.length,
        'timestamp': DateTime.now().millisecondsSinceEpoch,
      };
      request.response.write(jsonEncode(data));
      await request.response.close();
      return;
    }

    if (path == '/api/devices') {
      final list = masterHub.devices.map((d) => d.toJson()).toList();
      request.response.write(jsonEncode({'code': 200, 'devices': list}));
      await request.response.close();
      return;
    }

    if (path == '/api/control') {
      String action = uri.queryParameters['action'] ?? '';
      Map<String, dynamic> params = Map.from(uri.queryParameters);

      if (request.method == 'POST') {
        try {
          final bodyStr = await utf8.decodeStream(request);
          if (bodyStr.isNotEmpty) {
            final jsonBody = jsonDecode(bodyStr) as Map<String, dynamic>;
            if (jsonBody.containsKey('action')) {
              action = jsonBody['action'] as String;
            }
            params.addAll(jsonBody);
          }
        } catch (_) {}
      }

      final resp = _dispatchJson(action, params, protocol: 'HTTP');
      request.response.write(jsonEncode(resp));
      await request.response.close();
      return;
    }

    request.response.statusCode = HttpStatus.notFound;
    request.response.write(jsonEncode({'error': 'Not Found'}));
    await request.response.close();
  }

  Map<String, dynamic> _dispatch(String rawCmd, {required String protocol}) {
    if (rawCmd.startsWith('{') && rawCmd.endsWith('}')) {
      try {
        final jsonMap = jsonDecode(rawCmd) as Map<String, dynamic>;
        final action = (jsonMap['action'] ?? jsonMap['cmd'] ?? '').toString();
        return _dispatchJson(action, jsonMap, protocol: protocol);
      } catch (_) {}
    }

    // 纯文本指令解析，如 ALL_SHUTDOWN 或 SET_VOLUME:80
    final parts = rawCmd.split(':');
    final action = parts[0].toUpperCase().trim();
    final params = <String, dynamic>{};
    if (parts.length > 1) {
      params['value'] = parts[1].trim();
      params['level'] = int.tryParse(parts[1].trim()) ?? 50;
    }

    return _dispatchJson(action, params, protocol: protocol);
  }

  Map<String, dynamic> _dispatchJson(
    String action,
    Map<String, dynamic> params, {
    required String protocol,
  }) {
    final act = action.toUpperCase();
    onLog?.call('🎮 [$protocol中控] 收到指令: $act');

    switch (act) {
      case 'ALL_SHUTDOWN':
        final count = masterHub.broadcastCommand(
          'CMD_SHUTDOWN',
          {'force': true, 'timeout': 0},
        );
        return {'status': 'SUCCESS', 'code': 200, 'msg': '已向全馆 $count 台设备下发关机指令'};

      case 'ALL_REBOOT':
        final count = masterHub.broadcastCommand(
          'CMD_REBOOT',
          {'force': true, 'timeout': 0},
        );
        return {'status': 'SUCCESS', 'code': 200, 'msg': '已向全馆 $count 台设备下发重启指令'};

      case 'ALL_MUTE':
        final count = masterHub.broadcastCommand(
          'CMD_VOLUME',
          {'action': 'mute'},
        );
        return {'status': 'SUCCESS', 'code': 200, 'msg': '已向全馆 $count 台设备下发静音'};

      case 'ALL_UNMUTE':
        final count = masterHub.broadcastCommand(
          'CMD_VOLUME',
          {'action': 'unmute'},
        );
        return {'status': 'SUCCESS', 'code': 200, 'msg': '已向全馆 $count 台设备解除静音'};

      case 'ALL_VOLUME':
      case 'SET_ALL_VOLUME':
        final level = (params['level'] as num?)?.toInt() ?? 50;
        final count = masterHub.broadcastCommand(
          'CMD_VOLUME',
          {'action': 'set', 'level': level},
        );
        return {'status': 'SUCCESS', 'code': 200, 'msg': '已向全馆 $count 台设备设定音量: $level%'};

      case 'DEV_SHUTDOWN':
        final ip = (params['ip'] ?? '').toString();
        final ok = masterHub.sendCommand(ip, 'CMD_SHUTDOWN', {'force': true, 'timeout': 0});
        return {'status': ok ? 'SUCCESS' : 'ERROR', 'msg': '向 [$ip] 下发关机: ${ok ? "成功" : "失败(离线)"}'};

      case 'DEV_REBOOT':
        final ip = (params['ip'] ?? '').toString();
        final ok = masterHub.sendCommand(ip, 'CMD_REBOOT', {'force': true, 'timeout': 0});
        return {'status': ok ? 'SUCCESS' : 'ERROR', 'msg': '向 [$ip] 下发重启: ${ok ? "成功" : "失败(离线)"}'};

      case 'DEV_VOLUME':
        final ip = (params['ip'] ?? '').toString();
        final level = (params['level'] as num?)?.toInt() ?? 50;
        final ok = masterHub.sendCommand(ip, 'CMD_VOLUME', {'action': 'set', 'level': level});
        return {'status': ok ? 'SUCCESS' : 'ERROR', 'msg': '向 [$ip] 设定音量为 $level%: ${ok ? "成功" : "失败(离线)"}'};

      case 'PING':
      case 'STATUS':
        return {
          'status': 'SUCCESS',
          'msg': 'PONG:GWC_MASTER_HUB_ANDROID',
          'online_count': masterHub.onlineCount,
        };

      default:
        return {'status': 'ERROR', 'code': 400, 'msg': '未识别的中控指令: $act'};
    }
  }
}
