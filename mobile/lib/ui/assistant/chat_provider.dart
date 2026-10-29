import 'package:cashctrl/core/models/chat_event.dart';
import 'package:cashctrl/core/models/chat_message.dart';
import 'package:cashctrl/core/repositories/assistant_repository.dart';
import 'package:cashctrl/exceptions.dart';
import 'package:cashctrl/ui/assistant/chat_state.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

// Necessary for code-generation to work
// Run: dart run build_runner watch
part 'chat_provider.g.dart';

/// The provider that stores the chat with the assistant.
@riverpod
class Chat extends _$Chat {
  @override
  Future<ChatState> build() async {
    final messages = await ref.watch(assistantRepositoryProvider).getMessages();
    return ChatState(messages: messages);
  }

  /// Adds the user's [message] to the chat, followed by the assistant's reply
  /// as it streams in.
  ///
  /// When the reply fails, the state becomes an error that still holds the
  /// chat's messages.
  Future<void> sendMessage(String message) async {
    final chat = state.value ?? const ChatState(messages: []);
    if (chat.isReplying) {
      return;
    }
    // Displayed until the server returns the stored message.
    var userMessage = ChatMessage(
      id: 0,
      text: message,
      sender: .user,
      createdAt: DateTime.now(),
    );
    ChatMessage? reply;
    state = AsyncData(
      ChatState(messages: [...chat.messages, userMessage], isReplying: true),
    );

    try {
      var isDone = false;
      final events = ref.read(assistantRepositoryProvider).sendMessage(message);
      await for (final event in events) {
        if (!ref.mounted) {
          return;
        }
        switch (event) {
          case ChatMessageStored(message: final storedMessage):
            userMessage = storedMessage;
          case ChatReplyDelta(:final text):
            reply = ChatMessage(
              id: 0,
              text: '${reply?.text ?? ''}$text',
              sender: .assistant,
              createdAt: reply?.createdAt ?? DateTime.now(),
            );
          case ChatReplyDone(reply: final storedReply):
            reply = storedReply;
            isDone = true;
        }
        state = AsyncData(
          ChatState(
            messages: [...chat.messages, userMessage, ?reply],
            isReplying: !isDone,
          ),
        );
      }
      if (!isDone) {
        throw const UIException.somethingWentWrong();
      }
    } on Exception catch (error, stackTrace) {
      if (!ref.mounted) {
        return;
      }
      state = AsyncData(
        ChatState(messages: [...chat.messages, userMessage, ?reply]),
      );
      state = AsyncError(error, stackTrace);
    }
  }
}
