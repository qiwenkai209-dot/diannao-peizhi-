import 'package:flutter/material.dart';
import '../models/agent_device.dart';
import '../core/master_hub.dart';
import '../core/license_core.dart';
import 'theme.dart';

class DeviceControlSheet extends StatefulWidget {
  final AgentDevice device;
  final GwcMasterHub masterHub;

  const DeviceControlSheet({
    super.key,
    required this.device,
    required this.masterHub,
  });

  @override
  State<DeviceControlSheet> createState() => _DeviceControlSheetState();
}

class _DeviceControlSheetState extends State<DeviceControlSheet> {
  late double _volume;
  late bool _isMuted;
  final TextEditingController _procNameController = TextEditingController();

  @override
  void initState() {
    super.initState();
    _volume = widget.device.volume.toDouble();
    _isMuted = widget.device.isMuted;
  }

  @override
  void dispose() {
    _procNameController.dispose();
    super.dispose();
  }

  void _sendVolume(double val) {
    setState(() => _volume = val);
    widget.masterHub.sendCommand(
      widget.device.ip,
      'CMD_VOLUME',
      {'action': 'set', 'level': val.toInt()},
    );
  }

  void _toggleMute() {
    setState(() => _isMuted = !_isMuted);
    widget.masterHub.sendCommand(
      widget.device.ip,
      'CMD_VOLUME',
      {'action': _isMuted ? 'mute' : 'unmute'},
    );
  }

  void _confirmPower(String title, String content, String cmd) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: GwcTheme.surface,
        title: Text(title, style: const TextStyle(color: GwcTheme.accentAmber)),
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
              widget.masterHub.sendCommand(
                widget.device.ip,
                cmd,
                {'force': true, 'timeout': 0},
              );
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(content: Text('已向 [${widget.device.displayName}] 下发 $title 指令')),
              );
            },
            child: const Text('确认下发', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
    );
  }

  void _quickAuthorize() {
    if (widget.device.requestCode.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('未获取到该设备的申请码，无法签发！')),
      );
      return;
    }

    final dec = UniversalLicenseCore.decodeRequestCode(widget.device.requestCode);
    if (dec['valid'] != true) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('申请码解析失败: ${dec["error"]}')),
      );
      return;
    }

    // 签发永久商业授权 (31)
    final actCode = UniversalLicenseCore.encodeLicense(
      dec['hw_hash'] as int,
      dec['nonce'] as int,
      31,
      31,
      productId: 'VisualCast',
    );

    widget.masterHub.sendCommand(
      widget.device.ip,
      'CMD_REMOTE_AUTH',
      {'code': actCode},
    );

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('🎉 已向 [${widget.device.displayName}] 远程下发商业永久激活码: $actCode')),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
      decoration: const BoxDecoration(
        color: GwcTheme.surface,
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Center(
              child: Container(
                width: 48,
                height: 5,
                decoration: BoxDecoration(
                  color: Colors.white.withOpacity(0.2),
                  borderRadius: BorderRadius.circular(4),
                ),
              ),
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: GwcTheme.primary.withOpacity(0.15),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Icon(Icons.desktop_windows, color: GwcTheme.primary, size: 28),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        widget.device.displayName,
                        style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                      ),
                      Text(
                        'IP: ${widget.device.ip}  |  延迟: ${widget.device.latencyMs}ms',
                        style: const TextStyle(color: GwcTheme.textSecondary, fontSize: 13),
                      ),
                    ],
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.close),
                  onPressed: () => Navigator.pop(context),
                ),
              ],
            ),
            const SizedBox(height: 20),

            // 音量与静音控制
            Card(
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text('🔊 主音量调节', style: TextStyle(fontWeight: FontWeight.w600)),
                        Text('${_volume.toInt()}%', style: const TextStyle(color: GwcTheme.primary, fontWeight: FontWeight.bold)),
                      ],
                    ),
                    Row(
                      children: [
                        IconButton(
                          icon: Icon(
                            _isMuted ? Icons.volume_off : Icons.volume_up,
                            color: _isMuted ? GwcTheme.accentAmber : GwcTheme.primary,
                          ),
                          onPressed: _toggleMute,
                        ),
                        Expanded(
                          child: Slider(
                            value: _volume,
                            min: 0,
                            max: 100,
                            divisions: 100,
                            activeColor: GwcTheme.primary,
                            onChanged: _sendVolume,
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),

            // 预设应用快捷调用
            if (widget.device.presetApps.isNotEmpty) ...[
              const Text('🚀 预设常用应用一键启动', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 15)),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: widget.device.presetApps.map((app) {
                  final name = app['name'] ?? app['title'] ?? '应用';
                  final path = app['path'] ?? '';
                  return ActionChip(
                    avatar: const Icon(Icons.play_arrow, size: 16, color: GwcTheme.primary),
                    label: Text(name),
                    backgroundColor: GwcTheme.surfaceCard,
                    onPressed: () {
                      widget.masterHub.sendCommand(
                        widget.device.ip,
                        'CMD_RUN_APP',
                        {'path': path},
                      );
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(content: Text('已下发启动: $name')),
                      );
                    },
                  );
                }).toList(),
              ),
              const SizedBox(height: 16),
            ],

            // 电源管理与授权
            Row(
              children: [
                Expanded(
                  child: ElevatedButton.icon(
                    style: ElevatedButton.styleFrom(backgroundColor: GwcTheme.surfaceCard),
                    icon: const Icon(Icons.refresh, color: GwcTheme.secondary),
                    label: const Text('远程重启'),
                    onPressed: () => _confirmPower('远程重启', '确定要重启该工控机吗？', 'CMD_REBOOT'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: ElevatedButton.icon(
                    style: ElevatedButton.styleFrom(backgroundColor: GwcTheme.accentRed.withOpacity(0.85)),
                    icon: const Icon(Icons.power_settings_new, color: Colors.white),
                    label: const Text('远程关机', style: TextStyle(color: Colors.white)),
                    onPressed: () => _confirmPower('远程关机', '确定要关闭该工控机电源吗？', 'CMD_SHUTDOWN'),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),

            // 远程授权按钮
            if (!widget.device.isAuthorized)
              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  style: ElevatedButton.styleFrom(
                    backgroundColor: GwcTheme.accentAmber,
                    foregroundColor: Colors.black,
                  ),
                  icon: const Icon(Icons.verified),
                  label: const Text('一键签发永久商业授权并下发', style: TextStyle(fontWeight: FontWeight.bold)),
                  onPressed: _quickAuthorize,
                ),
              ),
            const SizedBox(height: 24),
          ],
        ),
      ),
    );
  }
}
