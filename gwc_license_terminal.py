# -*- coding: utf-8 -*-
"""
展馆控制终端专属商业授权加密算法引擎 (Exhibit Terminal License Engine 2026)
========================================================================
1. 与原国文创加密机 (VisualCast) 完全区分独立，拥有专属算法体系与防伪签名。
2. 设备申请码: 8 位动态随机格式 (XXXX-XXXX)，一机一码 + 动态防二次激活。
3. 商业激活码: 16 位专属格式 (XXXX-XXXX-XXXX-XXXX)，包含硬件绑定、有效期与防伪签名。
4. 全面支持新授权覆盖升级写入 (支持从试用到永久、或新密钥无缝覆盖)。
"""

import os
import sys
import shutil
import time
import struct
import hashlib
import hmac
import uuid
import json
import platform
import re

# 专属防伪私钥盐值 (与原 VisualCast 完全独立区分)
TERMINAL_HMAC_SALT = b"Exhibit_Control_Terminal_Pro_Engine_2026_Secure_Salt_Key!"

# 字符集 (排除容易混淆的 0, 1, I, O)
CHARSET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
CHAR_TO_VAL = {c: i for i, c in enumerate(CHARSET)}

# 有效期模式常量定义
MODE_LEGACY = 0      # 兼容模式 (旧 dur_code 映射)
MODE_CUSTOM_HOUR = 1 # 自定义小时模式 (1 ~ 16383 小时)
MODE_CUSTOM_MONTH = 2 # 自定义月份模式 (1 ~ 16383 个月，按30天计)
MODE_PERMANENT = 3   # 永久商业授权模式

# 预设传统编码映射 (完全兼容旧接口)
DURATION_DICT = {
    0: ("1 小时 (临时体验/调试)", 3600, "hour"),
    1: ("2 小时 (短期演示)", 7200, "hour"),
    2: ("6 小时 (半天运维)", 21600, "hour"),
    3: ("12 小时 (单班次授权)", 43200, "hour"),
    4: ("24 小时 (1天测试)", 86400, "hour"),
    5: ("48 小时 (2天体验)", 172800, "hour"),
    6: ("72 小时 (3天短租)", 259200, "hour"),
    7: ("168 小时 (7天体验)", 604800, "hour"),
    8: ("1 个月 (30天标准商业授权)", 30 * 86400, "month"),
    9: ("3 个月 (90天季度授权)", 90 * 86400, "month"),
    10: ("6 个月 (180天半年授权)", 180 * 86400, "month"),
    11: ("12 个月 (1年商业授权)", 365 * 86400, "month"),
    15: ("永久商业授权 (终身永久有效)", -1, "forever")
}

# 64 位非线性置换表 (用于 16 位激活码混淆置换)
PERM_64 = [
    27, 4, 51, 18, 33, 10, 47, 0, 23, 60, 37, 14, 59, 28, 5, 42,
    19, 56, 32, 9, 46, 24, 1, 38, 15, 52, 29, 6, 43, 20, 57, 34,
    11, 48, 25, 2, 39, 16, 53, 30, 7, 44, 21, 58, 35, 12, 49, 26,
    3, 40, 17, 54, 31, 8, 45, 22, 63, 62, 61, 55, 50, 36, 13, 61
]
UNPERM_64 = [0] * 64
for _idx, _p in enumerate(PERM_64[:64]):
    UNPERM_64[_p] = _idx

# 40 位置换表 (用于 8 位申请码)
PERM_40 = [
    19, 7, 31, 15, 3, 27, 11, 35, 0, 23, 8, 32, 16, 4, 28, 12,
    36, 1, 20, 9, 33, 17, 5, 29, 13, 37, 2, 21, 10, 34, 18, 6,
    30, 14, 38, 25, 26, 24, 22, 39
]
UNPERM_40 = [0] * 40
for _idx, _p in enumerate(PERM_40[:40]):
    UNPERM_40[_p] = _idx


