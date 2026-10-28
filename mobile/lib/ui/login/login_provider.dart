import 'dart:async';

import 'package:cashctrl/core/models/auth_details.dart';
import 'package:cashctrl/core/models/auth_method.dart';
import 'package:cashctrl/core/request/auth_token_controller.dart';
import 'package:cashctrl/exceptions.dart';
import 'package:cashctrl/main_providers.dart';
import 'package:cashctrl/ui/main/user_provider.dart';
import 'package:cashctrl/utils/validators.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

// Necessary for code-generation to work
// Run: dart run build_runner watch
part 'login_provider.g.dart';

/// The login provider that handles the login process.
@riverpod
class Login extends _$Login {
  @override
  Future<bool> build() => Future.value(false);

  /// Calls [_login] with the [email], [password] and [AuthMethod.email].
  Future<void> loginWithEmail(String email, String password) async {
    state = const .loading();
    state = await .guard(() => _login(email, password, .email));
  }

  /// Checks if the [email] and [password] are not empty and if the email is
  /// valid (only if the [authMethod] is [AuthMethod.email]). If the checks
  /// pass, then it makes a login request.
  ///
  /// If the login process goes without issues, then the following actions will
  /// be done:
  /// - the device token will be sent to the server
  ///
  /// If anything goes wrong, an appropriate exception will be thrown.
  Future<bool> _login(
    String email,
    String password,
    AuthMethod authMethod,
  ) async {
    if (authMethod == .email) {
      if (email.trim().isEmpty || password.trim().isEmpty) {
        throw const UIException.allFieldsRequired();
      }
      if (!Validators.instance.isEmailValid(email)) {
        throw const UIException.invalidEmail();
      }
    }

    // Simulate a request. Remove these lines after you implement this method.
    await Future.delayed(const Duration(seconds: 2));

    // Dummy data. Must be removed entirely when the feature is implemented.
    // The insert method from the UserRepository handles saving the AuthDetails
    // in the SharedPreferences.
    final authDetails = AuthDetails(
      authToken: 'lorem-ipsum',
      refreshToken: 'dolor-sit-amet',
    );
    await ref.read(authTokenControllerProvider).saveAuthDetails(authDetails);
    // End of dummy data.

    // TODO(everyone): don't remove the code below. Skipping the login will be
    // used just for the base project!
    /*final body = {
      'mail': email,
      'key': password,
      'auth_method': '${authMethod.id}',
    };

    final userRepository = ref.read(userRepositoryProvider);

    final json = await userRepository.login(body: body);

    if (json['status'] != 'ok') {
      throw UIException.serverError(json['message']);
    }

    final user = User.fromJson(json).copyWith(
      key: AESHelper.encrypt(password),
      authMethod: authMethod,
      loggedIn: true,
    );
    final authDetails = AuthDetails.fromJson(json);
    await userRepository.insert(user, authDetails: authDetails);
    sendOrDeleteDeviceToken(deleteToken: false);*/

    // We invalidate the auth and userData providers so that their build method
    // is called again and every widget that observes them is redrawn with the
    // new state.
    ref
      ..invalidate(authProvider)
      ..invalidate(userDataProvider);

    return true;
  }
}
