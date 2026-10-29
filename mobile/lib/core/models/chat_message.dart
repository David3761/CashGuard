import 'package:cashctrl/core/models/chat_sender.dart';

/// A model class that stores the data of a message in the chat with the
/// assistant.
class ChatMessage {
  /// Creates a [ChatMessage].
  const ChatMessage({
    required this.id,
    required this.text,
    required this.sender,
    required this.createdAt,
  });

  /// Creates a [ChatMessage] from the given [json].
  factory ChatMessage.fromJson(Map<String, dynamic> json) {
    return ChatMessage(
      id: json['id'] as int,
      text: json['text'] as String,
      sender: .fromJson(json['sender'] as String),
      createdAt: DateTime.parse(json['created_at'] as String).toLocal(),
    );
  }

  /// The message's identifier, or `0` while the message isn't stored by the
  /// server yet.
  final int id;

  /// The message's text.
  final String text;

  /// Who sent the message.
  final ChatSender sender;

  /// The moment the message was sent.
  final DateTime createdAt;
}
