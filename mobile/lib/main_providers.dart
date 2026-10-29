import 'dart:async';

import 'package:cashctrl/core/database/app_database.dart';
import 'package:cashctrl/core/repositories/user_repository.dart';
import 'package:cashctrl/core/request/auth_token_controller.dart';
import 'package:cashctrl/core/utils/logging.dart';
import 'package:cashctrl/ui/assistant/assistant_screen.dart';
import 'package:cashctrl/ui/forgot_password/forgot_password_screen.dart';
import 'package:cashctrl/ui/login/login_screen.dart';
import 'package:cashctrl/ui/main/user_provider.dart';
import 'package:cashctrl/ui/register/register_screen.dart';
import 'package:cashctrl/ui/settings/settings_screen.dart';
import 'package:cashctrl/ui/shell/app_shell.dart';
import 'package:cashctrl/ui/transactions/transactions_screen.dart';
import 'package:cashctrl/utils/connection_util.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

// Necessary for code-generation to work
// Run: dart run build_runner watch
part 'main_providers.g.dart';

/// Global navigator required for the GoRouter.
/// A navigator key that can be used to get access to the current context
/// of the app.
///
/// **Only use it when no context is available and only if getting a more
/// appropriate context would be completely out of hand.**
final rootNavigatorKey = GlobalKey<NavigatorState>();

/// The provider that performs any initializations prior to app opening.
/// A new "splash screen" will continue to be displayed following the default
/// OS splash screen.
///
/// This provider was inspired from:
/// https://codewithandrea.com/articles/robust-app-initialization-riverpod/
@riverpod
Future<void> appStartup(Ref ref) async {
  // We watch the AppDatabase provider here so that it is kept alive for the
  // entire lifecycle of the app. Only 1 instance of the AppDatabase should
  // be created by the app.
  ref
    ..watch(appDatabaseProvider)
    // We watch the InternetConnection provider here so that the app has direct
    // access to the internet connection state.
    ..watch(internetConnectionProvider);

  // TODO(everyone): uncomment these lines once the backend has accounts, so
  // that the auth token is refreshed when the app loads.
  //
  // Check if the user has previously signed, by looking at any locally saved
  // auth token.
  /*final authTokenController = ref.watch(authTokenControllerProvider);
    var authToken = await authTokenController.getToken();
    // Check if we have an auth token.
    if (authToken != null) {
      // Refresh the auth token.
      authToken = await authTokenController.getToken(usedToken: authToken);
      if (authToken == null) {
        // Logout if refresh token failed.
        await ref.watch(authProvider.notifier).logout();
      }
    }*/
}

/// The provider that knows whether the user is logged in or not.
///
/// The code you put in here should be easy, simple and quick to execute.
/// Don't fetch the user from the server and don't do any other expensive
/// calculations, since this provider is used by the [routerProvider] to
/// figure out whether to show the login screen or not. Failing to do so, will
/// make the UI stay in an awkward screen while the app figures out whether the
/// user is logged in or not.
///
/// If you need access to the user's data, use the [userDataProvider] instead.
@riverpod
class Auth extends _$Auth {
  // this should be a quick loading provider, so that the UI doesn't sit in
  // an awkward screen while the app figures out whether the user is loaded
  // or not.
  @override
  Future<bool> build() {
    ref.watch(userRepositoryProvider);
    return ref.watch(authTokenControllerProvider).isUserLoggedIn();
  }

  /// Makes a request to remove the device token from the server, then it
  /// removes the user's data from the local files and invalidates the
  /// [authProvider] in order to trigger an update in the UI (i.e.: redirect
  /// the user to the login screen).
  Future<void> logout() async {
    state = const .loading();
    // TODO(everyone): uncomment this once the backend stores the device
    // tokens for push notifications. Otherwise, remove it.
    // await sendOrDeleteDeviceToken(deleteToken: true);
    await ref.read(userRepositoryProvider).logoutUserLocally();
    ref.invalidateSelf();
  }
}

