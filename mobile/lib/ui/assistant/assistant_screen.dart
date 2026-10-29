import 'dart:async';

import 'package:cashctrl/core/models/chat_message.dart';
import 'package:cashctrl/core/utils/relative_time.dart';
import 'package:cashctrl/exceptions.dart';
import 'package:cashctrl/l10n/app_localizations.dart';
import 'package:cashctrl/resources/colors.dart';
import 'package:cashctrl/resources/images.dart';
import 'package:cashctrl/resources/text_styles.dart';
import 'package:cashctrl/ui/assistant/chat_provider.dart';
import 'package:cashctrl/utils/dialogs.dart';
import 'package:cashctrl/widgets/app_header.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

/// The text style of the chat's messages.
final _messageTextStyle = TextStyles.text16R.copyWith(height: 1.31);

/// The style of the suggested questions, which are filled with the brand color
/// while pressed.
final _suggestionStyle = ButtonStyle(
  backgroundColor: WidgetStateProperty.resolveWith((states) {
    return states.contains(WidgetState.pressed)
        ? AppColors.surfaceBrand
        : AppColors.surfaceBase;
  }),
  foregroundColor: const WidgetStatePropertyAll(AppColors.textPrimary),
  overlayColor: const WidgetStatePropertyAll(Colors.transparent),
  side: WidgetStateProperty.resolveWith((states) {
    return states.contains(WidgetState.pressed)
        ? BorderSide.none
        : const BorderSide(color: AppColors.borderDefault);
  }),
  shape: WidgetStatePropertyAll(
    RoundedRectangleBorder(borderRadius: .circular(8)),
  ),
  padding: const WidgetStatePropertyAll(
    .directional(start: 14, top: 10, end: 14, bottom: 11),
  ),
  minimumSize: const WidgetStatePropertyAll(.zero),
  tapTargetSize: .shrinkWrap,
);

/// The screen that displays the chat with the assistant.
class AssistantScreen extends ConsumerStatefulWidget {
  /// Creates an [AssistantScreen].
  const AssistantScreen({super.key});

  /// The route's name.
  static const route = 'assistant';

  @override
  ConsumerState<AssistantScreen> createState() => _AssistantScreenState();
}

class _AssistantScreenState extends ConsumerState<AssistantScreen> {
  /// The controller of the message field.
  final _messageController = TextEditingController();

  /// Disposes of the [_messageController].
  @override
  void dispose() {
    _messageController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context);
    final chatState = ref.watch(chatProvider);
    _listenForProviders();

    final chat = chatState.value;
    final messages = chat?.messages;
    return Column(
      children: [
        AppHeader(title: localizations.assistant),
        Expanded(
          child: switch (messages) {
            null when chatState.isLoading => const Center(
              child: CircularProgressIndicator(),
            ),
            null || [] => _Greeting(onSuggestionTap: _sendMessage),
            _ => _MessageList(messages: messages),
          },
        ),
        _MessageComposer(
          controller: _messageController,
          canSend: chat == null ? !chatState.isLoading : !chat.isReplying,
          onSend: () => _sendMessage(_messageController.text),
        ),
      ],
    );
  }

  /// Displays an alert when the chat fails to load or a reply fails.
  void _listenForProviders() {
    ref.listen(chatProvider, (_, state) {
      if (state case AsyncError(:final error)) {
        unawaited(
          showAlert(
            context: context,
            title: AppLocalizations.of(context).error_,
            message: getLocalizedMessage(context, error),
          ),
        );
      }
    });
  }

  /// Sends the given [message] to the assistant and clears the message field.
  void _sendMessage(String message) {
    final text = message.trim();
    if (text.isEmpty) {
      return;
    }
    _messageController.clear();
    unawaited(ref.read(chatProvider.notifier).sendMessage(text));
  }
}

/// A widget that displays the assistant's greeting and the suggested
/// questions, shown before the first message.
class _Greeting extends StatelessWidget {
  /// Creates a [_Greeting].
  const _Greeting({required this.onSuggestionTap});

