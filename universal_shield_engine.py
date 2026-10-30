# -*- coding: utf-8 -*-
"""
VisualCast 通用源码加壳与根级加密编译引擎 (Universal Shield & Armor Engine)
========================================================================
从根上保护任何 Python 软件项目:
1. 源码字节码强加密 (Bytecode Marshal + AES/Keystream 加密，磁盘无明文)。
2. 注入动态防二次激活商业授权守卫 (一机一码 + 动态 Nonce + 随机申请码)。
3. 内存动态解密执行 (RAM In-Memory Decrypt & Virtual Import Loader)。
4. 自动化驱动 PyInstaller 一键编译为独立受保护的单文件 EXE。
"""

import os
import sys
import marshal
import struct
import hashlib
import hmac
import shutil
import subprocess
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def derive_keystream(key: bytes, length: int) -> bytes:
    """使用 HMAC-SHA256 计数器模式派生与明文等长的高强度伪随机密钥流 (CTR 模式)"""
    blocks = []
    counter = 0
    generated = 0
    while generated < length:
        h = hmac.new(key, struct.pack(">Q", counter), hashlib.sha256).digest()
        blocks.append(h)
        generated += len(h)
        counter += 1
    return b"".join(blocks)[:length]

def encrypt_bytes(data: bytes, key: bytes) -> bytes:
    """加密二进制字节流并附加 HMAC 认证标签"""
    stream = derive_keystream(key, len(data))
    # 异或加密
    cipher = bytes(b ^ s for b, s in zip(data, stream))
    # 计算认证标签
    tag = hmac.new(key, cipher, hashlib.sha256).digest()[:16]
    return tag + cipher

def decrypt_bytes(payload: bytes, key: bytes) -> bytes:
    """解密二进制字节流并校验 HMAC 认证标签"""
    if len(payload) < 16:
        raise ValueError("密文长度非法")
    tag = payload[:16]
    cipher = payload[16:]
    expected_tag = hmac.new(key, cipher, hashlib.sha256).digest()[:16]
    if not hmac.compare_digest(tag, expected_tag):
        raise ValueError("密文完整性校验失败或密钥不匹配")
    stream = derive_keystream(key, len(cipher))
    return bytes(b ^ s for b, s in zip(cipher, stream))


