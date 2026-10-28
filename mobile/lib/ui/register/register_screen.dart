import 'dart:async';

import 'package:cashctrl/exceptions.dart';
import 'package:cashctrl/l10n/app_localizations.dart';
import 'package:cashctrl/resources/text_styles.dart';
import 'package:cashctrl/ui/register/register_provider.dart';
import 'package:cashctrl/utils/dialogs.dart';
import 'package:cashctrl/widgets/widgets.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// The register screen.
class RegisterScreen extends ConsumerStatefulWidget {
  /// Creates a [RegisterScreen].
  const RegisterScreen({super.key});

  /// The route's name.
  static const route = 'register';

  @override
  ConsumerState<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends ConsumerState<RegisterScreen> {
  var _email = '';
  var _password = '';
  var _rePassword = '';
  var _fullName = '';
  var _phone = '';
  String? _gender;

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context);
    final registerState = ref.watch(registerProvider);
    _listenForProviders();
    final gendersList = localizations.gendersList.split('|');
    return ScreenStack(
      backgroundColor: Colors.white,
      showProgressIndicator: registerState.isLoading,
      showLogo: false,
      children: [
        SingleChildScrollView(
          child: Column(
            children: [
              Padding(
                padding: const .all(20),
                child: Column(
                  crossAxisAlignment: .stretch,
                  children: [
                    Align(
                      alignment: .centerStart,
                      child: Text(
                        localizations.register,
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
                    const SizedBox(height: 10),
                    TextForm(
                      labelText: localizations.fullName,
                      text: _fullName,
                      obscured: false,
                      onChanged: (text) {
                        _fullName = text;
                      },
                    ),
                    const SizedBox(height: 10),
                    TextForm(
                      labelText: localizations.phone,
                      text: _phone,
                      obscured: false,
                      keyboardType: .phone,
                      onChanged: (text) {
                        _phone = text;
                      },
                    ),
                    const SizedBox(height: 10),
                    DropdownForm<String>(
                      hint: Text(localizations.gender),
                      value: _gender,
                      itemBuilder: Text.new,
                      items: gendersList,
                      onChanged: (value) {
                        _gender = value ?? '';
                      },
                    ),
                    const SizedBox(height: 10),
                    TextForm(
                      labelText: localizations.password,
                      text: _password,
                      obscured: true,
                      onChanged: (text) {
                        _password = text;
                      },
                    ),
                    const SizedBox(height: 10),
                    TextForm(
                      labelText: localizations.passwordConfirmation,
                      text: _rePassword,
                      obscured: true,
                      onChanged: (text) {
                        _rePassword = text;
                      },
                    ),
                    const SizedBox(height: 20),
                    BigButton(
                      labelText: localizations.register,
                      onPressed: () async {
                        await ref
                            .read(registerProvider.notifier)
                            .registerWithEmail(
                              email: _email,
                              password: _password,
                              rePassword: _rePassword,
                              fullName: _fullName,
                              phone: _phone,
                              gender: _gender,
                            );
                      },
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  /// Listens to providers value changes in order to display one time events
  /// (e.g.: alert dialogs, snack bars, toasts, etc) or perform actions.
  ///
  /// **This method should always be called from [build].**
  void _listenForProviders() {
    ref.listen<AsyncValue<bool>>(registerProvider, (_, state) {
      if (state case AsyncData(value: true)) {
        unawaited(
          showAlert(
            context: context,
            title: AppLocalizations.of(context).alert,
            message: AppLocalizations.of(context).accountCreated,
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
