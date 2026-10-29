import 'package:cashctrl/core/models/transaction_type.dart';
import 'package:cashctrl/core/utils/relative_time.dart';
import 'package:cashctrl/l10n/app_localizations.dart';
import 'package:cashctrl/resources/colors.dart';
import 'package:cashctrl/resources/text_styles.dart';
import 'package:cashctrl/ui/transactions/amount_range.dart';
import 'package:cashctrl/ui/transactions/transaction_filters.dart';
import 'package:cashctrl/widgets/widgets.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

/// The number of years the period can be picked from.
const _pickerYears = 2;

/// A widget that displays the filters applied to the transactions.
class TransactionFiltersSheet extends StatefulWidget {
  /// Creates a [TransactionFiltersSheet].
  const TransactionFiltersSheet({super.key, required this.filters});

  /// The filters that are currently applied.
  final TransactionFilters filters;

  /// Displays a [TransactionFiltersSheet] and returns the filters the user
  /// applied, or `null` when the user closed the sheet.
  static Future<TransactionFilters?> show(
    BuildContext context,
    TransactionFilters filters,
  ) {
    return showSheet<TransactionFilters>(
      context,
      TransactionFiltersSheet(filters: filters),
    );
  }

  @override
  State<TransactionFiltersSheet> createState() =>
      _TransactionFiltersSheetState();
}

class _TransactionFiltersSheetState extends State<TransactionFiltersSheet> {
  /// The types selected in the sheet.
  late final _types = {...widget.filters.types};

  /// The amount ranges selected in the sheet.
  late final _amountRanges = {...widget.filters.amountRanges};

  /// The period selected in the sheet.
  late var _period = widget.filters.period;

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context);
    final period = _period;
    return Material(
      color: AppColors.surfaceBase,
      borderRadius: const .vertical(top: .circular(20)),
      clipBehavior: .antiAlias,
      child: SafeArea(
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: .min,
            crossAxisAlignment: .stretch,
            children: [
              Center(
                child: Container(
                  width: 40,
                  height: 5,
                  margin: const .directional(top: 10, bottom: 14),
                  decoration: BoxDecoration(
                    color: AppColors.borderDefault,
                    borderRadius: .circular(3),
                  ),
                ),
              ),
              Padding(
                padding: const .directional(start: 20, end: 20, bottom: 4),
                child: Text(localizations.filters, style: TextStyles.text17SB),
              ),
              ExpansionTile(
                title: Text(localizations.type, style: TextStyles.text14_5M),
                shape: const Border(),
                children: [
                  for (final type in TransactionType.values) ...[
                    CheckboxListTile(
                      value: _types.contains(type),
                      onChanged: (_) => _toggle(_types, type),
                      title: Text(
                        type.getLabel(localizations),
                        style: TextStyles.text14M,
                      ),
                    ),
                  ],
                ],
              ),
              ExpansionTile(
                title: Text(localizations.amount, style: TextStyles.text14_5M),
                shape: const Border(),
                children: [
                  for (final range in AmountRange.values) ...[
                    CheckboxListTile(
                      value: _amountRanges.contains(range),
                      onChanged: (_) => _toggle(_amountRanges, range),
                      title: Text(
                        range.getLabel(localizations),
                        style: TextStyles.text14M,
                      ),
                    ),
                  ],
                ],
              ),
              ListTile(
                title: Text(localizations.period, style: TextStyles.text14_5M),
                subtitle: Text(
                  period == null
                      ? localizations.choosePeriod
                      : formatDateRange(
                          period,
                          localeName: localizations.localeName,
                        ),
                  style: TextStyles.text14M.copyWith(
                    color: period == null
                        ? AppColors.textMuted
                        : AppColors.textPrimary,
                  ),
                ),
                onTap: _pickPeriod,
              ),
              Padding(
                padding: const .directional(
                  start: 20,
                  top: 12,
                  end: 20,
                  bottom: 16,
                ),
                child: Row(
                  spacing: 12,
                  children: [
                    Expanded(
                      child: OutlinedButton(
                        onPressed: _reset,
                        child: Text(localizations.reset),
                      ),
                    ),
                    Expanded(
                      child: FilledButton(
                        onPressed: _apply,
                        child: Text(localizations.applyFilters),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// Selects [value] in [values] when it isn't selected yet, or deselects it
  /// otherwise.
  void _toggle<T>(Set<T> values, T value) {
    setState(() {
      if (!values.remove(value)) {
        values.add(value);
      }
    });
  }

  /// Displays the date range picker and stores the picked period.
  Future<void> _pickPeriod() async {
    final now = DateTime.now();
    final period = await showDialog<DateTimeRange>(
      context: context,
      builder: (context) => Dialog(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 400, maxHeight: 760),
          child: DateRangePickerDialog(
            firstDate: DateTime(now.year - _pickerYears, now.month, now.day),
            lastDate: now,
            initialDateRange: _period,
          ),
        ),
      ),
    );
    if (period != null) {
      setState(() => _period = period);
    }
  }

  /// Removes every filter and applies the change.
  void _reset() {
    context.pop(const TransactionFilters());
  }

  /// Applies the selected filters.
  void _apply() {
    context.pop(
      TransactionFilters(
        types: _types,
        amountRanges: _amountRanges,
        period: _period,
      ),
    );
  }
}
