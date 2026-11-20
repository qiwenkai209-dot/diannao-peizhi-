import 'dart:convert';

/// 展馆工控受控设备实体模型
class AgentDevice {
  final String ip;
  String hostname;
  String customName;
  double cpu;
  double gpu;
  double mem;
  String activeWindow;
  bool isAuthorized;
  String requestCode;
  String licenseStatus;
  List<Map<String, dynamic>> presetApps;
  DateTime lastSeen;
  int latencyMs;
  String source;
  int volume;
  bool isMuted;

  AgentDevice({
    required this.ip,
    this.hostname = '',
    this.customName = '',
    this.cpu = 0.0,
    this.gpu = 0.0,
    this.mem = 0.0,
    this.activeWindow = '',
    this.isAuthorized = false,
    this.requestCode = '',
    this.licenseStatus = 'UNKNOWN',
    List<Map<String, dynamic>>? presetApps,
    DateTime? lastSeen,
    this.latencyMs = 1,
    this.source = 'beacon',
    this.volume = 50,
    this.isMuted = false,
  })  : presetApps = presetApps ?? [],
        lastSeen = lastSeen ?? DateTime.now();

  /// 显示名称：优先自定义备注名，其次工控机主机名，最后为 IP
  String get displayName {
    if (customName.isNotEmpty) return customName;
    if (hostname.isNotEmpty) return hostname;
    return ip;
  }

  /// 状态是否活跃（10秒内有心跳则在线）
  bool get isOnline {
    final diff = DateTime.now().difference(lastSeen).inSeconds;
    return diff < 10;
  }

  /// 从心跳或探测 JSON 数据更新属性
  void updateFromReport(Map<String, dynamic> data) {
    if (data.containsKey('hostname') && (data['hostname'] as String).isNotEmpty) {
      hostname = data['hostname'] as String;
    }
    if (data.containsKey('custom_name') && (data['custom_name'] as String).isNotEmpty) {
      customName = data['custom_name'] as String;
    }
    if (data.containsKey('cpu')) {
      cpu = (data['cpu'] as num).toDouble();
    }
    if (data.containsKey('gpu')) {
      gpu = (data['gpu'] as num).toDouble();
    }
    if (data.containsKey('mem')) {
      mem = (data['mem'] as num).toDouble();
    }
    if (data.containsKey('active_window')) {
      activeWindow = (data['active_window'] as String?) ?? '';
    }
    if (data.containsKey('authorized')) {
      isAuthorized = data['authorized'] == true;
    }
    if (data.containsKey('request_code')) {
      requestCode = (data['request_code'] as String?) ?? '';
    }
    if (data.containsKey('license_status')) {
      licenseStatus = (data['license_status'] as String?) ?? 'UNKNOWN';
    }
    if (data.containsKey('preset_apps') && data['preset_apps'] is List) {
      presetApps = List<Map<String, dynamic>>.from(
        (data['preset_apps'] as List).map((x) => Map<String, dynamic>.from(x as Map)),
      );
    }
    if (data.containsKey('volume')) {
      volume = (data['volume'] as num).toInt();
    }
    if (data.containsKey('is_muted')) {
      isMuted = data['is_muted'] == true;
    }
    lastSeen = DateTime.now();
  }

  Map<String, dynamic> toJson() => {
        'ip': ip,
        'hostname': hostname,
        'custom_name': customName,
        'cpu': cpu,
        'gpu': gpu,
        'mem': mem,
        'active_window': activeWindow,
        'authorized': isAuthorized,
        'request_code': requestCode,
        'license_status': licenseStatus,
        'is_online': isOnline,
        'volume': volume,
        'is_muted': isMuted,
        'last_seen': lastSeen.toIso8601String(),
      };
}
