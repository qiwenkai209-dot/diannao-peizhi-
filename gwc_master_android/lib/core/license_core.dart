import 'dart:convert';
import 'dart:typed_data';
import 'package:crypto/crypto.dart';

/// 国文创商业授权算法核心引擎 (Dart 实现，100% 兼容 universal_license_core.py)
class UniversalLicenseCore {
  static const String charset = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ';
  static final Map<String, int> charToVal = {
    for (var i = 0; i < charset.length; i++) charset[i]: i
  };

  static final List<int> defaultGlobalSalt =
      utf8.encode('VisualCast_Universal_Armor_License_v3_2026_Secure!');
  static final List<int> legacyVisualcastSalt =
      utf8.encode('VisualCast_License_Salt_v3_2026_RandomNonceSecure!');

  static const List<int> shuffleP40 = [
    31, 7, 23, 15, 39, 3, 19, 11, 27, 35,
    0, 16, 8, 24, 32, 4, 20, 12, 28, 36,
    1, 17, 9, 25, 33, 5, 21, 13, 29, 37,
    2, 18, 10, 26, 34, 6, 22, 14, 30, 38
  ];

  static late final List<int> unshuffleP40 = () {
    final list = List<int>.filled(40, 0);
    for (var i = 0; i < shuffleP40.length; i++) {
      list[shuffleP40[i]] = i;
    }
    return list;
  }();

  static const List<int> shuffleP60 = [
    13, 50, 27, 4, 41, 18, 55, 32, 9, 46, 23, 0, 37, 14, 51, 28, 5, 42, 19, 56,
    33, 10, 47, 24, 1, 38, 15, 52, 29, 6, 43, 20, 57, 34, 11, 48, 25, 2, 39, 16,
    53, 30, 7, 44, 21, 58, 35, 12, 49, 26, 3, 40, 17, 54, 31, 8, 45, 22, 59, 36
  ];

  static late final List<int> unshuffleP60 = () {
    final list = List<int>.filled(60, 0);
    for (var i = 0; i < shuffleP60.length; i++) {
      list[shuffleP60[i]] = i;
    }
    return list;
  }();

  static List<int> getProductSalt(String productId) {
    if (productId == 'VisualCast_Native' || productId == 'LEGACY_NATIVE') {
      return legacyVisualcastSalt;
    }
    if (productId.isEmpty || productId == 'DEFAULT') {
      return defaultGlobalSalt;
    }
    final toHash = <int>[...defaultGlobalSalt, ...utf8.encode('::$productId')];
    return sha256.convert(toHash).bytes;
  }

  static BigInt _permuteBitsBigInt(BigInt val, List<int> perm) {
    var result = BigInt.zero;
    for (var newPos = 0; newPos < perm.length; newPos++) {
      final oldPos = perm[newPos];
      final bit = (val >> oldPos) & BigInt.one;
      result |= (bit << newPos);
    }
    return result;
  }

  static int calcReqChecksumWithSalt(int hwHash, int nonce, List<int> salt) {
    final payload = ByteData(4)
      ..setUint16(0, hwHash & 0x0FFF, Endian.big)
      ..setUint16(2, nonce & 0xFFFF, Endian.big);
    final toSign = <int>[...utf8.encode('REQ:'), ...payload.buffer.asUint8List()];
    final digest = Hmac(sha256, salt).convert(toSign).bytes;
    final raw = (digest[0] << 8) | digest[1];
    return raw & 0x0FFF;
  }

