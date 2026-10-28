// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'fcm_token_refresh_provider.dart';

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning
/// The provider that handles the Firebase device token refresh. Whenever the
/// token is refreshed by the operating system, the new token will be sent to
/// the server.

@ProviderFor(fcmTokenRefresh)
final fcmTokenRefreshProvider = FcmTokenRefreshProvider._();

/// The provider that handles the Firebase device token refresh. Whenever the
/// token is refreshed by the operating system, the new token will be sent to
/// the server.

final class FcmTokenRefreshProvider
    extends $FunctionalProvider<void, void, void>
    with $Provider<void> {
  /// The provider that handles the Firebase device token refresh. Whenever the
  /// token is refreshed by the operating system, the new token will be sent to
  /// the server.
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

String _$fcmTokenRefreshHash() => r'1d3d8c409aa2e174b4a5505737531a9f085adbd3';
