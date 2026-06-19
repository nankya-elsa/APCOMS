import 'package:flutter_test/flutter_test.dart';
import 'package:shuttlego/models/booking_record.dart';

void main() {
  group('BookingRecord.fromMap', () {
    test('returns null for missing required fields', () {
      final map = <String, Object?>{
        'booking_id': ' ', // invalid when trimmed
      };
      final r = BookingRecord.fromMap(map);
      expect(r, isNull);
    });

    test('parses valid map with string qr payload', () {
      final map = <String, Object?>{
        'booking_id': 'b1',
        'shuttle_key': 's1',
        'user_uid': 'u1',
        'pickup_stop': 'A',
        'destination_stop': 'B',
        'pickup_index': 0,
        'destination_index': 1,
        'status': 'reserved',
        'qr_payload': '{"v":1}',
        'created_at': 123,
      };
      final r = BookingRecord.fromMap(map);
      expect(r, isNotNull);
      expect(r!.bookingId, 'b1');
      expect(r.status, 'reserved');
      expect(r.createdAt, 123);
    });

    test('parses qr payload when provided as Map', () {
      final map = <String, Object?>{
        'booking_id': 'b2',
        'shuttle_key': 's2',
        'user_uid': 'u2',
        'pickup_stop': 'A',
        'destination_stop': 'B',
        'pickup_index': 0,
        'destination_index': 1,
        'status': ' active ',
        'qr_payload': {'v': 1, 'bookingId': 'b2'},
      };
      final r = BookingRecord.fromMap(map);
      expect(r, isNotNull);
      expect(r!.status, 'active');
      expect(r.qrPayload.contains('bookingId'), isTrue);
    });
  });

  group('BookingRecord.isActive', () {
    test('reserved and active are considered active', () {
      final r1 = BookingRecord(
        bookingId: 'x',
        shuttleKey: 's',
        userUid: 'u',
        pickupStop: 'A',
        pickupIndex: 0,
        destinationStop: 'B',
        destinationIndex: 1,
        status: 'reserved',
        qrPayload: '{}',
      );
      final r2 = BookingRecord(
        bookingId: 'y',
        shuttleKey: 's',
        userUid: 'u',
        pickupStop: 'A',
        pickupIndex: 0,
        destinationStop: 'B',
        destinationIndex: 1,
        status: 'Active',
        qrPayload: '{}',
      );
      final r3 = BookingRecord(
        bookingId: 'z',
        shuttleKey: 's',
        userUid: 'u',
        pickupStop: 'A',
        pickupIndex: 0,
        destinationStop: 'B',
        destinationIndex: 1,
        status: 'completed',
        qrPayload: '{}',
      );

      expect(r1.isActive, isTrue);
      expect(r2.isActive, isTrue);
      expect(r3.isActive, isFalse);
    });
  });
}
