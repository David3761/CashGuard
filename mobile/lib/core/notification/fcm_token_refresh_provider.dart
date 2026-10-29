import 'dart:async';

import 'package:cashctrl/core/notification/app_notification_service.dart';
import 'package:cashctrl/core/utils/retry.dart';
import 'package:cashctrl/ui/account/login_controller.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

// Necessary for code-generation to work
// Run: dart run build_runner watch
part 'fcm_token_refresh_provider.g.dart';

/// The provider that sends the Firebase device token to the server when the
/// app starts and whenever the token is refreshed by the operating system.
@riverpod
void fcmTokenRefresh(Ref ref) {
  if (!AppNotificationService.instance.isAvailable) {
    return;
  }

  unawaited(sendOrDeleteDeviceToken(ref, deleteToken: false));
  // The provider might be called before Firebase.initializeApp() completes,
  // in which case, we need to retry adding the onTokenRefresh listener until
  // it succeeds.
  unawaited(
    retry(() {
      final subscription = FirebaseMessaging.instance.onTokenRefresh.listen((
        _,
      ) {
        unawaited(sendOrDeleteDeviceToken(ref, deleteToken: false));
      });
      ref.onDispose(subscription.cancel);
    }),
  );
}
