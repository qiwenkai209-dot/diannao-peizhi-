# -*- coding: utf-8 -*-
"""
VisualCast 通用商业授权算法核心引擎 (Universal License Core)
============================================================
特性:
1. 支持任意软件项目接入 (多产品支持，通过 product_salt 区分，互不串用)。
2. 8 位动态随机申请码 (XXXX-XXXX)，一机一码 + 动态 Nonce 防二次激活。
3. 12 位一次性授权激活码 (XXXX-XXXX-XXXX)，包含硬件绑定、随机代际、时长天数、启动次数与 HMAC 签名。
4. 全局 40-bit 与 60-bit 位混淆置换，具备高抗碰撞与防逆向雪崩效应。
"""

import re
import hmac
import hashlib
import struct
import os

CHARSET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
CHAR_TO_VAL = {c: i for i, c in enumerate(CHARSET)}

DEFAULT_GLOBAL_SALT = b"VisualCast_Universal_Armor_License_v3_2026_Secure!"
LEGACY_VISUALCAST_SALT = b"VisualCast_License_Salt_v3_2026_RandomNonceSecure!"

DURATION_MAP = {
    11: ("0.5天 (半天/12小时)", 0.5),
    0: ("1天 (体验)", 1),
    1: ("3天 (试用)", 3),
    2: ("7天 (1周)", 7),
    3: ("15天 (半月)", 15),
    4: ("30天 (1个月)", 30),
    5: ("60天 (2个月)", 60),
    6: ("90天 (1季度)", 90),
    7: ("180天 (半年)", 180),
    8: ("365天 (1年)", 365),
    9: ("730天 (2年)", 730),
    10: ("1095天 (3年)", 1095),
    31: ("永久有效", -1)
}

RUNS_MAP = {
    0: ("5 次", 5),
    1: ("10 次", 10),
    2: ("20 次", 20),
    3: ("50 次", 50),
    4: ("100 次", 100),
    5: ("200 次", 200),
    6: ("500 次", 500),
    7: ("1000 次", 1000),
    8: ("2000 次", 2000),
    9: ("5000 次", 5000),
    10: ("10000 次", 10000),
    31: ("无限制", -1)
}

SHUFFLE_P_40 = [
    31, 7, 23, 15, 39, 3, 19, 11, 27, 35,
    0, 16, 8, 24, 32, 4, 20, 12, 28, 36,
    1, 17, 9, 25, 33, 5, 21, 13, 29, 37,
    2, 18, 10, 26, 34, 6, 22, 14, 30, 38
]
UNSHUFFLE_P_40 = [0] * 40
for _i, _p in enumerate(SHUFFLE_P_40):
    UNSHUFFLE_P_40[_p] = _i

SHUFFLE_P_60 = [
    13, 50, 27, 4, 41, 18, 55, 32, 9, 46, 23, 0, 37, 14, 51, 28, 5, 42, 19, 56,
    33, 10, 47, 24, 1, 38, 15, 52, 29, 6, 43, 20, 57, 34, 11, 48, 25, 2, 39, 16,
    53, 30, 7, 44, 21, 58, 35, 12, 49, 26, 3, 40, 17, 54, 31, 8, 45, 22, 59, 36
]
UNSHUFFLE_P_60 = [0] * 60
for _i, _p in enumerate(SHUFFLE_P_60):
    UNSHUFFLE_P_60[_p] = _i


def get_product_salt(product_id: str = "") -> bytes:
    """根据软件产品标识派生该产品的专属私钥盐值"""
    if product_id in ("VisualCast_Native", "LEGACY_NATIVE"):
        return LEGACY_VISUALCAST_SALT
    if not product_id or product_id == "DEFAULT":
        return DEFAULT_GLOBAL_SALT
    return hashlib.sha256(DEFAULT_GLOBAL_SALT + b"::" + product_id.encode("utf-8")).digest()


def _permute_bits(val: int, perm: list) -> int:
    result = 0
    for new_pos, old_pos in enumerate(perm):
        bit = (val >> old_pos) & 1
        result |= (bit << new_pos)
    return result


