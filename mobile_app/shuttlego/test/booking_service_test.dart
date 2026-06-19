import 'package:flutter_test/flutter_test.dart';
import 'package:shuttlego/services/booking_service.dart';
import 'package:shuttlego/services/database_adapter.dart';

class InMemoryAdapter implements DatabaseAdapter {
  final Map<String, dynamic> _data = {};

  @override
  Future<Object?> get(String path) async {
    return _readPath(path);
  }

  @override
  Future<Object?> queryGet(String path, {required String orderByChild, required Object? equalTo}) async {
    final collection = _readPath(path);
    if (collection is! Map) return null;
    final out = <String, dynamic>{};
    collection.forEach((k, v) {
      if (v is Map && v[orderByChild] == equalTo) out[k] = v;
    });
    return out;
  }

  @override
  Future<String?> pushKey(String path) async {
    return 'k${DateTime.now().microsecondsSinceEpoch}';
  }

  @override
  Future<void> update(Map<String, Object?> updates) async {
    updates.forEach((k, v) {
      _writePath(k, v);
    });
  }

  @override
  Stream<Object?> onValue(String path) => Stream.fromFuture(get(path));

  @override
  Stream<Object?> queryOnValue(String path, {required String orderByChild, required Object? equalTo}) =>
      Stream.fromFuture(queryGet(path, orderByChild: orderByChild, equalTo: equalTo));

  Object? _readPath(String path) {
    if (path.isEmpty) return null;
    final segs = path.split('/');
    Object? node = _data;
    for (final s in segs) {
      if (node is Map && node.containsKey(s)) {
        node = node[s];
      } else {
        return null;
      }
    }
    return node;
  }

  void _writePath(String path, Object? value) {
    final segs = path.split('/');
    if (segs.isEmpty) return;
    var node = _data;
    for (var i = 0; i < segs.length - 1; i++) {
      final s = segs[i];
      if (!node.containsKey(s) || node[s] is! Map) node[s] = <String, dynamic>{};
      node = node[s] as Map<String, dynamic>;
    }
    final last = segs.last;
    if (value == null) {
      node.remove(last);
    } else {
      node[last] = value;
    }
  }

}

void main() {
  group('BookingService.createBooking', () {
    test('creates booking when seats available', () async {
      final db = InMemoryAdapter();
      // Setup shuttle with 3 available seats
      await db.update({
        'shuttles/s1': {'available_seats': 3, 'current_count': 0},
        'bookings': <String, dynamic>{},
        'user_bookings': <String, dynamic>{},
      });

      final service = BookingService(adapter: db);
      final receipt = await service.createBooking(
        shuttleKey: 's1',
        userUid: 'u1',
        pickupStop: 'A',
        pickupIndex: 0,
        destinationStop: 'B',
        destinationIndex: 1,
      );

      expect(receipt.bookingId, isNotEmpty);
      // Check that booking was persisted
      final bookings = await db.get('bookings') as Map<String, dynamic>;
      expect(bookings.containsKey(receipt.bookingId), isTrue);
      final byUser = await db.get('user_bookings') as Map<String, dynamic>;
      expect(byUser['u1'][receipt.bookingId]['status'], 'reserved');
    });

    test('throws when no free seats', () async {
      final db = InMemoryAdapter();
      await db.update({
        'shuttles/s2': {'available_seats': 0, 'current_count': 10},
        'bookings': <String, dynamic>{},
        'user_bookings': <String, dynamic>{},
      });

      final service = BookingService(adapter: db);
      expect(
        service.createBooking(
          shuttleKey: 's2',
          userUid: 'u2',
          pickupStop: 'A',
          pickupIndex: 0,
          destinationStop: 'B',
          destinationIndex: 1,
        ),
        throwsA(isA<BookingException>()),
      );
    });

    test('prevents user with existing reserved booking', () async {
      final db = InMemoryAdapter();
      await db.update({
        'shuttles/s3': {'available_seats': 5, 'current_count': 0},
        'user_bookings': {
          'u3': {
            'b_existing': {
              'booking_id': 'b_existing',
              'status': 'reserved',
              'shuttle_key': 's3',
            }
          }
        },
        'bookings': {
          'b_existing': {
            'booking_id': 'b_existing',
            'shuttle_key': 's3',
            'status': 'reserved',
          }
        }
      });

      final service = BookingService(adapter: db);
      expect(
        service.createBooking(
          shuttleKey: 's3',
          userUid: 'u3',
          pickupStop: 'A',
          pickupIndex: 0,
          destinationStop: 'B',
          destinationIndex: 1,
        ),
        throwsA(isA<BookingException>()),
      );
    });
  });
}
