import 'dart:async';

import 'package:cashctrl/core/request/api_config.dart';
import 'package:cashctrl/core/request/api_service.dart';
import 'package:cashctrl/core/utils/logging.dart';
import 'package:chopper/chopper.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

// Necessary for code-generation to work
// Run: dart run build_runner watch
part 'api_client.g.dart';

/// The provider that returns an instance of `ApiService`.
@riverpod
ApiService apiService(Ref ref) => ApiClient._()._apiService;

/// The main class that handles all requests.
class ApiClient {
  ApiClient._();

  late final _chopper = ChopperClient(
    baseUrl: .parse(apiBaseUrl),
    services: [ApiService.create()],
    converter: const JsonConverter(),
    // TODO(everyone): add an interceptor that sends the auth token once the
    // backend has authentication. AuthTokenController already stores and
    // refreshes the tokens.
    interceptors: [
      // The app key (`--dart-define=APP_API_KEY`) goes on every request.
      HeadersInterceptor({
        'Content-Type': 'application/json',
        ...appKeyHeaders(),
      }),
      const _LoggingInterceptor(),
    ],
  );

  late final _apiService = _chopper.getService<ApiService>();
}

/// An interceptor class that prints every request and its response in debug
/// mode.
class _LoggingInterceptor implements Interceptor {
  /// Creates a [_LoggingInterceptor].
  const _LoggingInterceptor();

  @override
  Future<Response<BodyType>> intercept<BodyType>(Chain<BodyType> chain) async {
    final request = chain.request;
    devPrint('--> ${request.method} ${request.url}');
    final response = await chain.proceed(request);
    devPrint(
      '<-- ${response.statusCode} ${request.method} ${request.url}\n'
      '${response.bodyString}',
    );
    return response;
  }
}
