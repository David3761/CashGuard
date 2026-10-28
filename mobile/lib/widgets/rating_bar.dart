import 'dart:math';

import 'package:flutter/material.dart';

/// A widget to receive rating input from users.
///
/// [RatingBar] can also be used to display rating.
///
/// Prefer using [RatingBarIndicator] instead, if read only version is required.
/// As RatingBarIndicator supports any fractional rating value.
class RatingBar extends StatefulWidget {
  /// Creates [RatingBar] using the [_ratingWidget].
  const RatingBar({
    /// Customizes the Rating Bar item with `RatingWidget`.
    required RatingWidget this._ratingWidget,
    required this.onRatingUpdate,
    this.glowColor,
    this.maxRating,
    this.textDirection,
    this.unratedColor,
    this.allowHalfRating = false,
    this.direction = .horizontal,
    this.glow = true,
    this.glowRadius = 2,
    this.ignoreGestures = false,
    this.initialRating = 0.0,
    this.itemCount = 5,
    this.itemPadding = .zero,
    this.itemSize = 40.0,
    this.minRating = 0,
    this.tapOnlyMode = false,
    this.updateOnDrag = false,
    this.wrapAlignment = .start,
    super.key,
  }) : _itemBuilder = null;

  /// Creates [RatingBar] using the [_itemBuilder].
  const RatingBar.builder({
    /// Widget for each rating bar item.
    required IndexedWidgetBuilder this._itemBuilder,
    required this.onRatingUpdate,
    this.glowColor,
    this.maxRating,
    this.textDirection,
    this.unratedColor,
    this.allowHalfRating = false,
    this.direction = .horizontal,
    this.glow = true,
    this.glowRadius = 2,
    this.ignoreGestures = false,
    this.initialRating = 0.0,
    this.itemCount = 5,
    this.itemPadding = .zero,
    this.itemSize = 40.0,
    this.minRating = 0,
    this.tapOnlyMode = false,
    this.updateOnDrag = false,
    this.wrapAlignment = .start,
    super.key,
  }) : _ratingWidget = null;

  /// Called when the rating is updated.
  ///
  /// The [updateOnDrag] parameter can be used to change the behaviour (how the
  /// callback reports the update).
  final ValueChanged<double> onRatingUpdate;

  /// The color for the glow.
  ///
  /// Default is [ColorScheme.secondary].
  final Color? glowColor;

  /// The maximum rating.
  ///
  /// Default is [itemCount].
  final double? maxRating;

  /// The text flows from right to left if
  /// [textDirection] = `TextDirection.rtl`.
  final TextDirection? textDirection;

  /// The color for the unrated portion.
  ///
  /// Default is [ThemeData.disabledColor].
  final Color? unratedColor;

  /// If `true` then half rating is supported.
  ///
  /// Default is `false`.
  final bool allowHalfRating;

  /// The direction of the rating bar.
  ///
  /// Default is [Axis.horizontal].
  final Axis direction;

  /// If `true` then the rating bar item will glow when being touched.
  ///
  /// Default is `true`.
  final bool glow;

  /// The radius of the glow.
  ///
  /// Default is 2.
  final double glowRadius;

  /// If `true` then the gestures over the rating bar are disabled.
  ///
  /// Default is `false`.
  final bool ignoreGestures;

  /// The initial rating of the rating bar.
  final double initialRating;

  /// The total number of rating bar items.
  ///
  /// Default is 5.
  final int itemCount;

  /// The amount of space between each rating item.
  final EdgeInsetsGeometry itemPadding;

  /// Defines the width and height of each rating item in the bar.
  ///
  /// Default is 40.0.
  final double itemSize;

  /// The minimum rating.
  ///
  /// Default is 0.
  final double minRating;

  /// If `true` then the *drag to rate* feature will be disabled.
  ///
  /// **Note:** Enabling this mode will disable half rating capability.
  ///
  /// Default is `false`.
  final bool tapOnlyMode;

  /// If `true` then `onRatingUpdate` will be called while dragging.
  ///
  /// Default is `false`.
  final bool updateOnDrag;

  /// How the item within the [RatingBar] should be placed in the main axis.
  ///
  /// For example, if [wrapAlignment] is [WrapAlignment.center], the item in
  /// the RatingBar are grouped together in the center of their run in the
  /// main axis.
  ///
  /// Defaults to [WrapAlignment.start].
  final WrapAlignment wrapAlignment;

  final IndexedWidgetBuilder? _itemBuilder;

  final RatingWidget? _ratingWidget;

  @override
  State<RatingBar> createState() => _RatingBarState();
}

