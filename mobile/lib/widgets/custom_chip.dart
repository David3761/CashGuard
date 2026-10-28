import 'package:cashctrl/resources/text_styles.dart';
import 'package:flutter/material.dart';

/// A widget that displays a custom chip.
class CustomChip extends StatelessWidget {
  /// Creates a [CustomChip].
  const CustomChip({
    super.key,
    required this.backgroundColor,
    this.border,
    this.borderRadius = 50,
    this.padding = const .symmetric(horizontal: 12, vertical: 4),
    this.icon,
    this.labelText,
    this.labelStyle,
    this.label,
  });

  /// The chip's background color.
  final Color backgroundColor;

  /// The chip's border.
  final BoxBorder? border;

  /// The chip's border radius.
  final double borderRadius;

  /// The chip's content padding.
  final EdgeInsetsGeometry padding;

  /// The chip's icon that will be displayed to the left of [labelText] or
  /// [label] (depending on which is present).
  final Widget? icon;

  /// The chip's label text.
  ///
  /// If both [label] and [labelText] are used, then [labelText] will be
  /// ignored.
  final String? labelText;

  /// The chip's label text style.
  ///
  /// If [label] is used, then this will be ignored.
  final TextStyle? labelStyle;

  /// The chip's label.
  ///
  /// If both [label] and [labelText] are used, then [labelText] will be
  /// ignored.
  final Widget? label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: padding,
      decoration: BoxDecoration(
        color: backgroundColor,
        borderRadius: .circular(borderRadius),
        border: border,
      ),
      child: Row(
        mainAxisSize: .min,
        children: [
          if (icon != null) ...[icon!, const SizedBox(width: 6)],
          Flexible(
            child:
                label ??
                Text(
                  labelText ?? '',
                  style:
                      labelStyle ??
                      TextStyles.text14SB.copyWith(color: Colors.white),
                ),
          ),
        ],
      ),
    );
  }
}

/// A widget that displays a choice chip.
class CustomChoiceChip extends StatelessWidget {
  /// Creates a [CustomChoiceChip].
  const CustomChoiceChip({
    super.key,
    required this.selectedBackgroundColor,
    required this.unselectedBackgroundColor,
    required this.isSelected,
    required this.labelText,
    required this.selectedLabelStyle,
    required this.unselectedLabelStyle,
    this.disabledLabelStyle,
    this.padding = const .symmetric(vertical: 4, horizontal: 8),
    this.borderRadius = 50,
    this.borderSide,
    this.onTap,
  });

  /// The chip's selected background color.
  final Color selectedBackgroundColor;

  /// The chip's unselected background color.
  final Color unselectedBackgroundColor;

  /// The chip's selected state.
  final bool isSelected;

  /// The chip's label text.
  final String labelText;

  /// The chip's label text style when the state is selected.
  final TextStyle selectedLabelStyle;

  /// The chip's label text style when the state is unselected.
  final TextStyle unselectedLabelStyle;

  /// The chip's label text style when the state is disabled.
  final TextStyle? disabledLabelStyle;

  /// The chip's content padding.
  final EdgeInsetsGeometry padding;

  /// The chip's border radius.
  final double borderRadius;

  /// The chip's border side.
  final BorderSide? borderSide;

  /// Called when the user taps the chip.
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      shape: borderSide != null
          ? RoundedRectangleBorder(
              borderRadius: .circular(borderRadius),
              side: borderSide!,
            )
          : null,
      borderRadius: borderSide == null ? .circular(borderRadius) : null,
      color: isSelected ? selectedBackgroundColor : unselectedBackgroundColor,
      child: InkWell(
        borderRadius: .circular(50),
        onTap: onTap,
        child: CustomChip(
          backgroundColor: Colors.transparent,
          padding: padding,
          labelText: labelText,
          labelStyle: onTap == null
              ? disabledLabelStyle
              : isSelected
              ? selectedLabelStyle
              : unselectedLabelStyle,
        ),
      ),
    );
  }
}
