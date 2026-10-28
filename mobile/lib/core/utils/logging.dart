import 'dart:developer';

import 'package:cashctrl/exceptions.dart';
import 'package:flutter/foundation.dart';

/// Prints a developer log only when running the app in debug mode. The log
/// doesn't have a character limit.
void devPrint(String message, {StackTrace? stackTrace}) {
  if (kDebugMode) {
    log(message, stackTrace: stackTrace, name: 'DEVELOPER LOG');
  }
}

/// Uses the [devPrint] method to record the exception.
///
/// You are strongly encouraged to pass in a [stackTrace] so that the logged
/// exception is easier to debug. You may use [StackTrace.current] if you're
/// calling this method from outside a catch block.
Future<void> logException(Object exception, {StackTrace? stackTrace}) async {
  if (exception is ProviderDisposedException) {
    return;
  }
  final stack = (stackTrace == null || stackTrace.toString().isEmpty)
      ? StackTrace.current
      : stackTrace;
  devPrint('$exception', stackTrace: stack);
}
