import 'dart:async';

import 'package:cashctrl/l10n/app_localizations.dart';
import 'package:cashctrl/resources/colors.dart';
import 'package:cashctrl/resources/images.dart';
import 'package:cashctrl/utils/dialogs.dart';
import 'package:cashctrl/utils/utils.dart';
import 'package:cashctrl/widgets/web_page_sheet.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// A widget used as the main container for a new screen. It contains a
/// Scaffold and a [MyAppBar].
class ScreenStack extends StatelessWidget {
  /// Creates a [ScreenStack].
  const ScreenStack({
    super.key,
    required this.children,
    this.title,
    this.appBarHeight,
    this.leading,
    this.actions,
    this.drawer,
    this.backgroundColor,
    this.centerTitle = true,
    this.showAppBar = true,
    this.showLogo = true,
    this.showProgressIndicator = false,
  });

  /// The body of the screen. This child will be placed in a [Scaffold].
  final List<Widget> children;

  /// The app bar's title. Even if this is not null and [showLogo] is `true`
  /// then the logo will be displayed instead.
  final Widget? title;

  /// The app bar's height. Defaults to [kToolbarHeight].
  final double? appBarHeight;

  /// A button that should be displayed on the left, if any.
  final Widget? leading;

  /// The app bar's actions.
  final List<Widget>? actions;

  /// A widget that displays the menu drawer.
  final Widget? drawer;

  /// The scaffold's background color.
  final Color? backgroundColor;

  /// If this is `true` then the [title] will be centered.
  final bool centerTitle;

  /// Whether or not to show the app bar.
  ///
  /// If [showAppBar] is `false`, then [showLogo] will be ignored.
  final bool showAppBar;

  /// Whether or not to show the app logo in the middle of the app bar.
  ///
  /// If [showAppBar] is `false`, then [showLogo] will be ignored.
  final bool showLogo;

  /// If `true`, then a circular progress indicator, centered in parent, will
  /// be displayed.
  final bool showProgressIndicator;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: backgroundColor,
      appBar: showAppBar
          ? MyAppBar(
              title: title,
              leading: leading,
              actions: actions,
              showLogo: showLogo,
            )
          : null,
      body: LoadingStack(
        showProgressIndicator: showProgressIndicator,
        children: children,
      ),
      drawer: drawer,
    );
  }
}

/// A widget for displaying the app's AppBar.
class MyAppBar extends StatelessWidget implements PreferredSizeWidget {
  /// Creates a [MyAppBar].
  const MyAppBar({
    super.key,
    this.title,
    this.centerTitle = true,
    this.leading,
    this.showLogo = true,
    this.backgroundColor = Colors.white,
    this.actions,
    double? height,
  }) : height = height ?? kToolbarHeight;

  /// The app bar's title. If this is not null and [showLogo] is `true` then
  /// the logo will be displayed instead.
  final Widget? title;

  /// If this is `true` then the [title] will be centered.
  final bool centerTitle;

  /// A button that should be displayed on the left, if any.
  final Widget? leading;

  /// Whether or not to show the app logo in the app bar. If this is `true` and
  /// [title] is not null, then the logo will be displayed.
  final bool showLogo;

  /// The app bar's background color.
  final Color backgroundColor;

  /// The app bar's actions.
  final List<Widget>? actions;

  /// The app bar's height. Defaults to [kToolbarHeight].
  final double height;

  @override
  Widget build(BuildContext context) {
    return AppBar(
      // Don't remove! Only use the lines below if you're not setting the
      // status bar color in the "main" method right after the "runApp" call.
      /*systemOverlayStyle: const SystemUiOverlayStyle(
        statusBarColor: AppColors.blue700,
      ),*/
      leading: leading,
      title: switch ((showLogo, title)) {
        (true, _) => const Image(
          image: AssetImage(AppImages.appLogo),
          height: 30,
        ),
        (_, != null) => title,
        _ => null,
      },
      backgroundColor: backgroundColor,
      // this will hide Drawer hamburger icon
      centerTitle: centerTitle,
      // this will hide endDrawer hamburger icon
      actions: actions ?? const [SizedBox.shrink()],
      toolbarHeight: height,
    );
  }

