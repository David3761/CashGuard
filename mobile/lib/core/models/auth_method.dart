import 'package:drift/drift.dart';

/// An enum class that lists all types of auth methods: email.
enum AuthMethod {
  /// The email option.
  email(0);

  const AuthMethod(this.id);

  // Returns the enum value for the given [id].
  factory AuthMethod.fromId(int id) {
    return values.firstWhere((e) => e.id == id);
  }

  /// The id of the auth method option.
  final int id;
}

/// Utility class for the database that provides bidirectional conversion
/// between an [AuthMethod] object and its id as [int].
class AuthMethodConverter extends TypeConverter<AuthMethod, int>
    with JsonTypeConverter<AuthMethod, int> {
  /// Creates an [AuthMethodConverter].
  const AuthMethodConverter();

  @override
  AuthMethod fromSql(int fromDb) => .fromId(fromDb);

  @override
  int toSql(AuthMethod value) => value.id;
}
