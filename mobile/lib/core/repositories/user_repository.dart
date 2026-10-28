import 'package:cashctrl/core/database/app_database.dart';
import 'package:cashctrl/core/models/auth_details.dart';
import 'package:cashctrl/core/request/api_client.dart';
import 'package:cashctrl/core/request/auth_token_controller.dart';
import 'package:http/http.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

// Necessary for code-generation to work
// Run: dart run build_runner watch
part 'user_repository.g.dart';

/// The provider that returns an instance of [UserRepository].
@riverpod
UserRepository userRepository(Ref ref) => UserRepository._(ref);

/// The Repository for the [User] model. Provides access to both local storage
/// and requests.
class UserRepository {
  UserRepository._(this.ref);

  /// A [Ref] object used to access any providers (such as `ApiService`).
  final Ref ref;

  /// Returns a [Future] that contains the current logged in user or null
  /// otherwise.
  Future<User?> getLoggedIn() {
    return ref.read(appDatabaseProvider).userDao.getLoggedIn();
  }

  /// Inserts the given [user] in the database and saves the [authDetails] in
  /// the SharedPreferences.
  Future<void> insert(User user, {AuthDetails? authDetails}) async {
    await ref.read(appDatabaseProvider).userDao.insert(user);
    if (authDetails != null) {
      await ref.read(authTokenControllerProvider).saveAuthDetails(authDetails);
    }
  }

  /// Updates the key of the current logged in user with the given [key].
  Future<void> updateKey(String key) {
    return ref.read(appDatabaseProvider).userDao.updateKey(key);
  }

  /// Sets the user as logged out in the database and clears the auth details
  /// from the SharedPreferences.
  Future<void> logoutUserLocally() async {
    await ref.read(appDatabaseProvider).userDao.logoutUser();
    await ref.read(authTokenControllerProvider).removeAuthDetails();
  }

  // ---------- REQUESTS ----------

  /// Makes a request to change the password.
  Future<Map<String, dynamic>> changePassword({
    required Map<String, String> body,
  }) {
    return ref.read(apiServiceProvider).changePassword(body);
  }

  /// Makes a request to send a reset password email.
  Future<Map<String, dynamic>> forgotPassword({
    required Map<String, String> body,
  }) {
    return ref.read(apiServiceProvider).forgotPassword(body);
  }

  /// Makes a request to login the user.
  Future<Map<String, dynamic>> login({required Map<String, String> body}) {
    return ref.read(apiServiceProvider).login(body);
  }

  /// Makes a request to register the user.
  Future<Map<String, dynamic>> register({required Map<String, String> body}) {
    return ref.read(apiServiceProvider).register(body);
  }

  /// Makes a request to refresh the auth token based on the given refresh auth
  /// token found in the [body].
  Future<Map<String, dynamic>> refreshAuthToken({
    required Map<String, String> body,
  }) {
    return ref.read(apiServiceProvider).refreshAuthToken(body);
  }

  /// Makes a request to retrieve the user.
  Future<Map<String, dynamic>> getUserFromServer() {
    return ref.read(apiServiceProvider).getUser();
  }

  /// Makes a request to update the user's data.
  Future<Map<String, dynamic>> editUser({
    required Map<String, String> body,
    MultipartFile? photoFile,
  }) {
    return ref.read(apiServiceProvider).editUser(body, photoFile);
  }

  /// Makes a request to send the user's data to their email address.
  Future<Map<String, dynamic>> viewData() {
    return ref.read(apiServiceProvider).viewData();
  }

  /// Makes a request to send a delete confirmation message to the user's
  /// email address.
  Future<Map<String, dynamic>> deleteData() {
    return ref.read(apiServiceProvider).deleteData();
  }
}