def get_local_hw_fingerprint() -> int:
    """计算本机硬件唯一指纹 (MAC + CPU + 机器标识) -> 16 位无符号整数 (1-65535)"""
    parts = []
    try:
        parts.append(f"MAC_{uuid.getnode():012X}")
    except Exception:
        pass
    parts.append(f"CPU_{os.environ.get('PROCESSOR_IDENTIFIER', '')}_{os.environ.get('NUMBER_OF_PROCESSORS', '1')}")
    parts.append(f"NODE_{platform.node()}")
    h = int(hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:8], 16)
    return (h % 65530) + 1


def _calc_req_hmac(hw_hash: int, nonce: int) -> int:
    msg = struct.pack(">HH", hw_hash & 0xFFFF, nonce & 0x0FFF)
    dig = hmac.new(TERMINAL_HMAC_SALT, b"TERM_REQ:" + msg, hashlib.sha256).digest()
    return ((dig[0] << 8) | dig[1]) & 0x0FFF


def encode_request_code(hw_hash: int = None, nonce: int = None) -> str:
    """生成 8 位终端申请码 (XXXX-XXXX)"""
    if hw_hash is None:
        hw_hash = get_local_hw_fingerprint()
    if nonce is None:
        import random
        nonce = random.randint(1, 4090)

    chk = _calc_req_hmac(hw_hash, nonce)
    # 40 bits = 16-bit hw_hash + 12-bit nonce + 12-bit chk
    val40 = ((hw_hash & 0xFFFF) << 24) | ((nonce & 0x0FFF) << 12) | (chk & 0x0FFF)

    # 非线性置换
    perm_val = 0
    for new_pos, old_pos in enumerate(PERM_40):
        bit = (val40 >> old_pos) & 1
        perm_val |= (bit << new_pos)

    # 5-bit Base32 编码 -> 8 个字符
    chars = []
    for _ in range(8):
        chars.append(CHARSET[perm_val & 0x1F])
        perm_val >>= 5
    chars.reverse()
    return f"{''.join(chars[:4])}-{''.join(chars[4:])}"


def decode_request_code(code_str: str) -> dict:
    """解析 8 位终端申请码"""
    clean = re.sub(r"[^A-Za-z0-9]", "", code_str.upper())
    if len(clean) != 8:
        return {"valid": False, "error": "申请码必须为 8 位"}
    for c in clean:
        if c not in CHAR_TO_VAL:
            return {"valid": False, "error": f"包含非法字符: {c}"}

    val40 = 0
    for c in clean:
        val40 = (val40 << 5) | CHAR_TO_VAL[c]

    # 逆置换
    orig_val = 0
    for new_pos, old_pos in enumerate(PERM_40):
        bit = (val40 >> new_pos) & 1
        orig_val |= (bit << old_pos)

    chk = orig_val & 0x0FFF
    nonce = (orig_val >> 12) & 0x0FFF
    hw_hash = (orig_val >> 24) & 0xFFFF

    expected_chk = _calc_req_hmac(hw_hash, nonce)
    if chk != expected_chk:
        return {"valid": False, "error": "申请码防伪校验失败 (非本系统有效申请码)"}

    return {"valid": True, "hw_hash": hw_hash, "nonce": nonce}


def _calc_act_hmac(hw_hash: int, nonce: int, dur_code: int) -> int:
    msg = struct.pack(">HHB", hw_hash & 0xFFFF, nonce & 0x0FFF, dur_code & 0x0F)
    dig = hmac.new(TERMINAL_HMAC_SALT, b"TERM_ACT:" + msg, hashlib.sha256).digest()
    raw24 = (dig[0] << 16) | (dig[1] << 8) | dig[2]
    return raw24 & 0xFFFFF


