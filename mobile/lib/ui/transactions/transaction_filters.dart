import 'package:cashctrl/core/models/transaction.dart';
import 'package:cashctrl/core/models/transaction_type.dart';
import 'package:cashctrl/ui/transactions/amount_range.dart';
import 'package:flutter/material.dart';

/// A class that stores the filters applied to the transactions.
class TransactionFilters {
  /// Creates a [TransactionFilters].
  const TransactionFilters({
    this.types = const {},
    this.amountRanges = const {},
    this.period,
  });

  /// The types the transactions are filtered by. When empty, every type is
  /// displayed.
  final Set<TransactionType> types;

  /// The ranges the transactions' amounts are filtered by. When empty, every
  /// amount is displayed.
  final Set<AmountRange> amountRanges;

  /// The period the transactions are filtered by, if any.
  final DateTimeRange? period;

  /// Whether any filter is applied.
  bool get isNotEmpty {
    return types.isNotEmpty || amountRanges.isNotEmpty || period != null;
  }

  /// Returns `true` when [transaction] matches every applied filter.
  bool matches(Transaction transaction) {
    if (types.isNotEmpty && !types.contains(transaction.type)) {
      return false;
    }
    if (amountRanges.isNotEmpty &&
        !amountRanges.any((range) => range.contains(transaction.amount))) {
      return false;
    }
    final period = this.period;
    if (period == null) {
      return true;
    }
    final createdAt = transaction.createdAt;
    final dayAfterEnd = DateTime(
      period.end.year,
      period.end.month,
      period.end.day + 1,
    );
    return !createdAt.isBefore(period.start) && createdAt.isBefore(dayAfterEnd);
  }
}
