import 'dart:async';

import 'package:cashctrl/core/models/auth_details.dart';
import 'package:cashctrl/core/repositories/user_repository.dart';
import 'package:cashctrl/core/request/api_client.dart';
import 'package:cashctrl/core/security/aes_helper.dart';
import 'package:cashctrl/core/utils/locker.dart';
import 'package:cashctrl/core/utils/logging.dart';
import 'package:cashctrl/utils/shared_pref_utils.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

// Necessary for code-generation to work
// Run: dart run build_runner watch
part 'auth_token_controller.g.dart';

/// The provider that returns an instance of `AuthTokenController`.
@riverpod
AuthTokenController authTokenController(Ref ref) => AuthTokenController._(ref);

/// Utility class for:
/// - retrieving the auth token
/// - refreshing the auth token if it expired
///
/// The class is thread safe and it provides a way of refreshing the token
/// synchronously (i.e.: if a refresh token request is started, then no other
/// refresh token request will start and every other request will wait until
/// the token is refreshed).
class AuthTokenController {
  AuthTokenController._(this.ref);

  /// A [Ref] object used to access any providers (such as `ApiService`).
  final Ref ref;

  /// A *Semaphore* like feature. It's used for waiting for a method to be
  /// fully executed before the same method or any other related one is started.
  final _locker = Locker();

  /// Main method used for getting the latest available token. The refresh auth
  /// token implementation is based on the refresh auth token request.
  ///
  /// If a request has failed with status code 401, then this method must be
  /// called with a non null [usedToken]. **The [usedToken] must be the *auth
  /// token* that was used in the request that failed due to expired/invalid
  /// auth token without the *Bearer* part.**
  ///
  /// The reason behind not using 2 methods (one for get and one for refreshing
  /// the token) is due to the following reason: if 2 requests were to fail
  /// in parallel and both would ask to refresh the token, then one will wait
  /// until the other has refreshed the auth token, and then a new refresh
  /// token request will be triggered because the latter, wouldn't know that
  /// the first already refreshed it. By passing a [usedToken], this ensures
  /// that if the token is refreshed, the other requests will use the new token.
  /// *In other words, the requests don't need to know when the token is
  /// refreshed or not; their only job is informing the [AuthTokenController]
  /// that the token they used didn't work.*
  Future<String?> getToken({String? usedToken}) async {
    // Acquire lock
    if (_locker.locked) {
      await _locker.waitLock();
      // return getToken(usedToken: usedToken);
    }
    _locker.lock();

    var authToken = await _getAuthTokenFromSharedPreferences();
    if (usedToken == null) {
      // Release lock
      _locker.unlock();
      return authToken;
    }
    if (usedToken == authToken) {
      authToken = await _refreshAuthToken();
    }

    // Release lock
    _locker.unlock();
    return authToken;
  }

  /// Main method used for getting the latest available token. The refresh auth
  /// token implementation is based on the login request.
  ///
  /// If a request has failed with status code 401, then this method must be
  /// called with a non null [usedToken]. **The [usedToken] must be the *auth
  /// token* that was used in the request that failed due to expired/invalid
  /// auth token without the *Bearer* part.**
  ///
  /// The same reasoning from [getToken] applies here too.
  Future<String?> getTokenLogin({String? usedToken}) async {
    // Acquire lock
    if (_locker.locked) {
      await _locker.waitLock();
      // return getTokenLogin(usedToken: usedToken);
    }
    _locker.lock();

    var authToken = await _getAuthTokenFromSharedPreferences();
    if (usedToken == null) {
      // Release lock
      _locker.unlock();
      return authToken;
    }
    if (usedToken == authToken) {
      authToken = await _refreshAuthTokenLogin();
    }

    // Release lock
    _locker.unlock();
    return authToken;
  }

  /// Returns the auth token for the current logged in user.
  Future<String?> _getAuthTokenFromSharedPreferences() async {
    final authDetails = await SharedPrefUtils.instance.getAuthDetails();
    return authDetails?.authToken;
  }

  /// Refreshes the auth token for the current logged in user.
  ///
  /// This method is called by [getToken].
  ///
  /// This method is intended to be used for apps that don't refresh the token
  /// by doing a login and rely on a refresh auth token request instead.
  Future<String?> _refreshAuthToken() async {
    final authDetails = await SharedPrefUtils.instance.getAuthDetails();
    if (authDetails == null) {
      return null;
    }
    final body = {'refresh_token': authDetails.refreshToken};

    try {
      final json = await ref.read(apiServiceProvider).refreshAuthToken(body);
      final data = AuthDetails.fromJson(json);
      if (data.authToken.isEmpty) {
        return null;
      }
      authDetails
        ..authToken = data.authToken
        ..refreshToken = data.refreshToken;
      await SharedPrefUtils.instance.saveAuthDetails(authDetails);
      return data.authToken;
    } on Exception catch (e, stacktrace) {
      // Log request errors
      unawaited(logException(e, stackTrace: stacktrace));
      return null;
    }
  }

  /// Refreshes the auth token for the current logged in user.
  ///
  /// This method is called by [getTokenLogin].
  ///
  /// This method is intended to be used for apps that refresh the token by
  /// doing a login.
  Future<String?> _refreshAuthTokenLogin() async {
    final user = await ref.read(userRepositoryProvider).getLoggedIn();
    if (user == null) {
      return null;
    }

    try {
      // Decrypting fails if the AES key was lost (e.g.: the app's data was
      // restored on another device). It's handled like a failed request: no
      // token is returned, so the user has to log in again.
      final urlKey = await AESHelper.instance.decrypt(user.key);
      final body = {'mail': user.email, 'key': urlKey};
      final json = await ref.read(apiServiceProvider).login(body);
      devPrint('Response refresh: $json}');
      final authDetails = AuthDetails.fromJson(json);
      if (authDetails.authToken.isEmpty) {
        return null;
      }
      await SharedPrefUtils.instance.saveAuthDetails(authDetails);
      return authDetails.authToken;
    } on Exception catch (e, stacktrace) {
      // Log request errors
      unawaited(logException(e, stackTrace: stacktrace));
      return null;
    }
  }

  /// Saves the [authDetails] consisting of the auth token and refresh auth
  /// token in the SharedPreferences.
  Future<void> saveAuthDetails(AuthDetails authDetails) async {
    await SharedPrefUtils.instance.saveAuthDetails(authDetails);
  }

  /// Removes the [AuthDetails] from the SharedPreferences.
  Future<void> removeAuthDetails() async {
    await SharedPrefUtils.instance.removeAuthDetails();
  }

  /// Checks if there is any auth token in the SharedPreferences.
  Future<bool> isUserLoggedIn() async {
    final authDetails = await SharedPrefUtils.instance.getAuthDetails();
    return authDetails != null;
  }
}