  @override
  Size get preferredSize => const .fromHeight(kToolbarHeight);
}

/// A infinite height container with a red-violet gradient background.
class GradientContainer extends StatelessWidget {
  /// Creates a [GradientContainer].
  const GradientContainer({super.key, required this.child});

  /// A widget that will be places as a child of this [GradientContainer].
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: double.infinity,
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          colors: [AppColors.red, AppColors.violet],
          begin: .topCenter,
          end: .bottomCenter,
        ),
      ),
      child: child,
    );
  }
}

/// A widget that displays a TextField.
class TextForm extends StatefulWidget {
  /// Creates a [TextForm].
  const TextForm({
    super.key,
    required this.text,
    required this.labelText,
    required this.obscured,
    required this.onChanged,
    this.keyboardType,
    this.inputFormatters,
  });

  /// The initial text.
  final String text;

  /// The label of the text form.
  final String labelText;

  /// Whether the content of the text form should be hidden (e.g.: a password).
  final bool obscured;

  /// Called when the text inside the text form changes.
  final ValueChanged<String> onChanged;

  /// The keyboard type (e.g.: numbers, text, text multiline, etc).
  final TextInputType? keyboardType;

  /// A list with input formatters.
  final List<TextInputFormatter>? inputFormatters;

  @override
  State<TextForm> createState() => _TextFormState();
}

class _TextFormState extends State<TextForm> {
  final _controller = TextEditingController();

  /// Initializes the [_controller].
  @override
  void initState() {
    super.initState();
    _controller.text = widget.text;
  }

  /// Disposes of the [_controller].
  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: _controller,
      decoration: InputDecoration(
        filled: true,
        labelText: widget.labelText,
        // enabledBorder: const UnderlineInputBorder(
        //     borderSide: BorderSide(color: Colors.white)),
        /*border: OutlineInputBorder(
          borderRadius: .circular(100),
          borderSide: const BorderSide(color: AppColors.darkerGray, width: 1),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: .circular(100),
          borderSide: const BorderSide(color: AppColors.darkerGray, width: 1),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: .circular(100),
          borderSide: const BorderSide(color: AppColors.violet, width: 1),
        ),*/
      ),
      keyboardType: widget.keyboardType,
      inputFormatters: widget.inputFormatters,
      obscureText: widget.obscured,
      onChanged: widget.onChanged,
    );
  }

  /// This method ensures that when the widget's text property changes, the
  /// [TextField] is also updated using the [_controller].
  ///
  /// Since this is a [StatefulWidget] and the [TextField] text value is
  /// dictated by the [TextEditingController], in order to be able to change
  /// the current displayed text from outside of this [TextForm] widget, we need
  /// to add some code inside the [didUpdateWidget] method that updates the
  /// [TextEditingController] text value to the latest widget's text value.
  @override
  void didUpdateWidget(covariant TextForm oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.text != widget.text) {
      _controller.text = widget.text;
    }
  }
}

/// A widget that displays a rounded TextField.
class RoundedTextForm extends StatefulWidget {
  /// Creates a [RoundedTextForm].
  const RoundedTextForm({
    super.key,
    required this.text,
    required this.labelText,
    required this.obscured,
    required this.onChanged,
    this.keyboardType,
    this.inputFormatters,
  });

  /// The initial text.
  final String text;

  /// The label of the text form.
  final String labelText;

  /// Whether the content of the text form should be hidden (e.g.: a password).
  final bool obscured;

  /// Called when the text inside the text form changes.
  final ValueChanged<String> onChanged;

  /// The keyboard type (e.g.: numbers, text, text multiline, etc).
  final TextInputType? keyboardType;

  /// A list with input formatters.
  final List<TextInputFormatter>? inputFormatters;

  @override
  State<RoundedTextForm> createState() => _RoundedTextFormState();
}

class _RoundedTextFormState extends State<RoundedTextForm> {
  final _controller = TextEditingController();

  /// Initializes the [_controller].
  @override
  void initState() {
    super.initState();
    _controller.text = widget.text;
  }

