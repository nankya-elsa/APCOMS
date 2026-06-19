import 'package:flutter_test/flutter_test.dart';
import 'package:shuttlego/models/booking_availability.dart';

void main() {
  group('BookingAvailability', () {
    test('freeSeats computes available minus reserved', () {
      final a = BookingAvailability(
        reportedAvailableSeats: 5,
        occupiedSeats: 3,
        reservedSeats: 2,
      );
      expect(a.freeSeats, 3);
      expect(a.capacity, 8);
      expect(a.canBook, isTrue);
    });

    test('freeSeats is zero when reserved exceed available (boundary)', () {
      final a = BookingAvailability(
        reportedAvailableSeats: 2,
        occupiedSeats: 1,
        reservedSeats: 5,
      );
      expect(a.freeSeats, 0);
      expect(a.canBook, isFalse);
    });

    test('handles zero and large values', () {
      final a = BookingAvailability(
        reportedAvailableSeats: 0,
        occupiedSeats: 0,
        reservedSeats: 0,
      );
      expect(a.freeSeats, 0);
      expect(a.capacity, 0);

      final b = BookingAvailability(
        reportedAvailableSeats: 1000000,
        occupiedSeats: 123456,
        reservedSeats: 500000,
      );
      expect(b.freeSeats, 500000);
      expect(b.capacity, 1123456);
    });
  });
}