def _calc_act_hmac_ext(hw_hash: int, nonce: int, mode: int, val14: int) -> int:
    msg = struct.pack(">HHBH", hw_hash & 0xFFFF, nonce & 0x0FFF, mode & 0x03, val14 & 0x3FFF)
    dig = hmac.new(TERMINAL_HMAC_SALT, b"TERM_ACT_EXT:" + msg, hashlib.sha256).digest()
    raw24 = (dig[0] << 16) | (dig[1] << 8) | dig[2]
    return raw24 & 0xFFFFF


def generate_terminal_license(hw_hash: int, nonce: int, auth_type: str = "permanent", custom_val: int = 1) -> str:
    """
    生成 16 位专属商业激活码 (原生支持 自定义小时、自定义月、永久商业授权)
    :param hw_hash: 本机硬件指纹 (16-bit)
    :param nonce: 动态 Nonce (12-bit)
    :param auth_type: "hour" (小时), "month" (月), "permanent" (永久)
    :param custom_val: 自定义小时数 (1 ~ 16383) 或 自定义月数 (1 ~ 16383)
    """
    auth_type = (auth_type or "permanent").lower()
    if auth_type in ["hour", "hours", "h"]:
        mode = MODE_CUSTOM_HOUR
        val14 = max(1, min(16383, int(custom_val)))
    elif auth_type in ["month", "months", "m"]:
        mode = MODE_CUSTOM_MONTH
        val14 = max(1, min(16383, int(custom_val)))
    else:
        mode = MODE_PERMANENT
        val14 = 0

    sig20 = _calc_act_hmac_ext(hw_hash, nonce, mode, val14)

    # 64-bit 结构:
    # [16-bit hw_hash] + [12-bit nonce] + [2-bit mode] + [14-bit val14] + [20-bit sig20]
    val64 = ((hw_hash & 0xFFFF) << 48) | \
            ((nonce & 0x0FFF) << 36) | \
            ((mode & 0x03) << 34) | \
            ((val14 & 0x3FFF) << 20) | \
            (sig20 & 0xFFFFF)

    hdr16 = ((sig20 >> 4) ^ hw_hash ^ (nonce << 4) ^ (mode << 14) ^ (val14 & 0xFFFF)) & 0xFFFF
    val80 = (hdr16 << 64) | val64

    # 编码为 16 个 Base32 字符 (XXXX-XXXX-XXXX-XXXX)
    chars = []
    v = val80
    for _ in range(16):
        chars.append(CHARSET[v & 0x1F])
        v >>= 5
    chars.reverse()
    return f"{''.join(chars[0:4])}-{''.join(chars[4:8])}-{''.join(chars[8:12])}-{''.join(chars[12:16])}"