  /// Disposes of the [_controller].
  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: _controller,
      decoration: InputDecoration(
        filled: true,
        labelText: widget.labelText,
        labelStyle: const TextStyle(color: Colors.white),
        // enabledBorder: const UnderlineInputBorder(
        //     borderSide: BorderSide(color: Colors.white)),
        border: OutlineInputBorder(
          borderRadius: .circular(100),
          borderSide: const BorderSide(color: AppColors.darkerGray),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: .circular(100),
          borderSide: const BorderSide(color: AppColors.darkerGray),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: .circular(100),
          borderSide: const BorderSide(color: AppColors.violet),
        ),
      ),
      style: const TextStyle(color: Colors.white),
      keyboardType: widget.keyboardType,
      inputFormatters: widget.inputFormatters,
      obscureText: widget.obscured,
      onChanged: widget.onChanged,
    );
  }

  /// This method ensures that when the widget's text property changes, the
  /// [TextField] is also updated using the [_controller].
  ///
  /// Since this is a [StatefulWidget] and the [TextField] text value is
  /// dictated by the [TextEditingController], in order to be able to change
  /// the current displayed text from outside of this [TextForm] widget, we need
  /// to add some code inside the [didUpdateWidget] method that updates the
  /// [TextEditingController] text value to the latest widget's text value.
  @override
  void didUpdateWidget(covariant RoundedTextForm oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.text != oldWidget.text && widget.text != _controller.text) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _controller.text = widget.text;
      });
    }
  }
}

/// A widget that displays a dropdown form.
class DropdownForm<T> extends StatelessWidget {
  /// Creates a [DropdownForm].
  const DropdownForm({
    super.key,
    required this.items,
    required this.value,
    required this.itemBuilder,
    required this.onChanged,
    this.hint,
  });

  /// The items list.
  final List<T> items;

  /// The selected item.
  final T? value;

  /// A builder that draws the items of the dropdown form.
  final Widget Function(T) itemBuilder;

  /// Called when a new item is selected.
  final Function(T?)? onChanged;

  /// The dropdown form hint, that acts as a pre-selected value.
  final Widget? hint;

  @override
  Widget build(BuildContext context) {
    return DropdownButtonFormField<T>(
      hint: hint,
      initialValue: value,
      isExpanded: true,
      items: items
          .map(
            (item) => DropdownMenuItem(value: item, child: itemBuilder(item)),
          )
          .toList(),
      onChanged: onChanged,
      decoration: const InputDecoration(
        focusedBorder: UnderlineInputBorder(),
        contentPadding: .symmetric(horizontal: 10, vertical: 17),
        filled: true,
      ),
    );
  }
}

/// A widget that displays a bigger ElevatedButton.
class BigButton extends StatelessWidget {
  /// Creates a [BigButton].
  const BigButton({
    super.key,
    required this.labelText,
    required this.onPressed,
  });

  /// The button's label.
  final String labelText;

  /// Called when the user taps the button.
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return ElevatedButton(
      onPressed: onPressed,
      child: Padding(padding: const .all(15), child: Text(labelText)),
    );
  }
}

/// A widget that displays a rounded white ElevatedButton.
class RoundedBigButton extends StatelessWidget {
  /// Creates a [RoundedBigButton].
  const RoundedBigButton({
    super.key,
    required this.labelText,
    required this.onPressed,
  });

  /// The button's label.
  final String labelText;

  /// Called when the user taps the button.
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return ElevatedButton(
      onPressed: onPressed,
      style: ElevatedButton.styleFrom(
        minimumSize: const Size(double.infinity, 50),
        foregroundColor: Colors.white,
        backgroundColor: Colors.white,
        shape: RoundedRectangleBorder(
          borderRadius: .circular(100),
          side: const BorderSide(color: Colors.white, width: 0.5),
        ),
      ),
      child: Text(labelText, style: const TextStyle(color: Colors.black)),
    );
  }
}

/// A widget that displays a rounded gray ElevatedButton.
class RoundedGrayButton extends StatelessWidget {
  /// Creates a [RoundedGrayButton].
  const RoundedGrayButton({
    super.key,
    required this.labelText,
    required this.onPressed,
  });

