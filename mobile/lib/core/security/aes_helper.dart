import 'dart:convert';
import 'dart:typed_data';

import 'package:encrypt/encrypt.dart';
import 'package:flutter/foundation.dart' show visibleForTesting;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// A utility class that provides methods for encrypting and decrypting text.
///
/// The text is encrypted with AES-256/GCM, which also authenticates it: a
/// cipher text that was tampered with fails to decrypt instead of returning
/// altered text.
///
/// - **Key:** 256 random bits, generated with a cryptographically secure
///   generator the first time the key is needed, then kept with
///   [FlutterSecureStorage] (the Keychain on iOS, a key wrapped by the Android
///   Keystore on Android). The key is never part of the source code or of the
///   app's binary.
/// - **IV (nonce):** 96 new random bits for every encryption, prepended to the
///   cipher text, so encrypting the same text twice gives different results.
///
/// The encrypted text is the Base64 of `IV (12 bytes) | cipher text | tag
/// (16 bytes)`.
class AESHelper {
  AESHelper._(this._storage);

  /// Creates an [AESHelper] that keeps its key in the given [storage]. Use
  /// [instance] in the app.
  @visibleForTesting
  AESHelper.withStorage(FlutterSecureStorage storage) : this._(storage);

  /// Returns the singleton instance of this class.
  static final instance = AESHelper._(const FlutterSecureStorage());

  /// The name the key is saved under in the secure storage.
  @visibleForTesting
  static const keyStorageName = 'aes_helper_key';

  /// The length of the key, in bytes (AES-256).
  static const _keyLength = 32;

  /// The length of the IV, in bytes. 12 bytes is the size recommended for GCM.
  static const _ivLength = 12;

  /// The length of the GCM authentication tag, in bytes.
  static const _tagLength = 16;

  /// The storage the key is kept in.
  final FlutterSecureStorage _storage;

  /// The encrypter, created once the key is read from the [_storage].
  Future<Encrypter>? _encrypterFuture;

  /// Returns an encrypter object configured with the AES/GCM protocol and the
  /// key from the secure storage. The key is generated the first time.
  Future<Encrypter> get _encrypter => _encrypterFuture ??= _createEncrypter();

  /// Creates the encrypter returned by [_encrypter].
  Future<Encrypter> _createEncrypter() async {
    try {
      final key = await _readOrCreateKey();
      return Encrypter(AES(key, mode: .gcm));
    } on Exception {
      // Lets the next call try again (e.g.: the keystore was locked).
      _encrypterFuture = null;
      rethrow;
    }
  }

  /// Returns the key from the secure storage. If there's none, a random key is
  /// generated and saved first.
  Future<Key> _readOrCreateKey() async {
    final storedKey = await _storage.read(key: keyStorageName);
    if (storedKey != null) {
      return Key.fromBase64(storedKey);
    }
    final key = Key.fromSecureRandom(_keyLength);
    await _storage.write(key: keyStorageName, value: key.base64);
    return key;
  }

  /// Encrypts the given [plainText] using the AES/GCM protocol and a new
  /// random IV. Check the class's documentation for more info.
  Future<String> encrypt(String plainText) async {
    final encrypter = await _encrypter;
    final iv = IV.fromSecureRandom(_ivLength);
    final encrypted = encrypter.encrypt(plainText, iv: iv);
    return base64.encode([...iv.bytes, ...encrypted.bytes]);
  }

  /// Decrypts the given [encrypted] text, returned by [encrypt], using the
  /// AES/GCM protocol. Check the class's documentation for more info.
  ///
  /// Throws a [FormatException] if [encrypted] isn't a text returned by
  /// [encrypt], or an `InvalidCipherTextException` if it was tampered with or
  /// it was encrypted with another key.
  Future<String> decrypt(String encrypted) async {
    final bytes = base64.decode(encrypted);
    if (bytes.length < _ivLength + _tagLength) {
      throw const FormatException('The encrypted text is too short.');
    }
    final encrypter = await _encrypter;
    final iv = IV(Uint8List.sublistView(bytes, 0, _ivLength));
    final cipherText = Encrypted(Uint8List.sublistView(bytes, _ivLength));
    return encrypter.decrypt(cipherText, iv: iv);
  }
}
