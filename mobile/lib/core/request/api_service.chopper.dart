// GENERATED CODE - DO NOT MODIFY BY HAND
// dart format width=80

part of 'api_service.dart';

// **************************************************************************
// ChopperGenerator
// **************************************************************************

// coverage:ignore-file
// ignore_for_file: type=lint
final class _$ApiService extends ApiService {
  _$ApiService([ChopperClient? client]) {
    if (client == null) return;
    this.client = client;
  }

  @override
  final Type definitionType = ApiService;

  @override
  Future<Map<String, dynamic>> changePassword(Map<String, String> body) async {
    final Uri $url = Uri.parse('/auth_method');
    final $body = body;
    final Request $request = Request('POST', $url, client.baseUrl, body: $body);
    final Response<Map<String, dynamic>> $response = await client
        .send<Map<String, dynamic>, Map<String, dynamic>>($request);
    return $response.bodyOrThrow;
  }

  @override
  Future<Map<String, dynamic>> forgotPassword(Map<String, String> body) async {
    final Uri $url = Uri.parse('/password_token');
    final $body = body;
    final Request $request = Request('POST', $url, client.baseUrl, body: $body);
    final Response<Map<String, dynamic>> $response = await client
        .send<Map<String, dynamic>, Map<String, dynamic>>($request);
    return $response.bodyOrThrow;
  }

  @override
  Future<Map<String, dynamic>> login(Map<String, String> body) async {
    final Uri $url = Uri.parse('/login');
    final $body = body;
    final Request $request = Request('POST', $url, client.baseUrl, body: $body);
    final Response<Map<String, dynamic>> $response = await client
        .send<Map<String, dynamic>, Map<String, dynamic>>($request);
    return $response.bodyOrThrow;
  }

  @override
  Future<Map<String, dynamic>> register(Map<String, String> body) async {
    final Uri $url = Uri.parse('/register');
    final $body = body;
    final Request $request = Request('POST', $url, client.baseUrl, body: $body);
    final Response<Map<String, dynamic>> $response = await client
        .send<Map<String, dynamic>, Map<String, dynamic>>($request);
    return $response.bodyOrThrow;
  }

  @override
  Future<Map<String, dynamic>> refreshAuthToken(
    Map<String, String> body,
  ) async {
    final Uri $url = Uri.parse('/refresh_auth_token');
    final $body = body;
    final Request $request = Request('POST', $url, client.baseUrl, body: $body);
    final Response<Map<String, dynamic>> $response = await client
        .send<Map<String, dynamic>, Map<String, dynamic>>($request);
    return $response.bodyOrThrow;
  }

  @override
  Future<Map<String, dynamic>> getUser() async {
    final Uri $url = Uri.parse('/user');
    final Request $request = Request('GET', $url, client.baseUrl);
    final Response<Map<String, dynamic>> $response = await client
        .send<Map<String, dynamic>, Map<String, dynamic>>($request);
    return $response.bodyOrThrow;
  }

  @override
  Future<Map<String, dynamic>> editUser(
    Map<String, String> body,
    MultipartFile? file,
  ) async {
    final Uri $url = Uri.parse('/user');
    final $body = body;
    final List<PartValue> $parts = <PartValue>[
      PartValueFile<MultipartFile?>('photo', file),
    ];
    final Request $request = Request(
      'PUT',
      $url,
      client.baseUrl,
      body: $body,
      parts: $parts,
      multipart: true,
    );
    final Response<Map<String, dynamic>> $response = await client
        .send<Map<String, dynamic>, Map<String, dynamic>>($request);
    return $response.bodyOrThrow;
  }

  @override
  Future<Map<String, dynamic>> registerDevice(Map<String, String> body) async {
    final Uri $url = Uri.parse('/devices');
    final $body = body;
    final Request $request = Request('POST', $url, client.baseUrl, body: $body);
    final Response<Map<String, dynamic>> $response = await client
        .send<Map<String, dynamic>, Map<String, dynamic>>($request);
    return $response.bodyOrThrow;
  }

  @override
  Future<Map<String, dynamic>> unregisterDevice(String fcmToken) async {
    final Uri $url = Uri.parse('/devices/${fcmToken}');
    final Request $request = Request('DELETE', $url, client.baseUrl);
    final Response<Map<String, dynamic>> $response = await client
        .send<Map<String, dynamic>, Map<String, dynamic>>($request);
    return $response.bodyOrThrow;
  }

  @override
  Future<Map<String, dynamic>> getBalance() async {
    final Uri $url = Uri.parse('/balance');
    final Request $request = Request('GET', $url, client.baseUrl);
    final Response<Map<String, dynamic>> $response = await client
        .send<Map<String, dynamic>, Map<String, dynamic>>($request);
    return $response.bodyOrThrow;
  }

  @override
  Future<Map<String, dynamic>> getTransactions() async {
    final Uri $url = Uri.parse('/transactions');
    final Request $request = Request('GET', $url, client.baseUrl);
    final Response<Map<String, dynamic>> $response = await client
        .send<Map<String, dynamic>, Map<String, dynamic>>($request);
    return $response.bodyOrThrow;
  }

  @override
  Future<Map<String, dynamic>> getChatMessages() async {
    final Uri $url = Uri.parse('/assistant/messages');
    final Request $request = Request('GET', $url, client.baseUrl);
    final Response<Map<String, dynamic>> $response = await client
        .send<Map<String, dynamic>, Map<String, dynamic>>($request);
    return $response.bodyOrThrow;
  }

  @override
  Future<Map<String, dynamic>> getData(Map<String, String> params) async {
    final Uri $url = Uri.parse('/user');
    final Map<String, dynamic> $params = params;
    final Request $request = Request(
      'GET',
      $url,
      client.baseUrl,
      parameters: $params,
    );
    final Response<Map<String, dynamic>> $response = await client
        .send<Map<String, dynamic>, Map<String, dynamic>>($request);
    return $response.bodyOrThrow;
  }

  @override
  Future<Map<String, dynamic>> viewData() async {
    final Uri $url = Uri.parse('/view-data');
    final Request $request = Request('POST', $url, client.baseUrl);
    final Response<Map<String, dynamic>> $response = await client
        .send<Map<String, dynamic>, Map<String, dynamic>>($request);
    return $response.bodyOrThrow;
  }

  @override
  Future<Map<String, dynamic>> deleteData() async {
    final Uri $url = Uri.parse('/delete-data');
    final Request $request = Request('POST', $url, client.baseUrl);
    final Response<Map<String, dynamic>> $response = await client
        .send<Map<String, dynamic>, Map<String, dynamic>>($request);
    return $response.bodyOrThrow;
  }
}
