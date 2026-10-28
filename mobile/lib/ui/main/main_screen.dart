import 'dart:async';
import 'dart:convert';

import 'package:cashctrl/core/notification/app_notification_service.dart';
import 'package:cashctrl/core/utils/logging.dart';
import 'package:cashctrl/exceptions.dart';
import 'package:cashctrl/l10n/app_localizations.dart';
import 'package:cashctrl/main.dart';
import 'package:cashctrl/main_providers.dart';
import 'package:cashctrl/resources/images.dart';
import 'package:cashctrl/resources/text_styles.dart';
import 'package:cashctrl/ui/settings/settings_screen.dart';
import 'package:cashctrl/utils/dialogs.dart';
import 'package:cashctrl/widgets/widgets.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:package_info_plus/package_info_plus.dart';

/// The main screen of the app.
class MainScreen extends ConsumerStatefulWidget {
  /// Creates a [MainScreen].
  const MainScreen({super.key, this.notificationData});

  /// The route's name.
  static const route = 'main';

  /// The data of the notification that triggered the app to open (if any).
  final String? notificationData;

  @override
  ConsumerState<MainScreen> createState() => _MainScreenState();
}

class _MainScreenState extends ConsumerState<MainScreen>
    with WidgetsBindingObserver, RouteAware {
  StreamSubscription<String>? _newNotificationSubscription;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    MyApp.isInMainScreen = true;
    _newNotificationSubscription = AppNotificationService
        .instance
        .newNotification
        .stream
        .listen(_loadDataFromNotification);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    unawaited(_newNotificationSubscription?.cancel());
    _newNotificationSubscription = null;
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    _listenForProviders();

    return PopScope(
      canPop: false,
      child: ScreenStack(
        leading: Builder(
          builder: (context) => IconButton(
            onPressed: Scaffold.of(context).openDrawer,
            icon: Image.asset(AppImages.menu, width: 30),
          ),
        ),
        drawer: SafeArea(
          child: SizedBox(
            // width: MediaQuery.of(context).size.width,
            child: Drawer(
              backgroundColor: Colors.white,
              child: AppDrawer(
                onMenuItemTap: (route) => context.goNamed(route),
                onLogout: ref.read(authProvider.notifier).logout,
              ),
            ),
          ),
        ),
        children: const [],
      ),
    );
  }

  /// Listens to providers value changes in order to display one time events
  /// (e.g.: alert dialogs, snack bars, toasts, etc) or perform actions.
  ///
  /// **This method should always be called from [build].**
  void _listenForProviders() {
    final localizations = AppLocalizations.of(context);
    ref.listen(authProvider, (_, state) {
      if (state case AsyncError(:final error)) {
        unawaited(
          showAlert(
            context: context,
            title: localizations.error_,
            message: getLocalizedMessage(context, error),
          ),
        );
      }
    });
  }

  /// If the app has resumed and the screen is the MainScreen, then call
  /// [_getNewNotificationDataIfAny].
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == .resumed && MyApp.isInMainScreen) {
      _getNewNotificationDataIfAny();
    }
  }

  /// Sets [MyApp.isInMainScreen] to `false`.
  @override
  void didPushNext() {
    // navigating forward to a new page
    MyApp.isInMainScreen = false;
  }

  /// Sets [MyApp.isInMainScreen] to `true` and calls
  /// [_getNewNotificationDataIfAny].
  @override
  void didPopNext() {
    // Covering route was popped off the navigator.
    MyApp.isInMainScreen = true;
    _getNewNotificationDataIfAny();
  }

  /// Should make a request to retrieve the data from the server and display
  /// it in the app. Currently this method only tries to decode the [data] as
  /// a JSON.
  void _loadDataFromNotification(String data) {
    try {
      final json = jsonDecode(data);
      devPrint('notification: $json');
    } on Exception catch (e, stacktrace) {
      unawaited(logException(e, stackTrace: stacktrace));
    }
  }

  /// Fetches the new notification data if present.
  void _getNewNotificationDataIfAny() {}
}

/// The widget that displays the app drawer.
class AppDrawer extends ConsumerWidget {
  /// Creates an [AppDrawer].
  const AppDrawer({
    super.key,
    required this.onMenuItemTap,
    required this.onLogout,
  });

  /// Called when the user taps a menu item.
  final ValueChanged<String> onMenuItemTap;

  /// Called when the user taps the logout option.
  final VoidCallback onLogout;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final localizations = AppLocalizations.of(context);
    return Stack(
      children: [
        Padding(
          padding: const .symmetric(vertical: 10),
          child: SingleChildScrollView(
            child: Column(
              children: [
                MenuItem(
                  localizations.settings,
                  onTap: () => onMenuItemTap(SettingsScreen.route),
                ),
                MenuItem(
                  localizations.logout,
                  onTap: () {
                    unawaited(
                      showYesNoAlert(
                        context: context,
                        title: localizations.logout,
                        message: localizations.logoutConfirmation,
                        yesClickListener: (context) {
                          context.pop();
                          onLogout();
                        },
                      ),
                    );
                  },
                ),
              ],
            ),
          ),
        ),
        Column(
          mainAxisAlignment: .end,
          children: [
            Align(
              alignment: .bottomCenter,
              child: Padding(
                padding: const .directional(bottom: 10),
                child: FutureBuilder<PackageInfo>(
                  future: PackageInfo.fromPlatform(),
                  builder: (context, packageInfo) => Text(
                    localizations.versionOf(packageInfo.data?.version ?? '-'),
                  ),
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }
}

/// A widget that displays a menu option.
class MenuItem extends StatelessWidget {
  /// Creates a [MenuItem].
  const MenuItem(this.labelText, {super.key, required this.onTap});

  /// The menu item's label.
  final String labelText;

  /// Called when the user taps the menu item.
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      title: Text(labelText, style: TextStyles.text14SB),
      onTap: onTap,
    );
  }
}
