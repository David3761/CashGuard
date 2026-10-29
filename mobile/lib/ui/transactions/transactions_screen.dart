import 'dart:async';
import 'dart:convert';

import 'package:cashctrl/core/models/transaction.dart';
import 'package:cashctrl/core/notification/app_notification_service.dart';
import 'package:cashctrl/core/utils/logging.dart';
import 'package:cashctrl/core/utils/relative_time.dart';
import 'package:cashctrl/core/utils/utils.dart';
import 'package:cashctrl/exceptions.dart';
import 'package:cashctrl/l10n/app_localizations.dart';
import 'package:cashctrl/main.dart';
import 'package:cashctrl/main_providers.dart';
import 'package:cashctrl/resources/colors.dart';
// import 'package:cashctrl/resources/images.dart';
import 'package:cashctrl/resources/text_styles.dart';
import 'package:cashctrl/ui/settings/settings_screen.dart';
import 'package:cashctrl/ui/transactions/transaction_filters.dart';
import 'package:cashctrl/ui/transactions/transaction_filters_sheet.dart';
import 'package:cashctrl/ui/transactions/transactions_provider.dart';
import 'package:cashctrl/utils/dialogs.dart';
import 'package:cashctrl/widgets/app_header.dart';
import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import 'package:package_info_plus/package_info_plus.dart';

/// The screen that displays the account's balance and transactions.
class TransactionsScreen extends ConsumerStatefulWidget {
  /// Creates a [TransactionsScreen].
  const TransactionsScreen({super.key, this.notificationData});

  /// The route's name.
  static const route = 'transactions';

  /// The data of the notification that triggered the app to open (if any).
  final String? notificationData;

  @override
  ConsumerState<TransactionsScreen> createState() => _TransactionsScreenState();
}

