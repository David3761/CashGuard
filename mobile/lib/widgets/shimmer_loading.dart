import 'package:cashctrl/widgets/shimmer.dart';
import 'package:flutter/material.dart';

/// A widget that syncs all the children shimmers widgets in order to provide
/// users with a continuous shimmer animation across the screen.
class ShimmerLoading extends StatefulWidget {
  /// Creates a [ShimmerLoading].
  const ShimmerLoading({
    super.key,
    required this.isLoading,
    required this.child,
  });

  /// Whether the shimmer animation should be displayed or not.
  final bool isLoading;

  /// The child that will be displayed when the shimmer animation is hidden.
  final Widget child;

  @override
  State<ShimmerLoading> createState() => _ShimmerLoadingState();
}

class _ShimmerLoadingState extends State<ShimmerLoading> {
  Listenable? _shimmerChanges;

  @override
  void dispose() {
    _shimmerChanges?.removeListener(_onShimmerChange);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.isLoading) {
      return widget.child;
    }

    // Collect ancestor shimmer information.
    final shimmer = Shimmer.of(context)!;
    if (!shimmer.isSized) {
      // The ancestor Shimmer widget isn't laid
      // out yet. Return an empty box.
      return const SizedBox();
    }
    final shimmerSize = shimmer.size;
    final gradient = shimmer.gradient;
    var offsetWithinShimmer = Offset.zero;
    if (context.findRenderObject() != null) {
      final box = context.findRenderObject()! as RenderBox;
      offsetWithinShimmer = shimmer.getDescendantOffset(descendant: box);
    }

    return ShaderMask(
      blendMode: .srcATop,
      shaderCallback: (bounds) {
        return gradient.createShader(
          .fromLTWH(
            -offsetWithinShimmer.dx,
            -offsetWithinShimmer.dy,
            shimmerSize.width,
            shimmerSize.height,
          ),
        );
      },
      child: Stack(
        children: [
          widget.child,
          Positioned.fill(child: Container(color: Colors.white)),
        ],
      ),
    );
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_shimmerChanges != null) {
      _shimmerChanges!.removeListener(_onShimmerChange);
    }
    _shimmerChanges = Shimmer.of(context)?.shimmerChanges;
    if (_shimmerChanges != null) {
      _shimmerChanges!.addListener(_onShimmerChange);
    }
  }

  void _onShimmerChange() {
    if (widget.isLoading) {
      setState(() {
        // update the shimmer painting.
      });
    }
  }
}
