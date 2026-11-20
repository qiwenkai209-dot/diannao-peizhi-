import 'package:flutter/material.dart';
import '../core/central_control.dart';
import 'theme.dart';

class CentralControlDocPage extends StatelessWidget {
  final CentralControlManager centralManager;

  const CentralControlDocPage({super.key, required this.centralManager});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('📖 展馆中控全协议速查与指令手册'),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Row(
                      children: [
                        Icon(Icons.hub, color: GwcTheme.primary),
                        SizedBox(width: 10),
                        Text('📡 中控总线端口速查', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
                      ],
                    ),
                    const Divider(height: 20),
                    const Text('• UDP 调度端口 : 9889 (广播或单播发往本平板)'),
                    const SizedBox(height: 6),
                    const Text('• TCP Socket 端口: 9890 (长连接指令流)'),
                    const SizedBox(height: 6),
                    const Text('• HTTP RESTful API : 9891 (网页/大屏浏览器直接访问)'),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 16),
            const Text('⚡ 常用中控指令集 (支持纯文本与 JSON)', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
            const SizedBox(height: 10),
            _buildCmdTile('全馆一键关机', 'ALL_SHUTDOWN', '{"action": "ALL_SHUTDOWN"}'),
            _buildCmdTile('全馆一键重启', 'ALL_REBOOT', '{"action": "ALL_REBOOT"}'),
            _buildCmdTile('全馆一键静音', 'ALL_MUTE', '{"action": "ALL_MUTE"}'),
            _buildCmdTile('全馆解除静音', 'ALL_UNMUTE', '{"action": "ALL_UNMUTE"}'),
            _buildCmdTile('全馆设定音量(80%)', 'ALL_VOLUME:80', '{"action": "ALL_VOLUME", "level": 80}'),
            _buildCmdTile('单机定向关机', 'DEV_SHUTDOWN', '{"action": "DEV_SHUTDOWN", "ip": "192.168.1.100"}'),
            _buildCmdTile('单机定向重启', 'DEV_REBOOT', '{"action": "DEV_REBOOT", "ip": "192.168.1.100"}'),
            _buildCmdTile('单机调音量(60%)', 'DEV_VOLUME', '{"action": "DEV_VOLUME", "ip": "192.168.1.100", "level": 60}'),
            _buildCmdTile('HTTP 状态查询', 'GET http://平板IP:9891/api/status', '返回当前在线设备数与状态'),
            _buildCmdTile('HTTP 简易控制', 'GET http://平板IP:9891/api/control?action=all_shutdown', '浏览器超链接即可触发全馆关机'),
          ],
        ),
      ),
    );
  }

  Widget _buildCmdTile(String title, String txtCmd, String jsonCmd) {
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: const TextStyle(fontWeight: FontWeight.bold, color: GwcTheme.primary)),
            const SizedBox(height: 4),
            Text('文本格式: $txtCmd', style: const TextStyle(fontSize: 12, color: GwcTheme.textSecondary)),
            const SizedBox(height: 2),
            Text('JSON格式: $jsonCmd', style: const TextStyle(fontSize: 12, color: Colors.white70)),
          ],
        ),
      ),
    );
  }
}