class _TransactionsScreenState extends ConsumerState<TransactionsScreen>
    with WidgetsBindingObserver, RouteAware {
  StreamSubscription<String>? _newNotificationSubscription;

  /// The controller of the search field.
  final _searchController = TextEditingController();

  /// The text the transactions are searched by.
  var _query = '';

  /// The filters applied to the transactions.
  var _filters = const TransactionFilters();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    MyApp.isInMainScreen = true;
    _newNotificationSubscription = AppNotificationService
        .instance
        .newNotification
        .stream
        .listen(_loadDataFromNotification);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    unawaited(_newNotificationSubscription?.cancel());
    _newNotificationSubscription = null;
    _searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context);
    final balance = ref.watch(balanceProvider).value;
    final transactions = ref.watch(transactionsProvider).value;
    _listenForProviders();

    return PopScope(
      canPop: false,
      child: Scaffold(
        backgroundColor: AppColors.surfaceCanvas,
        // drawer: SafeArea(
        //   child: SizedBox(
        //     // width: MediaQuery.of(context).size.width,
        //     child: Drawer(
        //       backgroundColor: Colors.white,
        //       child: AppDrawer(
        //         onMenuItemTap: (route) => context.goNamed(route),
        //         onLogout: ref.read(authProvider.notifier).logout,
        //       ),
        //     ),
        //   ),
        // ),
        body: Column(
          children: [
            AppHeader(
              title: localizations.transactions,
              // leading: Builder(
              //   builder: (context) => AppHeaderAction(
              //     iconAsset: AppImages.menu,
              //     onTap: Scaffold.of(context).openDrawer,
              //   ),
              // ),
              bottom: [
                _SearchBar(
                  controller: _searchController,
                  hasFilters: _filters.isNotEmpty,
                  onChanged: (value) {
                    setState(() => _query = value);
                  },
                  onFiltersTap: _openFilters,
                ),
              ],
            ),
            Expanded(
              child: transactions == null
                  ? const Center(child: CircularProgressIndicator())
                  : _TransactionsList(
                      balance: balance,
                      transactions: _visibleTransactions(transactions),
                    ),
            ),
          ],
        ),
      ),
    );
  }

  /// Listens to providers value changes in order to display one time events
  /// (e.g.: alert dialogs, snack bars, toasts, etc) or perform actions.
  ///
  /// **This method should always be called from [build].**
  void _listenForProviders() {
    final localizations = AppLocalizations.of(context);
    ref
      ..listen(authProvider, (_, state) {
        if (state case AsyncError(:final error)) {
          unawaited(
            showAlert(
              context: context,
              title: localizations.error_,
              message: getLocalizedMessage(context, error),
            ),
          );
        }
      })
      ..listen(transactionsProvider, (_, state) {
        if (state case AsyncError(:final error)) {
          unawaited(
            showAlert(
              context: context,
              title: localizations.error_,
              message: getLocalizedMessage(context, error),
            ),
          );
        }
      });
  }

  /// Displays the filters and applies the ones the user picked.
  Future<void> _openFilters() async {
    final filters = await TransactionFiltersSheet.show(context, _filters);
    if (filters != null && mounted) {
      setState(() => _filters = filters);
    }
  }

  /// Returns the transactions that match the search and the applied filters.
  List<Transaction> _visibleTransactions(List<Transaction> transactions) {
    final query = _query.trim().toLowerCase();
    return transactions.where((transaction) {
      return _filters.matches(transaction) &&
          transaction.title.toLowerCase().contains(query);
    }).toList();
  }

  /// If the app has resumed and the screen is the TransactionsScreen, then
  /// call [_getNewNotificationDataIfAny].
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == .resumed && MyApp.isInMainScreen) {
      _getNewNotificationDataIfAny();
    }
  }

  /// Sets [MyApp.isInMainScreen] to `false`.
  @override
  void didPushNext() {
    // navigating forward to a new page
    MyApp.isInMainScreen = false;
  }

  /// Sets [MyApp.isInMainScreen] to `true` and calls
  /// [_getNewNotificationDataIfAny].
  @override
  void didPopNext() {
    // Covering route was popped off the navigator.
    MyApp.isInMainScreen = true;
    _getNewNotificationDataIfAny();
  }

  /// Should make a request to retrieve the data from the server and display
  /// it in the app. Currently this method only tries to decode the [data] as
  /// a JSON.
  void _loadDataFromNotification(String data) {
    try {
      final json = jsonDecode(data);
      devPrint('notification: $json');
    } on Exception catch (e, stacktrace) {
      unawaited(logException(e, stackTrace: stacktrace));
    }
  }

  /// Fetches the new notification data if present.
  void _getNewNotificationDataIfAny() {}
}

/// A widget that displays the field the transactions are searched by, next to
/// the filters button.
class _SearchBar extends StatelessWidget {
  /// Creates a [_SearchBar].
  const _SearchBar({
    required this.controller,
    required this.hasFilters,
    required this.onChanged,
    required this.onFiltersTap,
  });

  /// The controller of the search field.
  final TextEditingController controller;

  /// Whether any filter is applied to the transactions.
  final bool hasFilters;

  /// Called when the searched text changes.
  final ValueChanged<String> onChanged;

