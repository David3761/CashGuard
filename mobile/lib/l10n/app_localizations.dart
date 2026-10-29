import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'app_localizations_en.dart';

// ignore_for_file: type=lint

/// Callers can lookup localized strings with an instance of AppLocalizations
/// returned by `AppLocalizations.of(context)`.
///
/// Applications need to include `AppLocalizations.delegate()` in their app's
/// `localizationDelegates` list, and the locales they support in the app's
/// `supportedLocales` list. For example:
///
/// ```dart
/// import 'l10n/app_localizations.dart';
///
/// return MaterialApp(
///   localizationsDelegates: AppLocalizations.localizationsDelegates,
///   supportedLocales: AppLocalizations.supportedLocales,
///   home: MyApplicationHome(),
/// );
/// ```
///
/// ## Update pubspec.yaml
///
/// Please make sure to update your pubspec.yaml to include the following
/// packages:
///
/// ```yaml
/// dependencies:
///   # Internationalization support.
///   flutter_localizations:
///     sdk: flutter
///   intl: any # Use the pinned version from flutter_localizations
///
///   # Rest of dependencies
/// ```
///
/// ## iOS Applications
///
/// iOS applications define key application metadata, including supported
/// locales, in an Info.plist file that is built into the application bundle.
/// To configure the locales supported by your app, you’ll need to edit this
/// file.
///
/// First, open your project’s ios/Runner.xcworkspace Xcode workspace file.
/// Then, in the Project Navigator, open the Info.plist file under the Runner
/// project’s Runner folder.
///
/// Next, select the Information Property List item, select Add Item from the
/// Editor menu, then select Localizations from the pop-up menu.
///
/// Select and expand the newly-created Localizations item then, for each
/// locale your application supports, add a new item and select the locale
/// you wish to add from the pop-up menu in the Value field. This list should
/// be consistent with the languages listed in the AppLocalizations.supportedLocales
/// property.
abstract class AppLocalizations {
  AppLocalizations(String locale)
    : localeName = intl.Intl.canonicalizedLocale(locale.toString());

  final String localeName;

  static AppLocalizations of(BuildContext context) {
    return Localizations.of<AppLocalizations>(context, AppLocalizations)!;
  }

  static const LocalizationsDelegate<AppLocalizations> delegate =
      _AppLocalizationsDelegate();

  /// A list of this localizations delegate along with the default localizations
  /// delegates.
  ///
  /// Returns a list of localizations delegates containing this delegate along with
  /// GlobalMaterialLocalizations.delegate, GlobalCupertinoLocalizations.delegate,
  /// and GlobalWidgetsLocalizations.delegate.
  ///
  /// Additional delegates can be added by appending to this list in
  /// MaterialApp. This list does not have to be used at all if a custom list
  /// of delegates is preferred or required.
  static const List<LocalizationsDelegate<dynamic>> localizationsDelegates =
      <LocalizationsDelegate<dynamic>>[
        delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
      ];

  /// A list of this localizations delegate's supported locales.
  static const List<Locale> supportedLocales = <Locale>[Locale('en')];

  /// No description provided for @appName.
  ///
  /// In en, this message translates to:
  /// **'CashCtrl'**
  String get appName;

  /// No description provided for @channelNotification.
  ///
  /// In en, this message translates to:
  /// **'Main Notifications'**
  String get channelNotification;

  /// No description provided for @channelNotificationDescription.
  ///
  /// In en, this message translates to:
  /// **'This is the main notification channel for CashCtrl'**
  String get channelNotificationDescription;

  /// No description provided for @error_.
  ///
  /// In en, this message translates to:
  /// **'Error!'**
  String get error_;

  /// No description provided for @alert.
  ///
  /// In en, this message translates to:
  /// **'Alert'**
  String get alert;

  /// No description provided for @yes.
  ///
  /// In en, this message translates to:
  /// **'Yes'**
  String get yes;

  /// No description provided for @no.
  ///
  /// In en, this message translates to:
  /// **'No'**
  String get no;

  /// No description provided for @ok.
  ///
  /// In en, this message translates to:
  /// **'OK'**
  String get ok;

  /// No description provided for @somethingWentWrong.
  ///
  /// In en, this message translates to:
  /// **'Something went wrong. Please try again.'**
  String get somethingWentWrong;

  /// No description provided for @noInternetConnection.
  ///
  /// In en, this message translates to:
  /// **'No internet connection available!'**
  String get noInternetConnection;

  /// No description provided for @account.
  ///
  /// In en, this message translates to:
  /// **'Account'**
  String get account;

  /// No description provided for @logoutConfirmation.
  ///
  /// In en, this message translates to:
  /// **'Are you sure you want to logout?'**
  String get logoutConfirmation;

  /// No description provided for @logout.
  ///
  /// In en, this message translates to:
  /// **'Log out'**
  String get logout;

  /// No description provided for @login.
  ///
  /// In en, this message translates to:
  /// **'Login'**
  String get login;

  /// No description provided for @register.
  ///
  /// In en, this message translates to:
  /// **'Register'**
  String get register;

