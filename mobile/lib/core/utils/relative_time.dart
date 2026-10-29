import 'package:cashctrl/l10n/app_localizations.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

/// Returns "Today", "Yesterday" or the date (e.g. `24 October`) of the given
/// [day].
String formatDay(DateTime day, {required AppLocalizations localizations}) {
  final now = DateTime.now();
  final yesterday = DateTime(now.year, now.month, now.day - 1);
  if (DateUtils.isSameDay(day, now)) {
    return localizations.today;
  } else if (DateUtils.isSameDay(day, yesterday)) {
    return localizations.yesterday;
  }
  return DateFormat('d MMMM').format(day);
}

/// Returns a description of [range] that repeats the month and the year only
/// when its dates don't share them, e.g. "5 - 23 Oct 2026", "1 Mar - 30 Apr
/// 2026" or "1 Dec 2025 - 18 Feb 2026".
String formatDateRange(DateTimeRange range, {required String localeName}) {
  final start = range.start;
  final end = range.end;
  final endLabel = '${end.day} ${_monthName(end, localeName)} ${end.year}';
  if (start.year == end.year && start.month == end.month) {
    return '${start.day} - $endLabel';
  }
  if (start.year == end.year) {
    return '${start.day} ${_monthName(start, localeName)} - $endLabel';
  }
  return '${start.day} ${_monthName(start, localeName)} ${start.year} '
      '- $endLabel';
}

/// Returns [date]'s capitalized month abbreviation, e.g. "Oct".
String _monthName(DateTime date, String localeName) {
  final month = DateFormat.MMM(localeName).format(date).replaceAll('.', '');
  return month[0].toUpperCase() + month.substring(1);
}
