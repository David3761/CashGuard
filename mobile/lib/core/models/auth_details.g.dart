// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'auth_details.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

AuthDetails _$AuthDetailsFromJson(Map<String, dynamic> json) => AuthDetails(
  authToken: json['auth_token'] as String,
  refreshToken: json['refresh_token'] as String,
);

Map<String, dynamic> _$AuthDetailsToJson(AuthDetails instance) =>
    <String, dynamic>{
      'auth_token': instance.authToken,
      'refresh_token': instance.refreshToken,
    };
