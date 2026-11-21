import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../core/license_core.dart';
import '../core/master_hub.dart';
import '../models/agent_device.dart';
import 'theme.dart';

class LicenseMachinePage extends StatefulWidget {
  final GwcMasterHub masterHub;

  const LicenseMachinePage({super.key, required this.masterHub});

  @override
  State<LicenseMachinePage> createState() => _LicenseMachinePageState();
}

class _LicenseMachinePageState extends State<LicenseMachinePage> {
  final TextEditingController _reqController = TextEditingController();
  String _generatedLic = '';
  int _selectedDuration = 0; // 0 为永久
  AgentDevice? _selectedDevice;

  final Map<int, String> _durations = {
    12: '12 小时 (半天)',
    24: '24 小时 (1天)',
    72: '72 小时 (3天)',
    30: '30 天 (1个月)',
    365: '365 天 (1年)',
    0: '♾️ 商业授权 (终身永久)',
  };

  void _generate() {
    final req = _reqController.text.trim();
    if (req.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('请输入或选择目标工控机的 8 位申请码！')),
      );
      return;
    }

    final dec = LicenseManager.decodeRequestCode(req);
    if (dec['valid'] != true) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('申请码格式错误: ${dec["error"]}')),
      );
      return;
    }

    String authType = 'permanent';
    int customVal = 0;

    if (_selectedDuration == 12 || _selectedDuration == 24 || _selectedDuration == 72) {
      authType = 'hour';
      customVal = _selectedDuration;
    } else if (_selectedDuration == 30) {
      authType = 'month';
      customVal = 1;
    } else if (_selectedDuration == 365) {
      authType = 'month';
      customVal = 12;
    } else {
      authType = 'permanent';
      customVal = 0;
    }

    final lic = LicenseManager.generateLicense(
      dec,
      authType: authType,
      customVal: customVal,
    );

    setState(() {
      _generatedLic = lic;
    });
  }

  void _remotePush() {
    if (_generatedLic.isEmpty) return;
    if (_selectedDevice == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('请先在上方向下拉框选择在线工控机！')),
      );
      return;
    }

    widget.masterHub.sendCommand(
      _selectedDevice!.ip,
      'CMD_REMOTE_AUTH',
      {'code': _generatedLic},
    );

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('🎉 已向 [${_selectedDevice!.displayName}] 远程下发激活码！')),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('🛡️ 国文创商业授权中枢 · 移动加密机'),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('🎯 快捷选择在线从机', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
                    const SizedBox(height: 10),
                    DropdownButtonFormField<AgentDevice>(
                      value: _selectedDevice,
                      decoration: const InputDecoration(
                        border: OutlineInputBorder(),
                        contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                      ),
                      hint: const Text('选择在线从机以自动填入申请码'),
                      items: widget.masterHub.devices.map((d) {
                        return DropdownMenuItem(
                          value: d,
                          child: Text('${d.displayName} (${d.ip}) [${d.isAuthorized ? "已授权" : "未授权"}]'),
                        );
                      }).toList(),
                      onChanged: (dev) {
                        setState(() {
                          _selectedDevice = dev;
                          if (dev != null && dev.requestCode.isNotEmpty) {
                            _reqController.text = dev.requestCode;
                          }
                        });
                      },
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 16),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('🔑 8 位设备随机申请码 (XXXX-XXXX)', style: TextStyle(fontWeight: FontWeight.bold)),
                    const SizedBox(height: 8),
                    TextField(
                      controller: _reqController,
                      style: const TextStyle(fontSize: 18, letterSpacing: 2, fontWeight: FontWeight.bold),
                      decoration: const InputDecoration(
                        hintText: '例如: 8K9M-P3X2',
                        border: OutlineInputBorder(),
                      ),
                    ),
                    const SizedBox(height: 16),
                    const Text('⏱️ 授权有效期定制', style: TextStyle(fontWeight: FontWeight.bold)),
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: _durations.entries.map((e) {
                        final isSel = _selectedDuration == e.key;
                        return ChoiceChip(
                          label: Text(e.value),
                          selected: isSel,
                          selectedColor: GwcTheme.primary.withOpacity(0.25),
                          onSelected: (_) => setState(() => _selectedDuration = e.key),
                        );
                      }).toList(),
                    ),
                    const SizedBox(height: 20),
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton.icon(
                        style: ElevatedButton.styleFrom(
                          backgroundColor: GwcTheme.primary,
                          foregroundColor: Colors.black,
                          padding: const EdgeInsets.symmetric(vertical: 14),
                        ),
                        icon: const Icon(Icons.calculate),
                        label: const Text('立即计算商业授权激活码', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
                        onPressed: _generate,
                      ),
                    ),
                  ],
                ),
              ),
            ),
            if (_generatedLic.isNotEmpty) ...[
              const SizedBox(height: 16),
              Card(
                color: GwcTheme.surfaceCard,
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    children: [
                      const Text('🎉 签发成功！商业授权激活码:'),
                      const SizedBox(height: 10),
                      SelectableText(
                        _generatedLic,
                        style: const TextStyle(
                          color: GwcTheme.accentGreen,
                          fontSize: 26,
                          fontWeight: FontWeight.bold,
                          letterSpacing: 2,
                        ),
                      ),
                      const SizedBox(height: 16),
                      Row(
                        children: [
                          Expanded(
                            child: OutlinedButton.icon(
                              icon: const Icon(Icons.copy),
                              label: const Text('复制到剪贴板'),
                              onPressed: () {
                                Clipboard.setData(ClipboardData(text: _generatedLic));
                                ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(content: Text('已复制到剪贴板！')),
                                );
                              },
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: ElevatedButton.icon(
                              style: ElevatedButton.styleFrom(backgroundColor: GwcTheme.accentGreen),
                              icon: const Icon(Icons.send, color: Colors.white),
                              label: const Text('一键下发至从机', style: TextStyle(color: Colors.white)),
                              onPressed: _remotePush,
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