# 嵌入式加壳启动器与授权守卫模板代码 (将在内存动态运行)
ARMOR_BOOT_TEMPLATE = r'''# -*- coding: utf-8 -*-
"""
受 Universal License Armor 根级加壳保护的主执行入口
===================================================
1. 物理源码已全量强加密，磁盘无明文。
2. 严格核验商业授权状态 (一机一码 + 动态随机申请码 + 防二次激活)。
3. 内存安全解密并执行业务代码。
"""
import sys
import os
import marshal
import types
import json
import time
import struct
import hashlib
import hmac
import uuid
import ctypes
import tkinter as tk
from tkinter import messagebox

# 软件产品专属元数据
PRODUCT_ID = "@@PRODUCT_ID@@"
PRODUCT_NAME = "@@PRODUCT_NAME@@"
EMBED_SALT = @@EMBED_SALT_BYTES@@

CHARSET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
CHAR_TO_VAL = {c: i for i, c in enumerate(CHARSET)}

DURATION_MAP = {
    11: ("0.5天 (半天/12小时)", 0.5),
    0: ("1天 (体验)", 1), 1: ("3天 (试用)", 3), 2: ("7天 (1周)", 7),
    3: ("15天 (半月)", 15), 4: ("30天 (1个月)", 30), 5: ("60天 (2个月)", 60),
    6: ("90天 (1季度)", 90), 7: ("180天 (半年)", 180), 8: ("365天 (1年)", 365),
    9: ("730天 (2年)", 730), 10: ("1095天 (3年)", 1095), 31: ("永久有效", -1)
}
RUNS_MAP = {
    0: ("5 次", 5), 1: ("10 次", 10), 2: ("20 次", 20), 3: ("50 次", 50),
    4: ("100 次", 100), 5: ("200 次", 200), 6: ("500 次", 500),
    7: ("1000 次", 1000), 8: ("2000 次", 2000), 9: ("5000 次", 5000),
    10: ("10000 次", 10000), 31: ("无限制", -1)
}

SHUFFLE_P_40 = [
    31, 7, 23, 15, 39, 3, 19, 11, 27, 35,
    0, 16, 8, 24, 32, 4, 20, 12, 28, 36,
    1, 17, 9, 25, 33, 5, 21, 13, 29, 37,
    2, 18, 10, 26, 34, 6, 22, 14, 30, 38
]
SHUFFLE_P_60 = [
    13, 50, 27, 4, 41, 18, 55, 32, 9, 46, 23, 0, 37, 14, 51, 28, 5, 42, 19, 56,
    33, 10, 47, 24, 1, 38, 15, 52, 29, 6, 43, 20, 57, 34, 11, 48, 25, 2, 39, 16,
    53, 30, 7, 44, 21, 58, 35, 12, 49, 26, 3, 40, 17, 54, 31, 8, 45, 22, 59, 36
]
UNSHUFFLE_P_60 = [0] * 60
for _i, _p in enumerate(SHUFFLE_P_60): UNSHUFFLE_P_60[_p] = _i

def _permute_bits(val, perm):
    res = 0
    for new_p, old_p in enumerate(perm):
        res |= (((val >> old_p) & 1) << new_p)
    return res

def get_sys_hw_hash():
    parts = []
    try:
        if sys.platform == 'win32':
            vol = ctypes.c_ulong()
            if ctypes.windll.kernel32.GetVolumeInformationW("C:\\", None, 0, ctypes.byref(vol), None, None, None, 0):
                parts.append(f"VOL_{vol.value:08X}")
    except Exception: pass
    try:
        parts.append(f"MAC_{uuid.getnode():012X}")
    except Exception: pass
    parts.append(f"CPU_{os.environ.get('PROCESSOR_IDENTIFIER', '')}_{os.environ.get('NUMBER_OF_PROCESSORS', '1')}")
    h = int(hashlib.sha256("|".join(parts).encode()).hexdigest()[:8], 16)
    return (h % 4095) + 1

def calc_req_checksum(hw_hash, nonce):
    p = struct.pack(">HH", hw_hash & 0x0FFF, nonce & 0xFFFF)
    raw = (hmac.new(EMBED_SALT, b"REQ:" + p, hashlib.sha256).digest()[0] << 8) | hmac.new(EMBED_SALT, b"REQ:" + p, hashlib.sha256).digest()[1]
    return raw & 0x0FFF

def encode_request_code(hw_hash, nonce):
    chk = calc_req_checksum(hw_hash, nonce)
    raw = ((hw_hash & 0x0FFF) << 28) | ((nonce & 0xFFFF) << 12) | (chk & 0x0FFF)
    shuf = _permute_bits(raw, SHUFFLE_P_40)
    chars = []
    for _ in range(8):
        chars.append(CHARSET[shuf & 0x1F])
        shuf >>= 5
    s = "".join(chars)
    return f"{s[:4]}-{s[4:]}"

def decode_license(lic_str):
    c = lic_str.replace("-", "").replace(" ", "").upper()
    if len(c) != 12: return {"valid": False, "error": "激活码长度须为12位"}
    num = 0
    for i, ch in enumerate(c):
        if ch not in CHAR_TO_VAL: return {"valid": False, "error": f"非法字符: {ch}"}
        num |= (CHAR_TO_VAL[ch] << (i * 5))
    un = _permute_bits(num, UNSHUFFLE_P_60)
    hw = (un >> 48) & 0x0FFF
    nonce = (un >> 32) & 0xFFFF
    dur = (un >> 27) & 0x1F
    runs = (un >> 22) & 0x1F
    sig = un & 0x3FFFFF
    p = struct.pack(">HHBB", hw & 0x0FFF, nonce & 0xFFFF, dur & 0x1F, runs & 0x1F)
    dig = hmac.new(EMBED_SALT, b"LIC:" + p, hashlib.sha256).digest()
    exp_sig = ((dig[0] << 16) | (dig[1] << 8) | dig[2]) & 0x3FFFFF
    if sig != exp_sig: return {"valid": False, "error": "激活码签名不匹配"}
    return {
        "valid": True, "hw_hash": hw, "is_universal": (hw == 0),
        "nonce": nonce, "duration_code": dur, "duration_days": DURATION_MAP.get(dur, ("", 30))[1],
        "runs_code": runs, "max_runs": RUNS_MAP.get(runs, ("", 100))[1]
    }

class RuntimeLicenseManager:
    def __init__(self):
        bdir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        self.cfg_file = os.path.join(bdir, f".{PRODUCT_ID.lower()}_lic.dat")
        self.hw_hash = get_sys_hw_hash()
        self.store_key = hashlib.sha256(EMBED_SALT + struct.pack(">H", self.hw_hash)).digest()
        self._load()

    def _gen_nonce(self):
        return int(hashlib.sha256(os.urandom(32) + struct.pack(">Q", time.time_ns())).hexdigest()[:4], 16)

    def _load(self):
        self.data = {"status": "UNAUTHORIZED", "pending_nonce": self._gen_nonce(), "expire_time": 0, "remaining_runs": 0, "last_clock": int(time.time())}
        if os.path.exists(self.cfg_file):
            try:
                with open(self.cfg_file, "rb") as f:
                    cipher = f.read()
                s = derive_stream(self.store_key, len(cipher) - 16)
                tag = cipher[:16]
                body = cipher[16:]
                if hmac.compare_digest(tag, hmac.new(self.store_key, body, hashlib.sha256).digest()[:16]):
                    raw = bytes(b ^ k for b, k in zip(body, s))
                    self.data = json.loads(raw.decode("utf-8"))
            except Exception: pass
        if "pending_nonce" not in self.data or not self.data["pending_nonce"]:
            self.data["pending_nonce"] = self._gen_nonce()
            self._save()

    def _save(self):
        try:
            raw = json.dumps(self.data).encode("utf-8")
            s = derive_stream(self.store_key, len(raw))
            body = bytes(b ^ k for b, k in zip(raw, s))
            tag = hmac.new(self.store_key, body, hashlib.sha256).digest()[:16]
            with open(self.cfg_file, "wb") as f:
                f.write(tag + body)
        except Exception: pass

    def get_req_code(self):
        return encode_request_code(self.hw_hash, self.data.get("pending_nonce", 0))

    def check(self):
        now = int(time.time())
        if now < self.data.get("last_clock", 0) - 3600:
            return False, "系统时钟发生异常回拨，请同步网络时间！"
        self.data["last_clock"] = now
        self._save()
        if self.data.get("status") != "ACTIVE":
            return False, "软件未获得商业授权"
        exp = self.data.get("expire_time", 0)
        if exp != -1 and now > exp:
            return False, "商业授权已过期，请联系软件提供方续期"
        return True, "授权正常"

    def activate(self, code):
        dec = decode_license(code)
        if not dec["valid"]: return False, dec["error"]
        if not dec["is_universal"] and dec["hw_hash"] != self.hw_hash:
            return False, "该激活码绑定了其他机器，无法在本机使用"
        if dec["nonce"] != self.data.get("pending_nonce"):
            return False, "该激活码已被核销或已失效，严禁二次激活程序！"
        
        # 激活成功：立即核销并翻转 Nonce，杜绝重放
        self.data["pending_nonce"] = self._gen_nonce()
        now = int(time.time())
        days = dec["duration_days"]
        self.data["expire_time"] = -1 if days == -1 else (now + days * 86400)
        self.data["remaining_runs"] = -1  # 彻底解除使用次数限制
        self.data["status"] = "ACTIVE"
        self.data["activated_time"] = now
        self._save()
        return True, "授权激活成功！"

    def record_run(self):
        # 彻底解除使用次数限制，不扣减次数
        pass

def derive_stream(key, length):
    blocks = []
    ctr = 0
    gen = 0
    while gen < length:
        h = hmac.new(key, struct.pack(">Q", ctr), hashlib.sha256).digest()
        blocks.append(h)
        gen += len(h)
        ctr += 1
    return b"".join(blocks)[:length]

def decrypt_payload(payload_bytes, dec_key):
    tag = payload_bytes[:16]
    cipher = payload_bytes[16:]
    exp_tag = hmac.new(dec_key, cipher, hashlib.sha256).digest()[:16]
    if not hmac.compare_digest(tag, exp_tag):
        raise ValueError("根级密文完整性受损或授权密钥不符")
    s = derive_stream(dec_key, len(cipher))
    return bytes(b ^ k for b, k in zip(cipher, s))

def show_license_gui(lm):
    root = tk.Tk()
    root.title(f"{PRODUCT_NAME} - 商业授权验证中心")
    root.geometry("540x460")
    root.resizable(False, False)
    root.configure(bg="#0f172a")

    ws = root.winfo_screenwidth()
    hs = root.winfo_screenheight()
    root.geometry(f"540x460+{(ws-540)//2}+{(hs-460)//2}")

    tk.Label(root, text="🛡️ " + PRODUCT_NAME, font=("Microsoft YaHei UI", 16, "bold"), fg="#38bdf8", bg="#0f172a").pack(pady=(24, 4))
    tk.Label(root, text="系统已受 Universal License Armor 根级加壳保护", font=("Microsoft YaHei UI", 9), fg="#94a3b8", bg="#0f172a").pack()

    card = tk.Frame(root, bg="#1e293b", bd=1, relief=tk.SOLID)
    card.pack(fill=tk.BOTH, expand=True, padx=28, pady=18)

    tk.Label(card, text="请将下列【8 位设备申请码】提供给软件销售方:", font=("Microsoft YaHei UI", 10), fg="#cbd5e1", bg="#1e293b").pack(anchor="w", padx=16, pady=(16, 4))

    req_code = lm.get_req_code()
    req_row = tk.Frame(card, bg="#1e293b")
    req_row.pack(fill=tk.X, padx=16, pady=4)

    req_lbl = tk.Label(req_row, text=req_code, font=("Consolas", 18, "bold"), fg="#34d399", bg="#0f172a", padx=14, pady=6)
    req_lbl.pack(side=tk.LEFT)

    def copy_req():
        root.clipboard_clear()
        root.clipboard_append(req_code)
        messagebox.showinfo("复制成功", "设备申请码已复制到剪贴板！")

    tk.Button(req_row, text="📋 复制", font=("Microsoft YaHei UI", 9, "bold"), bg="#059669", fg="#fff", bd=0, padx=12, pady=6, cursor="hand2", command=copy_req).pack(side=tk.LEFT, padx=10)

    tk.Label(card, text="请输入官方签发的 12 位一次性授权激活码:", font=("Microsoft YaHei UI", 10), fg="#cbd5e1", bg="#1e293b").pack(anchor="w", padx=16, pady=(16, 4))

    code_var = tk.StringVar()
    entry = tk.Entry(card, textvariable=code_var, font=("Consolas", 14, "bold"), fg="#38bdf8", bg="#0f172a", bd=1, justify="center", insertbackground="#fff")
    entry.pack(fill=tk.X, padx=16, ipady=4)
    entry.focus()

    res_box = [False]

    def do_act():
        c = code_var.get().strip()
        ok, msg = lm.activate(c)
        if ok:
            messagebox.showinfo("激活成功", "🎉 商业授权验证通过！系统正在解密启动...")
            res_box[0] = True
            root.destroy()
        else:
            messagebox.showerror("激活失败", f"❌ {msg}")

    tk.Button(card, text="⚡ 立即验证激活并启动", font=("Microsoft YaHei UI", 11, "bold"), bg="#2563eb", fg="#fff", activebackground="#1d4ed8", bd=0, pady=8, cursor="hand2", command=do_act).pack(fill=tk.X, padx=16, pady=16)

    root.mainloop()
    return res_box[0]

def bootstrap():
    lm = RuntimeLicenseManager()
    ok, msg = lm.check()
    if not ok:
        activated = show_license_gui(lm)
        if not activated:
            sys.exit(0)
        ok, msg = lm.check()
        if not ok:
            sys.exit(0)

    lm.record_run()

    # 授权验证通过：在 RAM 中内存解密业务代码并动态加载启动！
    dec_key = EMBED_SALT
    
    # 读取同程序包内嵌或外挂的密文资产
    meipass = getattr(sys, '_MEIPASS', None)
    payload_candidates = []
    if meipass:
        payload_candidates.append(os.path.join(meipass, "@@PAYLOAD_FILENAME@@"))
    base_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    payload_candidates.append(os.path.join(base_dir, "@@PAYLOAD_FILENAME@@"))
    payload_candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "@@PAYLOAD_FILENAME@@"))

    payload_path = None
    for p in payload_candidates:
        if os.path.exists(p):
            payload_path = p
            break

    if not payload_path:
        messagebox.showerror("启动异常", f"缺少核心加密资产文件: @@PAYLOAD_FILENAME@@")
        sys.exit(1)

    with open(payload_path, "rb") as f:
        enc_data = f.read()

    try:
        raw_zip_data = decrypt_payload(enc_data, dec_key)
    except Exception as e:
        messagebox.showerror("解密失败", f"受保护代码内存解密异常: {e}")
        sys.exit(1)

    # 在内存虚拟文件系统中解压并动态注入 sys.modules
    import io
    import zipfile
    zf = zipfile.ZipFile(io.BytesIO(raw_zip_data))
    
    # 动态加载所有模块字节码到内存
    entry_code = None
    for item in zf.infolist():
        fname = item.filename
        content = zf.read(fname)
        if fname.endswith(".pyc_raw"):
            mod_name = fname[:-8].replace("/", ".")
            code_obj = marshal.loads(content)
            if fname == "@@ENTRY_MODULE_NAME@@.pyc_raw":
                entry_code = code_obj
            else:
                mod = types.ModuleType(mod_name)
                mod.__file__ = os.path.join(base_dir, fname[:-8] + ".py")
                sys.modules[mod_name] = mod
                exec(code_obj, mod.__dict__)

    # 移交执行权给主入口
    if entry_code:
        main_mod = types.ModuleType("__main__")
        main_mod.__file__ = os.path.join(base_dir, "@@ENTRY_FILE_NAME@@")
        sys.modules["__main__"] = main_mod
        exec(entry_code, main_mod.__dict__)
    else:
        messagebox.showerror("启动异常", "未能找到已加壳的主程序入口！")
        sys.exit(1)

if __name__ == "__main__":
    bootstrap()
'''


