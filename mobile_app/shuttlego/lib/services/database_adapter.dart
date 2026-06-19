import 'package:firebase_database/firebase_database.dart';

/// A thin database adapter interface used to make `BookingService` testable
/// without depending on the full `FirebaseDatabase` API in unit tests.
abstract class DatabaseAdapter {
  Future<Object?> get(String path);
  Future<Object?> queryGet(String path, {required String orderByChild, required Object? equalTo});
  Future<void> update(Map<String, Object?> updates);
  /// Generate a new push-style key under the provided path (e.g. 'bookings').
  Future<String?> pushKey(String path);
  /// Optional: stream real-time updates for a node. The default implementation
  /// falls back to a single-shot read to preserve test behaviour.
  Stream<Object?> onValue(String path) => Stream.fromFuture(get(path));

  /// Optional: stream real-time updates for a query. Default falls back to
  /// a single-shot query read.
  Stream<Object?> queryOnValue(String path, {required String orderByChild, required Object? equalTo}) =>
      Stream.fromFuture(queryGet(path, orderByChild: orderByChild, equalTo: equalTo));
}

/// Production adapter that delegates to `FirebaseDatabase`.
class FirebaseDatabaseAdapter implements DatabaseAdapter {
  FirebaseDatabaseAdapter(this._db);

  final FirebaseDatabase _db;

  @override
  Future<Object?> get(String path) async {
    final ref = _db.ref();
    final segs = path.split('/');
    DatabaseReference node = ref;
    for (final s in segs) {
      if (s.isEmpty) continue;
      node = node.child(s);
    }
    final snap = await node.get();
    return snap.value;
  }

  @override
  Future<Object?> queryGet(String path, {required String orderByChild, required Object? equalTo}) async {
    final ref = _db.ref();
    final segs = path.split('/');
    DatabaseReference node = ref;
    for (final s in segs) {
      if (s.isEmpty) continue;
      node = node.child(s);
    }
    final snap = await node.orderByChild(orderByChild).equalTo(equalTo).get();
    return snap.value;
  }

  @override
  Future<void> update(Map<String, Object?> updates) async {
    await _db.ref().update(updates);
  }

  @override
  Future<String?> pushKey(String path) async {
    final ref = _db.ref();
    final segs = path.split('/');
    DatabaseReference node = ref;
    for (final s in segs) {
      if (s.isEmpty) continue;
      node = node.child(s);
    }
    return node.push().key;
  }

  @override
  Stream<Object?> onValue(String path) {
    final ref = _db.ref();
    final segs = path.split('/');
    DatabaseReference node = ref;
    for (final s in segs) {
      if (s.isEmpty) continue;
      node = node.child(s);
    }
    return node.onValue.map((event) => event.snapshot.value);
  }

  @override
  Stream<Object?> queryOnValue(String path, {required String orderByChild, required Object? equalTo}) {
    final ref = _db.ref();
    final segs = path.split('/');
    DatabaseReference node = ref;
    for (final s in segs) {
      if (s.isEmpty) continue;
      node = node.child(s);
    }
    return node.orderByChild(orderByChild).equalTo(equalTo).onValue.map((e) => e.snapshot.value);
  }
}