  /// Called when the user opens the filters.
  final VoidCallback onFiltersTap;

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context);
    return Padding(
      padding: const .directional(start: 16, end: 16, bottom: 16),
      child: Row(
        spacing: 8,
        children: [
          Expanded(
            child: Container(
              padding: const .directional(start: 14, end: 14),
              decoration: BoxDecoration(
                color: AppColors.surfaceBase,
                border: .all(color: AppColors.borderDefault),
                borderRadius: .circular(24),
              ),
              child: Row(
                spacing: 8,
                children: [
                  const Icon(Icons.search, color: AppColors.textMuted),
                  Expanded(
                    child: TextField(
                      controller: controller,
                      onChanged: onChanged,
                      cursorColor: AppColors.textPrimary,
                      style: TextStyles.text16R,
                      decoration: InputDecoration(
                        border: .none,
                        isCollapsed: true,
                        contentPadding: const .symmetric(vertical: 14),
                        hintText: localizations.search,
                        hintStyle: TextStyles.text16R.copyWith(
                          color: AppColors.textMuted,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
          IconButton(
            onPressed: onFiltersTap,
            style: IconButton.styleFrom(
              backgroundColor: hasFilters
                  ? AppColors.surfaceBrand
                  : AppColors.surfaceBase,
              side: hasFilters
                  ? null
                  : const BorderSide(color: AppColors.borderDefault),
            ),
            icon: const Icon(Icons.filter_list, color: AppColors.textPrimary),
          ),
        ],
      ),
    );
  }
}

/// A widget that displays the account's balance above the transactions grouped
/// by day, or above a message when there are no transactions.
class _TransactionsList extends StatelessWidget {
  /// Creates a [_TransactionsList].
  const _TransactionsList({required this.balance, required this.transactions});

  /// The account's balance in bani, or `null` while it's loading.
  final int? balance;

  /// The displayed transactions, the newest first.
  final List<Transaction> transactions;

  @override
  Widget build(BuildContext context) {
    final balance = this.balance;
    final transactionsByDay = groupBy(transactions, (transaction) {
      return DateUtils.dateOnly(transaction.createdAt);
    });
    return ListView(
      padding: const .directional(start: 16, end: 16, bottom: 24),
      children: [
        if (balance != null) ...[_BalanceSummary(balance: balance)],
        if (transactions.isEmpty) ...[
          Padding(
            padding: const .directional(top: 24),
            child: Text(
              AppLocalizations.of(context).noTransactionsFound,
              style: TextStyles.text14M.copyWith(color: AppColors.textMuted),
              textAlign: .center,
            ),
          ),
        ] else ...[
          for (final MapEntry(key: day, value: dayTransactions)
              in transactionsByDay.entries) ...[
            _DaySection(day: day, transactions: dayTransactions),
          ],
        ],
      ],
    );
  }
}

/// A widget that displays the account's balance.
class _BalanceSummary extends StatelessWidget {
  /// Creates a [_BalanceSummary].
  const _BalanceSummary({required this.balance});

  /// The account's balance in bani.
  final int balance;

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context);
    return Padding(
      padding: const .directional(top: 24),
      child: Column(
        spacing: 2,
        children: [
          Text(
            localizations.amountInLei(balance.formatBani()),
            style: TextStyles.text32B,
            textAlign: .center,
          ),
          Text(
            localizations.currentBalance,
            style: TextStyles.text14R.copyWith(color: AppColors.textSecondary),
            textAlign: .center,
          ),
        ],
      ),
    );
  }
}

/// A widget that displays a day's transactions below the day and its total.
class _DaySection extends StatelessWidget {
  /// Creates a [_DaySection].
  const _DaySection({required this.day, required this.transactions});

  /// The day the [transactions] were made on.
  final DateTime day;

  /// The transactions made on the [day].
  final List<Transaction> transactions;

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context);
    final total = transactions.map((transaction) => transaction.amount).sum;
    return Column(
      crossAxisAlignment: .stretch,
      children: [
        Padding(
          padding: const .directional(start: 4, top: 24, end: 4, bottom: 10),
          child: Row(
            spacing: 8,
            children: [
              Expanded(
                child: Text(
                  formatDay(day, localizations: localizations),
                  style: TextStyles.text20SB,
                ),
              ),
              Text(
                localizations.amountInLei(total.formatBani(showPlusSign: true)),
                style: TextStyles.text14R.copyWith(color: AppColors.textMuted),
              ),
            ],
          ),
        ),
        DecoratedBox(
          decoration: BoxDecoration(
            color: AppColors.surfaceBase,
            borderRadius: .circular(20),
          ),
          child: Padding(
            padding: const .symmetric(vertical: 4),
            child: Column(
              children: [
                for (final transaction in transactions) ...[
                  _TransactionRow(transaction: transaction),
                ],
              ],
            ),
          ),
        ),
      ],
    );
  }
}

/// A widget that displays a transaction's title, time and amount.
class _TransactionRow extends StatelessWidget {
  /// Creates a [_TransactionRow].
  const _TransactionRow({required this.transaction});

  /// The displayed transaction.
  final Transaction transaction;

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context);
    return Padding(
      padding: const .symmetric(horizontal: 16, vertical: 12),
      child: Row(
        crossAxisAlignment: .start,
        spacing: 12,
        children: [
          _TransactionAvatar(transaction: transaction),
          Expanded(
            child: Column(
              crossAxisAlignment: .start,
              spacing: 2,
              children: [
                Text(transaction.title, style: TextStyles.text16R),
                Text(
                  DateFormat.Hm().format(transaction.createdAt),
                  style: TextStyles.text14R.copyWith(
                    color: AppColors.textMuted,
                  ),
                ),
              ],
            ),
          ),
          Text(
            localizations.amountInLei(
              transaction.amount.formatBani(showPlusSign: true),
            ),
            style: TextStyles.text16R.copyWith(
              color: transaction.amount > 0
                  ? AppColors.statusSuccessForeground
                  : AppColors.textPrimary,
            ),
          ),
        ],
      ),
    );
  }
}

