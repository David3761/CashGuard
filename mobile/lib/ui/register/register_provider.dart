import 'dart:async';

import 'package:cashctrl/core/models/auth_method.dart';
import 'package:cashctrl/exceptions.dart';
import 'package:cashctrl/utils/validators.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

// Necessary for code-generation to work
// Run: dart run build_runner watch
part 'register_provider.g.dart';

/// The register provider that handles the registration process.
@riverpod
class Register extends _$Register {
  @override
  Future<bool> build() => Future.value(false);

  /// Calls [_register] with [email], [password] and [AuthMethod.email].
  Future<void> registerWithEmail({
    required String email,
    required String password,
    required String rePassword,
    required String fullName,
    required String phone,
    required String? gender,
  }) async {
    state = const .loading();
    state = await .guard(
      () => _register(
        email: email,
        password: password,
        rePassword: rePassword,
        authMethod: .email,
        fullName: fullName,
        phone: phone,
        gender: gender,
      ),
    );
  }

  /// If the [authMethod] is [AuthMethod.email], it performs the following
  /// checks:
  /// - the fields must not be empty
  /// - the email and phone must be valid
  /// - the password must have at least 6 characters
  /// - the password and password confirmation must match
  ///
  /// If the checks above pass, then it makes a register request.
  ///
  /// If the register process goes without issues, then the following actions
  /// will be done:
  /// - the user will be saved in the database
  ///
  /// If anything goes wrong, an appropriate exception will be thrown.
  Future<bool> _register({
    required String email,
    required String password,
    required String rePassword,
    required AuthMethod authMethod,
    required String fullName,
    required String phone,
    required String? gender,
  }) async {
    if (authMethod == .email) {
      if (!Validators.instance.isEmailValid(email)) {
        throw const UIException.invalidEmail();
      }
      if (password.length <= Validators.instance.passwordMinLength) {
        throw const UIException.passwordLengthError();
      }
      if (password != rePassword) {
        throw const UIException.passwordConfirmationMismatch();
      }

      final phoneState = Validators.instance.isPhoneValid(phone);
      if (phoneState == .countryCodeRequired) {
        throw const UIException.countryCodeRequired();
      } else if (phoneState == .phoneNumberNotValid) {
        throw const UIException.phoneNumberNotValid();
      }

      if (email.isEmpty ||
          fullName.isEmpty ||
          phone.isEmpty ||
          gender == null ||
          password.isEmpty) {
        throw const UIException.allFieldsRequired();
      }
    }

    // Simulate a request. Remove these lines after you implement this method.
    await Future.delayed(const Duration(seconds: 2));

    // TODO(everyone): the request is simulated because the backend has no
    // accounts yet. Once it has, remove the delay above and restore the
    // request below.
    /*final userRepository = ref.read(userRepositoryProvider);

    final body = {
      'mail': email,
      'auth_method': '${authMethod.id}',
      'key': password,
      if (phone.isNotEmpty) 'phone': phone,
      if (fullName.isNotEmpty) 'full_name': fullName,
    };

    final json = await userRepository.register(body: body);

    if (json['status'] != 'ok') {
      final data = RequestResponse.fromJson(json);
      throw UIException.serverError(data.message);
    }

    final user = User.fromJson(json).copyWith(loggedIn: true);
    await userRepository.insert(user);*/

    return true;
  }
}
