import 'package:encrypt/encrypt.dart';

/// A utility class that provides methods for encrypting and decrypting text.
class AESHelper {
  AESHelper._();

  /// Returns the singleton instance of this class.
  static final instance = AESHelper._();

  static final _key = Key.fromBase64(
    '4FgevxZPz5ePJ82EGb7x2i+9VeblQzUvBDbMGqAVqPc=',
  );
  static final _iv = IV.fromLength(16);

  /// Returns an encrypter object configured with the AES/CBC protocol.
  Encrypter get encrypter {
    return Encrypter(AES(_key, mode: .cbc));
  }

  /// Encrypts the given [plainText] using AES/CBC protocol.
  /// Check the [encrypter] getter for more info.
  String encrypt(String plainText) {
    return encrypter.encrypt(plainText, iv: _iv).base64;
  }

  /// Decrypts the given [encrypted] using AES/CBC protocol.
  /// Check the [encrypter] getter for more info.
  String decrypt(String encrypted) {
    return encrypter.decrypt(Encrypted.fromBase64(encrypted), iv: _iv);
  }
}
