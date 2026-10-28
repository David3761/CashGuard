// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'app_database.dart';

// ignore_for_file: type=lint
class $UsersTable extends Users with TableInfo<$UsersTable, User> {
  @override
  final GeneratedDatabase attachedDatabase;
  final String? _alias;
  $UsersTable(this.attachedDatabase, [this._alias]);
  static const VerificationMeta _idMeta = const VerificationMeta('id');
  @override
  late final GeneratedColumn<int> id = GeneratedColumn<int>(
    'id',
    aliasedName,
    false,
    hasAutoIncrement: true,
    type: DriftSqlType.int,
    requiredDuringInsert: false,
    defaultConstraints: GeneratedColumn.constraintIsAlways(
      'PRIMARY KEY AUTOINCREMENT',
    ),
  );
  static const VerificationMeta _emailMeta = const VerificationMeta('email');
  @override
  late final GeneratedColumn<String> email = GeneratedColumn<String>(
    'email',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _keyMeta = const VerificationMeta('key');
  @override
  late final GeneratedColumn<String> key = GeneratedColumn<String>(
    'key',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  @override
  late final GeneratedColumnWithTypeConverter<AuthMethod, int> authMethod =
      GeneratedColumn<int>(
        'auth_method',
        aliasedName,
        false,
        type: DriftSqlType.int,
        requiredDuringInsert: true,
      ).withConverter<AuthMethod>($UsersTable.$converterauthMethod);
  static const VerificationMeta _nameMeta = const VerificationMeta('name');
  @override
  late final GeneratedColumn<String> name = GeneratedColumn<String>(
    'name',
    aliasedName,
    true,
    type: DriftSqlType.string,
    requiredDuringInsert: false,
  );
  static const VerificationMeta _phoneMeta = const VerificationMeta('phone');
  @override
  late final GeneratedColumn<String> phone = GeneratedColumn<String>(
    'phone',
    aliasedName,
    true,
    type: DriftSqlType.string,
    requiredDuringInsert: false,
  );
  static const VerificationMeta _photoMeta = const VerificationMeta('photo');
  @override
  late final GeneratedColumn<String> photo = GeneratedColumn<String>(
    'photo',
    aliasedName,
    true,
    type: DriftSqlType.string,
    requiredDuringInsert: false,
  );
  static const VerificationMeta _loggedInMeta = const VerificationMeta(
    'loggedIn',
  );
  @override
  late final GeneratedColumn<bool> loggedIn = GeneratedColumn<bool>(
    'logged_in',
    aliasedName,
    false,
    type: DriftSqlType.bool,
    requiredDuringInsert: true,
    defaultConstraints: GeneratedColumn.constraintIsAlways(
      'CHECK ("logged_in" IN (0, 1))',
    ),
  );
  @override
  List<GeneratedColumn> get $columns => [
    id,
    email,
    key,
    authMethod,
    name,
    phone,
    photo,
    loggedIn,
  ];
  @override
  String get aliasedName => _alias ?? actualTableName;
  @override
  String get actualTableName => $name;
  static const String $name = 'users';
  @override
  VerificationContext validateIntegrity(
    Insertable<User> instance, {
    bool isInserting = false,
  }) {
    final context = VerificationContext();
    final data = instance.toColumns(true);
    if (data.containsKey('id')) {
      context.handle(_idMeta, id.isAcceptableOrUnknown(data['id']!, _idMeta));
    }
    if (data.containsKey('email')) {
      context.handle(
        _emailMeta,
        email.isAcceptableOrUnknown(data['email']!, _emailMeta),
      );
    } else if (isInserting) {
      context.missing(_emailMeta);
    }
    if (data.containsKey('key')) {
      context.handle(
        _keyMeta,
        key.isAcceptableOrUnknown(data['key']!, _keyMeta),
      );
    } else if (isInserting) {
      context.missing(_keyMeta);
    }
    if (data.containsKey('name')) {
      context.handle(
        _nameMeta,
        name.isAcceptableOrUnknown(data['name']!, _nameMeta),
      );
    }
    if (data.containsKey('phone')) {
      context.handle(
        _phoneMeta,
        phone.isAcceptableOrUnknown(data['phone']!, _phoneMeta),
      );
    }
    if (data.containsKey('photo')) {
      context.handle(
        _photoMeta,
        photo.isAcceptableOrUnknown(data['photo']!, _photoMeta),
      );
    }
    if (data.containsKey('logged_in')) {
      context.handle(
        _loggedInMeta,
        loggedIn.isAcceptableOrUnknown(data['logged_in']!, _loggedInMeta),
      );
    } else if (isInserting) {
      context.missing(_loggedInMeta);
    }
    return context;
  }

  @override
  Set<GeneratedColumn> get $primaryKey => {id};
  @override
  User map(Map<String, dynamic> data, {String? tablePrefix}) {
    final effectivePrefix = tablePrefix != null ? '$tablePrefix.' : '';
    return User(
      id: attachedDatabase.typeMapping.read(
        DriftSqlType.int,
        data['${effectivePrefix}id'],
      )!,
      email: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}email'],
      )!,
      key: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}key'],
      )!,
      authMethod: $UsersTable.$converterauthMethod.fromSql(
        attachedDatabase.typeMapping.read(
          DriftSqlType.int,
          data['${effectivePrefix}auth_method'],
        )!,
      ),
      name: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}name'],
      ),
      phone: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}phone'],
      ),
      photo: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}photo'],
      ),
      loggedIn: attachedDatabase.typeMapping.read(
        DriftSqlType.bool,
        data['${effectivePrefix}logged_in'],
      )!,
    );
  }

  @override
  $UsersTable createAlias(String alias) {
    return $UsersTable(attachedDatabase, alias);
  }

  static JsonTypeConverter2<AuthMethod, int, int> $converterauthMethod =
      const AuthMethodConverter();
}

