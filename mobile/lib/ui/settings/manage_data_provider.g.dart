// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'manage_data_provider.dart';

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning
/// The manage data provider that handles the *view data* and *delete data*
/// flows.

@ProviderFor(ManageData)
final manageDataProvider = ManageDataProvider._();

/// The manage data provider that handles the *view data* and *delete data*
/// flows.
final class ManageDataProvider
    extends $AsyncNotifierProvider<ManageData, ManageDataStatus> {
  /// The manage data provider that handles the *view data* and *delete data*
  /// flows.
  ManageDataProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'manageDataProvider',
        isAutoDispose: true,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$manageDataHash();

  @$internal
  @override
  ManageData create() => ManageData();
}

String _$manageDataHash() => r'a6c9682a2afa221c8b69fc06693b111c7ac5ffe5';

/// The manage data provider that handles the *view data* and *delete data*
/// flows.

abstract class _$ManageData extends $AsyncNotifier<ManageDataStatus> {
  FutureOr<ManageDataStatus> build();
  @$mustCallSuper
  @override
  WhenComplete runBuild() {
    final ref =
        this.ref as $Ref<AsyncValue<ManageDataStatus>, ManageDataStatus>;
    final element =
        ref.element
            as $ClassProviderElement<
              AnyNotifier<AsyncValue<ManageDataStatus>, ManageDataStatus>,
              AsyncValue<ManageDataStatus>,
              Object?,
              Object?
            >;
    return element.handleCreate(ref, build);
  }
}
