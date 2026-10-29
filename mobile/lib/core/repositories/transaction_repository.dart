import 'package:cashctrl/core/models/transaction.dart';
import 'package:cashctrl/core/request/api_client.dart';
import 'package:cashctrl/core/request/api_config.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

// Necessary for code-generation to work
// Run: dart run build_runner watch
part 'transaction_repository.g.dart';

/// The provider that returns an instance of [TransactionRepository].
@riverpod
TransactionRepository transactionRepository(Ref ref) {
  return TransactionRepository._(ref);
}

/// The repository for the *Transactions* flow.
class TransactionRepository {
  /// Creates a [TransactionRepository].
  const TransactionRepository._(this.ref);

  /// A [Ref] object used to access any providers (such as `ApiService`).
  final Ref ref;

  /// Returns the account's balance in bani.
  Future<int> getBalance() async {
    if (useMockApi) {
      return 284735;
    }
    final json = await ref.read(apiServiceProvider).getBalance();
    return json['balance'] as int;
  }

  /// Returns the account's transactions, the newest first.
  Future<List<Transaction>> getTransactions() async {
    if (useMockApi) {
      return _dummyTransactions();
    }
    final json = await ref.read(apiServiceProvider).getTransactions();
    final transactions = json['transactions'] as List<dynamic>;
    return transactions.map((transaction) {
      return Transaction.fromJson(transaction as Map<String, dynamic>);
    }).toList();
  }

  /// Returns the dummy transactions displayed while [useMockApi] is `true`.
  List<Transaction> _dummyTransactions() {
    final now = DateTime.now();
    return [
      Transaction(
        id: 1,
        title: 'Bean & Brew Café',
        amount: -1850,
        type: .payment,
        createdAt: DateTime(now.year, now.month, now.day, 8, 42),
      ),
      Transaction(
        id: 2,
        title: 'Ioana Stan',
        amount: 15000,
        type: .transferIn,
        createdAt: DateTime(now.year, now.month, now.day, 8, 5),
      ),
      Transaction(
        id: 3,
        title: 'Fresh Market',
        amount: -12764,
        type: .payment,
        createdAt: DateTime(now.year, now.month, now.day - 1, 19, 21),
      ),
      Transaction(
        id: 4,
        title: 'City Bike Rental',
        amount: -1200,
        type: .payment,
        createdAt: DateTime(now.year, now.month, now.day - 1, 17, 5),
      ),
      Transaction(
        id: 5,
        title: 'Andrei Popa',
        amount: -20000,
        type: .transferOut,
        createdAt: DateTime(now.year, now.month, now.day - 1, 13, 30),
      ),
      Transaction(
        id: 6,
        title: 'Orbit Software SRL',
        amount: 645000,
        type: .transferIn,
        createdAt: DateTime(now.year, now.month, now.day - 2, 9),
      ),
      Transaction(
        id: 7,
        title: 'StreamBox',
        amount: -4999,
        type: .payment,
        createdAt: DateTime(now.year, now.month, now.day - 2, 7, 12),
      ),
      Transaction(
        id: 8,
        title: 'Pharma Plus',
        amount: -3620,
        type: .payment,
        createdAt: DateTime(now.year, now.month, now.day - 3, 18, 47),
      ),
      Transaction(
        id: 9,
        title: 'Maria Ionescu',
        amount: 7500,
        type: .transferIn,
        createdAt: DateTime(now.year, now.month, now.day - 3, 12, 15),
      ),
      Transaction(
        id: 10,
        title: 'Fuel Station 24',
        amount: -21045,
        type: .payment,
        createdAt: DateTime(now.year, now.month, now.day - 3, 8, 30),
      ),
      Transaction(
        id: 11,
        title: 'Elena Dumitru',
        amount: -230000,
        type: .transferOut,
        createdAt: DateTime(now.year, now.month, now.day - 5, 10),
      ),
      Transaction(
        id: 12,
        title: 'Gym Pulse',
        amount: -18000,
        type: .payment,
        createdAt: DateTime(now.year, now.month, now.day - 5, 7, 45),
      ),
    ];
  }
}
