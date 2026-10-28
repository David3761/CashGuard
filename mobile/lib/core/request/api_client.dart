import 'dart:async';

import 'package:cashctrl/core/request/api_service.dart';
import 'package:cashctrl/core/request/auth_token_controller.dart';
import 'package:chopper/chopper.dart';
import 'package:collection/collection.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

// Necessary for code-generation to work
// Run: dart run build_runner watch
part 'api_client.g.dart';

/// The provider that returns an instance of `ApiService`.
@riverpod
ApiService apiService(Ref ref) => ApiClient._(ref)._apiService;

/// The main class that handles all requests. The [ApiClient] adds the
/// authorization token in every request. If a request fails due to bad
/// authorization, the authorization token is refreshed and the request is
/// retried.
class ApiClient {
  ApiClient._(this.ref);

  /// A [Ref] object used to access any providers (such as
  /// `AuthTokenController`).
  final Ref ref;

  late final _chopper = ChopperClient(
    // TODO(everyone): replace with the CashCtrl API url.
    baseUrl: .parse('https://api.cashctrl.invalid'),
    services: [ApiService.create()],
    converter: const JsonConverter(),
    interceptors: [
      const HeadersInterceptor({'Content-Type': 'application/json'}),
      _AuthInterceptor(ref),
    ],
    // authenticator: _AuthAuthenticator(),
  );

  late final _apiService = _chopper.getService<ApiService>();
}

/// An interceptor class that adds the authorization token to the headers list
/// of every request.
///
/// If the status code of the request is 401 or 403, the authorization token is
/// renewed by calling [AuthTokenController.getToken] and the request is done
/// again.
class _AuthInterceptor implements Interceptor {
  _AuthInterceptor(this.ref);

  final Ref ref;

  final _unrestrictedRequests = const [
    ('/login', 'POST'),
    ('/refresh_auth_token', 'POST'),
  ];

  @override
  Future<Response<BodyType>> intercept<BodyType>(Chain<BodyType> chain) async {
    final request = chain.request;

    String? authToken;
    final isRestricted =
        _unrestrictedRequests.firstWhereOrNull(
          (endpoint) =>
              request.url.path == endpoint.$1 &&
              endpoint.$2.toLowerCase() == request.method.toLowerCase(),
        ) ==
        null;

    Response<BodyType> response;
    if (isRestricted) {
      authToken = await ref.read(authTokenControllerProvider).getToken();
      if (authToken != null) {
        final newRequest = applyHeader(
          chain.request,
          'Authorization',
          'Bearer $authToken',
        );
        response = await chain.proceed(newRequest);
      } else {
        response = await chain.proceed(chain.request);
      }
    } else {
      // The request is unrestricted. We return the result immediately.
      return chain.proceed(chain.request);
    }

    // TODO(everyone): Dummy return. Remove this after you fork the repository.
    return response;

    // TODO(everyone): after you fork the repository, the code below needs to be
    // uncommented so that the refresh token mechanism works.
    // The request failed due to authentication errors.
    /*if (response.statusCode == 401 || response.statusCode == 403) {
      // If no auth token was passed, then we return the result as is.
      if (authToken == null) {
        return response;
      }

      // Retrieve the updated auth token from AuthTokenController. The token
      // could have been refreshed by now (by another request), or not.
      // In any case, the AuthTokenController has the authority to decide that.
      final newToken = await ref.read(authTokenControllerProvider).getToken(
            usedToken: authToken,
          );
      if (newToken != null) {
        final newRequest = applyHeader(
          chain.request,
          'Authorization',
          'Bearer $newToken',
        );
        response = await chain.proceed(newRequest);
      } else {
        // logout the user because the token could not be refreshed.
        unawaited(logout(ref, internetRequired: true));
      }
    }

    return response;*/
  }
}
