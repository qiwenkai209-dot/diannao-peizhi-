import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'ui/theme.dart';
import 'ui/dashboard_page.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();

  // 保持高刷与沉浸式状态栏体验
  SystemChrome.setSystemUIOverlayStyle(
    const SystemUiOverlayStyle(
      statusBarColor: Colors.transparent,
      statusBarIconBrightness: Brightness.light,
      systemNavigationBarColor: GwcTheme.surface,
      systemNavigationBarIconBrightness: Brightness.light,
    ),
  );

  runApp(const GwcMasterAndroidApp());
}

class GwcMasterAndroidApp extends StatelessWidget {
  const GwcMasterAndroidApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '展馆智能集群综合管控中心',
      debugShowCheckedModeBanner: false,
      theme: GwcTheme.darkTheme,
      home: const DashboardPage(),
    );
  }
}

