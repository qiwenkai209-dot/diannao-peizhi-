import 'dart:convert';
import 'dart:typed_data';
import 'package:crypto/crypto.dart';

/// 字符集 (排除容易混淆的 0, 1, I, O)
const String kLicenseCharset = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ';
final Map<String, int> kLicenseCharToVal = {
  for (var i = 0; i < kLicenseCharset.length; i++) kLicenseCharset[i]: i
};

// ==============================================================================
// 1. 2026 展馆控制终端专属商业授权算法引擎 (Exhibit Control Terminal 2026 Pro)
//    与 gwc_license_terminal.py 100% 互通
// ==============================================================================
class TerminalLicenseCore {
  static final List<int> terminalHmacSalt =
      utf8.encode('Exhibit_Control_Terminal_Pro_Engine_2026_Secure_Salt_Key!');

  // 40 位置换表 (用于 8 位申请码)
  static const List<int> perm40 = [
    19, 7, 31, 15, 3, 27, 11, 35, 0, 23, 8, 32, 16, 4, 28, 12,
    36, 1, 20, 9, 33, 17, 5, 29, 13, 37, 2, 21, 10, 34, 18, 6,
    30, 14, 38, 25, 26, 24, 22, 39
  ];

  static int calcReqHmac(int hwHash, int nonce) {
    final payload = ByteData(4)
      ..setUint16(0, hwHash & 0xFFFF, Endian.big)
      ..setUint16(2, nonce & 0x0FFF, Endian.big);
    final toSign = <int>[...utf8.encode('TERM_REQ:'), ...payload.buffer.asUint8List()];
    final dig = Hmac(sha256, terminalHmacSalt).convert(toSign).bytes;
    return ((dig[0] << 8) | dig[1]) & 0x0FFF;
  }

  static int calcActHmacExt(int hwHash, int nonce, int mode, int val14) {
    final payload = ByteData(7)
      ..setUint16(0, hwHash & 0xFFFF, Endian.big)
      ..setUint16(2, nonce & 0x0FFF, Endian.big)
      ..setUint8(4, mode & 0x03)
      ..setUint16(5, val14 & 0x3FFF, Endian.big);
    final toSign = <int>[...utf8.encode('TERM_ACT_EXT:'), ...payload.buffer.asUint8List()];
    final dig = Hmac(sha256, terminalHmacSalt).convert(toSign).bytes;
    final raw24 = (dig[0] << 16) | (dig[1] << 8) | dig[2];
    return raw24 & 0xFFFFF;
  }

  /// 解码并验证 8 位终端申请码 (XXXX-XXXX)
  static Map<String, dynamic> decodeRequestCode(String codeStr) {
    final clean = codeStr.toUpperCase().replaceAll(RegExp(r'[^23456789ABCDEFGHJKLMNPQRSTUVWXYZ]'), '');
    if (clean.length != 8) {
      return {'valid': false, 'error': '申请码必须为 8 位字符 (如: XXXX-XXXX)'};
    }

    var val40 = BigInt.zero;
    for (var i = 0; i < clean.length; i++) {
      val40 = (val40 << 5) | BigInt.from(kLicenseCharToVal[clean[i]]!);
    }

    // 逆置换
    var origVal = BigInt.zero;
    for (var newPos = 0; newPos < perm40.length; newPos++) {
      final oldPos = perm40[newPos];
      final bit = (val40 >> newPos) & BigInt.one;
      origVal |= (bit << oldPos);
    }

    final chk = (origVal & BigInt.from(0x0FFF)).toInt();
    final nonce = ((origVal >> 12) & BigInt.from(0x0FFF)).toInt();
    final hwHash = ((origVal >> 24) & BigInt.from(0xFFFF)).toInt();

    final expectedChk = calcReqHmac(hwHash, nonce);
    if (chk != expectedChk) {
      return {'valid': false, 'error': '申请码校验和不匹配'};
    }

    final formatted = '${clean.substring(0, 4)}-${clean.substring(4)}';
    return {
      'valid': true,
      'engine': 'terminal',
      'hw_hash': hwHash,
      'nonce': nonce,
      'code': formatted,
    };
  }

  /// 生成 16 位专属商业激活码 (XXXX-XXXX-XXXX-XXXX)
  /// authType: "permanent" | "hour" | "month"
  static String generateTerminalLicense(
    int hwHash,
    int nonce, {
    String authType = 'permanent',
    int customVal = 1,
  }) {
    final type = authType.toLowerCase();
    int mode;
    int val14;

    if (type.startsWith('h')) {
      mode = 1; // MODE_CUSTOM_HOUR
      val14 = customVal.clamp(1, 16383);
    } else if (type.startsWith('m')) {
      mode = 2; // MODE_CUSTOM_MONTH
      val14 = customVal.clamp(1, 16383);
    } else {
      mode = 3; // MODE_PERMANENT
      val14 = 0;
    }

    final sig20 = calcActHmacExt(hwHash, nonce, mode, val14);

    final val64 = (BigInt.from(hwHash & 0xFFFF) << 48) |
        (BigInt.from(nonce & 0x0FFF) << 36) |
        (BigInt.from(mode & 0x03) << 34) |
        (BigInt.from(val14 & 0x3FFF) << 20) |
        BigInt.from(sig20 & 0xFFFFF);

    final hdr16 = ((sig20 >> 4) ^
            (hwHash & 0xFFFF) ^
            ((nonce & 0x0FFF) << 4) ^
            ((mode & 0x03) << 14) ^
            (val14 & 0xFFFF)) &
        0xFFFF;

    final val80 = (BigInt.from(hdr16) << 64) | val64;

    final chars = <String>[];
    var v = val80;
    for (var i = 0; i < 16; i++) {
      final idx = (v & BigInt.from(0x1F)).toInt();
      chars.add(kLicenseCharset[idx]);
      v >>= 5;
    }
    final rev = chars.reversed.toList();
    return '${rev.sublist(0, 4).join()}-${rev.sublist(4, 8).join()}-${rev.sublist(8, 12).join()}-${rev.sublist(12, 16).join()}';
  }
}

