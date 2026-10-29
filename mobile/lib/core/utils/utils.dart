import 'dart:io';
import 'dart:math';

import 'package:http/http.dart' as http;
import 'package:intl/intl.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

/// An extension class for replicating the `let` function from *Kotlin*.
extension ObjectExt<T> on T {
  /// This method can be used to safely execute a block of code that depends on
  /// a nullable value, without checking if the value is null explicitly, but
  /// by using the type test operator (*?.*).
  R let<R>(R Function(T that) op) => op(this);
}

/// An extension class for strings.
extension StringExtension on String {
  /// Returns a capitalized version of the string (only the first letter is in
  /// caps, while the rest are lower case)
  ///
  /// e.g.: Empire State Building -> Empire state building
  String capitalize() {
    return '${this[0].toUpperCase()}${substring(1).toLowerCase()}';
  }

  /// Returns a substring after the last occurrence of [delimiter]. If the
  /// string does not contain the delimiter, returns [missingDelimiterValue]
  /// which defaults to the original string.
  String substringAfterLast(String delimiter, {String? missingDelimiterValue}) {
    final index = lastIndexOf(delimiter);
    if (index != -1 && index < length - 1) {
      return substring(index + 1);
    } else if (missingDelimiterValue != null) {
      return missingDelimiterValue;
    } else {
      return this;
    }
  }

  /// Tries to convert the String to a double. On failure, it returns null.
  double? toDoubleOrNull() => double.tryParse(this);
}

/// An extension class for integers.
extension IntExtension on int {
  /// Returns a "minutes:seconds" representation of the int value.
  String minutesSeconds() {
    final minutes = '${this ~/ (60 * 1000) % 60}'.padLeft(2, '0');
    final seconds = '${this ~/ 1000 % 60}'.padLeft(2, '0');
    return '$minutes:$seconds';
  }

  /// Returns the int value's amount of bani as lei (e.g. `-8,38` or `1.250`),
  /// without the decimals when they're `0`.
  String formatBani({bool showPlusSign = false}) {
    final format = NumberFormat.decimalPatternDigits(
      locale: 'ro',
      decimalDigits: this % 100 == 0 ? 0 : 2,
    );
    final formatted = format.format(this / 100);
    return showPlusSign && this > 0 ? '+$formatted' : formatted;
  }
}

/// Returns the log10 of the given number.
double log10(num x) => log(x) / ln10;

/// Downloads the image found at the given [imgUrl] to the internal app's files
/// under the name [filename]. The method returns the full path, including
/// the filename.
///
/// If you want other ways of downloading images or files, have a look at these
/// packages: [image_downloader](https://pub.dev/packages/image_downloader) and
/// [flutter_downloader](https://pub.dev/packages/flutter_downloader)
Future<String> downloadImage(String imgUrl, String filename) async {
  final uri = Uri.parse(imgUrl);
  final response = await http.get(uri);
  final documentDirectory = await getApplicationDocumentsDirectory();
  final file = File(p.join(documentDirectory.path, filename));
  await file.writeAsBytes(response.bodyBytes);
  return file.path;
}

/// Tries to cast an object to the given type.
// ignore: avoid_annotating_with_dynamic
T? tryCast<T>(dynamic object) => object is T ? object : null;
