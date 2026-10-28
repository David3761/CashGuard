import 'package:drift/drift.dart';
import 'package:flutter/material.dart';

/// A utility class for the database that provides bidirectional conversion
/// between a [TimeOfDay] object and the hour and minutes as [String].
class TimeOfDayConverter extends TypeConverter<TimeOfDay, String> {
  @override
  TimeOfDay fromSql(String fromDb) {
    final values = fromDb.split(':');
    return TimeOfDay(hour: int.parse(values[0]), minute: int.parse(values[1]));
  }

  @override
  String toSql(TimeOfDay value) => '${value.hour}:${value.minute}';
}
