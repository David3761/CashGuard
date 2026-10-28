import 'package:flutter/material.dart';

/// Displays a banner at the top left corner that opens the Chucker Request
/// Inspector when tapped.
class ChuckerOverlay extends StatelessWidget {
  /// Creates a [ChuckerOverlay].
  const ChuckerOverlay({super.key, required this.child});

  /// The child widget.
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Stack(
      textDirection: .ltr,
      children: [
        child,
        Banner(
          location: .topStart,
          textDirection: .ltr,
          layoutDirection: .ltr,
          message: 'Chucker',
          child: GestureDetector(
            onTap: () {},
            child: Container(color: Colors.transparent, height: 50, width: 50),
          ),
        ),
      ],
    );
  }
}
