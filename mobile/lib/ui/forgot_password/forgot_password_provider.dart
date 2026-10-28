import 'dart:async';

import 'package:cashctrl/exceptions.dart';
import 'package:cashctrl/utils/validators.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

// Necessary for code-generation to work
// Run: dart run build_runner watch
part 'forgot_password_provider.g.dart';

/// The forgot password provider that handles the forgot password process.
@riverpod
class ForgotPassword extends _$ForgotPassword {
  @override
  Future<bool> build() => Future.value(false);

  /// If the email is valid, it makes a request to reset the user's password.
  /// If the email is not valid, it throws an appropriate error.
  Future<void> resetPassword(String email) async {
    state = const .loading();
    state = await .guard(() async {
      if (!Validators.instance.isEmailValid(email)) {
        throw const UIException.invalidEmail();
      }

      // Simulate a request. Remove these lines after you implement this method.
      await Future.delayed(const Duration(seconds: 2));

      // TODO(everyone): don't remove the code below. Skipping the request
      // will be used just for the base project!
      /*final userRepository = ref.read(userRepositoryProvider);

      final body = {'mail': email, 'auth_method': '0'};

      final json = await userRepository.forgotPassword(body: body);

      if (json['status'] != 'ok') {
        throw UIException.serverError(json['message']);
      }*/

      return true;
    });
  }
}
