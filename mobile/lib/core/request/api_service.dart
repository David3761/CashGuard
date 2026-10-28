import 'package:chopper/chopper.dart';
import 'package:http/http.dart' hide Request, Response;

// Necessary for code-generation to work
// Run: dart run build_runner watch
part 'api_service.chopper.dart';

/// The main interface for all requests made using `ApiClient`.
@ChopperApi()
abstract class ApiService extends ChopperService {
  /// A helper method that instantiates the service.
  /// You can omit this method and use the generated class directly instead.
  static ApiService create([ChopperClient? client]) => _$ApiService(client);

  /// Makes a `PUT /auth_method` request.
  @POST(path: '/auth_method')
  // @formUrlEncoded
  Future<Map<String, dynamic>> changePassword(@Body() Map<String, String> body);

  /// Makes a `POST /password_token` request.
  @POST(path: '/password_token')
  // @formUrlEncoded
  Future<Map<String, dynamic>> forgotPassword(@Body() Map<String, String> body);

  /// Makes a `POST /login request`.
  @POST(path: '/login')
  // @formUrlEncoded
  Future<Map<String, dynamic>> login(@Body() Map<String, String> body);

  /// Makes a `POST /register` request.
  @POST(path: '/register')
  // @formUrlEncoded
  Future<Map<String, dynamic>> register(@Body() Map<String, String> body);

  /// Makes a `POST /refresh_auth_token`.
  @POST(path: '/refresh_auth_token')
  // @formUrlEncoded
  Future<Map<String, dynamic>> refreshAuthToken(
    @Body() Map<String, String> body,
  );

  /// Makes a `GET /user` request.
  @GET(path: '/user')
  Future<Map<String, dynamic>> getUser();

  /// Makes a `PUT /user` Multipart request.
  @PUT(path: '/user')
  @multipart
  Future<Map<String, dynamic>> editUser(
    @Body() Map<String, String> body,
    @PartFile('photo') MultipartFile? file,
  );

  /// Makes a `POST /device_token` request.
  @POST(path: '/device_token')
  // @formUrlEncoded
  Future<Map<String, dynamic>> postDeviceToken(
    @Body() Map<String, String> body,
  );

  /// Makes a `DELETE /device_token` request.
  @DELETE(path: '/device_token')
  // @formUrlEncoded
  Future<Map<String, dynamic>> deleteDeviceToken(
    @Body() Map<String, String> body,
  );

  /// Makes a `GET /user` request to retrieve the user's data.
  @GET(path: '/user')
  Future<Map<String, dynamic>> getData(@QueryMap() Map<String, String> params);

  /// Makes a `POST /view-data` request.
  @POST(path: '/view-data')
  Future<Map<String, dynamic>> viewData();

  /// Makes a `POST /delete-data` request.
  @POST(path: '/delete-data')
  Future<Map<String, dynamic>> deleteData();
}
