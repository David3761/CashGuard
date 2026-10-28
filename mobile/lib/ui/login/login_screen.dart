import 'dart:async';

import 'package:cashctrl/exceptions.dart';
import 'package:cashctrl/l10n/app_localizations.dart';
import 'package:cashctrl/resources/colors.dart';
import 'package:cashctrl/resources/text_styles.dart';
import 'package:cashctrl/ui/forgot_password/forgot_password_screen.dart';
import 'package:cashctrl/ui/login/login_provider.dart';
import 'package:cashctrl/ui/register/register_screen.dart';
import 'package:cashctrl/utils/dialogs.dart';
import 'package:cashctrl/widgets/widgets.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

/// The login screen.
class LoginScreen extends ConsumerStatefulWidget {
  /// Creates a [LoginScreen].
  const LoginScreen({super.key});

  /// The route's name.
  static const route = 'login';

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  var _email = '';
  var _password = '';

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context);
    final loginState = ref.watch(loginProvider);
    _listenForProviders();
    return Scaffold(
      backgroundColor: Colors.white,
      body: SafeArea(
        child: LoadingStack(
          showProgressIndicator: loginState.isLoading,
          children: [
            SingleChildScrollView(
              padding: const .directional(bottom: 20),
              child: Column(
                children: [
                  Padding(
                    padding: const .directional(start: 20, top: 20, end: 20),
                    child: Column(
                      crossAxisAlignment: .stretch,
                      children: [
                        Align(
                          alignment: .centerStart,
                          child: Text(
                            localizations.login,
                            style: TextStyles.text21R,
                          ),
                        ),
                        const SizedBox(height: 30),
                        TextForm(
                          labelText: localizations.emailAddress,
                          text: _email,
                          obscured: false,
                          keyboardType: .emailAddress,
                          onChanged: (text) {
                            _email = text;
                          },
                        ),
                        const SizedBox(height: 20),
                        TextForm(
                          labelText: localizations.password,
                          text: _password,
                          obscured: true,
                          onChanged: (text) {
                            _password = text;
                          },
                        ),
                        const SizedBox(height: 20),
                        BigButton(
                          labelText: localizations.login,
                          onPressed: () async {
                            await ref
                                .read(loginProvider.notifier)
                                .loginWithEmail(_email, _password);
                          },
                        ),
                        const SizedBox(height: 20),
                        Row(
                          mainAxisAlignment: .spaceBetween,
                          children: [
                            TextButton(
                              onPressed: () {
                                context.goNamed(ForgotPasswordScreen.route);
                              },
                              style: TextButton.styleFrom(
                                foregroundColor: AppColors.defaultGray,
                              ),
                              child: Text(localizations.forgotPassword_),
                            ),
                            TextButton(
                              onPressed: () {
                                context.goNamed(RegisterScreen.route);
                              },
                              style: TextButton.styleFrom(
                                foregroundColor: AppColors.defaultGray,
                              ),
                              child: Text(localizations.register),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// Listens to providers value changes in order to display one time events
  /// (e.g.: alert dialogs, snack bars, toasts, etc) or perform actions.
  ///
  /// **This method should always be called from [build].**
  void _listenForProviders() {
    ref.listen<AsyncValue<bool>>(loginProvider, (_, state) {
      if (state case AsyncData(value: true)) {
        FocusScope.of(context).unfocus();
      } else if (state case AsyncError(:final error)) {
        unawaited(
          showAlert(
            context: context,
            title: AppLocalizations.of(context).error_,
            message: getLocalizedMessage(context, error),
          ),
        );
      }
    });
  }
}
