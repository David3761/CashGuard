import 'package:cashctrl/core/models/transaction.dart';
import 'package:cashctrl/core/repositories/transaction_repository.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

// Necessary for code-generation to work
// Run: dart run build_runner watch
part 'transactions_provider.g.dart';

/// The provider that stores the account's balance in bani.
@riverpod
Future<int> balance(Ref ref) {
  return ref.watch(transactionRepositoryProvider).getBalance();
}

/// The provider that stores the account's transactions.
@riverpod
Future<List<Transaction>> transactions(Ref ref) {
  return ref.watch(transactionRepositoryProvider).getTransactions();
}
