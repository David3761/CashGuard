import 'package:cashctrl/l10n/app_localizations.dart';
import 'package:flutter/material.dart';

/// A custom exception class that is used throughout the app to display user
/// friendly messages. Whenever you need to show an alert, a snack bar, a toast
/// or other one time event, then add a new factory constructor that points
/// to the new exception class.
///
/// Then override its [toString] method if it has a message (or any other
/// printable data) and afterwards, add it to the switch in
/// [getLocalizedMessage].
sealed class UIException implements Exception {
  const factory UIException.serverError(String? message) = ServerError;

  const factory UIException.somethingWentWrong() = UnknownErrorException;

  const factory UIException.noInternet() = NoInternetException;

  const factory UIException.invalidEmail() = InvalidEmailException;

  const factory UIException.allFieldsRequired() = AllFieldsRequiredException;

  const factory UIException.passwordLengthError() = PasswordLengthException;

  const factory UIException.passwordConfirmationMismatch() =
      PasswordConfirmationException;

  const factory UIException.countryCodeRequired() =
      CountryCodeRequiredException;

  const factory UIException.phoneNumberNotValid() =
      PhoneNumberNotValidException;
}

/// An exception that is thrown when a request has failed.
class ServerError implements UIException {
  /// Creates a [ServerError].
  const ServerError(this.message);

  /// The error message of the failing request.
  final String? message;

  @override
  String toString() => message != null ? message! : super.toString();
}

/// An exception that is thrown when an unknown error was encountered.
class UnknownErrorException implements UIException {
  /// Creates a [UnknownErrorException].
  const UnknownErrorException();
}

/// An exception that is thrown when there's no internet connection.
class NoInternetException implements UIException {
  /// Creates a [NoInternetException].
  const NoInternetException();
}

/// An exception that is thrown when the email is invalid.
class InvalidEmailException implements UIException {
  /// Creates a [InvalidEmailException].
  const InvalidEmailException();
}

/// An exception that is thrown when not all the fields of a form are filled in.
class AllFieldsRequiredException implements UIException {
  /// Creates a [AllFieldsRequiredException].
  const AllFieldsRequiredException();
}

/// An exception that is thrown when the password doesn't have the required
/// length.
class PasswordLengthException implements UIException {
  /// Creates a [PasswordLengthException].
  const PasswordLengthException();
}

/// An exception that is thrown when the password and confirmation password
/// don't match.
class PasswordConfirmationException implements UIException {
  /// Creates a [PasswordConfirmationException].
  const PasswordConfirmationException();
}

/// An exception that is thrown when phone number is missing the country code.
class CountryCodeRequiredException implements UIException {
  /// Creates a [CountryCodeRequiredException].
  const CountryCodeRequiredException();
}

/// An exception that is thrown when the phone number doesn't match one of the
/// accepted formats..
class PhoneNumberNotValidException implements UIException {
  /// Creates a [PhoneNumberNotValidException].
  const PhoneNumberNotValidException();
}

/// An exception that is thrown when the `ref` object is used after the object
/// is disposed.
class ProviderDisposedException implements Exception {
  /// Creates a [ProviderDisposedException].
  const ProviderDisposedException();
}

/// Returns the localized message for the given [error].
String getLocalizedMessage(BuildContext context, Object error) {
  final localizations = AppLocalizations.of(context);
  if (error is! UIException) {
    return localizations.somethingWentWrong;
  }
  return switch (error) {
    ServerError(:final String message) => message,
    ServerError(message: null) => localizations.somethingWentWrong,
    UnknownErrorException() => localizations.somethingWentWrong,
    NoInternetException() => localizations.noInternetConnection,
    InvalidEmailException() => localizations.invalidEmail,
    AllFieldsRequiredException() => localizations.allFieldsAreRequired,
    PasswordLengthException() => localizations.passwordLengthError,
    PasswordConfirmationException() =>
      localizations.passwordConfirmationMismatch,
    CountryCodeRequiredException() => localizations.countryCodeRequired,
    PhoneNumberNotValidException() => localizations.phoneNumberNotValid,
  };
}
