import 'package:shared_preferences/shared_preferences.dart';

/// A utility class used for providing a unique id for each notification the app
/// receives.
///
/// Thus, no notification will overwrite the previous one.
class NotificationId {
  NotificationId._();

  static const _notificationIdKey = 'notification_id';

  /// Returns the singleton instance of this class.
  static final instance = NotificationId._();

  var _counter = 0;

  /// Increments the [_counter] by 1 and returns the new value.
  int getId() => ++_counter;

  /// Saves the current [_counter] value in the [SharedPreferences].
  Future<void> saveCurrentId() async {
    final sharedPref = await SharedPreferences.getInstance();
    await sharedPref.setInt(_notificationIdKey, _counter);
  }

  /// Loads the last saved notification id into the [_counter].
  Future<void> loadLastId() async {
    final sharedPref = await SharedPreferences.getInstance();
    _counter = sharedPref.getInt(_notificationIdKey) ?? 0;
  }
}
