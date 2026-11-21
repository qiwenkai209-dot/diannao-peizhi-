import 'dart:async';
import 'package:flutter/material.dart';
import '../core/master_hub.dart';
import '../core/discovery.dart';
import '../core/central_control.dart';
import '../models/agent_device.dart';
import 'theme.dart';
import 'device_control_sheet.dart';
import 'radar_scan_dialog.dart';
import 'license_machine_page.dart';
import 'central_control_doc_page.dart';

class DashboardPage extends StatefulWidget {
  const DashboardPage({super.key});

  @override
  State<DashboardPage> createState() => _DashboardPageState();
}

class _DashboardPageState extends State<DashboardPage> {
  late GwcMasterHub _masterHub;
  late GwcDiscovery _discovery;
  late CentralControlManager _centralControl;
  String _latestLog = '集群就绪，正在后台持续侦听受控工控机...';
  Timer? _refreshTimer;
  double _batchVolume = 50.0;

  @override
  void initState() {
    super.initState();

    _masterHub = GwcMasterHub(
      onDevicesChanged: () {
        if (mounted) setState(() {});
      },
      onLogMessage: (log) {
        if (mounted) setState(() => _latestLog = log);
      },
    );

    _discovery = GwcDiscovery(
      onDeviceDiscovered: (dev) {
        _masterHub.registerDiscoveredDevice(dev);
      },
    );

    _centralControl = CentralControlManager(
      masterHub: _masterHub,
      onLog: (log) {
        if (mounted) setState(() => _latestLog = log);
      },
    );

    // 启动所有服务
    _masterHub.start();
    _discovery.startBeaconListener();
    _centralControl.start();

    // 1秒定时刷新界面
    _refreshTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    _refreshTimer?.cancel();
    _discovery.stopBeaconListener();
    _masterHub.stop();
    _centralControl.stop();
    super.dispose();
  }