  /// The button's label.
  final String labelText;

  /// Called when the user taps the button
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return ElevatedButton(
      onPressed: onPressed,
      style: ElevatedButton.styleFrom(
        minimumSize: const Size(200, 44),
        backgroundColor: AppColors.gray,
        shape: RoundedRectangleBorder(borderRadius: .circular(100)),
      ),
      child: Text(labelText, style: const TextStyle(color: Colors.black)),
    );
  }
}

/// A widget that displays a line divider.
class LineDivider extends StatelessWidget {
  /// Creates a [LineDivider].
  const LineDivider({super.key, required this.color, this.height = 1.0});

  /// The height and thickness of the divider.
  final double height;

  /// The color of the divider.
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Divider(height: height, thickness: height, color: color);
  }
}

/// A widget that displays an image from the local assets directory provided
/// though the given ImageProvider.
class LocalImageItem extends StatelessWidget {
  /// Creates a [LocalImageItem].
  const LocalImageItem({super.key, required this.image});

  /// The provider containing the data of the image that will be displayed.
  final ImageProvider image;

  @override
  Widget build(BuildContext context) {
    return Image(image: image, fit: .cover);
  }
}

/// A widget that displays a scrollable view that extends to fill the screen
/// height if its contents don’t occupy the full height of the screen;
/// if the content is bigger, it scrolls.
class FullScrollView extends StatelessWidget {
  /// Creates a [FullScrollView].
  const FullScrollView({
    super.key,
    required this.controller,
    this.children = const [],
  });

  /// The children that will be displayed.
  final List<Widget> children;

  /// The controller that controls the scroll.
  final ScrollController controller;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        return SingleChildScrollView(
          controller: controller,
          child: ConstrainedBox(
            constraints: BoxConstraints(
              minWidth: constraints.maxWidth,
              minHeight: constraints.maxHeight,
            ),
            child: IntrinsicHeight(child: Column(children: children)),
          ),
        );
      },
    );
  }
}

/// A widget that displays a shadow around the child and can be used to replace
/// the Card for a more granular approach.
class CustomCard extends StatelessWidget {
  /// Creates a [CustomCard].
  const CustomCard({
    super.key,
    required this.child,
    required this.color,
    this.elevation = 2,
    this.borderRadius = const .all(.circular(10)),
    this.splashColor,
    this.padding,
    this.onTap,
  });

  /// The widget that the custom card will be applied to.
  final Widget child;

  /// The background color. Instead of having a Container in the [child], you
  /// can use this parameter to change the color.
  final Color color;

  /// The elevation of the custom card.
  final double elevation;

  /// The border's radius that will be applied to the child.
  final BorderRadius? borderRadius;

  /// The color that can be seen when the widget is tapped.
  final Color? splashColor;

  /// The padding that will be applied to the child.
  final EdgeInsetsGeometry? padding;

  /// Called when the user taps the card.
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: padding ?? .directional(bottom: 2 * elevation),
      child: Material(
        elevation: elevation,
        color: color,
        borderRadius: borderRadius,
        child: InkWell(
          splashColor: splashColor,
          borderRadius: borderRadius,
          onTap: onTap,
          child: child,
        ),
      ),
    );
  }
}

/// A widget that adds a shadow effect to the bottom of the view.
class BottomShadow extends StatelessWidget {
  /// Creates a [BottomShadow].
  const BottomShadow({
    super.key,
    required this.child,
    this.backgroundColor,
    this.shadowColor = AppColors.shadowGray,
    this.shadowOffset = const Offset(0, 4),
    this.shadowBlurRadius = 15,
    this.borderRadius,
    this.border,
    this.padding,
    this.shape = .rectangle,
    this.clipBehavior = .none,
  });

  /// The widget that the bottom shadow will be applied to.
  final Widget child;

  /// The background color. Instead of having a Container in the [child], you
  /// can use this parameter to change the color.
  final Color? backgroundColor;

  /// The shadow's color.
  final Color shadowColor;

  /// The shadow's offset.
  final Offset shadowOffset;

