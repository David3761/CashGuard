import 'package:cashctrl/core/database/app_database.dart';
import 'package:drift/drift.dart';

// Necessary for code-generation to work
// Run: dart run build_runner watch
part 'user_dao.g.dart';

/// The User DAO that provides access to the [Users] table.
///
/// The `_$UserDaoMixin` will be created by **drift**. It contains all the
/// necessary fields for the table.
@DriftAccessor(tables: [Users])
class UserDao extends DatabaseAccessor<AppDatabase> with _$UserDaoMixin {
  /// Creates a [UserDao].
  UserDao(super.attachedDatabase);

  /// Inserts the given [user] into the database.
  Future<int> insert(User user) {
    return into(users).insert(user);
  }

  /// Returns the first user whose marked as logged in, or null.
  Future<User?> getLoggedIn() {
    return (select(
      users,
    )..where((u) => u.loggedIn.equals(true))).getSingleOrNull();
  }

  /// Returns the user for the given id, or null.
  Future<User?> getUserById(int id) {
    return (select(users)..where((u) => u.id.equals(id))).getSingleOrNull();
  }

  /// Updates the `key` property of the logged in user.
  Future<void> updateKey(String key) {
    return (update(users)..where((u) => u.loggedIn.equals(true))).write(
      UsersCompanion(key: Value(key)),
    );
  }

  /// Marks the logged in user as logged out.
  Future<void> logoutUser() {
    return (update(users)..where((u) => u.loggedIn.equals(true))).write(
      const UsersCompanion(loggedIn: Value(false)),
    );
  }
}
