// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'fcm_token_refresh_provider.dart';

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning
/// The provider that sends the Firebase device token to the server when the
/// app starts and whenever the token is refreshed by the operating system.

@ProviderFor(fcmTokenRefresh)
final fcmTokenRefreshProvider = FcmTokenRefreshProvider._();

/// The provider that sends the Firebase device token to the server when the
/// app starts and whenever the token is refreshed by the operating system.

final class FcmTokenRefreshProvider
    extends $FunctionalProvider<void, void, void>
    with $Provider<void> {
  /// The provider that sends the Firebase device token to the server when the
  /// app starts and whenever the token is refreshed by the operating system.
  FcmTokenRefreshProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'fcmTokenRefreshProvider',
        isAutoDispose: true,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$fcmTokenRefreshHash();

  @$internal
  @override
  $ProviderElement<void> $createElement($ProviderPointer pointer) =>
      $ProviderElement(pointer);

  @override
  void create(Ref ref) {
    return fcmTokenRefresh(ref);
  }

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(void value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<void>(value),
    );
  }
}

String _$fcmTokenRefreshHash() => r'536a40495b45cc8f2a22a2bf9bc0e49e5b4c73d1';