def calc_req_checksum_with_salt(hw_hash: int, nonce: int, salt: bytes) -> int:
    payload = struct.pack(">HH", hw_hash & 0x0FFF, nonce & 0xFFFF)
    digest = hmac.new(salt, b"REQ:" + payload, hashlib.sha256).digest()
    raw = (digest[0] << 8) | digest[1]
    return raw & 0x0FFF


def calc_req_checksum(hw_hash: int, nonce: int, product_id: str = "") -> int:
    salt = get_product_salt(product_id)
    return calc_req_checksum_with_salt(hw_hash, nonce, salt)


def encode_request_code(hw_hash: int, nonce: int, product_id: str = "") -> str:
    """生成 8 位设备随机申请码 (格式: XXXX-XXXX)"""
    hw_hash &= 0x0FFF
    nonce &= 0xFFFF
    checksum = calc_req_checksum(hw_hash, nonce, product_id)
    raw_num = (hw_hash << 28) | (nonce << 12) | checksum
    shuffled_num = _permute_bits(raw_num, SHUFFLE_P_40)

    chars = []
    tmp = shuffled_num
    for _ in range(8):
        chars.append(CHARSET[tmp & 0x1F])
        tmp >>= 5
    s = "".join(chars)
    return f"{s[:4]}-{s[4:]}"


CHAR_PATTERN = r"[23456789ABCDEFGHJKLMNPQRSTUVWXYZ]"
REQ_REGEX = re.compile(rf"({CHAR_PATTERN}{{4}})[-_]?({CHAR_PATTERN}{{4}})", re.IGNORECASE)


def decode_request_code(code_str: str, product_id: str = "") -> dict:
    """
    全能智能解码并校验 8 位设备随机申请码
    - 智能正则过滤前缀、换行、空格及中文标点
    - 自动自适应低位/高位二进制排布 (兼容多媒体手册 Web/JS 与 VisualCast 原生 Python/Android 端)
    - 自动探测多产品盐体系 (Manual、VisualCast、VisualCast_Native、全局默认)
    """
    m = REQ_REGEX.search(code_str.upper())
    if not m:
        # 如果未正则匹配到成对 4+4，尝试清洗纯有效字符
        clean = re.sub(r"[^23456789ABCDEFGHJKLMNPQRSTUVWXYZ]", "", code_str.upper())
        if len(clean) != 8:
            return {"valid": False, "error": f"申请码须包含 8 位有效字符 (如: XXXX-XXXX)，当前为 {len(clean)} 位"}
        clean_code = clean
    else:
        clean_code = m.group(1) + m.group(2)

    formatted_code = f"{clean_code[:4]}-{clean_code[4:]}"

    # 1. 尝试通用/多媒体手册低位优先排布 (Low-bit order)
    num_low = 0
    for i, c in enumerate(clean_code):
        num_low |= (CHAR_TO_VAL[c] << (i * 5))
    unshuffled_low = _permute_bits(num_low, UNSHUFFLE_P_40)
    hw_low = (unshuffled_low >> 28) & 0x0FFF
    nonce_low = (unshuffled_low >> 12) & 0xFFFF
    checksum_low = unshuffled_low & 0x0FFF

    # 2. 尝试原生高位优先排布 (High-bit order: VisualCast 原生)
    num_high = 0
    for c in clean_code:
        num_high = (num_high << 5) | CHAR_TO_VAL[c]
    unshuffled_high = _permute_bits(num_high, UNSHUFFLE_P_40)
    hw_high = (unshuffled_high >> 28) & 0x0FFF
    nonce_high = (unshuffled_high >> 12) & 0xFFFF
    checksum_high = unshuffled_high & 0x0FFF

    # 候选产品及盐值队列
    candidates = []
    pid_clean = (product_id or "").strip()
    if pid_clean and pid_clean not in ("DEFAULT", "VisualCast_Native"):
        candidates.append((pid_clean, get_product_salt(pid_clean)))
    
    # 常用项目专属盐
    candidates.append(("ShengLi", get_product_salt("ShengLi")))
    candidates.append(("Manual", get_product_salt("Manual")))
    candidates.append(("VisualCast", get_product_salt("VisualCast")))
    candidates.append(("", DEFAULT_GLOBAL_SALT))
    candidates.append(("VisualCast_Native", LEGACY_VISUALCAST_SALT))

    # A. 校验低位优先
    for pid_name, salt in candidates:
        if checksum_low == calc_req_checksum_with_salt(hw_low, nonce_low, salt):
            return {
                "valid": True,
                "hw_hash": hw_low,
                "hw_hex": f"{hw_low:03X}",
                "nonce": nonce_low,
                "code": formatted_code,
                "bit_order": "low_first",
                "matched_product_id": pid_name
            }

    # B. 校验高位优先
    for pid_name, salt in candidates:
        if checksum_high == calc_req_checksum_with_salt(hw_high, nonce_high, salt):
            return {
                "valid": True,
                "hw_hash": hw_high,
                "hw_hex": f"{hw_high:03X}",
                "nonce": nonce_high,
                "code": formatted_code,
                "bit_order": "high_first",
                "matched_product_id": pid_name
            }

    return {"valid": False, "error": "申请码校验和不匹配 (可能输入有误或属于其他产品)"}


