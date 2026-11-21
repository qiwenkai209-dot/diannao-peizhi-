import 'dart:async';
import 'package:flutter/material.dart';
import '../core/master_hub.dart';
import '../core/discovery.dart';
import '../core/central_control.dart';
import '../models/agent_device.dart';
import 'theme.dart';
import 'device_control_sheet.dart';
import 'radar_scan_dialog.dart';
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

    // 启动所有后台总线服务
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

  void _confirmPower(String title, String content, VoidCallback onConfirm) {
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

  void _showManualAddDialog() {
    final ipController = TextEditingController();
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: GwcTheme.surface,
        title: const Text('手动直连工控机 IP', style: TextStyle(color: GwcTheme.primary, fontWeight: FontWeight.bold)),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('输入展厅工控机或受控终端的局域网 IP (例如 192.168.1.123):', style: TextStyle(fontSize: 13, color: GwcTheme.textSecondary)),
            const SizedBox(height: 12),
            TextField(
              controller: ipController,
              decoration: const InputDecoration(
                hintText: '192.168.1.123',
                prefixIcon: Icon(Icons.lan, color: GwcTheme.primary),
                border: OutlineInputBorder(),
              ),
              keyboardType: TextInputType.datetime,
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('取消', style: TextStyle(color: GwcTheme.textSecondary)),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(backgroundColor: GwcTheme.primary, foregroundColor: Colors.black),
            onPressed: () {
              final ip = ipController.text.trim();
              if (ip.isNotEmpty) {
                _masterHub.registerDiscoveredDevice(AgentDevice(ip: ip, customName: '展馆工控机 ($ip)'));
                _masterHub.broadcastProbe();
                Navigator.pop(ctx);
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text('已添加工控机 [$ip]，正在握手连接...')),
                );
              }
            },
            child: const Text('立即直连纳管'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final devices = _masterHub.devices;

    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            const Icon(Icons.hub_outlined, color: GwcTheme.primary),
            const SizedBox(width: 10),
            const Text('展馆智能集群综合管控中心', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 18)),
            const SizedBox(width: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
              decoration: BoxDecoration(
                color: GwcTheme.primary.withOpacity(0.15),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: GwcTheme.primary.withOpacity(0.4)),
              ),
              child: Text(
                '在线: ${_masterHub.onlineCount}/${devices.length}',
                style: const TextStyle(fontSize: 12, color: GwcTheme.primary, fontWeight: FontWeight.bold),
              ),
            ),
          ],
        ),
        actions: [
          IconButton(
            tooltip: '一键雷达扫描',
            icon: const Icon(Icons.radar, color: GwcTheme.primary),
            onPressed: () {
              showDialog(
                context: context,
                builder: (ctx) => RadarScanDialog(masterHub: _masterHub),
              );
            },
          ),
          IconButton(
            tooltip: '手动直连工控机 IP',
            icon: const Icon(Icons.add_link, color: GwcTheme.secondary),
            onPressed: _showManualAddDialog,
          ),
          IconButton(
            tooltip: '第三方中控协议指南',
            icon: const Icon(Icons.code),
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => CentralControlDocPage(centralManager: _centralControl)),
              );
            },
          ),
          IconButton(
            tooltip: '全网广播探测刷新',
            icon: const Icon(Icons.refresh),
            onPressed: () {
              _masterHub.broadcastProbe();
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                  duration: Duration(milliseconds: 800),
                  content: Text('已向局域网广播 UDP 9887 探测指令'),
                ),
              );
            },
          ),
        ],
      ),
      body: Column(
        children: [
          // 顶部集群状态与通信总线指示条（无全馆重启、无全馆关机、无全馆音量条）
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            color: GwcTheme.surface,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
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
                    'TCP:9888 | UDP:9887 控制引擎',
                    style: TextStyle(fontSize: 11, color: Colors.white30),
                  ),
                ],
              ),
            ),
          ),

          // 工控机卡片列表 / 监控大厅（用户专注于单机监控与控制）
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
                      color: isOnline ? GwcTheme.accentGreen.withOpacity(0.2) : Colors.white10,
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text(
                      isOnline ? '在线' : '离线',
                      style: TextStyle(
                        fontSize: 10,
                        color: isOnline ? GwcTheme.accentGreen : GwcTheme.textSecondary,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 6),
              Text(
                'IP: ${dev.ip}   |   窗口: ${dev.activeWindow.isNotEmpty ? dev.activeWindow : "系统桌面 / 待机空闲"}',
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
                  Row(
                    children: [
                      Icon(
                        dev.isMuted ? Icons.volume_off : Icons.volume_up,
                        size: 16,
                        color: dev.isMuted ? GwcTheme.accentRed : GwcTheme.primary,
                      ),
                      const SizedBox(width: 4),
                      Text(
                        dev.isMuted ? '静音' : '音量: ${dev.volume}%',
                        style: TextStyle(
                          fontSize: 12,
                          color: dev.isMuted ? GwcTheme.accentRed : GwcTheme.textSecondary,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ],
                  ),
                  Row(
                    children: [
                      IconButton(
                        tooltip: '单机控制面板',
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
                        tooltip: '单机重启',
                        icon: const Icon(Icons.refresh, size: 18, color: GwcTheme.secondary),
                        onPressed: () {
                          _confirmPower(
                            '单机重启确认',
                            '确定远程重启工控机 [${dev.displayName}] (${dev.ip}) 吗？',
                            () => _masterHub.sendCommand(dev.ip, 'CMD_REBOOT', {'force': true, 'timeout': 0}),
                          );
                        },
                      ),
                      IconButton(
                        tooltip: '单机关机',
                        icon: const Icon(Icons.power_settings_new, size: 18, color: GwcTheme.accentRed),
                        onPressed: () {
                          _confirmPower(
                            '单机关机确认',
                            '确定远程关闭工控机 [${dev.displayName}] (${dev.ip}) 吗？',
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