  /// No description provided for @emailAddress.
  ///
  /// In en, this message translates to:
  /// **'Email address'**
  String get emailAddress;

  /// No description provided for @password.
  ///
  /// In en, this message translates to:
  /// **'Password'**
  String get password;

  /// No description provided for @passwordConfirmation.
  ///
  /// In en, this message translates to:
  /// **'Password confirmation'**
  String get passwordConfirmation;

  /// No description provided for @newPassword.
  ///
  /// In en, this message translates to:
  /// **'New password'**
  String get newPassword;

  /// No description provided for @retypePassword.
  ///
  /// In en, this message translates to:
  /// **'Retype password'**
  String get retypePassword;

  /// No description provided for @name.
  ///
  /// In en, this message translates to:
  /// **'Name'**
  String get name;

  /// No description provided for @fullName.
  ///
  /// In en, this message translates to:
  /// **'Full Name'**
  String get fullName;

  /// No description provided for @phone.
  ///
  /// In en, this message translates to:
  /// **'Phone'**
  String get phone;

  /// No description provided for @forgotPassword.
  ///
  /// In en, this message translates to:
  /// **'Forgot password'**
  String get forgotPassword;

  /// No description provided for @forgotPassword_.
  ///
  /// In en, this message translates to:
  /// **'Forgot password?'**
  String get forgotPassword_;

  /// No description provided for @enterEmail.
  ///
  /// In en, this message translates to:
  /// **'Enter your email address and we\'ll send you a link to reset your password.'**
  String get enterEmail;

  /// No description provided for @requestReset.
  ///
  /// In en, this message translates to:
  /// **'Request reset link'**
  String get requestReset;

  /// No description provided for @changePassword.
  ///
  /// In en, this message translates to:
  /// **'Change password'**
  String get changePassword;

  /// No description provided for @uploadYourPicture.
  ///
  /// In en, this message translates to:
  /// **'Upload your picture'**
  String get uploadYourPicture;

  /// No description provided for @cancel.
  ///
  /// In en, this message translates to:
  /// **'Cancel'**
  String get cancel;

  /// No description provided for @allFieldsAreRequired.
  ///
  /// In en, this message translates to:
  /// **'All fields are required.'**
  String get allFieldsAreRequired;

  /// No description provided for @invalidEmail.
  ///
  /// In en, this message translates to:
  /// **'Invalid email.'**
  String get invalidEmail;

  /// No description provided for @countryCodeRequired.
  ///
  /// In en, this message translates to:
  /// **'The country code is required for the phone number.'**
  String get countryCodeRequired;

  /// No description provided for @phoneNumberNotValid.
  ///
  /// In en, this message translates to:
  /// **'The number is not valid.'**
  String get phoneNumberNotValid;

  /// No description provided for @resetLinkSent.
  ///
  /// In en, this message translates to:
  /// **'We sent you an email with instructions for resetting your password.'**
  String get resetLinkSent;

  /// No description provided for @gender.
  ///
  /// In en, this message translates to:
  /// **'Gender'**
  String get gender;

  /// No description provided for @passwordLengthError.
  ///
  /// In en, this message translates to:
  /// **'Your password must contains at least 6 characters!'**
  String get passwordLengthError;

  /// No description provided for @passwordConfirmationMismatch.
  ///
  /// In en, this message translates to:
  /// **'Password does not match the confirm password!'**
  String get passwordConfirmationMismatch;

  /// No description provided for @accountCreated.
  ///
  /// In en, this message translates to:
  /// **'Your account has been created!'**
  String get accountCreated;

  /// No description provided for @versionOf.
  ///
  /// In en, this message translates to:
  /// **'Version {value}'**
  String versionOf(Object value);

  /// No description provided for @pageNotLoaded.
  ///
  /// In en, this message translates to:
  /// **'Error! The page could not be loaded!'**
  String get pageNotLoaded;

  /// No description provided for @couldNotOpenUrl.
  ///
  /// In en, this message translates to:
  /// **'We couldn\'t open the url.'**
  String get couldNotOpenUrl;

  /// No description provided for @gendersList.
  ///
  /// In en, this message translates to:
  /// **'Male|Female|Other'**
  String get gendersList;

  /// No description provided for @settings.
  ///
  /// In en, this message translates to:
  /// **'Settings'**
  String get settings;

  /// No description provided for @transactions.
  ///
  /// In en, this message translates to:
  /// **'Transactions'**
  String get transactions;

  /// No description provided for @assistant.
  ///
  /// In en, this message translates to:
  /// **'Assistant'**
  String get assistant;

  /// No description provided for @currentBalance.
  ///
  /// In en, this message translates to:
  /// **'Current balance'**
  String get currentBalance;

  /// No description provided for @search.
  ///
  /// In en, this message translates to:
  /// **'Search'**
  String get search;

  /// No description provided for @today.
  ///
  /// In en, this message translates to:
  /// **'Today'**
  String get today;

  /// No description provided for @yesterday.
  ///
  /// In en, this message translates to:
  /// **'Yesterday'**
  String get yesterday;

