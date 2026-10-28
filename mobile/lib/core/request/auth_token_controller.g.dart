// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'auth_token_controller.dart';

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning
/// The provider that returns an instance of `AuthTokenController`.

@ProviderFor(authTokenController)
final authTokenControllerProvider = AuthTokenControllerProvider._();

/// The provider that returns an instance of `AuthTokenController`.

final class AuthTokenControllerProvider
    extends
        $FunctionalProvider<
          AuthTokenController,
          AuthTokenController,
          AuthTokenController
        >
    with $Provider<AuthTokenController> {
  /// The provider that returns an instance of `AuthTokenController`.
  AuthTokenControllerProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'authTokenControllerProvider',
        isAutoDispose: true,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$authTokenControllerHash();

  @$internal
  @override
  $ProviderElement<AuthTokenController> $createElement(
    $ProviderPointer pointer,
  ) => $ProviderElement(pointer);

  @override
  AuthTokenController create(Ref ref) {
    return authTokenController(ref);
  }

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(AuthTokenController value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<AuthTokenController>(value),
    );
  }
}

String _$authTokenControllerHash() =>
    r'5de52ce51e8684517885ee8e5e54ad5a456f7cfb';