class User extends DataClass implements Insertable<User> {
  /// The user's id.
  final int id;

  /// The user's email.
  final String email;

  /// The user's password.
  final String key;

  /// The user's auth method.
  final AuthMethod authMethod;

  /// The user's full name.
  final String? name;

  /// The user's phone.
  final String? phone;

  /// The user's photo.
  final String? photo;

  /// The user's logged in status.
  final bool loggedIn;
  const User({
    required this.id,
    required this.email,
    required this.key,
    required this.authMethod,
    this.name,
    this.phone,
    this.photo,
    required this.loggedIn,
  });
  @override
  Map<String, Expression> toColumns(bool nullToAbsent) {
    final map = <String, Expression>{};
    map['id'] = Variable<int>(id);
    map['email'] = Variable<String>(email);
    map['key'] = Variable<String>(key);
    {
      map['auth_method'] = Variable<int>(
        $UsersTable.$converterauthMethod.toSql(authMethod),
      );
    }
    if (!nullToAbsent || name != null) {
      map['name'] = Variable<String>(name);
    }
    if (!nullToAbsent || phone != null) {
      map['phone'] = Variable<String>(phone);
    }
    if (!nullToAbsent || photo != null) {
      map['photo'] = Variable<String>(photo);
    }
    map['logged_in'] = Variable<bool>(loggedIn);
    return map;
  }

  UsersCompanion toCompanion(bool nullToAbsent) {
    return UsersCompanion(
      id: Value(id),
      email: Value(email),
      key: Value(key),
      authMethod: Value(authMethod),
      name: name == null && nullToAbsent ? const Value.absent() : Value(name),
      phone: phone == null && nullToAbsent
          ? const Value.absent()
          : Value(phone),
      photo: photo == null && nullToAbsent
          ? const Value.absent()
          : Value(photo),
      loggedIn: Value(loggedIn),
    );
  }

  factory User.fromJson(
    Map<String, dynamic> json, {
    ValueSerializer? serializer,
  }) {
    serializer ??= driftRuntimeOptions.defaultSerializer;
    return User(
      id: serializer.fromJson<int>(json['id']),
      email: serializer.fromJson<String>(json['mail']),
      key: serializer.fromJson<String>(json['key']),
      authMethod: $UsersTable.$converterauthMethod.fromJson(
        serializer.fromJson<int>(json['auth_method']),
      ),
      name: serializer.fromJson<String?>(json['full_name']),
      phone: serializer.fromJson<String?>(json['phone']),
      photo: serializer.fromJson<String?>(json['photo']),
      loggedIn: serializer.fromJson<bool>(json['loggedIn']),
    );
  }
  @override
  Map<String, dynamic> toJson({ValueSerializer? serializer}) {
    serializer ??= driftRuntimeOptions.defaultSerializer;
    return <String, dynamic>{
      'id': serializer.toJson<int>(id),
      'mail': serializer.toJson<String>(email),
      'key': serializer.toJson<String>(key),
      'auth_method': serializer.toJson<int>(
        $UsersTable.$converterauthMethod.toJson(authMethod),
      ),
      'full_name': serializer.toJson<String?>(name),
      'phone': serializer.toJson<String?>(phone),
      'photo': serializer.toJson<String?>(photo),
      'loggedIn': serializer.toJson<bool>(loggedIn),
    };
  }

