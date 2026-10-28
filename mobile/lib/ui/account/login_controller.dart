import 'dart:async';

import 'package:cashctrl/core/repositories/user_repository.dart';
import 'package:cashctrl/core/request/api_client.dart';
import 'package:cashctrl/core/utils/logging.dart';
import 'package:cashctrl/main_providers.dart';
import 'package:cashctrl/utils/connection_util.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Makes a request to remove the device token from the server, then it
/// removes the user's data from the local files and invalidates the
/// [authProvider] in order to trigger an update in the UI (i.e.: redirect
/// the user to the login screen).
Future<void> logout(Ref ref, {bool internetRequired = false}) async {
  if (internetRequired) {
    final hasInternetConnection =
        await ConnectionUtil.checkInternetConnection();
    if (!hasInternetConnection) {
      return;
    }
  }

  unawaited(ref.read(authProvider.notifier).logout());
}

/// Retrieves the current device token and calls [_sendOrDeleteDeviceToken] to
/// add or remove it from the server depending on the [deleteToken] flag.
Future<void> sendOrDeleteDeviceToken(
  Ref ref, {
  required bool deleteToken,
}) async {
  final deviceToken = await FirebaseMessaging.instance.getToken();
  if (deviceToken == null) {
    return;
  }

  await _sendOrDeleteDeviceToken(ref, deviceToken, deleteToken);
}

/// Makes a request to add the given [deviceToken] to the server if
/// [deleteToken] is `false` or makes a request to remove it if it's `true`.
Future<void> _sendOrDeleteDeviceToken(
  Ref ref,
  String deviceToken,
  bool deleteToken,
) async {
  final body = {'device_token': deviceToken, 'device_type': '1'};

  final dynamic json;

  try {
    if (deleteToken) {
      json = await ref.read(apiServiceProvider).deleteDeviceToken(body);
    } else {
      json = await ref.read(apiServiceProvider).postDeviceToken(body);
    }

    devPrint('Device token request: $json');

    if (deleteToken) {
      await ref.read(userRepositoryProvider).logoutUserLocally();
    }
  } on Exception catch (e, stacktrace) {
    unawaited(logException(e, stackTrace: stacktrace));
  }
}