class _RatingBarState extends State<RatingBar> {
  var _rating = 0.0;
  var _isRTL = false;
  var _iconRating = 0.0;

  late double _minRating;
  late double _maxRating;
  late final ValueNotifier<bool> _glow;

  bool get _isHorizontal => widget.direction == .horizontal;

  @override
  void initState() {
    super.initState();
    _glow = ValueNotifier(false);
    _minRating = widget.minRating;
    _maxRating = widget.maxRating ?? widget.itemCount.toDouble();
    _rating = widget.initialRating;
  }

  @override
  void dispose() {
    _glow.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final textDirection = widget.textDirection ?? Directionality.of(context);
    _isRTL = textDirection == .rtl;
    _iconRating = 0.0;

    return Material(
      color: Colors.transparent,
      child: Wrap(
        alignment: widget.wrapAlignment,
        textDirection: textDirection,
        direction: widget.direction,
        children: List.generate(widget.itemCount, _buildRatingItem),
      ),
    );
  }

  @override
  void didUpdateWidget(RatingBar oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.initialRating != widget.initialRating) {
      _rating = widget.initialRating;
    }
    _minRating = widget.minRating;
    _maxRating = widget.maxRating ?? widget.itemCount.toDouble();
  }

  /// Returns a widget that displays a rating item.
  Widget _buildRatingItem(int index) {
    final ratingWidget = widget._ratingWidget;
    final item = widget._itemBuilder?.call(context, index);
    final ratingOffset = widget.allowHalfRating ? 0.5 : 1.0;

    Widget resolvedRatingWidget;

    if (index >= _rating) {
      resolvedRatingWidget = _NoRatingWidget(
        size: widget.itemSize,
        enableMask: ratingWidget == null,
        unratedColor: widget.unratedColor ?? Theme.of(context).disabledColor,
        child: ratingWidget?.empty ?? item!,
      );
    } else if (index >= _rating - ratingOffset && widget.allowHalfRating) {
      if (ratingWidget?.half == null) {
        resolvedRatingWidget = _HalfRatingWidget(
          size: widget.itemSize,
          enableMask: ratingWidget == null,
          rtlMode: _isRTL,
          unratedColor: widget.unratedColor ?? Theme.of(context).disabledColor,
          child: item!,
        );
      } else {
        resolvedRatingWidget = SizedBox(
          width: widget.itemSize,
          height: widget.itemSize,
          child: FittedBox(
            child: _isRTL
                ? Transform(
                    transform: Matrix4.identity()..scaleByDouble(-1, 1, 1, 1),
                    alignment: .center,
                    transformHitTests: false,
                    child: ratingWidget!.half,
                  )
                : ratingWidget!.half,
          ),
        );
      }
      _iconRating += 0.5;
    } else {
      resolvedRatingWidget = SizedBox(
        width: widget.itemSize,
        height: widget.itemSize,
        child: FittedBox(child: ratingWidget?.full ?? item),
      );
      _iconRating += 1.0;
    }

    return IgnorePointer(
      ignoring: widget.ignoreGestures,
      child: GestureDetector(
        onTapDown: (details) {
          double value;
          if (index == 0 && (_rating == 1 || _rating == 0.5)) {
            value = 0;
          } else {
            final tappedPosition = details.localPosition.dx;
            final tappedOnFirstHalf = tappedPosition <= widget.itemSize / 2;
            value =
                index +
                (tappedOnFirstHalf && widget.allowHalfRating ? 0.5 : 1.0);
          }

          value = max(value, widget.minRating);
          widget.onRatingUpdate(value);
          _rating = value;
          setState(() {});
        },
        onHorizontalDragStart: _isHorizontal ? _onDragStart : null,
        onHorizontalDragEnd: _isHorizontal ? _onDragEnd : null,
        onHorizontalDragUpdate: _isHorizontal ? _onDragUpdate : null,
        onVerticalDragStart: _isHorizontal ? null : _onDragStart,
        onVerticalDragEnd: _isHorizontal ? null : _onDragEnd,
        onVerticalDragUpdate: _isHorizontal ? null : _onDragUpdate,
        child: Padding(
          padding: widget.itemPadding,
          child: ValueListenableBuilder<bool>(
            valueListenable: _glow,
            builder: (context, glow, child) {
              if (glow && widget.glow) {
                final glowColor =
                    widget.glowColor ?? Theme.of(context).colorScheme.secondary;
                return DecoratedBox(
                  decoration: BoxDecoration(
                    shape: .circle,
                    boxShadow: [
                      BoxShadow(
                        color: glowColor.withAlpha(30),
                        blurRadius: 10,
                        spreadRadius: widget.glowRadius,
                      ),
                      BoxShadow(
                        color: glowColor.withAlpha(20),
                        blurRadius: 10,
                        spreadRadius: widget.glowRadius,
                      ),
                    ],
                  ),
                  child: child,
                );
              }
              return child!;
            },
            child: resolvedRatingWidget,
          ),
        ),
      ),
    );
  }

  /// Activates the glow effect.
  void _onDragStart(DragStartDetails details) {
    _glow.value = true;
  }

  /// Updates the rating bar according to the drag event.
  void _onDragUpdate(DragUpdateDetails dragDetails) {
    if (!widget.tapOnlyMode) {
      final box = context.findRenderObject() as RenderBox?;
      if (box == null) {
        return;
      }

      final pos = box.globalToLocal(dragDetails.globalPosition);
      double i;
      if (widget.direction == .horizontal) {
        i = pos.dx / (widget.itemSize + widget.itemPadding.horizontal);
      } else {
        i = pos.dy / (widget.itemSize + widget.itemPadding.vertical);
      }
      var currentRating = widget.allowHalfRating ? i : i.round().toDouble();
      if (currentRating > widget.itemCount) {
        currentRating = widget.itemCount.toDouble();
      }
      if (currentRating < 0) {
        currentRating = 0.0;
      }
      if (_isRTL && widget.direction == .horizontal) {
        currentRating = widget.itemCount - currentRating;
      }

      _rating = currentRating.clamp(_minRating, _maxRating);
      if (widget.updateOnDrag) {
        widget.onRatingUpdate(_iconRating);
      }
      setState(() {});
    }
  }

  /// Deactivates the glow effect and calls `widget.onRatingUpdate`.
  void _onDragEnd(DragEndDetails details) {
    _glow.value = false;
    widget.onRatingUpdate(_iconRating);
    _iconRating = 0.0;
  }
}

