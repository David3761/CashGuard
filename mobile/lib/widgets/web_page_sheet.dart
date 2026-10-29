import 'package:cashctrl/resources/text_styles.dart';
import 'package:cashctrl/widgets/widgets.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:webview_flutter/webview_flutter.dart';

/// The web page sheet for opening links in a web view. This should be used in
/// conjunction with [showSheet].
class WebPageSheet extends StatefulWidget {
  /// Creates a [WebPageSheet].
  const WebPageSheet({super.key, required this.title, required this.url});

  /// The route's name.
  static const route = 'web-page';

  /// The web page title that will be displayed at the top of the screen.
  final String title;

  /// The url that will be opened.
  final String url;

  @override
  State<WebPageSheet> createState() => _WebPageSheetState();
}

class _WebPageSheetState extends State<WebPageSheet> {
  late final WebViewController _controller;
  bool _isLoading = false;

  @override
  Future<void> initState() async {
    super.initState();

    _controller = WebViewController();
    await _controller.setJavaScriptMode(.unrestricted);
    await _controller.setBackgroundColor(const Color(0x00000000));
    await _controller.setNavigationDelegate(
      NavigationDelegate(
        onPageStarted: (url) {
          if (mounted) {
            setState(() {
              _isLoading = true;
            });
          }
        },
        onPageFinished: (url) {
          if (mounted) {
            setState(() {
              _isLoading = false;
            });
          }
        },
        onWebResourceError: (error) {},
        onNavigationRequest: (request) => .navigate,
      ),
    );
    await _controller.loadRequest(.parse(widget.url));
  }

  @override
  Widget build(BuildContext context) {
    return ScreenStack(
      leading: const SizedBox.shrink(),
      title: Text(
        widget.title,
        style: TextStyles.text20SB.copyWith(color: Colors.white),
      ),
      backgroundColor: Colors.white,
      actions: [
        IconButton(
          color: Colors.white,
          icon: const Icon(Icons.close, color: Colors.white),
          tooltip: MaterialLocalizations.of(context).closeButtonTooltip,
          onPressed: context.pop,
        ),
      ],
      children: [
        WebViewWidget(controller: _controller),
        if (_isLoading) ...[
          const Align(
            alignment: .topCenter,
            child: LinearProgressIndicator(color: Colors.black),
          ),
        ],
      ],
    );
  }
}