/// A widget that displays a transaction's initials, with an arrow when the
/// transaction is a transfer.
class _TransactionAvatar extends StatelessWidget {
  /// Creates a [_TransactionAvatar].
  const _TransactionAvatar({required this.transaction});

  /// The displayed transaction.
  final Transaction transaction;

  @override
  Widget build(BuildContext context) {
    final transferIcon = switch (transaction.type) {
      .payment => null,
      .transferIn => Icons.arrow_back,
      .transferOut => Icons.arrow_forward,
    };
    return Stack(
      clipBehavior: .none,
      children: [
        Container(
          width: 44,
          height: 44,
          alignment: .center,
          decoration: const BoxDecoration(
            color: AppColors.avatarBackground,
            shape: .circle,
          ),
          child: Text(transaction.initials, style: TextStyles.text14SB),
        ),
        if (transferIcon != null) ...[
          PositionedDirectional(
            end: -4,
            bottom: -4,
            child: Container(
              width: 20,
              height: 20,
              decoration: BoxDecoration(
                color: AppColors.surfaceBase,
                shape: .circle,
                border: .all(color: AppColors.borderDefault),
              ),
              child: Icon(transferIcon, size: 12, color: AppColors.textPrimary),
            ),
          ),
        ],
      ],
    );
  }
}

/// The widget that displays the app drawer.
class AppDrawer extends ConsumerWidget {
  /// Creates an [AppDrawer].
  const AppDrawer({
    super.key,
    required this.onMenuItemTap,
    required this.onLogout,
  });

  /// Called when the user taps a menu item.
  final ValueChanged<String> onMenuItemTap;

  /// Called when the user taps the logout option.
  final VoidCallback onLogout;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final localizations = AppLocalizations.of(context);
    return Stack(
      children: [
        Padding(
          padding: const .symmetric(vertical: 10),
          child: SingleChildScrollView(
            child: Column(
              children: [
                MenuItem(
                  localizations.settings,
                  onTap: () => onMenuItemTap(SettingsScreen.route),
                ),
                MenuItem(
                  localizations.logout,
                  onTap: () {
                    unawaited(
                      showYesNoAlert(
                        context: context,
                        title: localizations.logout,
                        message: localizations.logoutConfirmation,
                        yesClickListener: (context) {
                          context.pop();
                          onLogout();
                        },
                      ),
                    );
                  },
                ),
              ],
            ),
          ),
        ),
        Column(
          mainAxisAlignment: .end,
          children: [
            Align(
              alignment: .bottomCenter,
              child: Padding(
                padding: const .directional(bottom: 10),
                child: FutureBuilder<PackageInfo>(
                  future: PackageInfo.fromPlatform(),
                  builder: (context, packageInfo) => Text(
                    localizations.versionOf(packageInfo.data?.version ?? '-'),
                  ),
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }
}

/// A widget that displays a menu option.
class MenuItem extends StatelessWidget {
  /// Creates a [MenuItem].
  const MenuItem(this.labelText, {super.key, required this.onTap});

  /// The menu item's label.
  final String labelText;

  /// Called when the user taps the menu item.
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      title: Text(labelText, style: TextStyles.text14SB),
      onTap: onTap,
    );
  }
}