  /// The shadow's blur radius.
  final double shadowBlurRadius;

  /// The border's radius that will be applied to the child.
  final BorderRadiusGeometry? borderRadius;

  /// The border that will be applied to the child.
  final BoxBorder? border;

  /// The padding that will be applied to the child.
  final EdgeInsetsGeometry? padding;

  /// The clip behavior that will be applied to the child.
  final Clip clipBehavior;

  /// The container's shape.
  final BoxShape shape;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: padding,
      decoration: BoxDecoration(
        color: backgroundColor,
        borderRadius: borderRadius,
        border: border,
        boxShadow: [
          BoxShadow(
            color: shadowColor,
            blurRadius: shadowBlurRadius,
            offset: shadowOffset,
          ),
        ],
        shape: shape,
      ),
      clipBehavior: clipBehavior,
      child: child,
    );
  }
}

/// A widget that displays a stack containing the given [children] and a
/// [CircularProgressIndicator].
///
/// The [CircularProgressIndicator] will be visible only if
/// [showProgressIndicator] is true.
class LoadingStack extends StatelessWidget {
  /// Creates a [LoadingStack].
  const LoadingStack({
    super.key,
    required this.showProgressIndicator,
    required this.children,
    this.progressIndicatorColor = Colors.black,
    this.alignment = .topStart,
  });

  /// If `true`, then a circular progress indicator, centered in parent, will
  /// be displayed.
  final bool showProgressIndicator;

  /// The progress indicator's color.
  final Color progressIndicatorColor;

  /// The stack's children.
  final List<Widget> children;

  /// The stack's alignment.
  final AlignmentGeometry alignment;

  @override
  Widget build(BuildContext context) {
    return Stack(
      alignment: alignment,
      children: [
        ...children,
        Align(
          child: Visibility(
            visible: showProgressIndicator,
            child: CircularProgressIndicator(color: progressIndicatorColor),
          ),
        ),
      ],
    );
  }
}

/// Returns a simple SnackBar containing the given [text].
SnackBar getSimpleSnackBar(String text) => SnackBar(content: Text(text));

/// Displays the given [child] in a bottom sheet.
Future<T?> showSheet<T>(
  BuildContext context,
  Widget child, {
  bool enableDrag = true,
  double topPadding = 0,
}) {
  return showModalBottomSheet(
    enableDrag: enableDrag,
    isScrollControlled: true,
    context: context,
    useSafeArea: true,
    backgroundColor: Colors.transparent,
    barrierColor: const .fromRGBO(0, 0, 0, 0.7),
    constraints: BoxConstraints(maxWidth: MediaQuery.sizeOf(context).width),
    builder: (context) => LayoutBuilder(
      builder: (context, constraints) => ConstrainedBox(
        constraints: BoxConstraints(
          maxHeight: constraints.maxHeight - kToolbarHeight - topPadding,
        ),
        child: Padding(
          padding: .directional(
            bottom: MediaQuery.viewInsetsOf(context).bottom,
          ),
          child: child,
        ),
      ),
    ),
  );
}

/// Returns a clickable text span that will change its color when is selected.
TextSpan buildClickableTextSpan({
  required String text,
  required bool isPressed,
  required TextStyle style,
  required Color pressedColor,
  required VoidCallback onTap,
  required Function(bool) onChangedSelection,
}) {
  return TextSpan(
    text: text,
    style: isPressed
        ? style.copyWith(color: pressedColor, decorationColor: pressedColor)
        : style,
    recognizer: TapGestureRecognizer()
      ..onTapUp = ((_) => onChangedSelection(false))
      ..onTap = onTap
      ..onTapDown = (_) => onChangedSelection(true),
  );
}

/// Opens the [WebPageSheet] to display the content for the given [url] or
/// displays an error alert if the [url] cannot be opened.
Future<void> openUrlOrShowError({
  required BuildContext context,
  required String name,
  required String url,
  double topPadding = 0,
}) async {
  if (await canOpenUrl(url)) {
    if (context.mounted) {
      unawaited(
        showSheet(
          context,
          WebPageSheet(title: name, url: url),
          enableDrag: false,
          topPadding: topPadding,
        ),
      );
    }
  } else {
    if (context.mounted) {
      unawaited(
        showAlert(
          context: context,
          title: AppLocalizations.of(context).error_,
          message: AppLocalizations.of(context).couldNotOpenUrl,
        ),
      );
    }
  }
}

