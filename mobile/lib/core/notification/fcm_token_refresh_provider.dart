import 'dart:async';

import 'package:cashctrl/core/notification/app_notification_service.dart';
import 'package:cashctrl/core/utils/retry.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

// Necessary for code-generation to work
// Run: dart run build_runner watch
part 'fcm_token_refresh_provider.g.dart';

/// The provider that handles the Firebase device token refresh. Whenever the
/// token is refreshed by the operating system, the new token will be sent to
/// the server.
@riverpod
void fcmTokenRefresh(Ref ref) {
  if (!AppNotificationService.instance.isAvailable) {
    return;
  }

  // final userDataNotifier = ref.watch(userDataProvider.notifier);
  // The provider might be called before Firebase.initializeApp() completes,
  // in which case, we need to retry adding the onTokenRefresh listener until
  // it succeeds.
  unawaited(
    retry(() {
      final subscription = FirebaseMessaging.instance.onTokenRefresh.listen((
        token,
      ) {
        // Note: This callback is fired whenever a new token is generated.
        // unawaited(userDataNotifier.sendDeviceToken());

        /*if (AppDatabase.getAppDatabase(applicationContext)
          .userDao()
          .isLoggedIn() != 0L) {
        AppDatabase
            .getAppDatabase(applicationContext)
            .userDao()
            .getLoggedIn()
            ?.let {
          LoginController.sendOrDeleteDeviceToken(
              application, serviceScope, false)
        }
      }*/
      });
      ref.onDispose(subscription.cancel);
    }),
  );
}
