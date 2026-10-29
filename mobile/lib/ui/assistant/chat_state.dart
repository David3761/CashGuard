import 'package:cashctrl/core/models/chat_message.dart';

/// A class that stores the chat with the assistant.
class ChatState {
  /// Creates a [ChatState].
  const ChatState({required this.messages, this.isReplying = false});

  /// The chat's messages, the oldest first.
  final List<ChatMessage> messages;

  /// Whether the assistant is replying to the user's last message.
  final bool isReplying;
}
