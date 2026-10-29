import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:cashctrl/core/notification/notification_id.dart';
import 'package:cashctrl/core/utils/logging.dart';
import 'package:cashctrl/l10n/app_localizations.dart';
import 'package:cashctrl/main.dart';
import 'package:cashctrl/main_providers.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

/// The class that manages the push notifications. The app needs to request
/// and store a firebase token for sending it to the server in order to receive
/// push notifications.
class AppNotificationService {
  AppNotificationService._();

  /// Returns the singleton instance of this class.
  static final instance = AppNotificationService._();

  /// A stream controller that sends events for new notifications.
  final newNotification = StreamController<String>.broadcast();

  final _localNotificationsPlugin = FlutterLocalNotificationsPlugin();
  static const _channelId = 'com.cashctrl.notification';
  static const _appName = 'CashCtrl';

  // TODO(Mihai): at some point, these may need to be translated, but there
  // doesn't seem to be a proper way of doing it currently.
  static const _channelNotification = 'Main Notifications';
  static const _channelNotificationDescription =
      'This is the main notification channel for the CashCtrl';

  /// Returns `true` if push notifications are available, or `false` otherwise.
  bool get isAvailable =>
      kIsWeb || Platform.isAndroid || Platform.isIOS || Platform.isMacOS;

  /// Initializes the notification click listener for both Android and iOS.
  /// The [onDidReceiveNotificationResponse] will be called whenever a new
  /// notification is received.
  ///
  /// The method also initializes the listener that intercepts notifications
  /// while the app is in background.
  Future<void> setup(
    Function(NotificationResponse) onDidReceiveNotificationResponse,
  ) async {
    // Load the last used notification id.
    await NotificationId.instance.loadLastId();
    // Setup Firebase Messaging
    FirebaseMessaging.onBackgroundMessage(_firebaseMessagingBackgroundHandler);

    // Check if app was opened from a notification
    final notificationAppLaunchDetails = await _localNotificationsPlugin
        .getNotificationAppLaunchDetails();
    final notificationResponse =
        notificationAppLaunchDetails?.notificationResponse;
    if (notificationResponse != null) {
      onDidReceiveNotificationResponse(notificationResponse);
    }

    // Setup Flutter Local Notifications
    const androidSettings = AndroidInitializationSettings(
      '@mipmap/ic_launcher_foreground',
    );
    const iosSettings = DarwinInitializationSettings();
    const initializationSettings = InitializationSettings(
      android: androidSettings,
      iOS: iosSettings,
    );

    await _localNotificationsPlugin.initialize(
      settings: initializationSettings,
      onDidReceiveNotificationResponse: onDidReceiveNotificationResponse,
    );
    if (Platform.isAndroid) {
      await _localNotificationsPlugin
          .resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin
          >()
          ?.requestNotificationsPermission();
    }
  }

  /// Parses the given [message] and returns the data.
  Map<String, dynamic> _parseNotification(RemoteMessage message) {
    final data = message.data;
    final pData = <String, dynamic>{};
    data.forEach((key, value) {
      // pData[key] = (value as String?)?.replaceAll('"', '') ?? '';
      try {
        pData[key] = jsonDecode(value ?? '');
      } on Exception {
        pData[key] = value;
      }
    });
    return pData;
  }

  /// Initializes the listener that intercepts notifications while the app is
  /// in foreground. If the TransactionsScreen widget is in foreground, then the
  /// notification will be added to [newNotification]. Otherwise, the
  /// [_showNotification] will be called.
  ///
  /// If the app doesn't have permissions for showing notifications, it
  /// requests them.
  Future<void> listenFCM() async {
    final settings = await FirebaseMessaging.instance.requestPermission();
    if (settings.authorizationStatus != .authorized) {
      return;
    }
    devPrint('FCM token: ${await FirebaseMessaging.instance.getToken()}');

    FirebaseMessaging.onMessage.listen((message) {
      devPrint(
        'Got a message whilst in the foreground! Message data: ${message.data}',
      );
      final data = _parseNotification(message);

      if (MyApp.isInMainScreen) {
        newNotification.add(jsonEncode(data));
      } else {
        _showNotification(data);
      }
    });
    /*FirebaseMessaging.onMessageOpenedApp.listen((message) {
      devPrint(
        'Got a message whilst in the background! Message data: ${message.data}',
      );
    });*/
  }

  /// Displays a notification for the given [data] for both Android and iOS.
  void _showNotification(Map<String, dynamic> data) {
    final messageBody = data['message'] ?? '';
    final notificationId = NotificationId.instance.getId();
    unawaited(NotificationId.instance.saveCurrentId());
    final AppLocalizations? localizations;
    if (rootNavigatorKey.currentContext != null) {
      localizations = AppLocalizations.of(rootNavigatorKey.currentContext!);
    } else {
      localizations = null;
    }

    /*final tripId = order['trip_id'] ?? 0;
    final notificationId = order['notification_id'] ?? 0;
    final timeToLive =
        order['time_to_live'] ? order['time_to_live'] * 1000 : null;*/

    /*if (notificationId == .notAvailable.id) {
      // Trip no longer available
      _localNotificationsPlugin.cancel(tripId);
      return;
    } else if (notificationId == .cancelled.id) {
    } else if (notificationId != .newOrder.id) {
      return;
    }*/

    final androidDetails = AndroidNotificationDetails(
      _channelId,
      localizations?.channelNotification ?? _channelNotification,
      channelDescription:
          localizations?.channelNotificationDescription ??
          _channelNotificationDescription,
      importance: .high,
      timeoutAfter: 60 * 1000,
    );
    const iosDetails = DarwinNotificationDetails();
    final notificationDetails = NotificationDetails(
      android: androidDetails,
      iOS: iosDetails,
    );

    unawaited(
      _localNotificationsPlugin.show(
        id: notificationId,
        title: localizations?.appName ?? _appName,
        body: messageBody,
        notificationDetails: notificationDetails,
        payload: jsonEncode(data),
      ),
    );
  }
}

/// A handler method that intercepts notifications while the app is in
/// background and calls [AppNotificationService._showNotification] with the
/// retrieved data from the given [message].
@pragma('vm:entry-point')
Future<void> _firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  devPrint('Handling a background message: ${message.data}');
  final data = AppNotificationService.instance._parseNotification(message);
  AppNotificationService.instance._showNotification(data);
}
