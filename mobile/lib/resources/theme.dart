import 'package:cashctrl/resources/colors.dart';
import 'package:flutter/material.dart';

/// The app's colors, so that the Material widgets that aren't designed (menus,
/// dialogs, sheets) use the design's surfaces instead of Material's defaults.
const colorScheme = ColorScheme.light(
  primary: AppColors.textPrimary,
  secondaryContainer: AppColors.surfaceSelection,
  onSecondaryContainer: AppColors.textPrimary,
  onSurface: AppColors.textPrimary,
  outline: AppColors.borderDefault,
  surfaceContainerLowest: AppColors.surfaceBase,
  surfaceContainerLow: AppColors.surfaceBase,
  surfaceContainer: AppColors.surfaceBase,
  surfaceContainerHigh: AppColors.surfaceBase,
  surfaceContainerHighest: AppColors.surfaceBase,
);

/// The theme of the filled buttons, which are the primary actions and use the
/// brand color.
final filledButtonTheme = FilledButtonThemeData(
  style: FilledButton.styleFrom(
    backgroundColor: AppColors.surfaceBrand,
    foregroundColor: AppColors.textPrimary,
  ),
);

/// The theme of the date pickers, which Material gives square corners by
/// default.
final datePickerTheme = DatePickerThemeData(
  rangePickerShape: RoundedRectangleBorder(borderRadius: .circular(20)),
);
