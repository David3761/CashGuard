import 'dart:async';
import 'dart:convert';

import 'package:cashctrl/core/request/api_config.dart';
import 'package:cashctrl/core/utils/logging.dart';
import 'package:cashctrl/exceptions.dart';
import 'package:http/http.dart' as http;
import 'package:riverpod_annotation/riverpod_annotation.dart';

// Necessary for code-generation to work
// Run: dart run build_runner watch
part 'event_stream_client.g.dart';

/// The provider that returns an instance of [EventStreamClient]. It's kept
/// alive so that its HTTP client isn't closed while a stream is being read.
@Riverpod(keepAlive: true)
EventStreamClient eventStreamClient(Ref ref) {
  final client = http.Client();
  ref.onDispose(client.close);
  return EventStreamClient(client);
}

/// An event received in a stream of Server-Sent Events.
typedef ServerSentEvent = ({String event, String data});

/// The class that makes the requests whose responses are streams of
/// Server-Sent Events, which the `ApiService` can't read.
class EventStreamClient {
  /// Creates an [EventStreamClient] that sends its requests with [_client].
  const EventStreamClient(this._client);

  /// The client the requests are sent with.
  final http.Client _client;

  /// Sends a `POST` request with the given [body] to [path] and returns the
  /// events the server streams back.
  ///
  /// Throws a [ServerError] when the server responds with an error status.
  Stream<ServerSentEvent> post(String path, Map<String, dynamic> body) async* {
    final request = http.Request('POST', .parse('$apiBaseUrl$path'))
      ..headers.addAll({
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',
      })
      ..body = jsonEncode(body);
    devPrint('--> POST ${request.url}');
    final response = await _client.send(request);
    devPrint('<-- ${response.statusCode} POST ${request.url}');
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw UIException.serverError(
        _errorMessage(await response.stream.bytesToString()),
      );
    }

    // The fields of an event arrive on separate lines and a blank line ends
    // the event. Lines starting with ":" are comments, such as keep-alives.
    var event = 'message';
    final data = <String>[];
    final lines = response.stream
        .transform(utf8.decoder)
        .transform(const LineSplitter());
    await for (final line in lines) {
      if (line.isEmpty) {
        if (data.isNotEmpty) {
          devPrint('<-- event: $event ${data.join('\n')}');
          yield (event: event, data: data.join('\n'));
        }
        event = 'message';
        data.clear();
      } else if (line.startsWith('event:')) {
        event = _fieldValue(line, 'event:');
      } else if (line.startsWith('data:')) {
        data.add(_fieldValue(line, 'data:'));
      }
    }
  }

  /// Returns the `message` of the given error response [body], or `null` when
  /// the body has no message.
  String? _errorMessage(String body) {
    try {
      final json = jsonDecode(body);
      return json is Map<String, dynamic> ? json['message'] as String? : null;
    } on FormatException {
      return null;
    }
  }

  /// Returns the value that follows the [field] name on the given [line],
  /// without the single space that may separate them.
  String _fieldValue(String line, String field) {
    final value = line.substring(field.length);
    return value.startsWith(' ') ? value.substring(1) : value;
  }
}
