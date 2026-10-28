import 'dart:async';

import 'package:cashctrl/exceptions.dart';
import 'package:cashctrl/l10n/app_localizations.dart';
import 'package:cashctrl/ui/settings/manage_data_provider.dart';
import 'package:cashctrl/utils/dialogs.dart';
import 'package:cashctrl/widgets/widgets.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// The settings screen.
class SettingsScreen extends ConsumerWidget {
  /// Creates a [SettingsScreen].
  const SettingsScreen({super.key});

  /// The route's name.
  static const route = 'settings';

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final localizations = AppLocalizations.of(context);
    final manageDataState = ref.watch(manageDataProvider);
    _listenForProviders(context, ref);
    return ScreenStack(
      showProgressIndicator: manageDataState.isLoading,
      children: [
        Padding(
          padding: const .directional(start: 10, top: 10, end: 10),
          child: Column(
            crossAxisAlignment: .start,
            children: [
              ElevatedButton(
                onPressed: () async {
                  await ref.read(manageDataProvider.notifier).viewData();
                },
                child: Text(localizations.viewData),
              ),
              ElevatedButton(
                onPressed: () async {
                  await ref.read(manageDataProvider.notifier).deleteData();
                },
                child: Text(localizations.deleteData),
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
  void _listenForProviders(BuildContext context, WidgetRef ref) {
    ref.listen<AsyncValue<ManageDataStatus>>(manageDataProvider, (_, state) {
      if (state case AsyncData(value: .viewDataEmailSent)) {
        unawaited(
          showAlert(
            context: context,
            title: AppLocalizations.of(context).alert,
            message: AppLocalizations.of(context).viewDataEmailSent,
          ),
        );
      } else if (state case AsyncData(value: .deleteDataEmailSent)) {
        unawaited(
          showAlert(
            context: context,
            title: AppLocalizations.of(context).alert,
            message: AppLocalizations.of(context).deleteDataEmailSent,
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
