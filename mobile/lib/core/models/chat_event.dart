import 'package:cashctrl/core/models/chat_message.dart';

/// A class that describes the progress of the assistant's reply to the user's
/// message.
sealed class ChatEvent {
  /// Creates a [ChatEvent].
  const ChatEvent();
}

/// An event that is received once the server has stored the user's message.
class ChatMessageStored extends ChatEvent {
  /// Creates a [ChatMessageStored].
  const ChatMessageStored(this.message);

  /// The user's stored message.
  final ChatMessage message;
}

/// An event that carries the next chunk of the assistant's reply.
class ChatReplyDelta extends ChatEvent {
  /// Creates a [ChatReplyDelta].
  const ChatReplyDelta(this.text);

  /// The chunk of text that follows the previous ones.
  final String text;
}

/// An event that carries the assistant's full reply, after which no other
/// event is received.
class ChatReplyDone extends ChatEvent {
  /// Creates a [ChatReplyDone].
  const ChatReplyDone(this.reply);

  /// The assistant's stored reply.
  final ChatMessage reply;
}
