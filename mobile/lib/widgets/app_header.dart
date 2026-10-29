import 'package:cashctrl/resources/colors.dart';
import 'package:cashctrl/resources/text_styles.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// The width of the areas that keep a centered title between the [AppHeader]'s
/// leading widget and its actions.
const _sideWidth = 70.0;

/// A widget that displays a screen's title with optional [actions] next to it.
///
/// The title is centered when a [leading] widget is displayed before it.
class AppHeader extends StatelessWidget {
  /// Creates an [AppHeader].
  const AppHeader({
    super.key,
    required this.title,
    this.leading,
    this.actions = const [],
    this.bottom = const [],
  });

  /// The header's title.
  final String title;

  /// The widget displayed before the [title], if any.
  final Widget? leading;

  /// The widgets displayed after the [title].
  final List<Widget> actions;

  /// The widgets displayed below the [title], on the same surface.
  final List<Widget> bottom;

  @override
  Widget build(BuildContext context) {
    final hasLeading = leading != null;
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: .dark,
      child: Material(
        color: AppColors.surfaceSubtle,
        shape: const Border(bottom: BorderSide(color: AppColors.borderDefault)),
        child: SafeArea(
          bottom: false,
          child: Column(
            children: [
              ConstrainedBox(
                constraints: const BoxConstraints(minHeight: 44),
                child: Padding(
                  padding: .directional(start: hasLeading ? 8 : 20, end: 8),
                  child: Row(
                    children: [
                      if (hasLeading) ...[
                        SizedBox(
                          width: _sideWidth,
                          child: Align(alignment: .centerStart, child: leading),
                        ),
                      ],
                      Expanded(
                        child: Text(
                          title,
                          style: hasLeading
                              ? TextStyles.text16SB
                              : TextStyles.text17SB,
                          textAlign: hasLeading ? .center : .start,
                        ),
                      ),
                      if (hasLeading) ...[
                        ConstrainedBox(
                          constraints: const BoxConstraints(
                            minWidth: _sideWidth,
                          ),
                          child: Row(
                            mainAxisSize: .min,
                            mainAxisAlignment: .end,
                            children: actions,
                          ),
                        ),
                      ] else ...[
                        const SizedBox(width: 8),
                        ...actions,
                      ],
                    ],
                  ),
                ),
              ),
              ...bottom,
            ],
          ),
        ),
      ),
    );
  }
}

/// A widget that displays a tappable icon in an [AppHeader].
class AppHeaderAction extends StatelessWidget {
  /// Creates an [AppHeaderAction].
  const AppHeaderAction({
    super.key,
    required this.iconAsset,
    required this.onTap,
    this.iconSize = 22,
  });

  /// The action's icon.
  final String iconAsset;

  /// Called when the user taps the action.
  final VoidCallback onTap;

  /// The size of the action's icon.
  final double iconSize;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: .circular(18),
      child: SizedBox.square(
        dimension: 36,
        child: Center(
          child: Image.asset(iconAsset, width: iconSize, height: iconSize),
        ),
      ),
    );
  }
}
