# -*- coding: utf-8 -*-
"""
自动化配置 Android Release 专属固定签名证书与独立包名 (永久解决 APK 安装签名不一致问题)
"""
import os
import sys
import base64
import re

def main():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    signing_dir = os.path.join(root_dir, "release_signing")
    android_app_dir = os.path.join(root_dir, "android", "app")
    
    os.makedirs(android_app_dir, exist_ok=True)
    target_jks = os.path.join(android_app_dir, "release.jks")
    
    # 1. 恢复 release.jks 固化签名证书
    src_jks = os.path.join(signing_dir, "release.jks")
    src_b64 = os.path.join(signing_dir, "release.jks.b64")
    
    if os.path.exists(src_jks) and os.path.getsize(src_jks) > 0:
        with open(src_jks, "rb") as f_in, open(target_jks, "wb") as f_out:
            f_out.write(f_in.read())
        print(f"[+] 成功从 release.jks 复制签名证书至: {target_jks}")
    elif os.path.exists(src_b64):
        with open(src_b64, "r", encoding="utf-8") as f_in:
            raw_bytes = base64.b64decode(f_in.read().strip())
        with open(target_jks, "wb") as f_out:
            f_out.write(raw_bytes)
        print(f"[+] 成功从 base64 还原签名证书至: {target_jks}")
    else:
        print("[-] 错误: 未找到 release.jks 或 release.jks.b64 证书源文件！")
        sys.exit(1)

    # 2. 复制 key.properties
    src_prop = os.path.join(signing_dir, "key.properties")
    target_prop = os.path.join(root_dir, "android", "key.properties")
    if os.path.exists(src_prop):
        with open(src_prop, "rb") as f_in, open(target_prop, "wb") as f_out:
            f_out.write(f_in.read())
        print(f"[+] 成功配置 key.properties 至: {target_prop}")

    # 3. 强制配置 android/app/build.gradle (包名切换为 com.guowenchuang.master.app + 固化 Release 签名)
    gradle_file = os.path.join(android_app_dir, "build.gradle")
    if not os.path.exists(gradle_file):
        print(f"[-] 警告: 未找到 {gradle_file}，请确保在 flutter create 后执行此脚本！")
        return

    with open(gradle_file, "r", encoding="utf-8") as f:
        content = f.read()

    # 确保 applicationId 为全新独立包名，彻底避开旧缓存
    new_app_id = 'applicationId "com.guowenchuang.master.app"'
    if "applicationId" in content:
        content = re.sub(r'applicationId\s+["\'][^"\']+["\']', new_app_id, content)
        print("[+] 成功将 applicationId 锁定为全新独立包名: com.guowenchuang.master.app")

    # 注入 signingConfigs
    signing_snippet = """
    signingConfigs {
        release {
            keyAlias 'gwc_master_key'
            keyPassword 'gwc2026secure'
            storeFile file('release.jks')
            storePassword 'gwc2026secure'
        }
    }
"""

    if "signingConfigs {" not in content:
        if "buildTypes {" in content:
            content = content.replace("buildTypes {", signing_snippet + "\n    buildTypes {", 1)
        else:
            content = re.sub(r"(android\s*\{)", r"\1" + signing_snippet, content, count=1)
    else:
        if "gwc_master_key" not in content:
            content = content.replace("signingConfigs {", "signingConfigs {\n        release {\n            keyAlias 'gwc_master_key'\n            keyPassword 'gwc2026secure'\n            storeFile file('release.jks')\n            storePassword 'gwc2026secure'\n        }", 1)

    # 确保 release buildTypes 强制使用 release 签名
    content = re.sub(
        r"(release\s*\{[^\}]*?signingConfig\s*=?\s*)signingConfigs\.debug",
        r"\1signingConfigs.release",
        content,
        flags=re.DOTALL
    )

    with open(gradle_file, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"[+] 成功注入 Release 签名配置至: {gradle_file}")

    # 4. 修改 AndroidManifest.xml 桌面名称为【展馆智能集群主控端】
    manifest_file = os.path.join(root_dir, "android", "app", "src", "main", "AndroidManifest.xml")
    if os.path.exists(manifest_file):
        with open(manifest_file, "r", encoding="utf-8") as f:
            man_content = f.read()
        man_content = re.sub(r'android:label="[^"]*"', 'android:label="展馆智能集群主控端"', man_content)
        with open(manifest_file, "w", encoding="utf-8") as f:
            f.write(man_content)
        print("[+] 成功更新 Android 桌面应用名称为: 展馆智能集群主控端")

if __name__ == "__main__":
    main()
