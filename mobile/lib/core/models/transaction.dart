import 'package:cashctrl/core/models/transaction_type.dart';

/// A model class that stores the data of one of the account's transactions.
class Transaction {
  /// Creates a [Transaction].
  const Transaction({
    required this.id,
    required this.title,
    required this.amount,
    required this.type,
    required this.createdAt,
  });

  /// Creates a [Transaction] from the given [json].
  factory Transaction.fromJson(Map<String, dynamic> json) {
    return Transaction(
      id: json['id'] as int,
      title: json['title'] as String,
      amount: json['amount'] as int,
      type: .fromJson(json['type'] as String),
      createdAt: DateTime.parse(json['created_at'] as String).toLocal(),
    );
  }

  /// The transaction's identifier.
  final int id;

  /// The name of the merchant or person the transaction was made with.
  final String title;

  /// The transaction's amount in bani, negative when money left the account.
  final int amount;

  /// The transaction's type.
  final TransactionType type;

  /// The moment the transaction was made.
  final DateTime createdAt;

  /// Returns the first letters of the [title]'s first two words that start
  /// with a letter.
  String get initials {
    final words = title.split(' ').where((word) {
      return word.isNotEmpty && _letter.hasMatch(word[0]);
    });
    return words.take(2).map((word) => word[0].toUpperCase()).join();
  }

  /// The pattern that matches a letter in any alphabet.
  static final _letter = RegExp(r'\p{L}', unicode: true);
}
