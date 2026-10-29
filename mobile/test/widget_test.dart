import 'package:cashctrl/core/request/api_config.dart';
import 'package:cashctrl/l10n/app_localizations.dart';
import 'package:cashctrl/ui/assistant/assistant_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

/// Displays the [AssistantScreen] the way the app does, with the mock data of
/// the repositories (see [useMockApi]).
Future<void> pumpAssistantScreen(WidgetTester tester) async {
  await tester.pumpWidget(
    const ProviderScope(
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(body: AssistantScreen()),
      ),
    ),
  );
  // Lets the chat load its (empty) mock history.
  await tester.pump();
}

void main() {
  testWidgets('the assistant greets the user and suggests questions', (
    tester,
  ) async {
    await pumpAssistantScreen(tester);

    expect(find.text('Assistant'), findsOneWidget);
    expect(find.text('Hi there'), findsOneWidget);
    expect(find.text('How much did I spend this week?'), findsOneWidget);
    expect(find.text("What's my current balance?"), findsOneWidget);
    // The icon-only send button is named for screen readers.
    expect(find.byTooltip('Send message'), findsOneWidget);
  }, skip: !useMockApi);

  testWidgets('tapping a suggestion sends it and streams the reply', (
    tester,
  ) async {
    await pumpAssistantScreen(tester);

    await tester.tap(find.text("What's my current balance?"));
    // The mock reply streams in word by word, in less than a second.
    await tester.pump(const Duration(seconds: 2));
    await tester.pump();

    expect(find.text('Hi there'), findsNothing);
    expect(find.text("What's my current balance?"), findsOneWidget);
    expect(find.text('Your current balance is 2.847,35 lei.'), findsOneWidget);
  }, skip: !useMockApi);
}