// ==============================================================================
// 2. 原版通用 VisualCast 商业授权算法核心 (Universal License Core)
//    与 universal_license_core.py 100% 互通
// ==============================================================================
class UniversalLicenseCore {
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

  /// 解码并验证 8 位申请码
  static Map<String, dynamic> decodeRequestCode(String codeStr,
      {String productId = ''}) {
    final clean =
        codeStr.toUpperCase().replaceAll(RegExp(r'[^23456789ABCDEFGHJKLMNPQRSTUVWXYZ]'), '');
    if (clean.length != 8) {
      return {'valid': false, 'error': '申请码必须为 8 位字符'};
    }

    final formattedCode = '${clean.substring(0, 4)}-${clean.substring(4)}';

    // 低位优先排布
    var numLow = BigInt.zero;
    for (var i = 0; i < clean.length; i++) {
      final val = BigInt.from(kLicenseCharToVal[clean[i]]!);
      numLow |= (val << (i * 5));
    }
    final unshuffledLow = _permuteBitsBigInt(numLow, unshuffleP40);
    final hwLow = ((unshuffledLow >> 28) & BigInt.from(0x0FFF)).toInt();
    final nonceLow = ((unshuffledLow >> 12) & BigInt.from(0xFFFF)).toInt();
    final checksumLow = (unshuffledLow & BigInt.from(0x0FFF)).toInt();

    // 高位优先排布
    var numHigh = BigInt.zero;
    for (var i = 0; i < clean.length; i++) {
      final val = BigInt.from(kLicenseCharToVal[clean[i]]!);
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
          'engine': 'universal',
          'hw_hash': hwLow,
          'nonce': nonceLow,
          'code': formattedCode,
          'product_id': entry.key,
        };
      }
      if (checksumHigh ==
          calcReqChecksumWithSalt(hwHigh, nonceHigh, entry.value)) {
        return {
          'valid': true,
          'engine': 'universal',
          'hw_hash': hwHigh,
          'nonce': nonceHigh,
          'code': formattedCode,
          'product_id': entry.key,
        };
      }
    }

    return {'valid': false, 'error': '申请码校验和不匹配'};
  }

  /// 签发 12 位一次性商业授权激活码 (XXXX-XXXX-XXXX)
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
      chars.add(kLicenseCharset[idx]);
      tmp >>= 5;
    }

    final s = chars.join('');
    return '${s.substring(0, 4)}-${s.substring(4, 8)}-${s.substring(8)}';
  }
}

// ==============================================================================
// 3. 统一双模商业授权调度中枢 (LicenseManager)
//    自适应识别 2026 控制终端算法与原版通用算法
// ==============================================================================
class LicenseManager {
  /// 自动探测并解码 8 位设备申请码
  static Map<String, dynamic> decodeRequestCode(String codeStr) {
    final reg = RegExp(r'([23456789ABCDEFGHJKLMNPQRSTUVWXYZ]{4})[-_\s]?([23456789ABCDEFGHJKLMNPQRSTUVWXYZ]{4})');
    final match = reg.firstMatch(codeStr.toUpperCase());
    final clean = match != null
        ? '${match.group(1)}${match.group(2)}'
        : codeStr.toUpperCase().replaceAll(RegExp(r'[^23456789ABCDEFGHJKLMNPQRSTUVWXYZ]'), '');

    if (clean.length != 8) {
      return {
        'valid': false,
        'error': '申请码必须为 8 位有效字符，当前为 ${clean.length} 位'
      };
    }

    // 1. 优先尝试 2026 展馆控制终端专属算法体系
    final decTerm = TerminalLicenseCore.decodeRequestCode(clean);
    if (decTerm['valid'] == true) {
      return decTerm;
    }

    // 2. 备用尝试原版通用 VisualCast 算法体系
    final decUniv = UniversalLicenseCore.decodeRequestCode(clean);
    if (decUniv['valid'] == true) {
      return decUniv;
    }

    return {
      'valid': false,
      'error': '申请码防伪校验未通过 (非本系统有效申请码，请核对输入)',
    };
  }

  /// 根据解码信息与授权模式，签发受控端能够正确激活的商业授权码
  /// authType: "permanent" | "hour" | "month"
  static String generateLicense(
    Map<String, dynamic> decodedReq, {
    String authType = 'permanent',
    int customVal = 1,
  }) {
    final engine = decodedReq['engine'] ?? 'terminal';
    final hwHash = decodedReq['hw_hash'] as int;
    final nonce = decodedReq['nonce'] as int;

    if (engine == 'terminal') {
      // 签发 2026 专属 16 位激活码 (XXXX-XXXX-XXXX-XXXX)
      return TerminalLicenseCore.generateTerminalLicense(
        hwHash,
        nonce,
        authType: authType,
        customVal: customVal,
      );
    } else {
      // 签发原版通用 12 位激活码 (XXXX-XXXX-XXXX)
      return UniversalLicenseCore.encodeLicense(
        hwHash,
        nonce,
        31, // 永久
        31, // 无限制
        productId: 'VisualCast',
      );
    }
  }
}
