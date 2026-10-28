import 'package:cashctrl/core/database/user_dao.dart';
import 'package:cashctrl/core/models/auth_method.dart';
import 'package:drift/drift.dart';
import 'package:drift_flutter/drift_flutter.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

// Necessary for code-generation to work
// Run: dart run build_runner watch
part 'app_database.g.dart';

/// The provider that returns an instance of `AppDatabase`.
@riverpod
AppDatabase appDatabase(Ref ref) {
  final appDatabase = AppDatabase._(ref);
  ref.onDispose(appDatabase.close);
  return appDatabase;
}

/// A utility class used for accessing a database.
///
/// The tables that it handles: [Users].
@DriftDatabase(tables: [Users], daos: [UserDao])
class AppDatabase extends _$AppDatabase {
  /// After generating code, this class needs to define a schemaVersion getter
  /// and a constructor telling drift where the database should be stored.
  /// These are described in the getting started guide:
  /// https://drift.simonbinder.eu/getting-started/#open
  AppDatabase._(this.ref) : super(_openConnection());

  /// A [Ref] object used to access any providers (such as `ApiService`).
  final Ref ref;

  @override
  int get schemaVersion => 1;

  /// Creates a [DriftDatabase] instance and returns it.
  static QueryExecutor _openConnection() {
    // The driftDatabase from package:drift_flutter stores the database in
    // getApplicationDocumentsDirectory().
    return driftDatabase(name: 'app_database');
  }
}

/// A table class for storing users.
class Users extends Table {
  /// The user's id.
  IntColumn get id => integer().autoIncrement()();

  /// The user's email.
  @JsonKey('mail')
  TextColumn get email => text()();

  /// The user's password.
  TextColumn get key => text()();

  /// The user's auth method.
  @JsonKey('auth_method')
  IntColumn get authMethod => integer().map(const AuthMethodConverter())();

  /// The user's full name.
  @JsonKey('full_name')
  TextColumn get name => text().nullable()();

  /// The user's phone.
  TextColumn get phone => text().nullable()();

  /// The user's photo.
  TextColumn get photo => text().nullable()();

  /// The user's logged in status.
  BoolColumn get loggedIn => boolean()();

  // If the primary key is not an auto-incremented field, then we need to
  // specify it explicitly.
  // @override
  // Set<Column> get primaryKey => {id};
}
