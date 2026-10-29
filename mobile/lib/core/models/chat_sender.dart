/// An enum class that lists who can send a chat message: the user or the
/// assistant.
enum ChatSender {
  /// The app's user.
  user,

  /// The assistant.
  assistant;

  /// Returns the sender matching the given [value] from a request's response.
  factory ChatSender.fromJson(String value) => switch (value) {
    'user' => .user,
    'assistant' => .assistant,
    _ => throw FormatException('Unknown chat sender: $value'),
  };
}