  User copyWith({
    int? id,
    String? email,
    String? key,
    AuthMethod? authMethod,
    Value<String?> name = const Value.absent(),
    Value<String?> phone = const Value.absent(),
    Value<String?> photo = const Value.absent(),
    bool? loggedIn,
  }) => User(
    id: id ?? this.id,
    email: email ?? this.email,
    key: key ?? this.key,
    authMethod: authMethod ?? this.authMethod,
    name: name.present ? name.value : this.name,
    phone: phone.present ? phone.value : this.phone,
    photo: photo.present ? photo.value : this.photo,
    loggedIn: loggedIn ?? this.loggedIn,
  );
  User copyWithCompanion(UsersCompanion data) {
    return User(
      id: data.id.present ? data.id.value : this.id,
      email: data.email.present ? data.email.value : this.email,
      key: data.key.present ? data.key.value : this.key,
      authMethod: data.authMethod.present
          ? data.authMethod.value
          : this.authMethod,
      name: data.name.present ? data.name.value : this.name,
      phone: data.phone.present ? data.phone.value : this.phone,
      photo: data.photo.present ? data.photo.value : this.photo,
      loggedIn: data.loggedIn.present ? data.loggedIn.value : this.loggedIn,
    );
  }

  @override
  String toString() {
    return (StringBuffer('User(')
          ..write('id: $id, ')
          ..write('email: $email, ')
          ..write('key: $key, ')
          ..write('authMethod: $authMethod, ')
          ..write('name: $name, ')
          ..write('phone: $phone, ')
          ..write('photo: $photo, ')
          ..write('loggedIn: $loggedIn')
          ..write(')'))
        .toString();
  }

  @override
  int get hashCode =>
      Object.hash(id, email, key, authMethod, name, phone, photo, loggedIn);
  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      (other is User &&
          other.id == this.id &&
          other.email == this.email &&
          other.key == this.key &&
          other.authMethod == this.authMethod &&
          other.name == this.name &&
          other.phone == this.phone &&
          other.photo == this.photo &&
          other.loggedIn == this.loggedIn);
}

class UsersCompanion extends UpdateCompanion<User> {
  final Value<int> id;
  final Value<String> email;
  final Value<String> key;
  final Value<AuthMethod> authMethod;
  final Value<String?> name;
  final Value<String?> phone;
  final Value<String?> photo;
  final Value<bool> loggedIn;
  const UsersCompanion({
    this.id = const Value.absent(),
    this.email = const Value.absent(),
    this.key = const Value.absent(),
    this.authMethod = const Value.absent(),
    this.name = const Value.absent(),
    this.phone = const Value.absent(),
    this.photo = const Value.absent(),
    this.loggedIn = const Value.absent(),
  });
  UsersCompanion.insert({
    this.id = const Value.absent(),
    required String email,
    required String key,
    required AuthMethod authMethod,
    this.name = const Value.absent(),
    this.phone = const Value.absent(),
    this.photo = const Value.absent(),
    required bool loggedIn,
  }) : email = Value(email),
       key = Value(key),
       authMethod = Value(authMethod),
       loggedIn = Value(loggedIn);
  static Insertable<User> custom({
    Expression<int>? id,
    Expression<String>? email,
    Expression<String>? key,
    Expression<int>? authMethod,
    Expression<String>? name,
    Expression<String>? phone,
    Expression<String>? photo,
    Expression<bool>? loggedIn,
  }) {
    return RawValuesInsertable({
      if (id != null) 'id': id,
      if (email != null) 'email': email,
      if (key != null) 'key': key,
      if (authMethod != null) 'auth_method': authMethod,
      if (name != null) 'name': name,
      if (phone != null) 'phone': phone,
      if (photo != null) 'photo': photo,
      if (loggedIn != null) 'logged_in': loggedIn,
    });
  }

  UsersCompanion copyWith({
    Value<int>? id,
    Value<String>? email,
    Value<String>? key,
    Value<AuthMethod>? authMethod,
    Value<String?>? name,
    Value<String?>? phone,
    Value<String?>? photo,
    Value<bool>? loggedIn,
  }) {
    return UsersCompanion(
      id: id ?? this.id,
      email: email ?? this.email,
      key: key ?? this.key,
      authMethod: authMethod ?? this.authMethod,
      name: name ?? this.name,
      phone: phone ?? this.phone,
      photo: photo ?? this.photo,
      loggedIn: loggedIn ?? this.loggedIn,
    );
  }

