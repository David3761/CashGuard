import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:internet_connection_checker_plus/internet_connection_checker_plus.dart';

/// The class that provides a method for checking if there is an internet
/// connection available.
///
/// The class can be used as either a on-off use by calling the static method
/// [checkInternetConnection] or if a listener is needed, then it must be
/// initialized first (call [initialize]) and then retrieve the
/// [connectionChange] stream and listen to it. When you don't need the
/// listener anymore, first cancel your [StreamSubscription] that was returned
/// by listening the [connectionChange] stream and then call the [dispose]
/// method of this class.
class ConnectionUtil {
  var _hasConnection = false;
  final _connectionChangeController = StreamController<bool>();
  final _connectivity = Connectivity();
  StreamSubscription<List<ConnectivityResult>>? _connectivitySubscription;

  /// Initializes the [_connectivity] listener.
  void initialize() {
    _connectivitySubscription = _connectivity.onConnectivityChanged.listen(
      _connectionChange,
    );
  }

  /// Calls [_hasInternetInternetConnection] with the given [result].
  void _connectionChange(List<ConnectivityResult> result) {
    unawaited(_hasInternetInternetConnection(result));
  }

  /// Returns a stream that can be listened for connection changes.
  Stream<bool> get connectionChange => _connectionChangeController.stream;

  /// Checks if the connection change is related to mobile data or wifi and if
  /// so, then it checks to see if the device has an internet connection.
  Future<bool> _hasInternetInternetConnection(
    List<ConnectivityResult> result,
  ) async {
    final previousConnection = _hasConnection;
    // var connectivityResult = await (Connectivity().checkConnectivity());
    if (result.contains(ConnectivityResult.mobile) ||
        result.contains(ConnectivityResult.wifi)) {
      _hasConnection = await InternetConnection().hasInternetAccess;
    } else {
      _hasConnection = false;
    }

    if (previousConnection != _hasConnection) {
      _connectionChangeController.add(_hasConnection);
    }
    return _hasConnection;
  }

  /// Disposes the [_connectivitySubscription].
  /// The [_connectionChangeController] can be left alone because it won't send
  /// new data.
  void dispose() {
    unawaited(_connectivitySubscription?.cancel());
  }

  /// Returns a [Future] which contains `true` if the device has an internet
  /// connection or `false` otherwise.
  ///
  /// The method is safe to be called everywhere.
  ///
  /// **Note**: In some cases, this method takes ~5s to execute. Calling this
  /// method before every request might add some delay (this was already seen
  /// in the past); you shouldn't use it in those scenarios.
  static Future<bool> checkInternetConnection() async {
    final result = await Connectivity().checkConnectivity();
    if (result.contains(ConnectivityResult.mobile) ||
        result.contains(ConnectivityResult.wifi)) {
      return InternetConnection().hasInternetAccess;
    } else {
      return false;
    }
  }
}
