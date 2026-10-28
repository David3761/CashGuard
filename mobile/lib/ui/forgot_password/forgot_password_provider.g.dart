// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'forgot_password_provider.dart';

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning
/// The forgot password provider that handles the forgot password process.

@ProviderFor(ForgotPassword)
final forgotPasswordProvider = ForgotPasswordProvider._();

/// The forgot password provider that handles the forgot password process.
final class ForgotPasswordProvider
    extends $AsyncNotifierProvider<ForgotPassword, bool> {
  /// The forgot password provider that handles the forgot password process.
  ForgotPasswordProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'forgotPasswordProvider',
        isAutoDispose: true,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$forgotPasswordHash();

  @$internal
  @override
  ForgotPassword create() => ForgotPassword();
}

String _$forgotPasswordHash() => r'acce24bc90a6d441335e464c9cff4b142bbf365a';

/// The forgot password provider that handles the forgot password process.

abstract class _$ForgotPassword extends $AsyncNotifier<bool> {
  FutureOr<bool> build();
  @$mustCallSuper
  @override
  WhenComplete runBuild() {
    final ref = this.ref as $Ref<AsyncValue<bool>, bool>;
    final element =
        ref.element
            as $ClassProviderElement<
              AnyNotifier<AsyncValue<bool>, bool>,
              AsyncValue<bool>,
              Object?,
              Object?
            >;
    return element.handleCreate(ref, build);
  }
}
