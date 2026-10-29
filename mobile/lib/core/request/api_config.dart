// Both values are compile-time settings read with `--dart-define`, so that a
// build can target another backend without editing the code, e.g.:
//   flutter run --dart-define=API_BASE_URL=http://localhost:8000 \
//     --dart-define=USE_MOCK_API=false
// ignore_for_file: do_not_use_environment

/// The url of the backend the requests are made to. Defaults to `10.0.2.2`,
/// the development machine's address from the Android emulator. Override it
/// with `--dart-define=API_BASE_URL=…`.
const apiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://10.0.2.2:8000',
);

/// Whether the repositories return mock data instead of making requests. Set
/// it to `false` with `--dart-define=USE_MOCK_API=false` once the backend is
/// running.
const useMockApi = bool.fromEnvironment('USE_MOCK_API', defaultValue: true);