  /// No description provided for @noTransactionsFound.
  ///
  /// In en, this message translates to:
  /// **'No transactions found.'**
  String get noTransactionsFound;

  /// No description provided for @filters.
  ///
  /// In en, this message translates to:
  /// **'Filters'**
  String get filters;

  /// No description provided for @type.
  ///
  /// In en, this message translates to:
  /// **'Type'**
  String get type;

  /// No description provided for @amount.
  ///
  /// In en, this message translates to:
  /// **'Amount'**
  String get amount;

  /// No description provided for @period.
  ///
  /// In en, this message translates to:
  /// **'Period'**
  String get period;

  /// No description provided for @choosePeriod.
  ///
  /// In en, this message translates to:
  /// **'Choose period'**
  String get choosePeriod;

  /// No description provided for @reset.
  ///
  /// In en, this message translates to:
  /// **'Reset'**
  String get reset;

  /// No description provided for @applyFilters.
  ///
  /// In en, this message translates to:
  /// **'Apply filters'**
  String get applyFilters;

  /// No description provided for @cardPayments.
  ///
  /// In en, this message translates to:
  /// **'Card payments'**
  String get cardPayments;

  /// No description provided for @incomingTransfers.
  ///
  /// In en, this message translates to:
  /// **'Incoming transfers'**
  String get incomingTransfers;

  /// No description provided for @outgoingTransfers.
  ///
  /// In en, this message translates to:
  /// **'Outgoing transfers'**
  String get outgoingTransfers;

  /// No description provided for @amountUnder50.
  ///
  /// In en, this message translates to:
  /// **'Under 50 lei'**
  String get amountUnder50;

  /// No description provided for @amount50To500.
  ///
  /// In en, this message translates to:
  /// **'50 – 500 lei'**
  String get amount50To500;

  /// No description provided for @amountOver500.
  ///
  /// In en, this message translates to:
  /// **'Over 500 lei'**
  String get amountOver500;

  /// No description provided for @assistantGreeting.
  ///
  /// In en, this message translates to:
  /// **'Hi there'**
  String get assistantGreeting;

  /// No description provided for @assistantIntro.
  ///
  /// In en, this message translates to:
  /// **'I\'m your CashCtrl assistant.\nAsk me about your transactions, spending or balance.'**
  String get assistantIntro;

  /// No description provided for @tryLabel.
  ///
  /// In en, this message translates to:
  /// **'TRY'**
  String get tryLabel;

  /// No description provided for @suggestionWeeklySpending.
  ///
  /// In en, this message translates to:
  /// **'How much did I spend this week?'**
  String get suggestionWeeklySpending;

  /// No description provided for @suggestionBiggestExpense.
  ///
  /// In en, this message translates to:
  /// **'What was my biggest expense?'**
  String get suggestionBiggestExpense;

  /// No description provided for @suggestionBalance.
  ///
  /// In en, this message translates to:
  /// **'What\'s my current balance?'**
  String get suggestionBalance;

  /// No description provided for @suggestionIncomingMoney.
  ///
  /// In en, this message translates to:
  /// **'Who sent me money recently?'**
  String get suggestionIncomingMoney;

  /// No description provided for @messageHint.
  ///
  /// In en, this message translates to:
  /// **'Write a message…'**
  String get messageHint;

  /// No description provided for @sendMessage.
  ///
  /// In en, this message translates to:
  /// **'Send message'**
  String get sendMessage;

  /// No description provided for @amountInLei.
  ///
  /// In en, this message translates to:
  /// **'{amount} lei'**
  String amountInLei(String amount);

  /// No description provided for @viewData.
  ///
  /// In en, this message translates to:
  /// **'View data'**
  String get viewData;

  /// No description provided for @deleteData.
  ///
  /// In en, this message translates to:
  /// **'Delete data'**
  String get deleteData;

  /// No description provided for @viewDataEmailSent.
  ///
  /// In en, this message translates to:
  /// **'An email with your data has been sent.'**
  String get viewDataEmailSent;

  /// No description provided for @deleteDataEmailSent.
  ///
  /// In en, this message translates to:
  /// **'Confirm the deletion of your account by clicking the button in the email!'**
  String get deleteDataEmailSent;
}

class _AppLocalizationsDelegate
    extends LocalizationsDelegate<AppLocalizations> {
  const _AppLocalizationsDelegate();

  @override
  Future<AppLocalizations> load(Locale locale) {
    return SynchronousFuture<AppLocalizations>(lookupAppLocalizations(locale));
  }

  @override
  bool isSupported(Locale locale) =>
      <String>['en'].contains(locale.languageCode);

  @override
  bool shouldReload(_AppLocalizationsDelegate old) => false;
}

AppLocalizations lookupAppLocalizations(Locale locale) {
  // Lookup logic when only language code is specified.
  switch (locale.languageCode) {
    case 'en':
      return AppLocalizationsEn();
  }

  throw FlutterError(
    'AppLocalizations.delegate failed to load unsupported locale "$locale". This is likely '
    'an issue with the localizations generation tool. Please file an issue '
    'on GitHub with a reproducible sample app and the gen-l10n configuration '
    'that was used.',
  );
}
