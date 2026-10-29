import 'package:cashctrl/core/request/api_config.dart';
import 'package:cashctrl/core/request/event_stream_client.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('appKeyHeaders sends the key in X-App-Key', () {
    expect(appKeyHeaders(key: 'key-123'), {'X-App-Key': 'key-123'});
  });

  test('appKeyHeaders follows --dart-define=APP_API_KEY by default', () {
    // `flutter test` runs without the define, so no header is sent.
    expect(
      appKeyHeaders(),
      appApiKey.isEmpty ? isEmpty : {'X-App-Key': appApiKey},
    );
  });

  test('EventStreamClient sends the app key headers with the chat', () async {
    final sent = <http.Request>[];
    final client = EventStreamClient(
      MockClient((request) {
        sent.add(request);
        return Future.value(http.Response('event: done\ndata: {}\n\n', 200));
      }),
    );

    final stream = client.post('/assistant/messages', {'text': 'hi'});
    final events = await stream.toList();

    expect(events, [(event: 'done', data: '{}')]);
    expect(sent, hasLength(1));
    expect(sent.single.headers, containsPair('Accept', 'text/event-stream'));
    expect(sent.single.headers['X-App-Key'], appKeyHeaders()['X-App-Key']);
  });
}
