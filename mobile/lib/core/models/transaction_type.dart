import 'package:cashctrl/l10n/app_localizations.dart';

/// An enum class that lists all types of transactions: payments and incoming
/// or outgoing transfers.
enum TransactionType {
  /// A card payment.
  payment,

  /// A transfer received from someone else.
  transferIn,

  /// A transfer sent to someone else.
  transferOut;

  /// Returns the type matching the given [value] from a request's response.
  factory TransactionType.fromJson(String value) => switch (value) {
    'payment' => .payment,
    'transfer_in' => .transferIn,
    'transfer_out' => .transferOut,
    _ => throw FormatException('Unknown transaction type: $value'),
  };

  /// Returns the type's label.
  String getLabel(AppLocalizations localizations) => switch (this) {
    .payment => localizations.cardPayments,
    .transferIn => localizations.incomingTransfers,
    .transferOut => localizations.outgoingTransfers,
  };
}
