# CashCtrl

The CashCtrl mobile app.

### 1. Project structure:

- core
    - database
    - models
    - repositories
    - request
    - etc.; other non-UI related classes
- ui
    - account
    - login
    - main
    - register
    - etc.; each screen has its own package containing all the classes it needs
- utils
- widgets

### 2. Project app structure:

**Language**: Dart <br>
**Architecture**: [Riverpod](https://pub.dev/packages/riverpod) <br>
**State management**: [Riverpod](https://pub.dev/packages/riverpod) <br>
**Compiled for**: Android, iOS <br>
**Database**: [Drift](https://pub.dev/packages/drift) <br>
**Key-Value Local Files**: [Shared Preferences](https://pub.dev/packages/shared_preferences) <br>
**Requests**: [Chopper](https://pub.dev/packages/chopper) <br>
**Dependency Injection**: - <br>
**Request Logger**: a Chopper interceptor that prints requests to the debug console <br>
**Crash Logger**: - <br>
**Product Flavors**: single / only 1 <br>
**Documentation Generator**: dart doc

### 3. Project screens:

- Splashscreen (using the Splashscreen API)
- Login
- Register
- Forgot Password
- Main
- Settings

### 4. Project features:

- **Notifications**
- **Auth Token Refresher**: retrieves the last token and if it is expired, it refreshes it
- **Crypting support**: AES
- **Type Adapters**: AuthMethod (for converting an auth method id to an AuthMethod object when
  parsing a request)
- **SharedPreferences**
- **Validators**: Email & Phone
- Methods designed specifically for **Riverpod**:
    - executing any kind of async operations (including requests)
    - transforming an exception into a user-friendly error
- **AlertDialogWithItems**: utility class for displaying an alert with title, message and multiple
  items that can be clicked
- Methods for:
    - checking for internet connection
    - displaying Alerts, Toasts and Snackbars
    - opening the Phone app, a URL, an E-mail app, the Play Store or App Store
    - downloading an image from a url to a given path

### 5. Backend

The API contract is in [`backend/app/app_api/router.py`](../backend/app/app_api/router.py). The app uses mock data until
`useMockApi` is set to `false` in `lib/core/request/api_config.dart`. By default it then calls
`http://10.0.2.2:8000`, the development machine seen from the Android emulator. Debug builds are
allowed to use plain HTTP for that address only.

### 6. Generating the documentation

The project is fully documented. In order to generate the documentation you only have to run
``dart doc``. The documentation can then be found in *doc > api*. The main file you have to open to
see the documentation properly is **index.html**.