/// The provider that is in charge with the app routing. Basically, every
/// navigation is done through the `GoRouter`, by using this provider.
///
/// This provider uses the [authProvider] to figure out whether the user is
/// logged in or not.
@riverpod
class Router extends _$Router {
  @override
  GoRouter build() {
    final isLoggedIn = ValueNotifier<AsyncValue<bool>>(const .loading());

    final router = GoRouter(
      initialLocation: '/',
      navigatorKey: rootNavigatorKey,
      routes: [
        GoRoute(
          path: '/',
          builder: (context, state) => const ColoredBox(color: Colors.white),
        ),
        GoRoute(
          path: '/${LoginScreen.route}',
          name: LoginScreen.route,
          builder: (context, state) => const LoginScreen(),
          routes: [
            GoRoute(
              path: ForgotPasswordScreen.route,
              name: ForgotPasswordScreen.route,
              builder: (context, state) => const ForgotPasswordScreen(),
            ),
            GoRoute(
              path: RegisterScreen.route,
              name: RegisterScreen.route,
              builder: (context, state) => const RegisterScreen(),
            ),
          ],
        ),
        // The branches' order must match the order of the [ShellTab] values.
        StatefulShellRoute.indexedStack(
          builder: (context, state, navigationShell) {
            return AppShell(navigationShell: navigationShell);
          },
          branches: [
            StatefulShellBranch(
              routes: [
                GoRoute(
                  path: '/${TransactionsScreen.route}',
                  name: TransactionsScreen.route,
                  builder: (context, state) {
                    final data = state.extra as String?;
                    return TransactionsScreen(notificationData: data);
                  },
                  routes: [
                    GoRoute(
                      path: SettingsScreen.route,
                      name: SettingsScreen.route,
                      parentNavigatorKey: rootNavigatorKey,
                      builder: (context, state) => const SettingsScreen(),
                    ),
                  ],
                ),
              ],
            ),
            StatefulShellBranch(
              routes: [
                GoRoute(
                  path: '/${AssistantScreen.route}',
                  name: AssistantScreen.route,
                  builder: (context, state) => const AssistantScreen(),
                ),
              ],
            ),
          ],
        ),
      ],
      refreshListenable: isLoggedIn,
      redirect: (context, state) {
        final routePath = state.fullPath;
        devPrint('redirect with route: $routePath');
        if (routePath == null) {
          return null;
        }

        if (isLoggedIn.value.isLoading || !isLoggedIn.value.hasValue) {
          return null;
        }

        if (isLoggedIn.value.requireValue) {
          if (routePath == '/') {
            return '/${TransactionsScreen.route}';
          } else if (!_routeExists(routePath) || !_requireAuth(routePath)) {
            // In case the app tries to load a page for which the route doesn't
            // exist or it corresponds to one of the unauthenticated screens,
            // then we redirect the user to the root screen.
            return '/';
          }
        } else {
          // Check for deep link routes here and do the appropriate redirects.

          // If the user is not logged in, then they can only navigate through
          // the unauthenticated screens.
          if (_requireAuth(routePath)) {
            return '/${LoginScreen.route}';
          }
        }
        return null;
      },
    );

    // When this provider is disposed, also dispose the router isLoggedIn
    // notifier and router instance.
    //
    // This provider listens for changes in authProvider, so that the UI is
    // updated accordingly.
    ref
      ..onDispose(isLoggedIn.dispose)
      ..onDispose(router.dispose)
      ..listen(authProvider, (_, next) {
        isLoggedIn.value = next;
      });

    return router;
  }

  /// Checks if the given route exists.
  ///
  // TODO(Mihai): routeExists implementation is a workaround to a known issue:
  // https://github.com/flutter/flutter/issues/117514
  bool _routeExists(String route) {
    try {
      final uri = Uri.parse(route);
      return state.routeInformationParser.configuration
          .findMatch(uri)
          .matches
          .isNotEmpty;
    } on Exception catch (_) {
      return false;
    }
  }

  /// Returns `true` if the given [route] requires the user to be authenticated
  /// or `false` otherwise.
  bool _requireAuth(String route) {
    return !route.startsWith('/${LoginScreen.route}');
  }
}

/// The provider that is aware of changes in internet connection. When you
/// want to check if you the device has an active internet connection, you may
/// use this provider.
@riverpod
class InternetConnection extends _$InternetConnection {
  final _connectionUtil = ConnectionUtil();

  @override
  bool build() {
    _connectionUtil.initialize();
    _connectionUtil.connectionChange.listen((hasInternet) {
      state = hasInternet;
    });
    ref.onDispose(_connectionUtil.dispose);

    return false;
  }
}
