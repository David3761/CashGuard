import 'package:flutter/material.dart';

/// A widget that reports its size after each frame.
///
/// This is intended to be used whenever a widget's size needs to be determined
/// a priori so that a parent that can expand indefinitely can wrap its size
/// based on the children size, instead of occupying the remaining screen space
/// or throwing size overflow errors.
///
/// Source: https://stackoverflow.com/a/65332810
class SizeReportingWidget extends StatefulWidget {
  /// Creates a [SizeReportingWidget].
  const SizeReportingWidget({
    super.key,
    required this.child,
    required this.onSizeChange,
  });

  /// The child that will be measured.
  final Widget child;

  /// Called when the [child]'s size changes.
  final ValueChanged<Size> onSizeChange;

  @override
  State<SizeReportingWidget> createState() => _SizeReportingWidgetState();
}

class _SizeReportingWidgetState extends State<SizeReportingWidget> {
  Size? _oldSize;

  @override
  Widget build(BuildContext context) {
    WidgetsBinding.instance.addPostFrameCallback((_) => _notifySize());
    return widget.child;
  }

  /// Determines the current widget size and reports it through the callback
  /// provided.
  void _notifySize() {
    if (!mounted) {
      return;
    }
    final size = context.size;
    if (_oldSize != size && size != null) {
      _oldSize = size;
      widget.onSizeChange(size);
    }
  }
}
