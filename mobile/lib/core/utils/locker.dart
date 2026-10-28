import 'dart:async';

/// A *Semaphore* like class that syncs a part of the code to prevent
/// concurrency issues.
///
/// You can see more info [here](https://stackoverflow.com/questions/42071051/dart-how-to-manage-concurrency-in-async-function).
class Locker {
  Future<void>? _isWorking;
  Completer<void>? _completer;

  /// Returns `true` if the locker is in the locked state or `false` otherwise.
  bool get locked => _isWorking != null;

  /// Acquires the lock.
  void lock() {
    _completer = Completer();
    _isWorking = _completer?.future;
  }

  /// Releases the lock.
  void unlock() {
    _completer?.complete();
    _isWorking = null;
  }

  /// Waits for the lock to be released.
  Future<void> waitLock() async {
    await _isWorking;
  }
}
