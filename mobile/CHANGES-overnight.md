# Mobile: overnight hardening (2026-10-29)

These are small, reviewable changes on top of David V.'s "Mobile mvp" (`aa6c172`). They don't change the UI design or rename the package. `google-services.json` and the backend are untouched.

Checked with Flutter 3.47.8 (Dart 3.13.7):

|                  | before          | after             |
|------------------|-----------------|-------------------|
| `flutter analyze` | no issues       | no issues         |
| `flutter test`    | 0 passed, 1 failed | 8 passed, 0 failed |

## What changed and why

### 1. `AESHelper`: no hard-coded key, random IV for every encryption

`lib/core/security/aes_helper.dart` had two problems:

- **CWE-321:** the AES key was hard-coded in the source, so anyone with the APK or IPA could decrypt.
- **CWE-329:** the IV came from `IV.fromLength(16)`. In encrypt 5.0.3 this is random, but it was created once per app run and never saved. Every encryption in a run reused it, and after a restart `decrypt` garbled the first 16 bytes.

The class now:

- generates a random 256-bit key on first use and keeps it with **`flutter_secure_storage`**, a new dependency. On iOS the key lives in the Keychain; on Android it's wrapped by an Android Keystore key.
- uses **AES-256/GCM**, which also authenticates the data: a tampered cipher text fails to decrypt.
- creates a new random 96-bit IV for every encryption and prepends it to the cipher text: `base64(IV | cipher text | tag)`.

**The API is now async:** `await AESHelper.instance.encrypt(…)` / `decrypt(…)`.

- The only live call site, `AuthTokenController._refreshAuthTokenLogin`, now awaits it inside the existing `try`. A lost key (data restored on another device) then means "log in again" instead of a crash.
- The commented-out call in `login_provider.dart` is updated too.
- Values encrypted by the old code can't be decrypted. None exist, because the login is still simulated.

**Android:** `android:allowBackup="false"` is set, as flutter_secure_storage requires. Keystore keys are never backed up, so restored data couldn't be decrypted. This also keeps financial data out of cloud backups.

Tests: `test/core/security/aes_helper_test.dart` covers six cases: round trip, random IV, key persisted, wrong key, tampering and malformed input.

### 2. Backend URL and mock mode come from `--dart-define`

`lib/core/request/api_config.dart`:

```dart
const apiBaseUrl = String.fromEnvironment('API_BASE_URL', defaultValue: 'http://10.0.2.2:8000');
const useMockApi = bool.fromEnvironment('USE_MOCK_API', defaultValue: true);
```

The defaults are exactly the values David V. set, so `flutter run` with no flags behaves as before.

### 3. Template leftovers

- **`test/widget_test.dart`:** the template's "Dummy test" pumped `MyApp` without a `ProviderScope` and failed. It's replaced by two real widget tests of `AssistantScreen` on the mock data: the greeting and suggestions show, and tapping a suggestion sends it and streams the mock reply.
- **TODOs:** the "after you fork the repository" / "used just for the base project" TODOs now say what is simulated and when to restore it (once the backend has accounts). These are comment-only changes.
- The real TODOs are unchanged: the auth interceptor in `api_client.dart`, notification channel translations, the `routeExists` workaround and the design icons.

### 4. iOS App Transport Security

`ios/Runner/Info.plist` had `NSAllowsArbitraryLoads = true`, which turns ATS off for every host. It's replaced by `NSExceptionDomains` that allow plain HTTP only to `localhost` and `127.0.0.1`, i.e. the dev machine from the iOS simulator. Every other host must use HTTPS.

Android was already correct: cleartext is allowed only in debug builds, only to `10.0.2.2`, `localhost` and `127.0.0.1` (`src/debug/res/xml/network_security_config.xml`). Release builds allow HTTPS only.

### 5. Accessibility

- The icon-only buttons now have a tooltip, which screen readers read as the button's label: send (assistant), filters (transactions) and close (web page sheet).
- This adds the `sendMessage` string; `app_localizations*.dart` is regenerated.
- The bottom tabs are marked as buttons with a selected state.
- Nothing changes visually. Tooltips appear only on long press.

## How to run

```bash
cd mobile
flutter pub get

# Mock data, no backend (same as before)
flutter run

# Android emulator, backend on the dev machine (port 8000)
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000 --dart-define=USE_MOCK_API=false

# iOS simulator, backend on the dev machine
flutter run --dart-define=API_BASE_URL=http://localhost:8000 --dart-define=USE_MOCK_API=false

# Physical Android device over USB
adb reverse tcp:8000 tcp:8000
flutter run --dart-define=API_BASE_URL=http://localhost:8000 --dart-define=USE_MOCK_API=false

# Deployed backend (release builds allow HTTPS only)
flutter run --release --dart-define=API_BASE_URL=https://<host> --dart-define=USE_MOCK_API=false
```

To run the checks: `flutter analyze && flutter test`. With `--dart-define=USE_MOCK_API=false` the widget tests are skipped, because they need the mock data.

## Notes for David V.

- **Not built on a device:** there was no Android SDK or Xcode on the machine. `flutter_secure_storage` 11.2.0 needs Android minSdk 23 (the app uses 26) and supports Swift Package Manager on iOS, so it should build as is. Please do one `flutter run` on each platform.
- **Left as is, worth a look:**
  - `WRITE_EXTERNAL_STORAGE` in the main manifest is unused, and scanners flag it.
  - Release builds are signed with the committed `debug.keystore`, which is a template TODO in `build.gradle.kts`.
- The brief mentioned a mic button, but there is none in the app yet.
