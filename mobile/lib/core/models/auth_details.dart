import 'package:json_annotation/json_annotation.dart';

// Necessary for code-generation to work
// Run: dart run build_runner watch
part 'auth_details.g.dart';

/// A model class that stores the auth data of a user:
/// - auth token
/// - refresh token
///
/// Having these tokens in a separate model, decouples the auth and
/// refresh token process from the main `User` model and allows easier access
/// and updates to these tokens.
///
/// Furthermore, if the app is meant to be used solely online, then there's no
/// need to save any other information besides the 2 tokens.
@JsonSerializable()
class AuthDetails {
  /// Creates an [AuthDetails].
  AuthDetails({required this.authToken, required this.refreshToken});

  /// Constructs an instance of this object from a key-value map of data.
  ///
  /// The map needs to have named string keys with values matching the names
  /// and types of all of the members on this class.
  factory AuthDetails.fromJson(Map<String, dynamic> json) =>
      _$AuthDetailsFromJson(json);

  /// The auth token for authenticated users.
  @JsonKey(name: 'auth_token')
  String authToken = '';

  /// The refresh token for authenticated users.
  @JsonKey(name: 'refresh_token')
  String refreshToken = '';
}
