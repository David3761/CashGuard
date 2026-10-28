// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'user_provider.dart';

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning
/// The provider that stores the data of the currently logged in user or an
/// empty [User] instance.
/*@riverpod
Future<User> userData(Ref ref) async {
  // You can make it always return User if you're sure that the provider won't
  // be called with nullable data. Otherwise, you may leave it as is, or change
  // it so it returns User? and when you'll use it, you can force unwrap it.
  return ref.watch(userRepositoryProvider).getLoggedIn().then(
        (user) => user ?? User(),
      );
}*/
/// The provider that stores the data of the currently logged in user, or null
/// if no users are logged in.

@ProviderFor(UserData)
final userDataProvider = UserDataProvider._();

/// The provider that stores the data of the currently logged in user or an
/// empty [User] instance.
/*@riverpod
Future<User> userData(Ref ref) async {
  // You can make it always return User if you're sure that the provider won't
  // be called with nullable data. Otherwise, you may leave it as is, or change
  // it so it returns User? and when you'll use it, you can force unwrap it.
  return ref.watch(userRepositoryProvider).getLoggedIn().then(
        (user) => user ?? User(),
      );
}*/
/// The provider that stores the data of the currently logged in user, or null
/// if no users are logged in.
final class UserDataProvider extends $AsyncNotifierProvider<UserData, User?> {
  /// The provider that stores the data of the currently logged in user or an
  /// empty [User] instance.
  /*@riverpod
Future<User> userData(Ref ref) async {
  // You can make it always return User if you're sure that the provider won't
  // be called with nullable data. Otherwise, you may leave it as is, or change
  // it so it returns User? and when you'll use it, you can force unwrap it.
  return ref.watch(userRepositoryProvider).getLoggedIn().then(
        (user) => user ?? User(),
      );
}*/
  /// The provider that stores the data of the currently logged in user, or null
  /// if no users are logged in.
  UserDataProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'userDataProvider',
        isAutoDispose: true,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$userDataHash();

  @$internal
  @override
  UserData create() => UserData();
}

String _$userDataHash() => r'0adbcfc5bc5484d69ed27d87bfd283745539f65a';

/// The provider that stores the data of the currently logged in user or an
/// empty [User] instance.
/*@riverpod
Future<User> userData(Ref ref) async {
  // You can make it always return User if you're sure that the provider won't
  // be called with nullable data. Otherwise, you may leave it as is, or change
  // it so it returns User? and when you'll use it, you can force unwrap it.
  return ref.watch(userRepositoryProvider).getLoggedIn().then(
        (user) => user ?? User(),
      );
}*/
/// The provider that stores the data of the currently logged in user, or null
/// if no users are logged in.

abstract class _$UserData extends $AsyncNotifier<User?> {
  FutureOr<User?> build();
  @$mustCallSuper
  @override
  WhenComplete runBuild() {
    final ref = this.ref as $Ref<AsyncValue<User?>, User?>;
    final element =
        ref.element
            as $ClassProviderElement<
              AnyNotifier<AsyncValue<User?>, User?>,
              AsyncValue<User?>,
              Object?,
              Object?
            >;
    return element.handleCreate(ref, build);
  }
}
