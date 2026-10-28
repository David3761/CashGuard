import 'package:cashctrl/l10n/app_localizations.dart';
import 'package:flutter/material.dart';
import 'package:fluttertoast/fluttertoast.dart';
import 'package:go_router/go_router.dart';

/// Creates and displays an alert with the following configuration:
/// - title: [title]
/// - message: [message]
/// - neutral button: 'Ok', upon clicking it calls [okClickListener] if
/// not null, otherwise it just dismisses the alert.
Future<T?> showAlert<T>({
  required BuildContext context,
  required String title,
  required String message,
  Function(BuildContext context)? okClickListener,
}) {
  return showDialog(
    context: context,
    builder: (context) => AlertDialog(
      title: Text(title),
      content: Text(message),
      actions: [
        TextButton(
          onPressed: () {
            if (okClickListener != null) {
              okClickListener(context);
            } else {
              context.pop();
            }
          },
          child: Text(
            AppLocalizations.of(context).ok,
            style: const TextStyle(color: Colors.black),
          ),
        ),
      ],
    ),
  );
}

/// Utility class for displaying [AlertDialog]s.
/// Creates and displays an alert with the following configuration:
/// - title: [title]
/// - message: [message]
/// - positive button: 'Yes', upon clicking it calls [yesClickListener] if
// not null, otherwise it just dismisses the alert.
/// - negative button: 'No', upon clicking it calls [noClickListener] if
// not null, otherwise it just dismisses the alert.
Future<T?> showYesNoAlert<T>({
  required BuildContext context,
  required String title,
  String? message,
  Function(BuildContext context)? yesClickListener,
  Function(BuildContext context)? noClickListener,
}) {
  return showDialog(
    context: context,
    builder: (context) => AlertDialog(
      title: Text(title),
      content: message != null ? Text(message) : null,
      actions: [
        TextButton(
          onPressed: () {
            if (noClickListener != null) {
              noClickListener(context);
            } else {
              context.pop();
            }
          },
          child: Text(
            AppLocalizations.of(context).no,
            style: const TextStyle(color: Colors.black),
          ),
        ),
        TextButton(
          onPressed: () {
            if (yesClickListener != null) {
              yesClickListener(context);
            } else {
              context.pop();
            }
          },
          child: Text(
            AppLocalizations.of(context).yes,
            style: const TextStyle(color: Colors.black),
          ),
        ),
      ],
    ),
  );
}

/// Creates and displays a toast with the given [message].
/// If [toastLength] is null, then it defaults to [Toast.LENGTH_SHORT].
/// If [gravity] is null, then it defaults to [ToastGravity.BOTTOM].
Future<bool?> showToast({
  required String message,
  Toast? toastLength,
  ToastGravity? gravity,
}) {
  return Fluttertoast.showToast(
    msg: message,
    toastLength: toastLength,
    gravity: gravity,
  );
}

/// Utility class for displaying an alert with title, message and multiple
/// items that can be clicked. This is similar to a 'Single Choice Items'
/// alert. The message is included in a [SingleChildScrollView] in order to
/// have a long message without sacrificing from the space of the alert items.
///
/// Example:
/// ```dart
/// AlertDialogWithItems.create(
///    context: context,
///    title: 'An alert dialog with a lot of items',
///    message: 'Lorem ipsum dolor sit amet, consectetur adipiscing elit.'
///    Duis malesuada, tellus nec posuere rhoncus, dolor neque iaculis diam, at
///    sagittis mauris nisi in urna. Nullam arcu ipsum, feugiat nec mi id,
///    cursus sagittis ipsum. Morbi consectetur sem at libero egestas interdum.
///    Suspendisse finibus vestibulum felis, eleifend vehicula tellus fermentum
///    vitae. Fusce commodo, odio dapibus varius dapibus, lorem augue sodales
///    leo, at mattis lacus felis sed nunc. Vivamus lacinia sagittis odio,
///    lacinia facilisis felis maximus a. Duis tempus ipsum ac sapien pulvinar
///    pretium. Mauris vulputate, risus interdum auctor accumsan, quam arcu
///    auctor leo, vitae porttitor nisl quam non magna. Ut quis tortor
///    malesuada, suscipit sem sed, tristique erat. Vivamus sed fringilla
///    tortor.  In posuere, diam nec posuere euismod, ligula neque euismod mi,
///    ac congue metus tortor eget felis. Sed sit amet mollis felis. Praesent ex
///    nisl, tincidunt sed luctus luctus, tristique sit amet sapien. Donec sit
///    amet lorem est. Nullam in efficitur sapien. In sollicitudin, eros ac
///    cursus tincidunt, nulla ex aliquam nibh, eget posuere mauris nisl eget
///    lacus. Fusce auctor pharetra dolor a posuere. ',
///    items: ['Lorem ipsum', 'Dolor sit amet', 'Vivamus sed fringilla tortor.',
///    'Mauris vulputate', 'Duis tempus'],
///    clickListener: (position) {
///      devPrint('clicked $position');
///    },
/// );
/// ```
class AlertDialogWithItems {
  /// The private constructor prevents the cases where this class could be
  /// instantiated.
  AlertDialogWithItems._();

  /// Creates and displays an alert with the following configuration:
  /// - title: [title]
  /// - message: [message]
  /// - items: [items], the available options that can be clicked
  /// - clickListener: the [clickListener] that will be called when the any of
  /// the options is pressed
  static Future<T?> create<T>({
    required BuildContext context,
    required String title,
    required String message,
    required List<String> items,
    required ValueChanged<int> clickListener,
  }) {
    final scrollController = ScrollController();
    return showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(title),
        content: Padding(
          padding: const .all(3),
          child: SizedBox(
            width: double.maxFinite,
            child: Column(
              mainAxisSize: .min,
              children: [
                Flexible(
                  child: Scrollbar(
                    thumbVisibility: true,
                    controller: scrollController,
                    child: SingleChildScrollView(
                      controller: scrollController,
                      child: Text(message),
                    ),
                  ),
                ),
                Flexible(
                  child: SingleChildScrollView(
                    child: Column(
                      children: items
                          .asMap()
                          .entries
                          .map(
                            (entry) => ListTile(
                              contentPadding: .zero,
                              onTap: () {
                                context.pop();
                                scrollController.dispose();
                                clickListener(entry.key);
                              },
                              title: Text(
                                entry.value,
                                style: const TextStyle(color: Colors.black),
                              ),
                            ),
                          )
                          .toList(),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
