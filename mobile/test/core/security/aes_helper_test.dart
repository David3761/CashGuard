import 'dart:convert';

import 'package:cashctrl/core/security/aes_helper.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  /// The in-memory secure storage used by the helper under test.
  late Map<String, String> storedValues;

  /// Returns a new [AESHelper] that uses [storedValues] as secure storage.
  AESHelper createHelper() {
    return AESHelper.withStorage(const FlutterSecureStorage());
  }

  setUp(() {
    storedValues = {};
    FlutterSecureStorage.setMockInitialValues(storedValues);
  });

  test('decrypt returns the text given to encrypt', () async {
    final helper = createHelper();

    final encrypted = await helper.encrypt('my secret password');

    expect(encrypted, isNot(contains('my secret password')));
    expect(await helper.decrypt(encrypted), 'my secret password');
  });

  test('encrypt uses a new random IV every time', () async {
    final helper = createHelper();

    final first = await helper.encrypt('same text');
    final second = await helper.encrypt('same text');

    expect(first, isNot(second));
    // The 12 byte IV is prepended to the cipher text.
    expect(
      base64.decode(first).sublist(0, 12),
      isNot(base64.decode(second).sublist(0, 12)),
    );
  });

  test('the key is random and kept in the secure storage', () async {
    final encrypted = await createHelper().encrypt('text');

    final key = storedValues[AESHelper.keyStorageName];
    expect(key, isNotNull);
    expect(base64.decode(key!), hasLength(32));
    // A new helper (e.g.: after the app restarts) reads the same key.
    expect(await createHelper().decrypt(encrypted), 'text');
  });

  test('decrypt fails with a different key', () async {
    final encrypted = await createHelper().encrypt('text');

    // Another install generates its own key.
    FlutterSecureStorage.setMockInitialValues({});

    await expectLater(createHelper().decrypt(encrypted), throwsException);
  });

  test('decrypt fails when the cipher text was tampered with', () async {
    final helper = createHelper();
    final bytes = base64.decode(await helper.encrypt('pay 10 lei'));
    bytes[bytes.length - 1] ^= 1;

    await expectLater(helper.decrypt(base64.encode(bytes)), throwsException);
  });

  test('decrypt rejects a text that is too short', () async {
    await expectLater(
      createHelper().decrypt(base64.encode([1, 2, 3])),
      throwsFormatException,
    );
  });
}
