// ignore: unused_import
import 'package:intl/intl.dart' as intl;

import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class AppLocalizationsEn extends AppLocalizations {
  AppLocalizationsEn([String locale = 'en']) : super(locale);

  @override
  String get appName => 'CashCtrl';

  @override
  String get channelNotification => 'Main Notifications';

  @override
  String get channelNotificationDescription =>
      'This is the main notification channel for CashCtrl';

  @override
  String get error_ => 'Error!';

  @override
  String get alert => 'Alert';

  @override
  String get yes => 'Yes';

  @override
  String get no => 'No';

  @override
  String get ok => 'OK';

  @override
  String get somethingWentWrong => 'Something went wrong. Please try again.';

  @override
  String get noInternetConnection => 'No internet connection available!';

  @override
  String get account => 'Account';

  @override
  String get logoutConfirmation => 'Are you sure you want to logout?';

  @override
  String get logout => 'Log out';

  @override
  String get login => 'Login';

  @override
  String get register => 'Register';

  @override
  String get emailAddress => 'Email address';

  @override
  String get password => 'Password';

  @override
  String get passwordConfirmation => 'Password confirmation';

  @override
  String get newPassword => 'New password';

  @override
  String get retypePassword => 'Retype password';

  @override
  String get name => 'Name';

  @override
  String get fullName => 'Full Name';

  @override
  String get phone => 'Phone';

  @override
  String get forgotPassword => 'Forgot password';

  @override
  String get forgotPassword_ => 'Forgot password?';

  @override
  String get enterEmail =>
      'Enter your email address and we\'ll send you a link to reset your password.';

  @override
  String get requestReset => 'Request reset link';

  @override
  String get changePassword => 'Change password';

  @override
  String get uploadYourPicture => 'Upload your picture';

  @override
  String get cancel => 'Cancel';

  @override
  String get allFieldsAreRequired => 'All fields are required.';

  @override
  String get invalidEmail => 'Invalid email.';

  @override
  String get countryCodeRequired =>
      'The country code is required for the phone number.';

  @override
  String get phoneNumberNotValid => 'The number is not valid.';

  @override
  String get resetLinkSent =>
      'We sent you an email with instructions for resetting your password.';

  @override
  String get gender => 'Gender';

  @override
  String get passwordLengthError =>
      'Your password must contains at least 6 characters!';

  @override
  String get passwordConfirmationMismatch =>
      'Password does not match the confirm password!';

  @override
  String get accountCreated => 'Your account has been created!';

  @override
  String versionOf(Object value) {
    return 'Version $value';
  }

  @override
  String get pageNotLoaded => 'Error! The page could not be loaded!';

  @override
  String get couldNotOpenUrl => 'We couldn\'t open the url.';

  @override
  String get gendersList => 'Male|Female|Other';

  @override
  String get settings => 'Settings';

  @override
  String get viewData => 'View data';

  @override
  String get deleteData => 'Delete data';

  @override
  String get viewDataEmailSent => 'An email with your data has been sent.';

  @override
  String get deleteDataEmailSent =>
      'Confirm the deletion of your account by clicking the button in the email!';
}