  /// Called when the user taps a suggested question.
  final ValueChanged<String> onSuggestionTap;

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context);
    final suggestions = [
      localizations.suggestionWeeklySpending,
      localizations.suggestionBiggestExpense,
      localizations.suggestionBalance,
      localizations.suggestionIncomingMoney,
    ];
    return Center(
      child: SingleChildScrollView(
        padding: const .directional(start: 20, top: 16, end: 20, bottom: 14),
        child: Column(
          spacing: 48,
          children: [
            Column(
              spacing: 16,
              children: [
                Image.asset(AppImages.assistantLogo),
                Text(
                  localizations.assistantGreeting,
                  style: TextStyles.text22SB,
                  textAlign: .center,
                ),
                ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 300),
                  child: Text(
                    localizations.assistantIntro,
                    style: TextStyles.text15R.copyWith(
                      height: 1.4,
                      color: AppColors.textMuted,
                    ),
                    textAlign: .center,
                  ),
                ),
              ],
            ),
            Column(
              spacing: 10,
              children: [
                Text(
                  localizations.tryLabel,
                  style: TextStyles.text13M.copyWith(
                    letterSpacing: 0.6,
                    color: AppColors.textMuted,
                  ),
                ),
                for (final suggestion in suggestions) ...[
                  TextButton(
                    onPressed: () => onSuggestionTap(suggestion),
                    style: _suggestionStyle,
                    child: Text(
                      suggestion,
                      style: TextStyles.text15R.copyWith(
                        height: 1.33,
                        letterSpacing: -0.23,
                      ),
                      textAlign: .center,
                    ),
                  ),
                ],
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// A widget that displays the chat's messages, the newest at the bottom.
class _MessageList extends StatelessWidget {
  /// Creates a [_MessageList].
  const _MessageList({required this.messages});

  /// The chat's messages, the oldest first.
  final List<ChatMessage> messages;

  @override
  Widget build(BuildContext context) {
    final items = <Widget>[];
    for (final (index, message) in messages.indexed) {
      final previous = index == 0 ? null : messages[index - 1];
      if (previous == null ||
          !DateUtils.isSameDay(previous.createdAt, message.createdAt)) {
        items.add(_TimeSeparator(dateTime: message.createdAt));
      }
      items.add(switch (message.sender) {
        .user => _UserMessage(message: message),
        .assistant => _AssistantMessage(
          message: message,
          showSender: previous?.sender != .assistant,
        ),
      });
    }
    final newestFirst = items.reversed.toList();

    return ListView.separated(
      reverse: true,
      keyboardDismissBehavior: .onDrag,
      padding: const .directional(start: 16, top: 14, end: 16, bottom: 16),
      itemCount: newestFirst.length,
      itemBuilder: (_, index) => newestFirst[index],
      separatorBuilder: (_, _) => const SizedBox(height: 14),
    );
  }
}

/// A widget that displays the day and time the messages below it started at.
class _TimeSeparator extends StatelessWidget {
  /// Creates a [_TimeSeparator].
  const _TimeSeparator({required this.dateTime});

  /// The moment the messages below the separator started at.
  final DateTime dateTime;

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context);
    return Text.rich(
      TextSpan(
        children: [
          TextSpan(
            text: formatDay(dateTime, localizations: localizations),
            style: TextStyles.text12B.copyWith(color: AppColors.textMuted),
          ),
          TextSpan(
            text: ' ${DateFormat.Hm().format(dateTime)}',
            style: TextStyles.text12M.copyWith(color: AppColors.textMuted),
          ),
        ],
      ),
      textAlign: .center,
    );
  }
}

/// A widget that displays a message the user sent.
class _UserMessage extends StatelessWidget {
  /// Creates a [_UserMessage].
  const _UserMessage({required this.message});

  /// The displayed message.
  final ChatMessage message;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const .directional(start: 48),
      child: Align(
        alignment: .centerEnd,
        child: DecoratedBox(
          decoration: const BoxDecoration(
            color: AppColors.surfaceMessageUser,
            borderRadius: BorderRadiusDirectional.only(
              topStart: .circular(18),
              topEnd: .circular(6),
              bottomEnd: .circular(18),
              bottomStart: .circular(18),
            ),
          ),
          child: Padding(
            padding: const .directional(
              start: 14,
              top: 10,
              end: 14,
              bottom: 11,
            ),
            child: Text(message.text, style: _messageTextStyle),
          ),
        ),
      ),
    );
  }
}

/// A widget that displays a message from the assistant, below the assistant's
/// name and the message's time when it starts a reply.
class _AssistantMessage extends StatelessWidget {
  /// Creates an [_AssistantMessage].
  const _AssistantMessage({required this.message, required this.showSender});