/// A widget that displays its children in a [Row] if the maximum width is at
/// least 600 pixels and in a [Wrap] otherwise. The provided [childrenBuilder]
/// method provides a [bool] that can be used to adapt the UI based on whether
/// the device has at least 600 pixels or not.
class ResponsiveRowBuilder extends StatelessWidget {
  /// Creates a [ResponsiveRowBuilder].
  const ResponsiveRowBuilder({
    super.key,
    required this.childrenBuilder,
    this.wrapAlignment = .start,
    this.wrapSpacing = 10,
    this.wrapRunAlignment = .start,
    this.wrapRunSpacing = 10,
    this.rowMainAxisAlignment = .start,
    this.rowCrossAxisAlignment = .center,
  });

  /// The `alignment` for the [Wrap] widget.
  final WrapAlignment wrapAlignment;

  /// The `spacing` to use for the [Wrap] widget.
  final double wrapSpacing;

  /// The `runAlignment` for the [Wrap] widget.
  final WrapAlignment wrapRunAlignment;

  /// The `runSpacing` to use for the [Wrap] widget.
  final double wrapRunSpacing;

  /// The `mainAxisAlignment` for the [Row] widget.
  final MainAxisAlignment rowMainAxisAlignment;

  /// The `crossAxisAlignment` for the [Row] widget.
  final CrossAxisAlignment rowCrossAxisAlignment;

  /// A builder function that provides the [BuildContext] and a [bool] that is
  /// `true` if the device is a phone (i.e. the maximum width is less than 600
  /// pixels), or `false` otherwise (i.e. the maximum width is at least 600
  /// pixels).
  final List<Widget> Function(BuildContext context, bool isPhone)
  childrenBuilder;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        if (constraints.maxWidth < 600) {
          // This is a small device. The content should be wrapped.
          return Wrap(
            alignment: wrapAlignment,
            spacing: wrapSpacing,
            runAlignment: wrapRunAlignment,
            runSpacing: wrapRunSpacing,
            crossAxisAlignment: .center,
            children: childrenBuilder(context, false),
          );
        } else {
          // This is a big device. The content can extend to fill the available
          // width.
          return Row(
            mainAxisAlignment: rowMainAxisAlignment,
            crossAxisAlignment: rowCrossAxisAlignment,
            children: childrenBuilder(context, true),
          );
        }
      },
    );
  }
}

/// A widget that returns the [child] wrapped with the result of the
/// [conditionalBuilder] if [condition] is `true`; otherwise it returns the
/// [child] directly.
///
/// This widget can be used in conjunction with the [ResponsiveRowBuilder] as
/// follows:
///
/// ```dart
/// ConditionalParentWidget(
///   condition: isPhone,
///   conditionalBuilder: (context, child) => Flexible(
///     child: child,
///   ),
///   child: StudyPlanItemTile(
///     title: localizations.practiceTarget,
///     value: localizations.ofMin(totalTarget),
///     imageAsset: AppImages.clockCircle,
///   ),
/// ),
/// ```
/// By using this widget, you can conditionally use [Expanded] or [Flexible]
/// widgets only the child is displayed in a [Row] or [Column].
class ConditionalParentWidget extends StatelessWidget {
  /// Creates a [ConditionalParentWidget].
  const ConditionalParentWidget({
    super.key,
    required this.condition,
    required this.conditionalBuilder,
    required this.child,
  });

  /// If `true` the widget will return the [conditionalBuilder] passing it the
  /// [child].
  final bool condition;

  /// A widget that provides the the [BuildContext] and [child] fields.
  final Widget Function(BuildContext context, Widget child) conditionalBuilder;

  /// The widget that will be displayed either directly or wrapped with the
  /// result of the [conditionalBuilder].
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return condition ? conditionalBuilder(context, child) : child;
  }
}
