import 'package:flutter/material.dart';
import '../models/agent_device.dart';
import '../core/discovery.dart';
import '../core/master_hub.dart';
import 'theme.dart';

class RadarScanDialog extends StatefulWidget {
  final GwcMasterHub masterHub;

  const RadarScanDialog({super.key, required this.masterHub});

  @override
  State<RadarScanDialog> createState() => _RadarScanDialogState();
}

class _RadarScanDialogState extends State<RadarScanDialog>
    with SingleTickerProviderStateMixin {
  late AnimationController _animController;
  final List<AgentDevice> _foundDevices = [];
  bool _scanning = false;
  late GwcDiscovery _discovery;

  @override
  void initState() {
    super.initState();
    _animController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat();

    _discovery = GwcDiscovery(
      onDeviceDiscovered: (dev) {
        if (!mounted) return;
        setState(() {
          if (!_foundDevices.any((d) => d.ip == dev.ip)) {
            _foundDevices.add(dev);
          }
        });
      },
    );

    _startScan();
  }

  @override
  void dispose() {
    _animController.dispose();
    super.dispose();
  }

  void _startScan() async {
    setState(() {
      _scanning = true;
      _foundDevices.clear();
    });

    final res = await _discovery.scan(
      timeout: const Duration(seconds: 3),
      autoConnect: true,
    );

    if (mounted) {
      setState(() {
        _scanning = false;
        for (final d in res) {
          if (!_foundDevices.any((x) => x.ip == d.ip)) {
            _foundDevices.add(d);
          }
        }
      });
    }
  }

  void _adoptDevice(AgentDevice dev) {
    widget.masterHub.registerDiscoveredDevice(dev);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('已将 [${dev.displayName}] 纳入主控大厅')),
    );
  }

  void _adoptAll() {
    for (final dev in _foundDevices) {
      widget.masterHub.registerDiscoveredDevice(dev);
    }
    Navigator.pop(context);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('已批量纳管 ${_foundDevices.length} 台工控机')),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: GwcTheme.surface,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      child: Container(
        width: 480,
        padding: const EdgeInsets.all(20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              children: [
                RotationTransition(
                  turns: _animController,
                  child: Icon(
                    Icons.radar,
                    color: _scanning ? GwcTheme.primary : GwcTheme.textSecondary,
                    size: 28,
                  ),
                ),
                const SizedBox(width: 12),
                const Text(
                  '局域网雷达搜索与纳管中心',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                ),
                const Spacer(),
                IconButton(
                  icon: const Icon(Icons.close),
                  onPressed: () => Navigator.pop(context),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Text(
              _scanning
                  ? '📡 正在向全网段发送 UDP 9887 广播探测包，请稍候...'
                  : '搜索完成: 发现 ${_foundDevices.length} 台在线受控端',
              style: TextStyle(
                color: _scanning ? GwcTheme.primary : GwcTheme.textSecondary,
                fontSize: 13,
              ),
            ),
            const SizedBox(height: 16),
            Container(
              height: 240,
              decoration: BoxDecoration(
                color: GwcTheme.background,
                borderRadius: BorderRadius.circular(12),
              ),
              child: _foundDevices.isEmpty
                  ? Center(
                      child: Text(
                        _scanning ? '正在探测局域网工控机...' : '未发现新设备，请确认从机已启动',
                        style: const TextStyle(color: GwcTheme.textSecondary),
                      ),
                    )
                  : ListView.separated(
                      padding: const EdgeInsets.all(8),
                      itemCount: _foundDevices.length,
                      separatorBuilder: (_, __) => const Divider(height: 1, color: Colors.white10),
                      itemBuilder: (ctx, i) {
                        final dev = _foundDevices[i];
                        return ListTile(
                          leading: const Icon(Icons.computer, color: GwcTheme.primary),
                          title: Text(dev.displayName, style: const TextStyle(fontWeight: FontWeight.bold)),
                          subtitle: Text('IP: ${dev.ip}  |  CPU: ${dev.cpu.toInt()}%  |  RAM: ${dev.mem.toInt()}%'),
                          trailing: ElevatedButton(
                            style: ElevatedButton.styleFrom(
                              backgroundColor: GwcTheme.primary.withOpacity(0.2),
                              foregroundColor: GwcTheme.primary,
                              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                            ),
                            onPressed: () => _adoptDevice(dev),
                            child: const Text('纳管'),
                          ),
                        );
                      },
                    ),
            ),
            const SizedBox(height: 16),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                OutlinedButton.icon(
                  icon: const Icon(Icons.refresh, size: 18),
                  label: const Text('重新扫描'),
                  onPressed: _scanning ? null : _startScan,
                ),
                const SizedBox(width: 12),
                ElevatedButton.icon(
                  style: ElevatedButton.styleFrom(backgroundColor: GwcTheme.primary, foregroundColor: Colors.black),
                  icon: const Icon(Icons.check_circle_outline, size: 18),
                  label: const Text('全部一键纳管', style: TextStyle(fontWeight: FontWeight.bold)),
                  onPressed: _foundDevices.isEmpty ? null : _adoptAll,
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

