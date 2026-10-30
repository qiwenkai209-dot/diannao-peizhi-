# -*- coding: utf-8 -*-
"""
国文创系统 · 一键加壳加密与安全构建脚本 (Protect & Build)
=========================================================
1. 提取 net_config_tool.py 源码编译为高强度混淆加密 Bytecode
2. 注入动态防二次激活商业授权守卫 (一机一码 + 动态 Nonce + 随机申请码)
3. 驱动 PyInstaller 编译为原生独立 EXE (Windows UAC 管理员提权 + 专属齿轮图标)
4. 输出至 dist/ 目录，支持本地与 GitHub Actions 云端流水线全自动执行
"""

import os
import sys
import subprocess
import time

# 兼容 Windows 控制台 UTF-8 输出，防止 emoji 或中文在 gbk 终端下抛出编码异常
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def ensure_dependencies():
    """检测并安装必要的打包依赖"""
    try:
        import PyInstaller
    except ImportError:
        print("[*] 正在安装 PyInstaller 打包套件...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

def main():
    start_time = time.time()
    base_dir = os.path.dirname(os.path.abspath(__file__))
    src_file = os.path.join(base_dir, "net_config_tool.py")
    output_dir = os.path.join(base_dir, "dist")
    icon_path = os.path.join(base_dir, "gear.ico")

    print("=" * 65)
    print("[*] 国文创通用加壳加密引擎 · 自动化构建流水线")
    print("=" * 65)
    print(f"[*] 源码入口: {src_file}")
    print(f"[*] 输出路径: {output_dir}")
    print(f"[*] 应用图标: {icon_path if os.path.exists(icon_path) else '使用系统默认'}")

    ensure_dependencies()

    # 导入通用加密与授权引擎
    from universal_shield_engine import UniversalShieldEngine

    product_id = "VisualCast"  # 100% 兼容国文创加密机默认产品体系
    product_name = "展馆系统配置与网络设置及电脑优化工具"
    output_exe_name = "展馆系统配置与网络设置及电脑优化工具"

    print(f"[*] 产品体系代号: {product_id}")
    print(f"[*] 软件正式名称: {product_name}")
    print(f"[*] 开始进行 AST 编译、HMAC 密钥流加壳与 PyInstaller 独立封装...")

    result = UniversalShieldEngine.pack_and_protect_project(
        project_dir_or_file=src_file,
        entry_file_name="net_config_tool.py",
        output_dir=output_dir,
        product_id=product_id,
        product_name=product_name,
        icon_path=icon_path if os.path.exists(icon_path) else "",
        windowed=True,
        auto_compile_exe=True,
        output_exe_name=output_exe_name,
        uac_admin=True
    )

    if result.get("success"):
        elapsed = time.time() - start_time
        target_path = result.get("path")
        file_size_mb = os.path.getsize(target_path) / (1024 * 1024)
        print("=" * 65)
        print("[+] 加壳加密构建圆满完成！")
        print(f"[*] 生成路径: {target_path}")
        print(f"[*] 文件大小: {file_size_mb:.2f} MB")
        print(f"[*] 耗时统计: {elapsed:.2f} 秒")
        print("=" * 65)
        print("【国文创授权机使用指引】")
        print("1. 客户首次打开该 EXE 时，会弹出【商业授权验证中心】并显示 8 位设备申请码。")
        print("2. 管理员打开《国文创加密机.exe》，在申请码输入框中粘贴该 8 位申请码。")
        print("3. 选择授权时长（如 1年 或 永久有效），点击【生成 12 位激活码】。")
        print("4. 客户在弹窗输入该 12 位激活码即可瞬间解锁启动，自动完成单次核销！")
        print("=" * 65)
        return 0
    else:
        print("=" * 65)
        print(f"[-] 加壳构建失败: {result.get('error')}")
        print("=" * 65)
        return 1

if __name__ == "__main__":
    sys.exit(main())