  @override
  Map<String, Expression> toColumns(bool nullToAbsent) {
    final map = <String, Expression>{};
    if (id.present) {
      map['id'] = Variable<int>(id.value);
    }
    if (email.present) {
      map['email'] = Variable<String>(email.value);
    }
    if (key.present) {
      map['key'] = Variable<String>(key.value);
    }
    if (authMethod.present) {
      map['auth_method'] = Variable<int>(
        $UsersTable.$converterauthMethod.toSql(authMethod.value),
      );
    }
    if (name.present) {
      map['name'] = Variable<String>(name.value);
    }
    if (phone.present) {
      map['phone'] = Variable<String>(phone.value);
    }
    if (photo.present) {
      map['photo'] = Variable<String>(photo.value);
    }
    if (loggedIn.present) {
      map['logged_in'] = Variable<bool>(loggedIn.value);
    }
    return map;
  }

  @override
  String toString() {
    return (StringBuffer('UsersCompanion(')
          ..write('id: $id, ')
          ..write('email: $email, ')
          ..write('key: $key, ')
          ..write('authMethod: $authMethod, ')
          ..write('name: $name, ')
          ..write('phone: $phone, ')
          ..write('photo: $photo, ')
          ..write('loggedIn: $loggedIn')
          ..write(')'))
        .toString();
  }
}

abstract class _$AppDatabase extends GeneratedDatabase {
  _$AppDatabase(QueryExecutor e) : super(e);
  $AppDatabaseManager get managers => $AppDatabaseManager(this);
  late final $UsersTable users = $UsersTable(this);
  late final UserDao userDao = UserDao(this as AppDatabase);
  @override
  Iterable<TableInfo<Table, Object?>> get allTables =>
      allSchemaEntities.whereType<TableInfo<Table, Object?>>();
  @override
  List<DatabaseSchemaEntity> get allSchemaEntities => [users];
}

typedef $$UsersTableCreateCompanionBuilder = UsersCompanion Function({
  Value<int> id,
  required String email,
  required String key,
  required AuthMethod authMethod,
  Value<String?> name,
  Value<String?> phone,
  Value<String?> photo,
  required bool loggedIn,
});
typedef $$UsersTableUpdateCompanionBuilder = UsersCompanion Function({
  Value<int> id,
  Value<String> email,
  Value<String> key,
  Value<AuthMethod> authMethod,
  Value<String?> name,
  Value<String?> phone,
  Value<String?> photo,
  Value<bool> loggedIn,
});

