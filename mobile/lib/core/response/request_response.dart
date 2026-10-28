import 'package:json_annotation/json_annotation.dart';

// Necessary for code-generation to work
// Run: dart run build_runner watch
part 'request_response.g.dart';

/// The base model class that should be extended by every model class used for
/// requests.
@JsonSerializable()
final class RequestResponse {
  /// Creates a [RequestResponse].
  RequestResponse({this.status = '', this.message, this.error});

  /// Constructs an instance of this object from a key-value map of data.
  ///
  /// The map needs to have named string keys with values matching the names
  /// and types of all of the members on this class.
  factory RequestResponse.fromJson(Map<String, dynamic> json) =>
      _$RequestResponseFromJson(json);

  /// The request's status.
  final String status;

  /// The request's message.
  final String? message;

  /// The request's error.
  final String? error;
}
