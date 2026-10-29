import 'package:cashctrl/l10n/app_localizations.dart';

/// An enum class that lists the ranges the transactions' amounts are filtered
/// by, regardless of whether the money came in or went out.
enum AmountRange {
  /// Amounts under 50 lei.
  under50,

  /// Amounts from 50 to 500 lei.
  from50To500,

  /// Amounts over 500 lei.
  over500;

  /// Returns `true` when the absolute value of the given [amount] of bani is
  /// within the range.
  bool contains(int amount) {
    final value = amount.abs();
    return switch (this) {
      .under50 => value < 5000,
      .from50To500 => value >= 5000 && value <= 50000,
      .over500 => value > 50000,
    };
  }

  /// Returns the range's label.
  String getLabel(AppLocalizations localizations) => switch (this) {
    .under50 => localizations.amountUnder50,
    .from50To500 => localizations.amount50To500,
    .over500 => localizations.amountOver500,
  };
}
