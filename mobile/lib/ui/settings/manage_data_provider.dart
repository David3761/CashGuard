import 'package:riverpod_annotation/riverpod_annotation.dart';

// Necessary for code-generation to work
// Run: dart run build_runner watch
part 'manage_data_provider.g.dart';

/// The manage data provider that handles the *view data* and *delete data*
/// flows.
@riverpod
class ManageData extends _$ManageData {
  @override
  Future<ManageDataStatus> build() => Future.value(.loading);

  /// Makes a request to send the user's data to their email address.
  Future<void> viewData() async {
    state = const .loading();
    state = await .guard(() async {
      // Simulate a request. Remove these lines after you implement this method.
      await Future.delayed(const Duration(seconds: 2));

      // TODO(everyone): the request is simulated because the backend has no
      // accounts yet. Once it has, remove the delay above and restore the
      // request below.
      /*final userRepository = ref.read(userRepositoryProvider);

      final json = await userRepository.viewData();

      if (json['status'] != 'ok') {
        throw UIException.serverError(json['message']);
      }*/

      return .viewDataEmailSent;
    });
  }

  /// Makes a request to send a delete confirmation message to the user's
  /// email address.
  Future<void> deleteData() async {
    state = const .loading();
    state = await .guard(() async {
      // Simulate a request. Remove these lines after you implement this method.
      await Future.delayed(const Duration(seconds: 2));

      // TODO(everyone): the request is simulated because the backend has no
      // accounts yet. Once it has, remove the delay above and restore the
      // request below.
      /*final userRepository = ref.read(userRepositoryProvider);

      final json = await userRepository.deleteData();

      if (json['status'] != 'ok') {
        throw UIException.serverError(json['message']);
      }*/

      return .deleteDataEmailSent;
    });
  }
}

/// An enum that lists all possible states of the [ManageData] provider.
enum ManageDataStatus {
  /// The initial loading state.
  loading,

  /// The *view data* email sent state.
  viewDataEmailSent,

  /// The *delete data* email sent state.
  deleteDataEmailSent,
}
