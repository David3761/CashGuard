// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'event_stream_client.dart';

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning
/// The provider that returns an instance of [EventStreamClient]. It's kept
/// alive so that its HTTP client isn't closed while a stream is being read.

@ProviderFor(eventStreamClient)
final eventStreamClientProvider = EventStreamClientProvider._();

/// The provider that returns an instance of [EventStreamClient]. It's kept
/// alive so that its HTTP client isn't closed while a stream is being read.

final class EventStreamClientProvider
    extends
        $FunctionalProvider<
          EventStreamClient,
          EventStreamClient,
          EventStreamClient
        >
    with $Provider<EventStreamClient> {
  /// The provider that returns an instance of [EventStreamClient]. It's kept
  /// alive so that its HTTP client isn't closed while a stream is being read.
  EventStreamClientProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'eventStreamClientProvider',
        isAutoDispose: false,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$eventStreamClientHash();

  @$internal
  @override
  $ProviderElement<EventStreamClient> $createElement(
    $ProviderPointer pointer,
  ) => $ProviderElement(pointer);

  @override
  EventStreamClient create(Ref ref) {
    return eventStreamClient(ref);
  }

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(EventStreamClient value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<EventStreamClient>(value),
    );
  }
}

String _$eventStreamClientHash() => r'33ff618aa092208f4a978945b7e96f3c3114a229';
