import 'dart:async';

import 'package:cashctrl/core/models/user.dart';
import 'package:cashctrl/core/repositories/user_repository.dart';
import 'package:cashctrl/core/response/request_response.dart';
import 'package:cashctrl/core/utils/logging.dart';
import 'package:cashctrl/exceptions.dart';
import 'package:cashctrl/main_providers.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

// Necessary for code-generation to work
// Run: dart run build_runner watch
part 'user_provider.g.dart';

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
@riverpod
class UserData extends _$UserData {
  @override
  Future<User?> build() async {
    final isUserLoggedIn = await ref.watch(authProvider.future);

    // If no user is logged in, there's no need to execute any requests.
    if (!isUserLoggedIn) {
      return null;
    }

    try {
      final json = await ref.watch(userRepositoryProvider).getUserFromServer();

      if (json['status'] != 'ok') {
        final data = RequestResponse.fromJson(json);
        throw UIException.serverError(data.message);
      }

      return User.fromJson(json);
      // If you plan to take the user from the database, you'll have something
      // like this set up:
      // - the build() returns the User from the database (Future or Stream),
      // depending on use case and preference (similar to the commented code
      // that you see above this class)
      // - you would have a method that returns the user from the server;
      // similar to this, but you need to save the user in the local database
      // after the request is done. If you're using a Stream, then don't change
      // the state and don't do anything else. If you're using a Future, you
      // can may call ref.invalidateSelf() to trigger the build method.
    } on Exception catch (e, stackTrace) {
      unawaited(logException(e, stackTrace: stackTrace));
    }

    return null;

    // In case you're saving the user locally, you need to use either the code
    // below or create a method that returns Stream in the drift database file.
    // The latter will provide a reactive stream that you can listen (i.e.:
    // provide live updates).
    //
    // return ref
    //     .read(userRepositoryProvider)
    //     .getLoggedIn()
    //     .then((user) => user ?? User());
  }

  /// Updates the provider's [state] with the given value.
  void updateState(User user) {
    state = .data(user);
  }
}
