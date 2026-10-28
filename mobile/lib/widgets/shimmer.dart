import 'package:flutter/material.dart';

/// A widget that displays a chrome color with a shimmer animation over the
/// shapes that approximate the type of content that is loading.
///
/// The use of a shimmer animation is to communicate to users, in a smooth
/// manner, that data is loading.
class Shimmer extends StatefulWidget {
  /// Creates a [Shimmer].
  const Shimmer({super.key, required this.linearGradient, this.child});

  /// A linear gradient to use when displaying the shimmer.
  final LinearGradient linearGradient;

  /// The child that sits underneath the shimmer widget.
  final Widget? child;

  @override
  State<Shimmer> createState() => ShimmerState();

  /// Returns the shimmer's state.
  static ShimmerState? of(BuildContext context) {
    return context.findAncestorStateOfType<ShimmerState>();
  }
}

/// The state of the [Shimmer] widget.
class ShimmerState extends State<Shimmer> with SingleTickerProviderStateMixin {
  late AnimationController _shimmerController;

  /// The linear gradient to be used for the shimmer.
  LinearGradient get gradient => LinearGradient(
    colors: widget.linearGradient.colors,
    stops: widget.linearGradient.stops,
    begin: widget.linearGradient.begin,
    end: widget.linearGradient.end,
    transform: _SlidingGradientTransform(
      slidePercent: _shimmerController.value,
    ),
  );

  /// Returns `true` if the widget has a size, or `false` otherwise.
  bool get isSized =>
      (context.findRenderObject() as RenderBox?)?.hasSize ?? false;

  /// Returns the widget's size or [Size.zero].
  Size get size => (context.findRenderObject() as RenderBox?)?.size ?? .zero;

  /// Returns the shimmer's animation controller as a listenable object that
  /// can be observed.
  Listenable get shimmerChanges => _shimmerController;

  @override
  void initState() {
    super.initState();
    _shimmerController = AnimationController.unbounded(vsync: this);
    _shimmerController.repeat(
      min: -0.5,
      max: 1.5,
      period: const Duration(milliseconds: 1000),
    );
  }

  @override
  void dispose() {
    _shimmerController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return widget.child ?? const SizedBox();
  }

  /// Calculates and returns the offset of the given descendant.
  Offset getDescendantOffset({
    required RenderBox descendant,
    Offset offset = .zero,
  }) {
    final shimmerBox = context.findRenderObject() as RenderBox?;
    return descendant.localToGlobal(offset, ancestor: shimmerBox);
  }
}

class _SlidingGradientTransform extends GradientTransform {
  const _SlidingGradientTransform({required this.slidePercent});

  final double slidePercent;

  @override
  Matrix4? transform(Rect bounds, {TextDirection? textDirection}) {
    return Matrix4.translationValues(bounds.width * slidePercent, 0, 0);
  }
}

/// The default shimmer gradient.
const shimmerGradient = LinearGradient(
  colors: [Color(0xFFEBEBF4), Color(0xFFF4F4F4), Color(0xFFEBEBF4)],
  stops: [0.1, 0.3, 0.4],
  begin: Alignment(-1, -0.3),
  end: Alignment(1, 0.3),
);
