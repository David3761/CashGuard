import 'dart:convert';

import 'package:cashctrl/core/models/chat_event.dart';
import 'package:cashctrl/core/models/chat_message.dart';
import 'package:cashctrl/core/request/api_client.dart';
import 'package:cashctrl/core/request/api_config.dart';
import 'package:cashctrl/core/request/event_stream_client.dart';
import 'package:cashctrl/exceptions.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

// Necessary for code-generation to work
// Run: dart run build_runner watch
part 'assistant_repository.g.dart';

/// The provider that returns an instance of [AssistantRepository].
@riverpod
AssistantRepository assistantRepository(Ref ref) {
  return AssistantRepository._(ref);
}

/// The repository for the *Assistant* flow.
class AssistantRepository {
  /// Creates an [AssistantRepository].
  const AssistantRepository._(this.ref);

  /// A [Ref] object used to access any providers (such as `ApiService`).
  final Ref ref;

  /// Returns the chat's messages, the oldest first.
  Future<List<ChatMessage>> getMessages() async {
    if (useMockApi) {
      return const [];
    }
    final json = await ref.read(apiServiceProvider).getChatMessages();
    final messages = json['messages'] as List<dynamic>;
    return messages.map((message) {
      return ChatMessage.fromJson(message as Map<String, dynamic>);
    }).toList();
  }

  /// Sends the given [message] to the assistant and returns the events of the
  /// reply as they stream in.
  ///
  /// Throws a [ServerError] when the server reports an error.
  Stream<ChatEvent> sendMessage(String message) async* {
    if (useMockApi) {
      yield* _dummyEvents(message);
      return;
    }
    final events = ref.read(eventStreamClientProvider).post(
      '/assistant/messages',
      {'text': message},
    );
    // Unknown events are skipped, so that the server can add new ones.
    await for (final event in events) {
      final json = jsonDecode(event.data) as Map<String, dynamic>;
      switch (event.event) {
        case 'message':
          yield ChatMessageStored(ChatMessage.fromJson(json));
        case 'delta':
          yield ChatReplyDelta(json['text'] as String);
        case 'done':
          yield ChatReplyDone(ChatMessage.fromJson(json));
        case 'error':
          throw UIException.serverError(json['message'] as String?);
      }
    }
  }

  /// Returns the dummy events of the reply to the given [message], streamed
  /// while [useMockApi] is `true`.
  Stream<ChatEvent> _dummyEvents(String message) async* {
    yield ChatMessageStored(
      ChatMessage(
        id: DateTime.now().microsecondsSinceEpoch,
        text: message,
        sender: .user,
        createdAt: DateTime.now(),
      ),
    );
    final reply = _dummyReply(message);
    await Future<void>.delayed(const Duration(milliseconds: 500));
    for (final (index, word) in reply.split(' ').indexed) {
      await Future<void>.delayed(const Duration(milliseconds: 60));
      yield ChatReplyDelta(index == 0 ? word : ' $word');
    }
    yield ChatReplyDone(
      ChatMessage(
        id: DateTime.now().microsecondsSinceEpoch,
        text: reply,
        sender: .assistant,
        createdAt: DateTime.now(),
      ),
    );
  }

  /// Returns the dummy reply to the given [message], streamed while
  /// [useMockApi] is `true`.
  String _dummyReply(String message) {
    final question = message.toLowerCase();
    if (question.contains('balance')) {
      return 'Your current balance is 2.847,35 lei.';
    } else if (question.contains('biggest') || question.contains('expense')) {
      return 'Your biggest expense was the 2.300 lei transfer to Elena '
          'Dumitru, five days ago.';
    } else if (question.contains('spend') || question.contains('spent')) {
      return 'In the last 7 days you spent 634,78 lei on card payments, '
          'mostly on fuel and groceries.';
    } else if (question.contains('sent') || question.contains('received')) {
      return 'Ioana Stan sent you 150 lei today, and Maria Ionescu sent you '
          '75 lei three days ago.';
    }
    return "I'm a demo for now, so I can only answer questions about your "
        'balance, spending and transfers.';
  }
}
