import 'package:flutter_test/flutter_test.dart';
import 'dart:convert';
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
      _writePath(k, _normalize(v));
    });
  }

  @override
  Stream<Object?> onValue(String path) => Stream.fromFuture(get(path));

  @override
  Stream<Object?> queryOnValue(String path, {required String orderByChild, required Object? equalTo}) =>
      Stream.fromFuture(queryGet(path, orderByChild: orderByChild, equalTo: equalTo));

  // Ensure any nested Map literals become Map<String, dynamic> at runtime
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
  group('BookingService.completeBookingFromQr', () {
    test('invalid json payload throws', () async {
      final svc = BookingService(adapter: InMemoryAdapter());
      expect(() => svc.completeBookingFromQr(qrPayload: 'not-json'), throwsA(isA<BookingException>()));
    });

    test('unsupported version throws', () async {
      final svc = BookingService(adapter: InMemoryAdapter());
      final payload = jsonEncode({'v': 2, 'bookingId': 'b', 't': 'x'});
      expect(() => svc.completeBookingFromQr(qrPayload: payload), throwsA(isA<BookingException>()));
    });

    test('invalid token throws', () async {
      final db = InMemoryAdapter();
      db.update({'bookings/b1': {'booking_id': 'b1', 'qr_token': 'tok1', 'status': 'reserved'}});
      final svc = BookingService(adapter: db);
      final payload = jsonEncode({'v': 1, 'bookingId': 'b1', 't': 'wrong'});
      expect(() => svc.completeBookingFromQr(qrPayload: payload), throwsA(isA<BookingException>()));
    });

    test('reserved -> active then active -> completed', () async {
      final db = InMemoryAdapter();
      db.update({
        'bookings/b2': {'booking_id': 'b2', 'qr_token': 'tok2', 'status': 'reserved', 'user_uid': 'u2', 'shuttle_key': 's2'},
        'user_bookings/u2': {
          'b2': {'booking_id': 'b2', 'qr_token': 'tok2', 'status': 'reserved', 'user_uid': 'u2', 'shuttle_key': 's2'}
        }
      });

      final svc = BookingService(adapter: db);
      final payload = jsonEncode({'v': 1, 'bookingId': 'b2', 't': 'tok2'});
      await svc.completeBookingFromQr(qrPayload: payload);
      final after = await db.get('bookings/b2') as Map<String, dynamic>;
      expect(after['status'], 'active');

      // Second scan completes
      await svc.completeBookingFromQr(qrPayload: payload);
      final after2 = await db.get('bookings/b2') as Map<String, dynamic>;
      expect(after2['status'], 'completed');
    });
  });
}