  void _confirmBatch(String title, String content, VoidCallback onConfirm) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: GwcTheme.surface,
        title: Text(title, style: const TextStyle(color: GwcTheme.accentAmber, fontWeight: FontWeight.bold)),
        content: Text(content),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('取消', style: TextStyle(color: GwcTheme.textSecondary)),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(backgroundColor: GwcTheme.accentRed),
            onPressed: () {
              Navigator.pop(ctx);
              onConfirm();
            },
            child: const Text('确认执行', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
    );
  }

  void _batchShutdown() {
    _confirmBatch(
      '⚠️ 全馆一键关机确认',
      '确定要向全展馆所有在线工控机发送【一键关机】指令吗？工控机将全部安全关闭电源。',
      () {
        final cnt = _masterHub.broadcastCommand('CMD_SHUTDOWN', {'force': true, 'timeout': 0});
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('已向全馆 $cnt 台工控机下发一键关机指令')),
        );
      },
    );
  }

  void _batchReboot() {
    _confirmBatch(
      '🔄 全馆一键重启确认',
      '确定要向全展馆所有在线工控机发送【一键重启】指令吗？',
      () {
        final cnt = _masterHub.broadcastCommand('CMD_REBOOT', {'force': true, 'timeout': 0});
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('已向全馆 $cnt 台工控机下发一键重启指令')),
        );
      },
    );
  }

  void _batchVolumeChange(double val) {
    setState(() => _batchVolume = val);
    _masterHub.broadcastCommand('CMD_VOLUME', {'action': 'set', 'level': val.toInt()});
  }

  @override
  Widget build(BuildContext context) {
    final devices = _masterHub.devices;
    final onlineCount = _masterHub.onlineCount;

    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                color: GwcTheme.primary.withOpacity(0.15),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: GwcTheme.primary.withOpacity(0.4)),
              ),
              child: const Text(
                '🏛️ 展馆智能集群综合管控中心 · 移动端',
                style: TextStyle(color: GwcTheme.primary, fontSize: 16, fontWeight: FontWeight.bold),
              ),
            ),
            const SizedBox(width: 14),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                color: onlineCount > 0 ? GwcTheme.accentGreen.withOpacity(0.2) : Colors.white10,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Text(
                '在线: $onlineCount / ${devices.length} 台',
                style: TextStyle(
                  color: onlineCount > 0 ? GwcTheme.accentGreen : GwcTheme.textSecondary,
                  fontSize: 12,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ),
          ],
        ),
        actions: [
          IconButton(
            tooltip: '局域网雷达搜索',
            icon: const Icon(Icons.radar, color: GwcTheme.primary),
            onPressed: () {
              showDialog(
                context: context,
                builder: (ctx) => RadarScanDialog(masterHub: _masterHub),
              );
            },
          ),
          IconButton(
            tooltip: '商业授权中枢',
            icon: const Icon(Icons.verified_user, color: GwcTheme.accentAmber),
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => LicenseMachinePage(masterHub: _masterHub)),
              );
            },
          ),
          IconButton(
            tooltip: '中控全协议手册',
            icon: const Icon(Icons.menu_book, color: GwcTheme.secondary),
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => CentralControlDocPage(centralManager: _centralControl)),
              );
            },
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: Column(
        children: [
          // 顶部全馆批量快捷调度条
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            color: GwcTheme.surface,
            child: Column(
              children: [
                Row(
                  children: [
                    ElevatedButton.icon(
                      style: ElevatedButton.styleFrom(
                        backgroundColor: GwcTheme.accentRed.withOpacity(0.9),
                        foregroundColor: Colors.white,
                      ),
                      icon: const Icon(Icons.power_settings_new, size: 18),
                      label: const Text('全馆一键关机', style: TextStyle(fontWeight: FontWeight.bold)),
                      onPressed: _batchShutdown,
                    ),
                    const SizedBox(width: 10),
                    ElevatedButton.icon(
                      style: ElevatedButton.styleFrom(
                        backgroundColor: GwcTheme.surfaceCard,
                        foregroundColor: GwcTheme.secondary,
                      ),
                      icon: const Icon(Icons.refresh, size: 18),
                      label: const Text('全馆一键重启'),
                      onPressed: _batchReboot,
                    ),
                    const SizedBox(width: 14),
                    const Text('🔊 统一音量:'),
                    Expanded(
                      child: Slider(
                        value: _batchVolume,
                        min: 0,
                        max: 100,
                        divisions: 100,
                        activeColor: GwcTheme.primary,
                        onChanged: _batchVolumeChange,
                      ),
                    ),
                    Text('${_batchVolume.toInt()}%', style: const TextStyle(fontWeight: FontWeight.bold)),
                  ],
                ),
                const SizedBox(height: 8),
                // 实时调度跑马灯
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    color: GwcTheme.background,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.notifications_active, size: 16, color: GwcTheme.primary),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          _latestLog,
                          style: const TextStyle(fontSize: 12, color: GwcTheme.textSecondary),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      const Text(
                        'TCP:9888 | UDP:9889 | TCP:9890 | HTTP:9891',
                        style: TextStyle(fontSize: 11, color: Colors.white30),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),

          // 工控机卡片列表 / 监控大厅
          Expanded(
            child: devices.isEmpty
                ? Center(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        const Icon(Icons.devices, size: 64, color: Colors.white24),
                        const SizedBox(height: 16),
                        const Text('当前大厅暂无受控工控机', style: TextStyle(fontSize: 16, color: GwcTheme.textSecondary)),
                        const SizedBox(height: 12),
                        ElevatedButton.icon(
                          style: ElevatedButton.styleFrom(backgroundColor: GwcTheme.primary, foregroundColor: Colors.black),
                          icon: const Icon(Icons.radar),
                          label: const Text('一键雷达扫描局域网从机'),
                          onPressed: () {
                            showDialog(
                              context: context,
                              builder: (ctx) => RadarScanDialog(masterHub: _masterHub),
                            );
                          },
                        ),
                      ],
                    ),
                  )
                : LayoutBuilder(
                    builder: (context, constraints) {
                      final crossAxisCount = constraints.maxWidth > 900 ? 3 : (constraints.maxWidth > 600 ? 2 : 1);
                      return GridView.builder(
                        padding: const EdgeInsets.all(16),
                        gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                          crossAxisCount: crossAxisCount,
                          childAspectRatio: 1.6,
                          crossAxisSpacing: 16,
                          mainAxisSpacing: 16,
                        ),
                        itemCount: devices.length,
                        itemBuilder: (context, index) {
                          final dev = devices[index];
                          return _buildDeviceCard(dev);
                        },
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }

  Widget _buildDeviceCard(AgentDevice dev) {
    final isOnline = dev.isOnline;

    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: () {
          showModalBottomSheet(
            context: context,
            isScrollControlled: true,
            backgroundColor: Colors.transparent,
            builder: (ctx) => DeviceControlSheet(device: dev, masterHub: _masterHub),
          );
        },
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    width: 10,
                    height: 10,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: isOnline ? GwcTheme.accentGreen : Colors.grey,
                      boxShadow: isOnline
                          ? [BoxShadow(color: GwcTheme.accentGreen.withOpacity(0.6), blurRadius: 6)]
                          : null,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      dev.displayName,
                      style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(
                      color: dev.isAuthorized ? GwcTheme.accentGreen.withOpacity(0.2) : GwcTheme.accentAmber.withOpacity(0.2),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text(
                      dev.isAuthorized ? '商业授权' : '未授权',
                      style: TextStyle(
                        fontSize: 10,
                        color: dev.isAuthorized ? GwcTheme.accentGreen : GwcTheme.accentAmber,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 6),
              Text(
                'IP: ${dev.ip}   |   活动窗口: ${dev.activeWindow.isNotEmpty ? dev.activeWindow : "桌面/空闲"}',
                style: const TextStyle(fontSize: 12, color: GwcTheme.textSecondary),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
              const Spacer(),
              // 硬件资源进度条
              _buildMetricRow('CPU', dev.cpu, GwcTheme.primary),
              const SizedBox(height: 4),
              _buildMetricRow('RAM', dev.mem, GwcTheme.secondary),
              if (dev.gpu > 0) ...[
                const SizedBox(height: 4),
                _buildMetricRow('GPU', dev.gpu, GwcTheme.accentAmber),
              ],
              const Spacer(),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text('音量: ${dev.volume}%', style: const TextStyle(fontSize: 12, color: GwcTheme.textSecondary)),
                  Row(
                    children: [
                      IconButton(
                        icon: const Icon(Icons.settings, size: 18, color: GwcTheme.primary),
                        onPressed: () {
                          showModalBottomSheet(
                            context: context,
                            isScrollControlled: true,
                            backgroundColor: Colors.transparent,
                            builder: (ctx) => DeviceControlSheet(device: dev, masterHub: _masterHub),
                          );
                        },
                      ),
                      IconButton(
                        icon: const Icon(Icons.power_settings_new, size: 18, color: GwcTheme.accentRed),
                        onPressed: () {
                          _confirmBatch(
                            '关机确认',
                            '确定远程关闭工控机 [${dev.displayName}] 吗？',
                            () => _masterHub.sendCommand(dev.ip, 'CMD_SHUTDOWN', {'force': true, 'timeout': 0}),
                          );
                        },
                      ),
                    ],
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildMetricRow(String label, double val, Color color) {
    return Row(
      children: [
        SizedBox(width: 32, child: Text(label, style: const TextStyle(fontSize: 11, color: GwcTheme.textSecondary))),
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: (val / 100.0).clamp(0.0, 1.0),
              backgroundColor: Colors.white10,
              valueColor: AlwaysStoppedAnimation<Color>(color),
              minHeight: 6,
            ),
          ),
        ),
        const SizedBox(width: 8),
        SizedBox(
          width: 35,
          child: Text('${val.toInt()}%', style: const TextStyle(fontSize: 11, fontWeight: FontWeight.bold)),
        ),
      ],
    );
  }
}

