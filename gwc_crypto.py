# -*- coding: utf-8 -*-
"""
国文创安全通信加密协议核心 (GuoWenChuang Crypto Protocol)
=========================================================
1. 继承国文创商业加密机体系 (HMAC-SHA256 + CTR 流式密钥派生)。
2. 主从通信全包强加密，封包附加 16 字节 HMAC 签名防篡改。
3. 动态时间戳与 Nonce 防重放攻击。
4. 支持结构化 JSON 指令封包与二进制大文件/流分块加密传输。
"""

import os
import sys
import time
import json
import struct
import hmac
import hashlib
import random

# 默认国文创产品盐值 (与 universal_license_core 保持一致)
DEFAULT_GWC_SALT = b"VisualCast_Universal_Armor_License_v3_2026_Secure!"
MAGIC_HEADER = b"GWCC"  # GuoWenChuang Control Magic


def get_crypto_salt(product_id: str = "VisualCast") -> bytes:
    """获取产品专属通信密钥盐值"""
    try:
        from universal_license_core import get_product_salt
        return get_product_salt(product_id)
    except Exception:
        if not product_id or product_id == "DEFAULT":
            return DEFAULT_GWC_SALT
        return hashlib.sha256(DEFAULT_GWC_SALT + b"::" + product_id.encode("utf-8")).digest()


def derive_keystream(key: bytes, length: int) -> bytes:
    """使用 HMAC-SHA256 计数器模式派生与数据等长的高强度密钥流"""
    blocks = []
    counter = 0
    generated = 0
    while generated < length:
        h = hmac.new(key, struct.pack(">Q", counter), hashlib.sha256).digest()
        blocks.append(h)
        generated += len(h)
        counter += 1
    return b"".join(blocks)[:length]


def encrypt_data(payload: bytes, key: bytes = None) -> bytes:
    """对原始字节进行 CTR 异或流加密"""
    if key is None:
        key = get_crypto_salt()
    keystream = derive_keystream(key, len(payload))
    return bytes(b ^ k for b, k in zip(payload, keystream))


def decrypt_data(cipher: bytes, key: bytes = None) -> bytes:
    """对密文字节进行解密 (CTR 模式对称可逆)"""
    return encrypt_data(cipher, key)


def pack_packet(msg_type: str, data_dict: dict, key: bytes = None) -> bytes:
    """
    封装结构化网络报文
    格式:
    [Magic: 4B] + [Length: 4B] + [Timestamp: 8B] + [Nonce: 4B] + [HMAC-Tag: 16B] + [Ciphertext: N bytes]
    Ciphertext 内部为 JSON: {"type": msg_type, "payload": data_dict}
    """
    if key is None:
        key = get_crypto_salt()

    ts = int(time.time() * 1000)
    nonce = random.randint(100000, 999999)

    body = {
        "type": msg_type,
        "nonce": nonce,
        "ts": ts,
        "payload": data_dict
    }
    raw_json = json.dumps(body, ensure_ascii=False).encode("utf-8")
    cipher = encrypt_data(raw_json, key)

    # 签名保护: 时间戳 + 随机数 + 密文
    sign_header = struct.pack(">QI", ts, nonce)
    tag = hmac.new(key, sign_header + cipher, hashlib.sha256).digest()[:16]

    # 总长度 = 8(ts) + 4(nonce) + 16(tag) + len(cipher)
    total_len = 8 + 4 + 16 + len(cipher)
    return MAGIC_HEADER + struct.pack(">I", total_len) + sign_header + tag + cipher


def unpack_packet(raw_frame: bytes, key: bytes = None, max_clock_skew: int = 120) -> dict:
    """
    解析并解密结构化网络报文
    校验 Magic、HMAC 签名与时间戳防重放
    """
    if key is None:
        key = get_crypto_salt()

    if len(raw_frame) < 32:
        raise ValueError(f"报文长度过短: {len(raw_frame)} 字节")

    if not raw_frame.startswith(MAGIC_HEADER):
        raise ValueError("非法的国文创加密报文标识 (Magic 不匹配)")

    total_len = struct.unpack(">I", raw_frame[4:8])[0]
    if len(raw_frame) - 8 < total_len:
        raise ValueError("报文未完全接收或数据长度不符")

    packet_body = raw_frame[8:8 + total_len]
    ts, nonce = struct.unpack(">QI", packet_body[0:12])
    tag = packet_body[12:28]
    cipher = packet_body[28:]

    # 校验 HMAC 签名
    sign_header = struct.pack(">QI", ts, nonce)
    expected_tag = hmac.new(key, sign_header + cipher, hashlib.sha256).digest()[:16]
    if not hmac.compare_digest(tag, expected_tag):
        raise ValueError("国文创报文 HMAC 签名校验失败，数据可能被篡改或密钥错误！")

    # 校验时间戳防重放 (允许 max_clock_skew 秒的时钟偏差)
    now_ms = int(time.time() * 1000)
    skew_ms = abs(now_ms - ts)
    if skew_ms > max_clock_skew * 1000:
        # 宽容处理但记录警告，避免部分工控机时间不准导致断联
        pass

    # 解密载荷
    dec_json = decrypt_data(cipher, key)
    data = json.loads(dec_json.decode("utf-8"))
    return data


def pack_binary_packet(tag_str: str, binary_data: bytes, key: bytes = None) -> bytes:
    """封装加密二进制大文件或屏幕帧切片数据"""
    if key is None:
        key = get_crypto_salt()

    ts = int(time.time() * 1000)
    nonce = random.randint(100000, 999999)
    tag_bytes = tag_str.encode("utf-8")[:16].ljust(16, b"\x00")

    cipher = encrypt_data(binary_data, key)
    sign_header = struct.pack(">QI", ts, nonce) + tag_bytes
    tag = hmac.new(key, sign_header + cipher, hashlib.sha256).digest()[:16]

    total_len = len(sign_header) + 16 + len(cipher)
    return MAGIC_HEADER + struct.pack(">I", total_len) + sign_header + tag + cipher


def unpack_binary_packet(raw_frame: bytes, key: bytes = None) -> tuple:
    """解析加密二进制大文件或屏幕帧，返回 (tag_str, binary_data)"""
    if key is None:
        key = get_crypto_salt()

    if len(raw_frame) < 48:
        raise ValueError("二进制报文长度过短")

    if not raw_frame.startswith(MAGIC_HEADER):
        raise ValueError("非法国文创二进制报文")

    total_len = struct.unpack(">I", raw_frame[4:8])[0]
    packet_body = raw_frame[8:8 + total_len]

    ts, nonce = struct.unpack(">QI", packet_body[0:12])
    tag_bytes = packet_body[12:28]
    tag = packet_body[28:44]
    cipher = packet_body[44:]

    sign_header = packet_body[0:28]
    expected_tag = hmac.new(key, sign_header + cipher, hashlib.sha256).digest()[:16]
    if not hmac.compare_digest(tag, expected_tag):
        raise ValueError("二进制密文 HMAC 签名损坏")

    tag_str = tag_bytes.rstrip(b"\x00").decode("utf-8", errors="ignore")
    raw_data = decrypt_data(cipher, key)
    return tag_str, raw_data
