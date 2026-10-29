// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'main_providers.dart';

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning
/// The provider that performs any initializations prior to app opening.
/// A new "splash screen" will continue to be displayed following the default
/// OS splash screen.
///
/// This provider was inspired from:
/// https://codewithandrea.com/articles/robust-app-initialization-riverpod/

@ProviderFor(appStartup)
final appStartupProvider = AppStartupProvider._();

/// The provider that performs any initializations prior to app opening.
/// A new "splash screen" will continue to be displayed following the default
/// OS splash screen.
///
/// This provider was inspired from:
/// https://codewithandrea.com/articles/robust-app-initialization-riverpod/

final class AppStartupProvider
    extends $FunctionalProvider<AsyncValue<void>, void, FutureOr<void>>
    with $FutureModifier<void>, $FutureProvider<void> {
  /// The provider that performs any initializations prior to app opening.
  /// A new "splash screen" will continue to be displayed following the default
  /// OS splash screen.
  ///
  /// This provider was inspired from:
  /// https://codewithandrea.com/articles/robust-app-initialization-riverpod/
  AppStartupProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'appStartupProvider',
        isAutoDispose: true,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$appStartupHash();

  @$internal
  @override
  $FutureProviderElement<void> $createElement($ProviderPointer pointer) =>
      $FutureProviderElement(pointer);

  @override
  FutureOr<void> create(Ref ref) {
    return appStartup(ref);
  }
}

String _$appStartupHash() => r'764c368933e82271e2d4cfb606769cfd381b8597';

/// The provider that knows whether the user is logged in or not.
///
/// The code you put in here should be easy, simple and quick to execute.
/// Don't fetch the user from the server and don't do any other expensive
/// calculations, since this provider is used by the [routerProvider] to
/// figure out whether to show the login screen or not. Failing to do so, will
/// make the UI stay in an awkward screen while the app figures out whether the
/// user is logged in or not.
///
/// If you need access to the user's data, use the [userDataProvider] instead.

@ProviderFor(Auth)
final authProvider = AuthProvider._();

/// The provider that knows whether the user is logged in or not.
///
/// The code you put in here should be easy, simple and quick to execute.
/// Don't fetch the user from the server and don't do any other expensive
/// calculations, since this provider is used by the [routerProvider] to
/// figure out whether to show the login screen or not. Failing to do so, will
/// make the UI stay in an awkward screen while the app figures out whether the
/// user is logged in or not.
///
/// If you need access to the user's data, use the [userDataProvider] instead.
final class AuthProvider extends $AsyncNotifierProvider<Auth, bool> {
  /// The provider that knows whether the user is logged in or not.
  ///
  /// The code you put in here should be easy, simple and quick to execute.
  /// Don't fetch the user from the server and don't do any other expensive
  /// calculations, since this provider is used by the [routerProvider] to
  /// figure out whether to show the login screen or not. Failing to do so, will
  /// make the UI stay in an awkward screen while the app figures out whether the
  /// user is logged in or not.
  ///
  /// If you need access to the user's data, use the [userDataProvider] instead.
  AuthProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'authProvider',
        isAutoDispose: true,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$authHash();

  @$internal
  @override
  Auth create() => Auth();
}

String _$authHash() => r'13ad8e9efe58c5a6a5a6824edda317b05b3b9ba7';

/// The provider that knows whether the user is logged in or not.
///
/// The code you put in here should be easy, simple and quick to execute.
/// Don't fetch the user from the server and don't do any other expensive
/// calculations, since this provider is used by the [routerProvider] to
/// figure out whether to show the login screen or not. Failing to do so, will
/// make the UI stay in an awkward screen while the app figures out whether the
/// user is logged in or not.
///
/// If you need access to the user's data, use the [userDataProvider] instead.

abstract class _$Auth extends $AsyncNotifier<bool> {
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

/// The provider that is in charge with the app routing. Basically, every
/// navigation is done through the `GoRouter`, by using this provider.
///
/// This provider uses the [authProvider] to figure out whether the user is
/// logged in or not.

@ProviderFor(Router)
final routerProvider = RouterProvider._();

/// The provider that is in charge with the app routing. Basically, every
/// navigation is done through the `GoRouter`, by using this provider.
///
/// This provider uses the [authProvider] to figure out whether the user is
/// logged in or not.
final class RouterProvider extends $NotifierProvider<Router, GoRouter> {
  /// The provider that is in charge with the app routing. Basically, every
  /// navigation is done through the `GoRouter`, by using this provider.
  ///
  /// This provider uses the [authProvider] to figure out whether the user is
  /// logged in or not.
  RouterProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'routerProvider',
        isAutoDispose: true,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$routerHash();

  @$internal
  @override
  Router create() => Router();

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(GoRouter value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<GoRouter>(value),
    );
  }
}

String _$routerHash() => r'669c0f81755329fc2ab57ba9577c8ee003c2de44';

/// The provider that is in charge with the app routing. Basically, every
/// navigation is done through the `GoRouter`, by using this provider.
///
/// This provider uses the [authProvider] to figure out whether the user is
/// logged in or not.

abstract class _$Router extends $Notifier<GoRouter> {
  GoRouter build();
  @$mustCallSuper
  @override
  WhenComplete runBuild() {
    final ref = this.ref as $Ref<GoRouter, GoRouter>;
    final element =
        ref.element
            as $ClassProviderElement<
              AnyNotifier<GoRouter, GoRouter>,
              GoRouter,
              Object?,
              Object?
            >;
    return element.handleCreate(ref, build);
  }
}

/// The provider that is aware of changes in internet connection. When you
/// want to check if you the device has an active internet connection, you may
/// use this provider.

@ProviderFor(InternetConnection)
final internetConnectionProvider = InternetConnectionProvider._();

/// The provider that is aware of changes in internet connection. When you
/// want to check if you the device has an active internet connection, you may
/// use this provider.
final class InternetConnectionProvider
    extends $NotifierProvider<InternetConnection, bool> {
  /// The provider that is aware of changes in internet connection. When you
  /// want to check if you the device has an active internet connection, you may
  /// use this provider.
  InternetConnectionProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'internetConnectionProvider',
        isAutoDispose: true,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$internetConnectionHash();

  @$internal
  @override
  InternetConnection create() => InternetConnection();

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(bool value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<bool>(value),
    );
  }
}

String _$internetConnectionHash() =>
    r'c2f40c06347bca8ba38da80e4ea2f02171c2ff0a';

/// The provider that is aware of changes in internet connection. When you
/// want to check if you the device has an active internet connection, you may
/// use this provider.

abstract class _$InternetConnection extends $Notifier<bool> {
  bool build();
  @$mustCallSuper
  @override
  WhenComplete runBuild() {
    final ref = this.ref as $Ref<bool, bool>;
    final element =
        ref.element
            as $ClassProviderElement<
              AnyNotifier<bool, bool>,
              bool,
              Object?,
              Object?
            >;
    return element.handleCreate(ref, build);
  }
}
