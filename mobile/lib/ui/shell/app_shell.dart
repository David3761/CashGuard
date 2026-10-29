import 'package:cashctrl/l10n/app_localizations.dart';
import 'package:cashctrl/resources/colors.dart';
import 'package:cashctrl/resources/images.dart';
import 'package:cashctrl/resources/text_styles.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

/// An enum class that lists the bottom navigation's tabs, in the same order as
/// the router's shell branches.
enum ShellTab {
  /// The transactions tab.
  transactions,

  /// The assistant tab.
  assistant,
}

/// A widget that displays the current tab's screen above the bottom
/// navigation.
class AppShell extends StatelessWidget {
  /// Creates an [AppShell].
  const AppShell({super.key, required this.navigationShell});

  /// The router's shell that holds the tabs' navigation state.
  final StatefulNavigationShell navigationShell;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.surfaceCanvas,
      body: navigationShell,
      bottomNavigationBar: _BottomNavigation(
        currentTab: ShellTab.values[navigationShell.currentIndex],
        onTabSelected: _goToTab,
      ),
    );
  }

  /// Displays the given [tab], or resets it to its first screen if it's
  /// already displayed.
  void _goToTab(ShellTab tab) {
    navigationShell.goBranch(
      tab.index,
      initialLocation: tab.index == navigationShell.currentIndex,
    );
  }
}

/// A widget that displays the bottom navigation.
class _BottomNavigation extends StatelessWidget {
  /// Creates a [_BottomNavigation].
  const _BottomNavigation({
    required this.currentTab,
    required this.onTabSelected,
  });

  /// The currently displayed tab.
  final ShellTab currentTab;

  /// Called when the user taps a tab.
  final ValueChanged<ShellTab> onTabSelected;

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context);
    return Material(
      color: AppColors.surfaceSubtle,
      shape: const Border(top: BorderSide(color: AppColors.borderDefault)),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const .directional(start: 20, top: 8, end: 20, bottom: 4),
          child: Row(
            children: [
              Expanded(
                child: _NavigationItem(
                  iconAsset: AppImages.navTransactions,
                  activeIconAsset: AppImages.navTransactionsActive,
                  label: localizations.transactions,
                  isActive: currentTab == .transactions,
                  onTap: () => onTabSelected(.transactions),
                ),
              ),
              Expanded(
                child: _NavigationItem(
                  iconAsset: AppImages.navAssistant,
                  activeIconAsset: AppImages.navAssistantActive,
                  label: localizations.assistant,
                  isActive: currentTab == .assistant,
                  onTap: () => onTabSelected(.assistant),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// A widget that displays a tab's icon above its label, highlighted when
/// [isActive] is `true`.
class _NavigationItem extends StatelessWidget {
  /// Creates a [_NavigationItem].
  const _NavigationItem({
    required this.iconAsset,
    required this.activeIconAsset,
    required this.label,
    required this.isActive,
    required this.onTap,
  });

  /// The icon displayed when the tab isn't active.
  final String iconAsset;

  /// The icon displayed when the tab is active.
  final String activeIconAsset;

  /// The tab's label.
  final String label;

  /// Whether the tab is currently displayed.
  final bool isActive;

  /// Called when the user taps the tab.
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      // borderRadius: .circular(8),
      child: Column(
        mainAxisSize: .min,
        children: [
          Image.asset(
            isActive ? activeIconAsset : iconAsset,
            color: isActive ? AppColors.textPrimary : AppColors.textSecondary,
          ),
          const SizedBox(height: 4),
          Text(
            label,
            style: TextStyles.text10_5M.copyWith(
              color: isActive ? AppColors.textPrimary : AppColors.textMuted,
            ),
            textAlign: .center,
          ),
        ],
      ),
    );
  }
}