def encode_activation_code(hw_hash: int, nonce: int, dur_code: int = 15, auth_type: str = None, custom_val: int = None) -> str:
    """
    生成 16 位商业激活码 (全能兼容接口)
    """
    if auth_type is not None:
        return generate_terminal_license(hw_hash, nonce, auth_type, custom_val if custom_val is not None else 1)

    # 根据旧版 dur_code 映射
    if dur_code == 15 or dur_code >= 15:
        return generate_terminal_license(hw_hash, nonce, "permanent", 0)
    dur_info = DURATION_DICT.get(dur_code, ("1 小时", 3600, "hour"))
    unit = dur_info[2]
    sec = dur_info[1]
    if unit == "hour":
        hrs = max(1, sec // 3600)
        return generate_terminal_license(hw_hash, nonce, "hour", hrs)
    elif unit == "month":
        months = max(1, sec // (30 * 86400))
        return generate_terminal_license(hw_hash, nonce, "month", months)
    else:
        return generate_terminal_license(hw_hash, nonce, "permanent", 0)


def decode_activation_code(act_str: str) -> dict:
    """解析并校验 16 位激活码 (全面支持 自定义小时、自定义月、永久 及兼容模式)"""
    clean = re.sub(r"[^A-Za-z0-9]", "", act_str.upper())
    if len(clean) != 16:
        return {"valid": False, "error": "激活码必须为 16 位 (格式: XXXX-XXXX-XXXX-XXXX)"}
    for c in clean:
        if c not in CHAR_TO_VAL:
            return {"valid": False, "error": f"激活码包含非法字符: {c}"}

    val80 = 0
    for c in clean:
        val80 = (val80 << 5) | CHAR_TO_VAL[c]

    val64 = val80 & 0xFFFFFFFFFFFFFFFF
    hdr16 = (val80 >> 64) & 0xFFFF

    sig20 = val64 & 0xFFFFF
    val14 = (val64 >> 20) & 0x3FFF
    mode = (val64 >> 34) & 0x03
    nonce = (val64 >> 36) & 0x0FFF
    hw_hash = (val64 >> 48) & 0xFFFF

    # 1. 优先校验扩展模式 (自定义小时、月、永久)
    expected_sig_ext = _calc_act_hmac_ext(hw_hash, nonce, mode, val14)
    expected_hdr_ext = ((sig20 >> 4) ^ hw_hash ^ (nonce << 4) ^ (mode << 14) ^ (val14 & 0xFFFF)) & 0xFFFF

    if sig20 == expected_sig_ext and hdr16 == expected_hdr_ext:
        if mode == MODE_CUSTOM_HOUR:
            dur_sec = val14 * 3600
            desc = f"{val14} 小时 (自定义商业授权)"
            unit = "hour"
        elif mode == MODE_CUSTOM_MONTH:
            dur_sec = val14 * 30 * 86400
            desc = f"{val14} 个月 (自定义商业授权)"
            unit = "month"
        else: # MODE_PERMANENT
            dur_sec = -1
            desc = "永久商业授权 (终身永久有效)"
            unit = "permanent"

        return {
            "valid": True,
            "hw_hash": hw_hash,
            "nonce": nonce,
            "mode": mode,
            "custom_val": val14,
            "duration_desc": desc,
            "duration_seconds": dur_sec,
            "duration_unit": unit
        }

    # 2. 兼容旧版固定 dur_code 校验 (0x9A6 flag)
    flag12 = (val64 >> 20) & 0x0FFF
    dur_code = (val64 >> 32) & 0x0F
    if flag12 == 0x9A6:
        expected_sig_leg = _calc_act_hmac(hw_hash, nonce, dur_code)
        expected_hdr_leg = ((sig20 >> 4) ^ hw_hash ^ (nonce << 4)) & 0xFFFF
        if sig20 == expected_sig_leg and hdr16 == expected_hdr_leg:
            dur_info = DURATION_DICT.get(dur_code, ("1 小时", 3600, "hour"))
            return {
                "valid": True,
                "hw_hash": hw_hash,
                "nonce": nonce,
                "mode": MODE_LEGACY,
                "custom_val": dur_code,
                "duration_desc": dur_info[0],
                "duration_seconds": dur_info[1],
                "duration_unit": dur_info[2]
            }

    return {"valid": False, "error": "激活码签名校验失败，可能已被篡改或不属于当前系统"}


# ==================== 本地授权管理器 (支持新授权随时覆盖) ====================
class TerminalLicenseManager:
    """展馆控制终端商业授权管理器 (支持随时输入新激活码覆盖写入)"""

    def __init__(self, lic_filename: str = ".terminal_lic_2026.dat"):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        if getattr(sys, "frozen", False):
            base_dir = os.path.dirname(os.path.abspath(sys.executable))

        # 统一归档在受控端专属文件夹 GWC_Terminal_Data/License/ 内部，绝不散落于程序根目录
        lic_dir = os.path.join(base_dir, "GWC_Terminal_Data", "License")
        os.makedirs(lic_dir, exist_ok=True)
        new_lic_path = os.path.join(lic_dir, lic_filename)
        old_lic_path = os.path.join(base_dir, lic_filename)

        # 自动迁移根目录下遗留的旧凭证并清理根目录
        if os.path.exists(old_lic_path) and not os.path.exists(new_lic_path):
            try:
                shutil.copy2(old_lic_path, new_lic_path)
                try: os.remove(old_lic_path)
                except Exception: pass
            except Exception:
                pass

        self.lic_path = new_lic_path
        self.hw_hash = get_local_hw_fingerprint()
        self.nonce = (int(time.time()) // 100) % 4090 + 1
        self._cached_req_code = encode_request_code(self.hw_hash, self.nonce)
        self.data = {}
        self.load()

    def get_req_code(self) -> str:
        """获取当前 8 位设备申请码"""
        return self._cached_req_code

    def get_request_code(self) -> str:
        return self._cached_req_code

    def load(self):
        """从磁盘加载授权数据"""
        self.data = {}
        if os.path.exists(self.lic_path):
            try:
                with open(self.lic_path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception:
                self.data = {}

    def save(self):
        """持久化保存授权数据到磁盘"""
        try:
            os.makedirs(os.path.dirname(self.lic_path), exist_ok=True)
            with open(self.lic_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[-] 保存授权文件失败: {e}")

    def check(self) -> tuple:
        """
        核验当前授权状态
        返回 (is_valid: bool, desc: str)
        """
        if not self.data or not self.data.get("act_code"):
            return False, "软件尚未获得有效商业授权 (未激活)"

        act_code = self.data.get("act_code", "")
        dec = decode_activation_code(act_code)
        if not dec.get("valid"):
            return False, f"授权文件已损坏或非法: {dec.get('error')}"

        # 硬件指纹核对
        if dec["hw_hash"] != self.hw_hash:
            return False, "授权绑定的工控机硬件不匹配 (已更换硬件或跨设备复制)"

        # 有效期核对 (支持小时、年、永久)
        exp_time = self.data.get("expire_time", 0)
        if exp_time == -1:
            return True, "官方商业永久授权正常 (永久有效)"
        elif exp_time > 0:
            left_sec = exp_time - time.time()
            if left_sec <= 0:
                return False, "商业授权已到期，请联系管理员续期"
            if left_sec < 3600:
                left_mins = max(1, int(left_sec // 60))
                return True, f"商业授权有效 (剩余 {left_mins} 分钟)"
            elif left_sec < 86400:
                left_hrs = int(left_sec // 3600)
                left_mins = int((left_sec % 3600) // 60)
                return True, f"商业授权有效 (剩余 {left_hrs} 小时 {left_mins} 分钟)"
            elif left_sec < 365 * 86400:
                left_days = int(left_sec // 86400)
                return True, f"商业授权有效 (剩余 {left_days} 天)"
            else:
                left_years = round(left_sec / (365 * 86400), 1)
                left_days = int(left_sec // 86400)
                return True, f"商业授权有效 (剩余 {left_years} 年 / {left_days} 天)"

        return False, "未授权"

    def is_authorized(self) -> bool:
        ok, _ = self.check()
        return ok

    def activate(self, act_code: str, force_overwrite: bool = True) -> tuple:
        """
        激活或覆盖当前授权 (支持任意新授权覆盖)
        返回 (success: bool, msg: str)
        """
        act_code = act_code.strip()
        dec = decode_activation_code(act_code)
        if not dec.get("valid"):
            return False, dec.get("error", "无效激活码")

        # 校验硬件指纹绑定
        if dec["hw_hash"] != self.hw_hash:
            return False, "激活码与当前本机硬件指纹不匹配！"

        dur_sec = dec["duration_seconds"]
        now = time.time()
        expire_time = -1 if dur_sec == -1 else (now + dur_sec)

        # 完整覆盖写入
        self.data = {
            "act_code": act_code,
            "hw_hash": self.hw_hash,
            "activated_at": int(now),
            "expire_time": expire_time,
            "duration_desc": dec["duration_desc"],
            "duration_unit": dec.get("duration_unit", "forever"),
            "algorithm": "EXHIBIT_PRO_2026"
        }
        self.save()
        return True, f"授权成功！{dec['duration_desc']} 已生效！"
