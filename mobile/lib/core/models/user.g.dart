// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'user.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

User _$UserFromJson(Map<String, dynamic> json) => User(
  id: (json['id'] as num?)?.toInt() ?? 0,
  email: json['mail'] as String? ?? '',
  authMethod:
      $enumDecodeNullable(_$AuthMethodEnumMap, json['auth_method']) ?? .email,
  name: json['full_name'] as String?,
  phone: json['phone'] as String?,
  photo: json['photo'] as String?,
);

Map<String, dynamic> _$UserToJson(User instance) => <String, dynamic>{
  'id': instance.id,
  'mail': instance.email,
  'auth_method': _$AuthMethodEnumMap[instance.authMethod]!,
  'full_name': instance.name,
  'phone': instance.phone,
  'photo': instance.photo,
};

const _$AuthMethodEnumMap = {AuthMethod.email: 'email'};