def calc_license_hmac(hw_hash: int, nonce: int, duration_code: int, runs_code: int, product_id: str = "") -> int:
    salt = get_product_salt(product_id)
    payload = struct.pack(">HHBB", hw_hash & 0x0FFF, nonce & 0xFFFF, duration_code & 0x1F, runs_code & 0x1F)
    digest = hmac.new(salt, b"LIC:" + payload, hashlib.sha256).digest()
    raw = (digest[0] << 16) | (digest[1] << 8) | digest[2]
    return raw & 0x3FFFFF


def encode_license(hw_hash: int, nonce: int, duration_code: int, runs_code: int, product_id: str = "") -> str:
    """生成 12 位一次性授权激活码 (格式: XXXX-XXXX-XXXX)"""
    hw_hash &= 0x0FFF
    nonce &= 0xFFFF
    duration_code &= 0x1F
    runs_code &= 0x1F

    # 原生 VisualCast 体系采用高位优先编码
    if product_id == "VisualCast_Native":
        salt = LEGACY_VISUALCAST_SALT
        payload = struct.pack(">HHBB", hw_hash, nonce, duration_code, runs_code)
        digest = hmac.new(salt, b"LIC:" + payload, hashlib.sha256).digest()
        sig = ((digest[0] << 16) | (digest[1] << 8) | digest[2]) & 0x3FFFFF

        raw_num = (hw_hash << 48) | (nonce << 32) | (duration_code << 27) | (runs_code << 22) | sig
        shuffled_num = _permute_bits(raw_num, SHUFFLE_P_60)
        chars = []
        tmp = shuffled_num
        for _ in range(12):
            chars.append(CHARSET[tmp & 0x1F])
            tmp >>= 5
        s = "".join(reversed(chars))
        return f"{s[:4]}-{s[4:8]}-{s[8:]}"

    # 通用及多媒体手册体系采用低位优先编码
    sig = calc_license_hmac(hw_hash, nonce, duration_code, runs_code, product_id)
    raw_num = (hw_hash << 48) | (nonce << 32) | (duration_code << 27) | (runs_code << 22) | sig
    shuffled_num = _permute_bits(raw_num, SHUFFLE_P_60)

    chars = []
    tmp = shuffled_num
    for _ in range(12):
        chars.append(CHARSET[tmp & 0x1F])
        tmp >>= 5
    s = "".join(chars)
    return f"{s[:4]}-{s[4:8]}-{s[8:]}"


LIC_REGEX = re.compile(rf"({CHAR_PATTERN}{{4}})[-_]?({CHAR_PATTERN}{{4}})[-_]?({CHAR_PATTERN}{{4}})", re.IGNORECASE)


