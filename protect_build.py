# -*- coding: utf-8 -*-
"""
国文创系统 · 一键加壳加密与安全构建脚本 (Protect & Build)
=========================================================
1. 提取 net_config_tool.py 及全部功能模块源码编译为高强度混淆加密 Bytecode
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
    required = [("PyInstaller", "pyinstaller"), ("PIL", "pillow"), ("psutil", "psutil")]
    missing = []
    for mod_name, pkg_name in required:
        try:
            __import__(mod_name)
        except ImportError:
            missing.append(pkg_name)

    if missing:
        print(f"[*] 正在安装依赖套件: {' '.join(missing)} ...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])


def kill_old_processes():
    """使用 psutil 精准扫描并终止可能占用输出 EXE 的残留进程"""
    import psutil
    target_names = ["展馆控制终端.exe", "展馆工控受控端.exe", "展馆智能集群主控端.exe", "展馆系统配置与网络设置及电脑优化工具.exe"]
    for p in psutil.process_iter(['pid', 'name']):
        try:
            p_name = p.name()
            if p_name in target_names or any(t in p_name for t in ["展馆", "控制终端", "主控端", "受控端"]):
                p.kill()
        except Exception:
            pass
    time.sleep(0.8)


def main():
    start_time = time.time()
    kill_old_processes()
    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(base_dir, "dist")
    icon_path = os.path.join(base_dir, "gear.ico")

    # 命令行目标判断: --agent, --master, 默认两者均打包
    build_targets = []
    if "--agent" in sys.argv:
        build_targets = [("gwc_agent_app.py", "展馆控制终端", "展馆控制终端 · 轻量守护版")]
    elif "--master" in sys.argv:
        build_targets = [("gwc_master_app.py", "展馆智能集群主控端", "展馆智能集群综合管控中心")]
    else:
        build_targets = [
            ("gwc_agent_app.py", "展馆控制终端", "展馆控制终端 · 轻量守护版"),
            ("gwc_master_app.py", "展馆智能集群主控端", "展馆智能集群综合管控中心")
        ]

    print("=" * 65)
    print("[*] 国文创通用加壳加密引擎 · 双模独立软件自动化构建流水线")
    print("=" * 65)
    print(f"[*] 项目根目录: {base_dir}")
    print(f"[*] 输出路径: {output_dir}")
    print(f"[*] 应用图标: {icon_path if os.path.exists(icon_path) else '使用系统默认'}")
    print(f"[*] 待构建目标: {[t[1] for t in build_targets]}")

    ensure_dependencies()

    # 导入通用加密与授权引擎
    from universal_shield_engine import UniversalShieldEngine

    product_id = "VisualCast"  # 100% 兼容国文创加密机默认产品体系

    success_targets = []

    for entry_file, output_exe_name, product_name in build_targets:
        print("\n" + "-" * 65)
        print(f"[*] 开始构建目标: {output_exe_name}")
        print(f"[*] 源码主入口: {entry_file}")
        print(f"[*] 产品体系代号: {product_id}")
        print(f"[*] 软件正式名称: {product_name}")
        print(f"[*] 开始进行 AST 编译、HMAC 密钥流加壳与 PyInstaller 独立封装...")

        result = UniversalShieldEngine.pack_and_protect_project(
            project_dir_or_file=base_dir,
            entry_file_name=entry_file,
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
            target_path = result.get("path")
            file_size_mb = os.path.getsize(target_path) / (1024 * 1024)
            print(f"[+] 目标 [{output_exe_name}] 构建成功！")
            print(f"[*] 生成路径: {target_path}")
            print(f"[*] 文件大小: {file_size_mb:.2f} MB")
            success_targets.append((output_exe_name, target_path))
        else:
            print(f"[-] 目标 [{output_exe_name}] 加壳构建失败: {result.get('error')}")

    elapsed = time.time() - start_time
    print("=" * 65)
    if len(success_targets) == len(build_targets):
        print(f"[+] 全部 {len(success_targets)} 个独立软件加壳加密构建圆满完成！(总耗时: {elapsed:.2f} 秒)")
        for name, p in success_targets:
            print(f"    - {name}: {p}")
        print("=" * 65)
        print("【使用指引】")
        print("1. 《展馆工控受控端.exe》: 部署在各展厅工控机，支持开机自启、隐藏运行、快捷键 (默认 Ctrl+Q) 唤出。")
        print("2. 《展馆智能集群主控端.exe》: 部署在中控室电脑，点击【搜索局域网在线受控端】即可一键发现并管理所有在线工控机！")
        print("=" * 65)

        # 自动部署到用户桌面
        import shutil
        desktop_dir = os.path.join(os.path.expanduser("~"), "Desktop")
        suite_dir = os.path.join(desktop_dir, "展馆智能管控软件套件")
        os.makedirs(suite_dir, exist_ok=True)
        for name, p in success_targets:
            dest_root = os.path.join(desktop_dir, f"{name}.exe")
            dest_suite = os.path.join(suite_dir, f"{name}.exe")
            for dest in [dest_root, dest_suite]:
                try:
                    if os.path.exists(dest):
                        try:
                            os.remove(dest)
                        except Exception:
                            bak_path = dest + f".old_{int(time.time())}"
                            try:
                                os.rename(dest, bak_path)
                            except Exception:
                                pass
                    shutil.copy2(p, dest)
                    print(f"[+] 部署成功: 已将 {name}.exe 复制到 -> {dest}")
                except Exception as e:
                    print(f"[-] 复制到 {dest} 失败: {e}")
        return 0
    else:
        print(f"[-] 部分目标构建失败，已成功: {len(success_targets)}/{len(build_targets)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