  /// 解码并验证 8 位申请码 (格式 XXXX-XXXX)
  static Map<String, dynamic> decodeRequestCode(String codeStr,
      {String productId = ''}) {
    final clean =
        codeStr.toUpperCase().replaceAll(RegExp(r'[^23456789ABCDEFGHJKLMNPQRSTUVWXYZ]'), '');
    if (clean.length != 8) {
      return {
        'valid': false,
        'error': '申请码须包含 8 位有效字符，当前为 ${clean.length} 位'
      };
    }

    final formattedCode = '${clean.substring(0, 4)}-${clean.substring(4)}';

    // 低位优先排布
    var numLow = BigInt.zero;
    for (var i = 0; i < clean.length; i++) {
      final val = BigInt.from(charToVal[clean[i]]!);
      numLow |= (val << (i * 5));
    }
    final unshuffledLow = _permuteBitsBigInt(numLow, unshuffleP40);
    final hwLow = ((unshuffledLow >> 28) & BigInt.from(0x0FFF)).toInt();
    final nonceLow = ((unshuffledLow >> 12) & BigInt.from(0xFFFF)).toInt();
    final checksumLow = (unshuffledLow & BigInt.from(0x0FFF)).toInt();

    // 高位优先排布
    var numHigh = BigInt.zero;
    for (var i = 0; i < clean.length; i++) {
      final val = BigInt.from(charToVal[clean[i]]!);
      numHigh = (numHigh << 5) | val;
    }
    final unshuffledHigh = _permuteBitsBigInt(numHigh, unshuffleP40);
    final hwHigh = ((unshuffledHigh >> 28) & BigInt.from(0x0FFF)).toInt();
    final nonceHigh = ((unshuffledHigh >> 12) & BigInt.from(0xFFFF)).toInt();
    final checksumHigh = (unshuffledHigh & BigInt.from(0x0FFF)).toInt();

    final candidates = <MapEntry<String, List<int>>>[
      if (productId.isNotEmpty) MapEntry(productId, getProductSalt(productId)),
      MapEntry('VisualCast', getProductSalt('VisualCast')),
      MapEntry('', defaultGlobalSalt),
      MapEntry('VisualCast_Native', legacyVisualcastSalt),
    ];

    for (final entry in candidates) {
      if (checksumLow == calcReqChecksumWithSalt(hwLow, nonceLow, entry.value)) {
        return {
          'valid': true,
          'hw_hash': hwLow,
          'nonce': nonceLow,
          'code': formattedCode,
          'bit_order': 'low_first',
          'product_id': entry.key,
        };
      }
      if (checksumHigh ==
          calcReqChecksumWithSalt(hwHigh, nonceHigh, entry.value)) {
        return {
          'valid': true,
          'hw_hash': hwHigh,
          'nonce': nonceHigh,
          'code': formattedCode,
          'bit_order': 'high_first',
          'product_id': entry.key,
        };
      }
    }

    return {'valid': false, 'error': '申请码校验和不符或非法'};
  }

  /// 签发 12 位一次性商业授权激活码 (格式: XXXX-XXXX-XXXX)
  /// durationCode: 31 为永久，4 为1个月，8 为1年等
  static String encodeLicense(
    int hwHash,
    int nonce,
    int durationCode,
    int runsCode, {
    String productId = '',
  }) {
    hwHash &= 0x0FFF;
    nonce &= 0xFFFF;
    durationCode &= 0x1F;
    runsCode &= 0x1F;

    final salt = getProductSalt(productId);
    final payload = ByteData(6)
      ..setUint16(0, hwHash, Endian.big)
      ..setUint16(2, nonce, Endian.big)
      ..setUint8(4, durationCode)
      ..setUint8(5, runsCode);

    final toSign = <int>[...utf8.encode('LIC:'), ...payload.buffer.asUint8List()];
    final digest = Hmac(sha256, salt).convert(toSign).bytes;
    final sig = ((digest[0] << 16) | (digest[1] << 8) | digest[2]) & 0x3FFFFF;

    final rawNum = (BigInt.from(hwHash) << 48) |
        (BigInt.from(nonce) << 32) |
        (BigInt.from(durationCode) << 27) |
        (BigInt.from(runsCode) << 22) |
        BigInt.from(sig);

    final shuffled = _permuteBitsBigInt(rawNum, shuffleP60);

    final chars = <String>[];
    var tmp = shuffled;
    for (var i = 0; i < 12; i++) {
      final idx = (tmp & BigInt.from(0x1F)).toInt();
      chars.add(charset[idx]);
      tmp >>= 5;
    }

    final s = chars.join('');
    return '${s.substring(0, 4)}-${s.substring(4, 8)}-${s.substring(8)}';
  }
}
