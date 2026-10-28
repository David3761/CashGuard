import 'dart:async';
import 'dart:io';

import 'package:url_launcher/url_launcher.dart';

// For sharing simple text, please see: [share_plus](https://pub.dev/packages/share_plus)

/// Shows a list of all the available apps that can make phone calls. If there
/// is only one, it will open that one automatically. If there are no apps that
/// can make phone calls, then `false` will be returned.
///
/// If successful the method returns `true`.
Future<bool> openPhone(String phone) async {
  final uri = Uri.parse('tel:$phone');
  if (await canLaunchUrl(uri)) {
    // await launchUrl(uri);
    return launchUrl(uri);
  } else {
    return false;
  }
}

/// Checks whether the given [url] can be opened.
Future<bool> canOpenUrl(String url) async {
  final uri = Uri.tryParse(url);
  if (uri != null && await canLaunchUrl(uri)) {
    return true;
  } else {
    return false;
  }
}

/// Shows a list of all the available apps that can open the given [url]. If
/// there is only one, it will open that one automatically. If there are no
/// apps available to open the given [url], then `false` will be returned.
///
/// If successful the method returns `true`.
Future<bool> openUrl(String url) async {
  final canLaunch = await canOpenUrl(url);
  if (canLaunch) {
    final uri = Uri.parse(url);
    return launchUrl(uri, mode: .externalApplication);
  } else {
    return false;
  }
}

/// Shows a list of all the available apps that can send emails. If there is
/// only one, it will open that one automatically. If there are no apps
/// available to send emails, then `false` will be returned.
///
/// If successful the method returns `true`.
///
/// If you want to open a specific mail app on iOS, please see:
/// [open_mail_app](https://pub.dev/packages/open_mail_app)
Future<bool> openMail(
  List<String> addresses, {
  String subject = '',
  String text = '',
}) async {
  final addressList = addresses.join(',');
  final uri = Uri.parse('mailto:$addressList?subject=$subject&body=$text');
  if (await canLaunchUrl(uri)) {
    return launchUrl(uri);
  } else {
    return false;
  }
}

/// On Android, it opens the Play Store app if it's available, otherwise it
/// opens the play store app page in the browser. If unsuccessful, it returns
/// `false`.
///
/// On iOS, it opens the App Store app if it's available, otherwise it returns
/// `false`.
///
/// If successful the method returns `true`.
Future<bool> openStore() async {
  if (Platform.isAndroid || Platform.isIOS) {
    final appId = Platform.isAndroid ? 'co.justnow.justnow' : '1165305539';
    var uri = Uri.parse(
      Platform.isAndroid
          ? 'market://details?id=$appId'
          : 'https://apps.apple.com/app/id$appId',
    );
    if (await canLaunchUrl(uri)) {
      return launchUrl(uri, mode: .externalApplication);
    } else if (Platform.isAndroid) {
      uri = Uri.parse('https://play.google.com/store/apps/details?id=$appId');
      if (await canLaunchUrl(uri)) {
        return launchUrl(uri, mode: .externalApplication);
      }
    }
  }
  return false;
}
