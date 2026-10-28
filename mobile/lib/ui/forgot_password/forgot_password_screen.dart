import 'dart:async';

import 'package:cashctrl/exceptions.dart';
import 'package:cashctrl/l10n/app_localizations.dart';
import 'package:cashctrl/resources/colors.dart';
import 'package:cashctrl/resources/text_styles.dart';
import 'package:cashctrl/ui/forgot_password/forgot_password_provider.dart';
import 'package:cashctrl/utils/dialogs.dart';
import 'package:cashctrl/widgets/widgets.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// The forgot password screen.
class ForgotPasswordScreen extends ConsumerStatefulWidget {
  /// Creates a [ForgotPasswordScreen].
  const ForgotPasswordScreen({super.key});

  /// The route's name.
  static const route = 'forgot-password';

  @override
  ConsumerState<ForgotPasswordScreen> createState() =>
      _ForgotPasswordScreenState();
}

class _ForgotPasswordScreenState extends ConsumerState<ForgotPasswordScreen> {
  var _email = '';

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context);
    final forgotPasswordState = ref.watch(forgotPasswordProvider);
    _listenForProviders();
    return ScreenStack(
      backgroundColor: Colors.white,
      showProgressIndicator: forgotPasswordState.isLoading,
      showLogo: false,
      children: [
        Column(
          children: [
            Padding(
              padding: const .directional(start: 20, top: 20, end: 20),
              child: Column(
                children: [
                  Align(
                    alignment: .centerStart,
                    child: Text(
                      localizations.forgotPassword,
                      style: TextStyles.text21R,
                    ),
                  ),
                  const SizedBox(height: 20),
                  Text(localizations.enterEmail),
                ],
              ),
            ),
            const SizedBox(height: 15),
            const LineDivider(height: 0.5, color: AppColors.darkerGray),
            const SizedBox(height: 10),
            Padding(
              padding: const .symmetric(horizontal: 20),
              child: Column(
                crossAxisAlignment: .stretch,
                children: [
                  TextForm(
                    labelText: localizations.emailAddress,
                    text: _email,
                    obscured: false,
                    onChanged: (text) {
                      _email = text;
                    },
                  ),
                  const SizedBox(height: 20),
                  BigButton(
                    labelText: localizations.requestReset,
                    onPressed: () async {
                      await ref
                          .read(forgotPasswordProvider.notifier)
                          .resetPassword(_email);
                    },
                  ),
                ],
              ),
            ),
          ],
        ),
      ],
    );
  }

  /// Listens to providers value changes in order to display one time events
  /// (e.g.: alert dialogs, snack bars, toasts, etc) or perform actions.
  ///
  /// **This method should always be called from [build].**
  void _listenForProviders() {
    ref.listen<AsyncValue<bool>>(forgotPasswordProvider, (_, state) {
      if (state case AsyncData(value: true)) {
        unawaited(
          showAlert(
            context: context,
            title: AppLocalizations.of(context).alert,
            message: AppLocalizations.of(context).resetLinkSent,
          ),
        );
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
