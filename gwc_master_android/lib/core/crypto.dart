import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';
import 'package:crypto/crypto.dart';

/// 国文创安全通信加密协议核心 (Dart 实现，100% 兼容 gwc_crypto.py)
class GwcCrypto {
  static final List<int> defaultSalt =
      utf8.encode('VisualCast_Universal_Armor_License_v3_2026_Secure!');
  static const List<int> magicHeader = [0x47, 0x57, 0x43, 0x43]; // 'GWCC'

  /// 使用 HMAC-SHA256 计数器模式派生与数据等长的高强度密钥流
  static Uint8List deriveKeystream(List<int> key, int length) {
    final blocks = <int>[];
    var counter = 0;
    var generated = 0;

    while (generated < length) {
      final counterBytes = ByteData(8)..setUint64(0, counter, Endian.big);
      final hmac = Hmac(sha256, key);
      final digest = hmac.convert(counterBytes.buffer.asUint8List()).bytes;
      blocks.addAll(digest);
      generated += digest.length;
      counter++;
    }

    return Uint8List.fromList(blocks.sublist(0, length));
  }

  /// 对原始字节进行 CTR 异或流加密
  static Uint8List encryptData(List<int> payload, {List<int>? key}) {
    final k = key ?? defaultSalt;
    final keystream = deriveKeystream(k, payload.length);
    final result = Uint8List(payload.length);
    for (var i = 0; i < payload.length; i++) {
      result[i] = payload[i] ^ keystream[i];
    }
    return result;
  }

  /// 对密文字节进行解密 (CTR 模式对称可逆)
  static Uint8List decryptData(List<int> cipher, {List<int>? key}) {
    return encryptData(cipher, key: key);
  }

  /// 封装结构化网络报文
  /// [Magic: 4B] + [Length: 4B] + [Timestamp: 8B] + [Nonce: 4B] + [HMAC-Tag: 16B] + [Ciphertext: N bytes]
  static Uint8List packPacket(String msgType, Map<String, dynamic> dataDict,
      {List<int>? key}) {
    final k = key ?? defaultSalt;
    final ts = DateTime.now().millisecondsSinceEpoch;
    final nonce = Random().nextInt(900000) + 100000;

    final body = {
      'type': msgType,
      'nonce': nonce,
      'ts': ts,
      'payload': dataDict,
    };

    final rawJson = utf8.encode(jsonEncode(body));
    final cipher = encryptData(rawJson, key: k);

    final signHeader = ByteData(12)
      ..setUint64(0, ts, Endian.big)
      ..setUint32(8, nonce, Endian.big);
    final signHeaderBytes = signHeader.buffer.asUint8List();

    final toSign = <int>[...signHeaderBytes, ...cipher];
    final fullTag = Hmac(sha256, k).convert(toSign).bytes;
    final tag = fullTag.sublist(0, 16);

    final totalLen = 8 + 4 + 16 + cipher.length;
    final lenBytes = ByteData(4)..setUint32(0, totalLen, Endian.big);

    final builder = BytesBuilder();
    builder.add(magicHeader);
    builder.add(lenBytes.buffer.asUint8List());
    builder.add(signHeaderBytes);
    builder.add(tag);
    builder.add(cipher);

    return builder.toBytes();
  }

  /// 解析并解密结构化网络报文
  static Map<String, dynamic> unpackPacket(List<int> rawFrame,
      {List<int>? key}) {
    final k = key ?? defaultSalt;

    if (rawFrame.length < 32) {
      throw FormatException('报文长度过短: ${rawFrame.length} 字节');
    }

    for (var i = 0; i < 4; i++) {
      if (rawFrame[i] != magicHeader[i]) {
        throw const FormatException('非法的国文创加密报文标识 (Magic 不匹配)');
      }
    }

    final totalLen = ByteData.sublistView(
      Uint8List.fromList(rawFrame.sublist(4, 8)),
    ).getUint32(0, Endian.big);

    if (rawFrame.length - 8 < totalLen) {
      throw const FormatException('报文未完全接收或数据长度不符');
    }

    final packetBody = rawFrame.sublist(8, 8 + totalLen);
    final signHeader = packetBody.sublist(0, 12);
    final tag = packetBody.sublist(12, 28);
    final cipher = packetBody.sublist(28);

    final toSign = <int>[...signHeader, ...cipher];
    final expectedTag =
        Hmac(sha256, k).convert(toSign).bytes.sublist(0, 16);

    // 常数时间比对防时序攻击
    var diff = 0;
    for (var i = 0; i < 16; i++) {
      diff |= tag[i] ^ expectedTag[i];
    }
    if (diff != 0) {
      throw const FormatException('报文 HMAC 签名校验失败，数据可能被篡改或密钥错误！');
    }

    final decJson = decryptData(cipher, key: k);
    final jsonStr = utf8.decode(decJson);
    return jsonDecode(jsonStr) as Map<String, dynamic>;
  }
}