class $$UsersTableFilterComposer extends Composer<_$AppDatabase, $UsersTable> {
  $$UsersTableFilterComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  ColumnFilters<int> get id => $composableBuilder(
    column: $table.id,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get email => $composableBuilder(
    column: $table.email,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get key => $composableBuilder(
    column: $table.key,
    builder: (column) => ColumnFilters(column),
  );

  ColumnWithTypeConverterFilters<AuthMethod, AuthMethod, int> get authMethod =>
      $composableBuilder(
        column: $table.authMethod,
        builder: (column) => ColumnWithTypeConverterFilters(column),
      );

  ColumnFilters<String> get name => $composableBuilder(
    column: $table.name,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get phone => $composableBuilder(
    column: $table.phone,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get photo => $composableBuilder(
    column: $table.photo,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<bool> get loggedIn => $composableBuilder(
    column: $table.loggedIn,
    builder: (column) => ColumnFilters(column),
  );
}

class $$UsersTableOrderingComposer
    extends Composer<_$AppDatabase, $UsersTable> {
  $$UsersTableOrderingComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  ColumnOrderings<int> get id => $composableBuilder(
    column: $table.id,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get email => $composableBuilder(
    column: $table.email,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get key => $composableBuilder(
    column: $table.key,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<int> get authMethod => $composableBuilder(
    column: $table.authMethod,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get name => $composableBuilder(
    column: $table.name,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get phone => $composableBuilder(
    column: $table.phone,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get photo => $composableBuilder(
    column: $table.photo,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<bool> get loggedIn => $composableBuilder(
    column: $table.loggedIn,
    builder: (column) => ColumnOrderings(column),
  );
}

class $$UsersTableAnnotationComposer
    extends Composer<_$AppDatabase, $UsersTable> {
  $$UsersTableAnnotationComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  GeneratedColumn<int> get id =>
      $composableBuilder(column: $table.id, builder: (column) => column);

  GeneratedColumn<String> get email =>
      $composableBuilder(column: $table.email, builder: (column) => column);

  GeneratedColumn<String> get key =>
      $composableBuilder(column: $table.key, builder: (column) => column);

  GeneratedColumnWithTypeConverter<AuthMethod, int> get authMethod =>
      $composableBuilder(
        column: $table.authMethod,
        builder: (column) => column,
      );

  GeneratedColumn<String> get name =>
      $composableBuilder(column: $table.name, builder: (column) => column);

  GeneratedColumn<String> get phone =>
      $composableBuilder(column: $table.phone, builder: (column) => column);

  GeneratedColumn<String> get photo =>
      $composableBuilder(column: $table.photo, builder: (column) => column);

  GeneratedColumn<bool> get loggedIn =>
      $composableBuilder(column: $table.loggedIn, builder: (column) => column);
}

class $$UsersTableTableManager
    extends
        RootTableManager<
          _$AppDatabase,
          $UsersTable,
          User,
          $$UsersTableFilterComposer,
          $$UsersTableOrderingComposer,
          $$UsersTableAnnotationComposer,
          $$UsersTableCreateCompanionBuilder,
          $$UsersTableUpdateCompanionBuilder,
          (User, BaseReferences<_$AppDatabase, $UsersTable, User>),
          User,
          PrefetchHooks Function()
        > {
  $$UsersTableTableManager(_$AppDatabase db, $UsersTable table)
    : super(
        TableManagerState(
          db: db,
          table: table,
          createFilteringComposer: () =>
              $$UsersTableFilterComposer($db: db, $table: table),
          createOrderingComposer: () =>
              $$UsersTableOrderingComposer($db: db, $table: table),
          createComputedFieldComposer: () =>
              $$UsersTableAnnotationComposer($db: db, $table: table),
          updateCompanionCallback:
              ({
                Value<int> id = const Value.absent(),
                Value<String> email = const Value.absent(),
                Value<String> key = const Value.absent(),
                Value<AuthMethod> authMethod = const Value.absent(),
                Value<String?> name = const Value.absent(),
                Value<String?> phone = const Value.absent(),
                Value<String?> photo = const Value.absent(),
                Value<bool> loggedIn = const Value.absent(),
              }) => UsersCompanion(
                id: id,
                email: email,
                key: key,
                authMethod: authMethod,
                name: name,
                phone: phone,
                photo: photo,
                loggedIn: loggedIn,
              ),
          createCompanionCallback:
              ({
                Value<int> id = const Value.absent(),
                required String email,
                required String key,
                required AuthMethod authMethod,
                Value<String?> name = const Value.absent(),
                Value<String?> phone = const Value.absent(),
                Value<String?> photo = const Value.absent(),
                required bool loggedIn,
              }) => UsersCompanion.insert(
                id: id,
                email: email,
                key: key,
                authMethod: authMethod,
                name: name,
                phone: phone,
                photo: photo,
                loggedIn: loggedIn,
              ),
          withReferenceMapper: (p0) => p0
              .map(
                (e) => (
                  e.readTable<$UsersTable, User>(table),
                  BaseReferences<_$AppDatabase, $UsersTable, User>(
                    db,
                    table,
                    e,
                  ),
                ),
              )
              .toList(),
          prefetchHooksCallback: null,
        ),
      );
}

typedef $$UsersTableProcessedTableManager =
    ProcessedTableManager<
      _$AppDatabase,
      $UsersTable,
      User,
      $$UsersTableFilterComposer,
      $$UsersTableOrderingComposer,
      $$UsersTableAnnotationComposer,
      $$UsersTableCreateCompanionBuilder,
      $$UsersTableUpdateCompanionBuilder,
      (User, BaseReferences<_$AppDatabase, $UsersTable, User>),
      User,
      PrefetchHooks Function()
    >;

class $AppDatabaseManager {
  final _$AppDatabase _db;
  $AppDatabaseManager(this._db);
  $$UsersTableTableManager get users =>
      $$UsersTableTableManager(_db, _db.users);
}

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning
/// The provider that returns an instance of `AppDatabase`.

@ProviderFor(appDatabase)
final appDatabaseProvider = AppDatabaseProvider._();

/// The provider that returns an instance of `AppDatabase`.

final class AppDatabaseProvider
    extends $FunctionalProvider<AppDatabase, AppDatabase, AppDatabase>
    with $Provider<AppDatabase> {
  /// The provider that returns an instance of `AppDatabase`.
  AppDatabaseProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'appDatabaseProvider',
        isAutoDispose: true,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$appDatabaseHash();

  @$internal
  @override
  $ProviderElement<AppDatabase> $createElement($ProviderPointer pointer) =>
      $ProviderElement(pointer);

  @override
  AppDatabase create(Ref ref) {
    return appDatabase(ref);
  }

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(AppDatabase value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<AppDatabase>(value),
    );
  }
}

String _$appDatabaseHash() => r'2cb310a0ec75a9cb603cc91d0dff743db2cdc09e';
