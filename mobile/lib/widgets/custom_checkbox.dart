import 'package:cashctrl/resources/colors.dart';
import 'package:flutter/material.dart';

/// A widget that displays a custom checkbox.
class CustomCheckbox extends StatelessWidget {
  /// Creates a [CustomCheckbox]
  const CustomCheckbox({
    super.key,
    required this.width,
    required this.height,
    required this.isSelected,
    required this.checkColor,
    required this.fillColor,
    required this.onChanged,
    this.unselectedBorderSide = const BorderSide(
      width: 2,
      color: AppColors.gray,
    ),
  });

  /// The checkbox width.
  final double width;

  /// The checkbox height.
  final double height;

  /// The checkbox selected state.
  final bool? isSelected;

  /// The checkbox selected color.
  final Color checkColor;

  /// The checkbox fill color.
  final Color fillColor;

  /// The checkbox border side for the unselected state.
  final BorderSide unselectedBorderSide;

  /// Called when the selected state changes.
  final ValueChanged<bool?>? onChanged;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: width,
      height: height,
      child: Checkbox(
        value: isSelected,
        onChanged: onChanged,
        checkColor: checkColor,
        shape: RoundedRectangleBorder(borderRadius: .circular(3)),
        fillColor: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            final opacity = states.contains(WidgetState.disabled) ? 0.5 : 1.0;
            return fillColor.withValues(alpha: opacity);
          }
          return Colors.transparent;
        }),
        side: WidgetStateBorderSide.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return null;
          }
          return const BorderSide(width: 2, color: AppColors.gray);
        }),
      ),
    );
  }
}