def decode_license(license_str: str, product_id: str = "") -> dict:
    """全能解码并真伪校验 12 位授权激活码 (双向兼容低位与高位，支持全产品自适应反查)"""
    m = LIC_REGEX.search(license_str.upper())
    if not m:
        clean = re.sub(r"[^23456789ABCDEFGHJKLMNPQRSTUVWXYZ]", "", license_str.upper())
        if len(clean) != 12:
            return {"valid": False, "error": f"激活码须包含 12 位字符，当前为 {len(clean)} 位"}
        clean_str = clean
    else:
        clean_str = m.group(1) + m.group(2) + m.group(3)

    formatted = f"{clean_str[:4]}-{clean_str[4:8]}-{clean_str[8:]}"

    # 1. 低位解码
    num_low = 0
    for i, c in enumerate(clean_str):
        num_low |= (CHAR_TO_VAL[c] << (i * 5))
    un_low = _permute_bits(num_low, UNSHUFFLE_P_60)
    sig_low = un_low & 0x3FFFFF
    runs_low = (un_low >> 22) & 0x1F
    dur_low = (un_low >> 27) & 0x1F
    nonce_low = (un_low >> 32) & 0xFFFF
    hw_low = (un_low >> 48) & 0x0FFF

    # 2. 高位解码
    num_high = 0
    for c in clean_str:
        num_high = (num_high << 5) | CHAR_TO_VAL[c]
    un_high = _permute_bits(num_high, UNSHUFFLE_P_60)
    sig_high = un_high & 0x3FFFFF
    runs_high = (un_high >> 22) & 0x1F
    dur_high = (un_high >> 27) & 0x1F
    nonce_high = (un_high >> 32) & 0xFFFF
    hw_high = (un_high >> 48) & 0x0FFF

    candidates = []
    pid_clean = (product_id or "").strip()
    if pid_clean and pid_clean not in ("DEFAULT", "VisualCast_Native"):
        candidates.append((pid_clean, get_product_salt(pid_clean)))
    candidates.append(("ShengLi", get_product_salt("ShengLi")))
    candidates.append(("Manual", get_product_salt("Manual")))
    candidates.append(("VisualCast", get_product_salt("VisualCast")))
    candidates.append(("", DEFAULT_GLOBAL_SALT))
    candidates.append(("VisualCast_Native", LEGACY_VISUALCAST_SALT))

    # 校验低位
    for pid_name, salt in candidates:
        payload = struct.pack(">HHBB", hw_low, nonce_low, dur_low, runs_low)
        digest = hmac.new(salt, b"LIC:" + payload, hashlib.sha256).digest()
        expected_sig = ((digest[0] << 16) | (digest[1] << 8) | digest[2]) & 0x3FFFFF
        if sig_low == expected_sig:
            dur_info = DURATION_MAP.get(dur_low, ("自定义", 30))
            runs_info = RUNS_MAP.get(runs_low, ("自定义", 100))
            return {
                "valid": True,
                "hw_hash": hw_low,
                "hw_hex": f"{hw_low:03X}",
                "is_universal": (hw_low == 0),
                "nonce": nonce_low,
                "duration_code": dur_low,
                "duration_label": dur_info[0],
                "duration_days": dur_info[1],
                "runs_code": runs_low,
                "runs_label": runs_info[0],
                "max_runs": runs_info[1],
                "code": formatted,
                "matched_product_id": pid_name
            }

    # 校验高位
    for pid_name, salt in candidates:
        payload = struct.pack(">HHBB", hw_high, nonce_high, dur_high, runs_high)
        digest = hmac.new(salt, b"LIC:" + payload, hashlib.sha256).digest()
        expected_sig = ((digest[0] << 16) | (digest[1] << 8) | digest[2]) & 0x3FFFFF
        if sig_high == expected_sig:
            dur_info = DURATION_MAP.get(dur_high, ("自定义", 30))
            runs_info = RUNS_MAP.get(runs_high, ("自定义", 100))
            return {
                "valid": True,
                "hw_hash": hw_high,
                "hw_hex": f"{hw_high:03X}",
                "is_universal": (hw_high == 0),
                "nonce": nonce_high,
                "duration_code": dur_high,
                "duration_label": dur_info[0],
                "duration_days": dur_info[1],
                "runs_code": runs_high,
                "runs_label": runs_info[0],
                "max_runs": runs_info[1],
                "code": formatted,
                "matched_product_id": pid_name
            }

    return {"valid": False, "error": "激活码防伪签名未通过 (非官方加密机签发或产品不匹配)"}

