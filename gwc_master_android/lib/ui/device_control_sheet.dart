import 'package:flutter/material.dart';
import '../models/agent_device.dart';
import '../core/master_hub.dart';
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
  bool _isDragging = false;
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
    if (_isMuted) {
      widget.masterHub.sendCommand(
        widget.device.ip,
        'CMD_VOLUME',
        {'action': 'mute'},
      );
    } else {
      widget.masterHub.sendCommand(
        widget.device.ip,
        'CMD_VOLUME',
        {'action': 'set', 'level': (_volume > 0 ? _volume.toInt() : 50)},
      );
    }
  }

  void _confirmPower(String title, String content, String cmd) {
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
              widget.masterHub.sendCommand(
                widget.device.ip,
                cmd,
                {'force': true, 'timeout': 0},
              );
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  backgroundColor: GwcTheme.surfaceCard,
                  content: Text('已向 [${widget.device.displayName}] 下发 $title 指令'),
                ),
              );
            },
            child: const Text('确认下发', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    // 动态同步工控机实时上报的音量与静音状态 (拖动调节期间不被后台轮询打断覆盖)
    if (!_isDragging) {
      if (_volume.toInt() != widget.device.volume) {
        _volume = widget.device.volume.toDouble();
      }
      _isMuted = widget.device.isMuted;
    }

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
            // 顶端拖动条
            Center(
              child: Container(
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                  color: Colors.white24,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
            const SizedBox(height: 16),

            // 设备头部
            Row(
              children: [
                CircleAvatar(
                  backgroundColor: widget.device.isOnline ? GwcTheme.accentGreen.withOpacity(0.2) : Colors.white10,
                  child: Icon(
                    Icons.computer,
                    color: widget.device.isOnline ? GwcTheme.accentGreen : GwcTheme.textSecondary,
                  ),
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
                        'IP: ${widget.device.ip} · 延迟: ${widget.device.latencyMs}ms · 通道: ${widget.device.source}',
                        style: const TextStyle(color: GwcTheme.textSecondary, fontSize: 12),
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
            const Divider(height: 24),

            // 前台活动窗口监控回显
            Card(
              color: GwcTheme.surfaceCard,
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Row(
                  children: [
                    const Icon(Icons.web_asset, size: 20, color: GwcTheme.primary),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text('当前工控前台运行窗口:', style: TextStyle(color: GwcTheme.textSecondary, fontSize: 11)),
                          Text(
                            widget.device.activeWindow.isNotEmpty ? widget.device.activeWindow : '系统桌面 / 待机空闲',
                            style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),

            // 快捷音量调控
            Card(
              color: GwcTheme.surfaceCard,
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Row(
                          children: [
                            Icon(
                              _isMuted ? Icons.volume_off : Icons.volume_up,
                              color: _isMuted ? GwcTheme.accentRed : GwcTheme.primary,
                            ),
                            const SizedBox(width: 8),
                            const Text('主音频音量 (实时回显与双向同步)', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
                          ],
                        ),
                        Text(
                          _isMuted ? '静音中' : '${_volume.toInt()}%',
                          style: TextStyle(
                            fontWeight: FontWeight.bold,
                            color: _isMuted ? GwcTheme.accentRed : GwcTheme.primary,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 6),
                    Row(
                      children: [
                        IconButton(
                          icon: Icon(_isMuted ? Icons.volume_off : Icons.volume_mute),
                          color: _isMuted ? GwcTheme.accentRed : GwcTheme.textSecondary,
                          onPressed: _toggleMute,
                          tooltip: _isMuted ? '解除静音' : '快速静音',
                        ),
                        Expanded(
                          child: Slider(
                            value: _volume,
                            min: 0,
                            max: 100,
                            divisions: 100,
                            activeColor: GwcTheme.primary,
                            onChangeStart: (val) {
                              setState(() => _isDragging = true);
                            },
                            onChanged: (val) {
                              setState(() => _volume = val);
                            },
                            onChangeEnd: (val) {
                              setState(() {
                                _volume = val;
                                _isDragging = false;
                              });
                              _sendVolume(val);
                            },
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
                        SnackBar(content: Text('已向 [${widget.device.displayName}] 下发启动: $name')),
                      );
                    },
                  );
                }).toList(),
              ),
              const SizedBox(height: 16),
            ],

            // 电源管理 (远程重启与关机)
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
            const SizedBox(height: 24),
          ],
        ),
      ),
    );
  }
}
