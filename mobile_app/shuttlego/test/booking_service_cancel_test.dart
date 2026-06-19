import 'package:flutter_test/flutter_test.dart';
import 'package:shuttlego/services/booking_service.dart';
import 'package:shuttlego/models/booking_record.dart';
import 'package:shuttlego/services/database_adapter.dart';

class InMemoryAdapter implements DatabaseAdapter {
  final Map<String, dynamic> _data = {};

  @override
  Future<Object?> get(String path) async => _readPath(path);

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
  Future<String?> pushKey(String path) async => 'k${DateTime.now().microsecondsSinceEpoch}';

  @override
  Future<void> update(Map<String, Object?> updates) async {
    updates.forEach((k, v) {
      _writePath(k, _normalize(v));
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

  Object? _normalize(Object? v) {
    if (v is Map) {
      final out = <String, dynamic>{};
      v.forEach((key, value) {
        out['$key'] = _normalize(value);
      });
      return out;
    }
    if (v is List) return v.map(_normalize).toList();
    return v;
  }
}

void main() {
  test('cancel active booking updates user and global entries', () async {
    final adapter = InMemoryAdapter();
    // seed a reserved booking
    await adapter.update({
      'bookings/bx': {
        'booking_id': 'bx',
        'user_uid': 'uX',
        'shuttle_key': 'sX',
        'pickup_stop': 'A',
        'pickup_index': 0,
        'destination_stop': 'B',
        'destination_index': 1,
        'status': 'reserved',
        'qr_payload': '{"v":1}',
      },
      'user_bookings/uX/bx': {
        'booking_id': 'bx',
        'user_uid': 'uX',
        'shuttle_key': 'sX',
        'pickup_stop': 'A',
        'pickup_index': 0,
        'destination_stop': 'B',
        'destination_index': 1,
        'status': 'reserved',
        'qr_payload': '{"v":1}',
      }
    });

    final svc = BookingService(adapter: adapter);
    final booking = BookingRecord(
      bookingId: 'bx',
      shuttleKey: 'sX',
      userUid: 'uX',
      pickupStop: 'A',
      pickupIndex: 0,
      destinationStop: 'B',
      destinationIndex: 1,
      status: 'reserved',
      qrPayload: '{"v":1}',
    );

    await svc.cancelBooking(booking: booking, reason: 'no longer');

    final userCopy = await adapter.get('user_bookings/uX/bx') as Map<String, dynamic>;
    final global = await adapter.get('bookings/bx') as Map<String, dynamic>;
    expect(userCopy['status'], 'cancelled');
    expect(global['status'], 'cancelled');
  });
}