  /// The displayed message.
  final ChatMessage message;

  /// Whether the assistant's name and the message's time are displayed above
  /// the message.
  final bool showSender;

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context);
    return Column(
      crossAxisAlignment: .start,
      spacing: 2,
      children: [
        if (showSender) ...[
          Padding(
            padding: const .directional(start: 16),
            child: Text.rich(
              TextSpan(
                children: [
                  TextSpan(
                    text: '${localizations.appName} ',
                    style: TextStyles.text12SB.copyWith(
                      height: 1.75,
                      color: AppColors.textMuted,
                    ),
                  ),
                  TextSpan(
                    text: '· ',
                    style: TextStyles.text12M.copyWith(
                      height: 1.75,
                      color: AppColors.textMuted,
                    ),
                  ),
                  TextSpan(
                    text: DateFormat.Hm().format(message.createdAt),
                    style: TextStyles.text12R.copyWith(
                      height: 1.75,
                      color: AppColors.textMuted,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
        DecoratedBox(
          decoration: BoxDecoration(
            color: AppColors.surfaceBase,
            border: .all(color: AppColors.borderDefault),
            borderRadius: const BorderRadiusDirectional.only(
              topStart: .circular(6),
              topEnd: .circular(18),
              bottomEnd: .circular(18),
              bottomStart: .circular(18),
            ),
          ),
          child: Padding(
            padding: const .directional(
              start: 16,
              top: 10,
              end: 16,
              bottom: 11,
            ),
            child: Text(message.text, style: _messageTextStyle),
          ),
        ),
      ],
    );
  }
}

/// A widget that displays the field the user writes messages in, next to the
/// button that sends them.
class _MessageComposer extends StatelessWidget {
  /// Creates a [_MessageComposer].
  const _MessageComposer({
    required this.controller,
    required this.canSend,
    required this.onSend,
  });

  /// The controller of the message field.
  final TextEditingController controller;

  /// Whether a message can be sent, which isn't the case while the chat loads
  /// or while the assistant is replying.
  final bool canSend;

  /// Called when the user sends the written message.
  final VoidCallback onSend;

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context);
    return DecoratedBox(
      decoration: const BoxDecoration(
        color: AppColors.surfaceSubtle,
        border: Border(top: BorderSide(color: AppColors.borderDefault)),
      ),
      child: Padding(
        padding: const .directional(start: 12, top: 10, end: 12, bottom: 8),
        child: ValueListenableBuilder(
          valueListenable: controller,
          builder: (_, value, _) {
            final isSendable = canSend && value.text.trim().isNotEmpty;
            return Row(
              spacing: 8,
              children: [
                Expanded(
                  child: Container(
                    constraints: const BoxConstraints(minHeight: 48),
                    padding: const .symmetric(horizontal: 14),
                    alignment: .centerStart,
                    decoration: BoxDecoration(
                      color: AppColors.surfaceBase,
                      border: .all(color: AppColors.borderDefault),
                      borderRadius: .circular(12),
                    ),
                    child: TextField(
                      controller: controller,
                      minLines: 1,
                      maxLines: 5,
                      textCapitalization: .sentences,
                      cursorColor: AppColors.textPrimary,
                      style: TextStyles.text16R,
                      decoration: InputDecoration(
                        border: .none,
                        isCollapsed: true,
                        contentPadding: const .symmetric(vertical: 10),
                        hintText: localizations.messageHint,
                        hintStyle: TextStyles.text16R.copyWith(
                          color: AppColors.textMuted,
                        ),
                      ),
                    ),
                  ),
                ),
                IconButton(
                  onPressed: isSendable ? onSend : null,
                  tooltip: localizations.sendMessage,
                  style: IconButton.styleFrom(
                    backgroundColor: AppColors.surfaceBrand,
                    disabledBackgroundColor: AppColors.surfaceBase,
                    fixedSize: const Size.square(48),
                    side: isSendable
                        ? null
                        : const BorderSide(color: AppColors.borderDefault),
                    shape: RoundedRectangleBorder(borderRadius: .circular(12)),
                  ),
                  icon: Image.asset(
                    AppImages.chatSend,
                    color: isSendable
                        ? AppColors.textPrimary
                        : AppColors.textMuted,
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}