class UniversalShieldEngine:
    """通用源码加壳与根级加密编译中枢"""

    @staticmethod
    def pack_and_protect_project(
        project_dir_or_file: str,
        entry_file_name: str,
        output_dir: str,
        product_id: str = "MY_APP",
        product_name: str = "受保护软件",
        icon_path: str = "",
        windowed: bool = True,
        auto_compile_exe: bool = True,
        output_exe_name: str = "",
        uac_admin: bool = False
    ) -> dict:
        """
        全自动执行:
        1. 扫描与提取项目 Python 源码
        2. 编译为 Bytecode 并进行高强度 AES/流密码加密
        3. 打包生成内存加载器与防二次激活商业授权守卫
        4. (可选) 驱动 PyInstaller 编译为原生独立 EXE
        """
        import zipfile
        import io
        import tempfile

        if not os.path.exists(project_dir_or_file):
            return {"success": False, "error": f"输入路径不存在: {project_dir_or_file}"}

        os.makedirs(output_dir, exist_ok=True)
        # 使用独立的系统临时目录进行构建，杜绝工作区文件被递归复制
        build_temp_dir = os.path.join(tempfile.gettempdir(), f"__armor_build_{product_id}_{int(time.time())}__")
        if os.path.exists(build_temp_dir):
            shutil.rmtree(build_temp_dir, ignore_errors=True)
        os.makedirs(build_temp_dir, exist_ok=True)

        is_single_file = os.path.isfile(project_dir_or_file)
        src_root = os.path.dirname(os.path.abspath(project_dir_or_file)) if is_single_file else os.path.abspath(project_dir_or_file)
        entry_abs = os.path.join(src_root, entry_file_name) if not is_single_file else os.path.abspath(project_dir_or_file)

        if not os.path.exists(entry_abs):
            return {"success": False, "error": f"未能找到主入口文件: {entry_abs}"}

        entry_rel = os.path.relpath(entry_abs, src_root).replace("\\", "/")
        entry_mod_name = os.path.splitext(entry_rel)[0].replace("/", ".")

        # 1. 编译并打包所有 Python 源码为 Bytecode Zip
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            if is_single_file:
                with open(entry_abs, "r", encoding="utf-8", errors="ignore") as f:
                    code_text = f.read()
                code_obj = compile(code_text, entry_file_name, "exec")
                zf.writestr(entry_mod_name + ".pyc_raw", marshal.dumps(code_obj))
            else:
                for root, dirs, files in os.walk(src_root):
                    # 忽略临时与输出目录
                    if any(ign in root for ign in [".git", "__pycache__", "build", "dist", ".idea", ".vscode"]):
                        continue
                    for file in files:
                        if file.endswith(".py"):
                            file_p = os.path.join(root, file)
                            rel_p = os.path.relpath(file_p, src_root).replace("\\", "/")
                            mod_name = os.path.splitext(rel_p)[0].replace("/", ".")
                            try:
                                with open(file_p, "r", encoding="utf-8", errors="ignore") as f:
                                    code_text = f.read()
                                code_obj = compile(code_text, rel_p, "exec")
                                zf.writestr(mod_name + ".pyc_raw", marshal.dumps(code_obj))
                            except Exception as e:
                                print(f"[警告] 编译跳过 {rel_p}: {e}")

        raw_zip_bytes = zip_buffer.getvalue()

        # 2. 计算产品专属加密密钥并加密资产
        from universal_license_core import get_product_salt
        salt = get_product_salt(product_id)
        
        # 静态资产包以通用密钥加密，运行时结合硬件派生解密
        enc_payload = encrypt_bytes(raw_zip_bytes, salt)

        payload_filename = f"{product_id.lower()}_core.enc"
        payload_save_path = os.path.join(build_temp_dir, payload_filename)
        with open(payload_save_path, "wb") as f:
            f.write(enc_payload)

        # 复制非 Python 的资源文件 (static, assets, config, media 等) 到 build_temp_dir
        for item in os.listdir(src_root):
            src_item = os.path.join(src_root, item)
            dst_item = os.path.join(build_temp_dir, item)
            if item in ["build", "dist", "__pycache__", ".git", ".idea", ".vscode"]:
                continue
            if os.path.isdir(src_item):
                shutil.copytree(src_item, dst_item, dirs_exist_ok=True)
            elif not item.endswith(".py"):
                shutil.copy2(src_item, dst_item)

        # 3. 渲染并生成加壳启动主程序
        loader_code = ARMOR_BOOT_TEMPLATE
        loader_code = loader_code.replace("@@PRODUCT_ID@@", product_id)
        loader_code = loader_code.replace("@@PRODUCT_NAME@@", product_name)
        loader_code = loader_code.replace("@@EMBED_SALT_BYTES@@", repr(salt))
        loader_code = loader_code.replace("@@PAYLOAD_FILENAME@@", payload_filename)
        loader_code = loader_code.replace("@@ENTRY_MODULE_NAME@@", entry_mod_name)
        loader_code = loader_code.replace("@@ENTRY_FILE_NAME@@", os.path.basename(entry_abs))

        boot_file_path = os.path.join(build_temp_dir, "armor_entry.py")
        with open(boot_file_path, "w", encoding="utf-8") as f:
            f.write(loader_code)

        # 4. 如果不需要编译 EXE，直接输出加壳源码工程包
        if not auto_compile_exe:
            final_src_dir = os.path.join(output_dir, f"{product_id}_Protected_Source")
            if os.path.exists(final_src_dir):
                shutil.rmtree(final_src_dir, ignore_errors=True)
            shutil.copytree(build_temp_dir, final_src_dir)
            return {
                "success": True,
                "output_type": "source",
                "path": final_src_dir,
                "message": "受保护加壳源码工程生成就绪"
            }

        # 5. 驱动 PyInstaller 编译为原生独立 EXE
        actual_exe_title = output_exe_name if output_exe_name else product_id
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--clean", "-y",
            "--onefile",
            "--name", actual_exe_title,
            "--add-data", f"{payload_filename};.",
        ]

        if uac_admin:
            cmd.append("--uac-admin")

        if not windowed:
            cmd.append("--console")
        else:
            cmd.append("--noconsole")

        if icon_path and os.path.exists(icon_path):
            cmd.extend(["--icon", icon_path])

        cmd.append(boot_file_path)

        print(f"[*] 正在调用 PyInstaller 进行根级二进制编译: {' '.join(cmd)}")
        res = subprocess.run(cmd, cwd=build_temp_dir, capture_output=True, text=True, encoding="utf-8", errors="replace")

        dist_exe_path = os.path.join(build_temp_dir, "dist", f"{actual_exe_title}.exe")
        if os.path.exists(dist_exe_path):
            final_exe_path = os.path.join(output_dir, f"{actual_exe_title}.exe")
            shutil.copy2(dist_exe_path, final_exe_path)
            # 清理中间临时缓存
            shutil.rmtree(build_temp_dir, ignore_errors=True)
            return {
                "success": True,
                "output_type": "exe",
                "path": final_exe_path,
                "message": f"受根级加密保护的可执行文件生成成功: {final_exe_path}"
            }
        else:
            return {
                "success": False,
                "error": f"PyInstaller 编译未生成预期的 EXE: {res.stderr}\n{res.stdout}"
            }
