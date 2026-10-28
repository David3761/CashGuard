import 'dart:async';

import 'package:cashctrl/core/notification/app_notification_service.dart';
import 'package:cashctrl/core/notification/fcm_token_refresh_provider.dart';
import 'package:cashctrl/core/utils/logging.dart';
import 'package:cashctrl/l10n/app_localizations.dart';
import 'package:cashctrl/main_providers.dart';
import 'package:cashctrl/ui/main/main_screen.dart';
import 'package:cashctrl/ui/main/user_provider.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/material.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

Future<void> main() async {
  // Set to use Android Photo Picker.
  /*final ImagePickerPlatform imagePickerImplementation =
      ImagePickerPlatform.instance;
  if (imagePickerImplementation is ImagePickerAndroid) {
    imagePickerImplementation.useAndroidPhotoPicker = true;
  }*/

  WidgetsFlutterBinding.ensureInitialized();
  await _initFirebase();

  runApp(
    // For widgets to be able to read providers, we need to wrap the entire
    // application in a "ProviderScope" widget.
    // This is where the state of our providers will be stored.
    const ProviderScope(child: MyApp()),
  );
  /*SystemChrome.setSystemUIOverlayStyle(
    const SystemUiOverlayStyle(statusBarColor: Colors.white),
  );*/
}

/// The main app widget.
class MyApp extends ConsumerStatefulWidget {
  /// Creates a [MyApp].
  const MyApp({super.key});

  /// `true` if the app is showing the main screen, or `false` otherwise.
  static bool isInMainScreen = false;

  @override
  ConsumerState<MyApp> createState() => _MyAppState();
}

class _MyAppState extends ConsumerState<MyApp> {
  // final _inAppPurchasesController = InAppPurchasesController();

  @override
  void initState() {
    super.initState();
    // inAppPurchasesController.init();
    unawaited(_initFCM());

    // Run code required to handle interacted messages in an async function
    // as initState() must not be async
    // _setupInteractedMessage();
  }

  @override
  void dispose() {
    // _inAppPurchasesController.dispose();
    super.dispose();
  }

  // This widget is the root of your application.
  @override
  Widget build(BuildContext context) {
    final router = ref.watch(routerProvider);
    // The AppStartup provider handles the initialization phase prior to app
    // opening.
    final appStartupState = ref.watch(appStartupProvider);
    // In order for app localizations file to work on iOS, you need to make
    // a minor change:
    // https://docs.flutter.dev/ui/accessibility-and-internationalization/internationalization#localizing-for-ios-updating-the-ios-app-bundle

    return switch (appStartupState) {
      // Show the loading only on app startup. Subsequent refreshes/reloads
      // shouldn't show the Flutter splashscreen anymore.
      final AsyncLoading state when !state.isRefreshing && !state.isReloading =>
        ColoredBox(
          color: Colors.white,
          // color:
          //     MediaQuery.platformBrightnessOf(context) == Brightness.light
          //         ? Colors.white
          //         : Colors.black,
          // TODO(everyone): after you fork the repository, replace the
          // following image with the same image that is used in the
          // default Android splashscreen. Be sure to also update the iOS
          // native app to use the same exact image.
          // Scale the image so that its height is roughly ~170 pixels (from
          // testing, that seems to match the default Android & iOS launch
          // screen's image size).
          child: Image.asset('images/launch_icon.png'),
        ),
      _ => _EagerInitialization(
        child: MaterialApp.router(
          routerConfig: router,
          onGenerateTitle: (context) => AppLocalizations.of(context).appName,
          theme: ThemeData(),
          // darkTheme: ThemeData.dark(),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
        ),
      ),
    };
  }

  /// If the [notificationResponse] contains some data, then the
  /// MainScreen is opened with the given data.
  void _onDidReceiveNotificationResponse(
    NotificationResponse notificationResponse,
  ) {
    final data = notificationResponse.payload;
    if (mounted) {
      context.goNamed(MainScreen.route, extra: data);
    }
  }

  /// Initializes the Firebase Messaging service, along with the device token
  /// refresh listener.
  Future<void> _initFCM() async {
    await AppNotificationService.instance.setup(
      _onDidReceiveNotificationResponse,
    );
    await AppNotificationService.instance.listenFCM();
  }

  /// Checks if there are messages that opened the app from a terminated state
  /// and handles them.
  ///
  /// The method is not needed using the current implementation. This relies on
  /// an another type of flow.
  ///
  // ignore: unused_element
  Future<void> _setupInteractedMessage() async {
    // Get any messages which caused the application to open from
    // a terminated state.
    final initialMessage = await FirebaseMessaging.instance.getInitialMessage();

    // If the message also contains a data property with a "type" of "chat",
    // navigate to a chat screen
    if (initialMessage != null) {
      _handleMessage(initialMessage);
    }

    // Also handle any interaction when the app is in the background via a
    // Stream listener
    FirebaseMessaging.onMessageOpenedApp.listen(_handleMessage);
  }

  /// Handles a notification message detected by [_setupInteractedMessage].
  ///
  /// The method is not needed using the current implementation. This relies on
  /// an another type of flow.
  void _handleMessage(RemoteMessage message) {
    devPrint('message: ---- ${message.data}');
  }
}

/// A widget used to eagerly initialize the providers that should be kept
/// alive so long the scope of the app is alive. You'd put here providers
/// that provide info about the user or app settings data.
///
/// **Note:** This must be a [StatefulWidget] in order for its state to be
/// preserved, so that the `userDataProvider` is also preserved.
///
/// *From riverpod's FAQ:*
///
/// > **Won't this rebuild our entire application when the provider changes?**
/// >
/// > No, this is not the case. In the sample given above, the consumer
/// responsible for eagerly initializing is a separate widget, which does
/// nothing but return a child.
/// >
/// > The key part is that it returns a child, rather than instantiating
/// > `MaterialApp` itself. This means that if `_EagerInitialization` ever
/// > rebuilds, the child variable will not have changed. And when a widget
/// > doesn't change, Flutter doesn't rebuild it.
/// >
/// > As such, only `_EagerInitialization` will rebuild, unless another widget
/// > is also listening to that provider.
///
/// Be sure to use `AsyncValue.requireValue` for eagerly initialized providers
/// that expose an `AsyncValue`, when you need their data. See the following
/// [example](https://riverpod.dev/docs/essentials/eager_initialization#ive-handled-loadingerror-states-but-other-consumers-still-receive-an-asyncvalue-is-there-a-way-to-not-have-to-handle-loadingerror-states-in-every-widget).
class _EagerInitialization extends ConsumerStatefulWidget {
  const _EagerInitialization({required this.child});

  final Widget child;

  @override
  ConsumerState<_EagerInitialization> createState() =>
      _EagerInitializationState();
}

class _EagerInitializationState extends ConsumerState<_EagerInitialization> {
  @override
  Widget build(BuildContext context) {
    // Eagerly initialize providers by watching them.
    // By using "watch", the provider will stay alive and not be disposed
    // (until this widget is disposed).
    ref
      ..watch(userDataProvider)
      ..watch(fcmTokenRefreshProvider);
    return widget.child;
  }
}

/// Initializes the Firebase app.
Future<void> _initFirebase() async {
  // If you're going to use other Firebase services in the background, such as
  // Firestore, make sure you call `initializeApp` before using other Firebase
  // services.
  await Firebase.initializeApp();
}
