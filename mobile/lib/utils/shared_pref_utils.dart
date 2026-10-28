import 'package:cashctrl/core/models/auth_details.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// A utility class used for storing data in the SharedPreferences (on Android
/// it uses the SharedPreferences and on iOS it uses the UserDefaults).
class SharedPrefUtils {
  SharedPrefUtils._();

  /// Returns the singleton instance of this class.
  static final instance = SharedPrefUtils._();

  final _authTokenKey = 'auth_token';
  final _refreshTokenKey = 'refresh_token';

  /// Creates an [AuthDetails] from the SharedPreferences data.
  Future<AuthDetails?> getAuthDetails() async {
    final sharedPref = await SharedPreferences.getInstance();
    final authToken = sharedPref.getString(_authTokenKey);
    final refreshToken = sharedPref.getString(_refreshTokenKey);
    if (authToken == null || refreshToken == null) {
      return null;
    }
    return AuthDetails(authToken: authToken, refreshToken: refreshToken);
  }

  /// Saves the auth details to the SharedPreferences.
  Future<void> saveAuthDetails(AuthDetails authDetails) async {
    final sharedPref = await SharedPreferences.getInstance();
    await sharedPref.setString(_authTokenKey, authDetails.authToken);
    await sharedPref.setString(_refreshTokenKey, authDetails.refreshToken);
  }

  /// Clears the auth details from SharedPreferences.
  Future<void> removeAuthDetails() async {
    final sharedPref = await SharedPreferences.getInstance();
    await sharedPref.remove(_authTokenKey);
    await sharedPref.remove(_refreshTokenKey);
  }
}