/// A class that stores the widgets which are used as rating bar items.
class RatingWidget {
  /// Creates [RatingWidget] with the given [full], [half] and [empty] widgets.
  const RatingWidget({
    required this.full,
    required this.half,
    required this.empty,
  });

  /// The widget to be used as rating bar item when it is completely rated.
  final Widget full;

  /// The widget to be used as rating bar item when half of it is rated.
  final Widget half;

  /// The widget to be used as rating bar item when it is unrated.
  final Widget empty;
}

/// A widget that displays the rating bar item that is half rated.
class _HalfRatingWidget extends StatelessWidget {
  const _HalfRatingWidget({
    required this.size,
    required this.child,
    required this.enableMask,
    required this.rtlMode,
    required this.unratedColor,
  });

  final Widget child;
  final double size;
  final bool enableMask;
  final bool rtlMode;
  final Color unratedColor;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: size,
      width: size,
      child: enableMask
          ? Stack(
              fit: .expand,
              children: [
                FittedBox(
                  child: _NoRatingWidget(
                    size: size,
                    unratedColor: unratedColor,
                    enableMask: enableMask,
                    child: child,
                  ),
                ),
                FittedBox(
                  child: ClipRect(
                    clipper: _HalfClipper(rtlMode: rtlMode),
                    child: child,
                  ),
                ),
              ],
            )
          : FittedBox(child: child),
    );
  }
}

class _HalfClipper extends CustomClipper<Rect> {
  _HalfClipper({required this.rtlMode});

  final bool rtlMode;

  @override
  Rect getClip(Size size) {
    return rtlMode
        ? .fromLTRB(size.width / 2, 0, size.width, size.height)
        : .fromLTRB(0, 0, size.width / 2, size.height);
  }

  @override
  bool shouldReclip(CustomClipper<Rect> oldClipper) => true;
}

/// A widget that displays the rating bar item that is unrated.
class _NoRatingWidget extends StatelessWidget {
  const _NoRatingWidget({
    required this.size,
    required this.child,
    required this.enableMask,
    required this.unratedColor,
  });

  final double size;
  final Widget child;
  final bool enableMask;
  final Color unratedColor;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: size,
      width: size,
      child: FittedBox(
        child: enableMask
            ? ColorFiltered(
                colorFilter: .mode(unratedColor, .srcIn),
                child: child,
              )
            : child,
      ),
    );
  }
}

/// A widget that displays a rating bar with a given rating.
///
/// This is a read only version of [RatingBar].
///
/// Use [RatingBar] if interactive version is required (i.e.: if user input
/// is required)
class RatingBarIndicator extends StatefulWidget {
  /// Creates a [RatingBarIndicator].
  const RatingBarIndicator({
    required this.itemBuilder,
    this.textDirection,
    this.unratedColor,
    this.direction = .horizontal,
    this.itemCount = 5,
    this.itemPadding = .zero,
    this.itemSize = 40.0,
    this.physics = const NeverScrollableScrollPhysics(),
    this.rating = 0.0,
    super.key,
  });

