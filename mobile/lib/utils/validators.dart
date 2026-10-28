/// The main class that contains various validators.
class Validators {
  Validators._();

  /// Returns the singleton instance of this class.
  static final instance = Validators._();

  final _emailRegex = RegExp(
    r'''^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,253}[a-zA-Z0-9])?(?:.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,253}[a-zA-Z0-9])?)*$''',
  );
  final _phoneRegex = RegExp(r'((\+)|(00))[0-9]{6,14}');
  final _alphanumericRegex = RegExp(r'^[a-zA-Z0-9]+$');

  /// The minimum length of the password.
  final passwordMinLength = 8;

  /// Checks whether the [email] is a valid email using a regex.
  bool isEmailValid(String email) => _emailRegex.hasMatch(email);

  /// Checks whether the [password] is at least [passwordMinLength] characters
  /// long and includes at least one letter, one digit and one special
  /// character.
  bool isPasswordValid(String password) {
    return password.length >= passwordMinLength &&
        containsAtLeastOneLetter(password) &&
        containsAtLeastOneDigit(password) &&
        !isAlphanumeric(password);
  }

  /// Checks whether the [input] contains at least one letter.
  bool containsAtLeastOneLetter(String input) {
    final regex = RegExp('[a-zA-Z]');
    return regex.hasMatch(input);
  }

  /// Checks whether the [input] contains at least one digit.
  bool containsAtLeastOneDigit(String input) {
    final regex = RegExp(r'\d');
    return regex.hasMatch(input);
  }

  /// Checks whether the [input] contains only letters and numbers.
  bool isAlphanumeric(String input) => _alphanumericRegex.hasMatch(input);

  /// Checks whether the [phoneNumber] is a valid number using a regex:
  /// - the country code is required
  /// - the number must look like a phone number
  PhoneNumberState isPhoneValid(String phoneNumber) {
    if (!phoneNumber.startsWith('+') && !phoneNumber.startsWith('00')) {
      return .countryCodeRequired;
    }
    if (!_phoneRegex.hasMatch(phoneNumber)) {
      return .phoneNumberNotValid;
    }
    return .valid;
  }
}

/// An enum that lists all possible states of the phone number validation
/// process.
enum PhoneNumberState {
  /// The phone number is missing the country code.
  countryCodeRequired,

  /// The phone number doesn't match one of the accepted formats.
  phoneNumberNotValid,

  /// The phone number is valid.
  valid,
}
