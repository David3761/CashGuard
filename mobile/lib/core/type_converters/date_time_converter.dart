import 'package:drift/drift.dart';

/// A utility class for the database that provides bidirectional conversion
/// between a [DateTime] object and milliseconds since epoch as [int].
class DateTimeConverter extends TypeConverter<DateTime, int> {
  @override
  DateTime fromSql(int fromDb) {
    return .fromMillisecondsSinceEpoch(fromDb);
  }

  @override
  int toSql(DateTime value) => value.millisecondsSinceEpoch;
}

/// A utility class for the database that provides bidirectional conversion
/// between a nullable [DateTime] object and milliseconds since epoch as [int].
class DateTimeNullableConverter extends TypeConverter<DateTime?, int?> {
  @override
  DateTime? fromSql(int? fromDb) {
    return fromDb != null ? .fromMillisecondsSinceEpoch(fromDb) : null;
  }

  @override
  int? toSql(DateTime? value) => value?.millisecondsSinceEpoch;
}