  /// The builder to use for creating the rating bar item.
  final IndexedWidgetBuilder itemBuilder;

  /// The text flows from right to left if
  /// [textDirection] = `TextDirection.rtl`.
  final TextDirection? textDirection;

  /// The color for the unrated portion.
  ///
  /// Default is [ThemeData.disabledColor].
  final Color? unratedColor;

  /// The direction of the rating bar.
  ///
  /// Default is [Axis.horizontal].
  final Axis direction;

  /// The total number of rating bar items.
  ///
  /// Default is 5.
  final int itemCount;

  /// The amount of space between each rating item.
  final EdgeInsets itemPadding;

  /// Defines the width and height of each rating item in the bar.
  ///
  /// Default is 40.0.
  final double itemSize;

  /// Controls the scrolling behaviour of rating bar.
  ///
  /// Default is [NeverScrollableScrollPhysics].
  final ScrollPhysics physics;

  /// The rating value for the rating bar indicator.
  ///
  /// Default is 0.0.
  final double rating;

  @override
  State<RatingBarIndicator> createState() => _RatingBarIndicatorState();
}

class _RatingBarIndicatorState extends State<RatingBarIndicator> {
  double _ratingFraction = 0;
  int _ratingNumber = 0;
  bool _isRTL = false;

  @override
  void initState() {
    super.initState();
    _ratingNumber = widget.rating.truncate() + 1;
    _ratingFraction = widget.rating - _ratingNumber + 1;
  }

  @override
  Widget build(BuildContext context) {
    final textDirection = widget.textDirection ?? Directionality.of(context);
    _isRTL = textDirection == .rtl;
    _ratingNumber = widget.rating.truncate() + 1;
    _ratingFraction = widget.rating - _ratingNumber + 1;
    return SingleChildScrollView(
      scrollDirection: widget.direction,
      physics: widget.physics,
      child: widget.direction == .horizontal
          ? Row(
              mainAxisSize: .min,
              textDirection: textDirection,
              children: _buildItems(),
            )
          : Column(
              mainAxisSize: .min,
              textDirection: textDirection,
              children: _buildItems(),
            ),
    );
  }

  List<Widget> _buildItems() {
    return List.generate(widget.itemCount, (index) {
      if (widget.textDirection != null) {
        if (widget.textDirection == .rtl &&
            Directionality.of(context) != .rtl) {
          return Transform(
            transform: Matrix4.identity()..scaleByDouble(-1, 1, 1, 1),
            alignment: .center,
            transformHitTests: false,
            child: _buildItem(index),
          );
        }
      }
      return _buildItem(index);
    });
  }

  Widget _buildItem(int index) {
    return Padding(
      padding: widget.itemPadding,
      child: SizedBox(
        width: widget.itemSize,
        height: widget.itemSize,
        child: Stack(
          fit: .expand,
          children: [
            FittedBox(
              child: index + 1 < _ratingNumber
                  ? widget.itemBuilder(context, index)
                  : ColorFiltered(
                      colorFilter: .mode(
                        widget.unratedColor ?? Theme.of(context).disabledColor,
                        .srcIn,
                      ),
                      child: widget.itemBuilder(context, index),
                    ),
            ),
            if (index + 1 == _ratingNumber) ...[
              if (_isRTL) ...[
                FittedBox(
                  child: ClipRect(
                    clipper: _IndicatorClipper(
                      ratingFraction: _ratingFraction,
                      rtlMode: _isRTL,
                    ),
                    child: widget.itemBuilder(context, index),
                  ),
                ),
              ] else ...[
                FittedBox(
                  child: ClipRect(
                    clipper: _IndicatorClipper(ratingFraction: _ratingFraction),
                    child: widget.itemBuilder(context, index),
                  ),
                ),
              ],
            ],
          ],
        ),
      ),
    );
  }
}

class _IndicatorClipper extends CustomClipper<Rect> {
  _IndicatorClipper({required this.ratingFraction, this.rtlMode = false});

  final double ratingFraction;
  final bool rtlMode;

  @override
  Rect getClip(Size size) {
    return rtlMode
        ? .fromLTRB(
            size.width - size.width * ratingFraction,
            0,
            size.width,
            size.height,
          )
        : .fromLTRB(0, 0, size.width * ratingFraction, size.height);
  }

  @override
  bool shouldReclip(_IndicatorClipper oldClipper) {
    return ratingFraction != oldClipper.ratingFraction ||
        rtlMode != oldClipper.rtlMode;
  }
}
