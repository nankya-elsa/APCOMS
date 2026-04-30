import 'dart:convert';

import 'package:firebase_database/firebase_database.dart';

import '../models/booking_availability.dart';
import '../models/booking_receipt.dart';

class BookingException implements Exception {
  BookingException(this.message);

  final String message;

  @override
  String toString() => message;
}

class BookingService {
  BookingService({FirebaseDatabase? database})
    : _database = database ?? FirebaseDatabase.instance;

  final FirebaseDatabase _database;

  Stream<BookingAvailability> watchAvailability({required String shuttleKey}) {
    final ref = _database.ref().child('shuttles').child(shuttleKey);

    return ref.onValue.map((event) {
      final raw = event.snapshot.value;
      final data = raw is Map ? Map<String, Object?>.from(raw) : const {};

      final freeSeats = _readInt(data['available_seats']);
      final occupiedSeats = _readInt(data['current_count']);

      return BookingAvailability(
        freeSeats: freeSeats,
        occupiedSeats: occupiedSeats,
      );
    });
  }

  Future<BookingReceipt> createBooking({
    required String shuttleKey,
    required String userUid,
    required String pickupStop,
    required int pickupIndex,
    required String destinationStop,
    required int destinationIndex,
  }) async {
    final shuttleRef = _database.ref().child('shuttles').child(shuttleKey);
    final bookingsRef = _database.ref().child('bookings');
    final bookingKey = bookingsRef.push().key;
    if (bookingKey == null || bookingKey.trim().isEmpty) {
      throw BookingException('Failed to allocate a booking id.');
    }

    // Clients are not allowed to update seat counts.
    // We only do a best-effort check here; the authoritative seat count should
    // be updated by a trusted system (driver/admin/backend simulation).
    final shuttleSnapshot = await shuttleRef.get();
    final shuttleRaw = shuttleSnapshot.value;
    final shuttleData = shuttleRaw is Map
        ? Map<String, Object?>.from(shuttleRaw)
        : const <String, Object?>{};
    final freeSeats = _readInt(shuttleData['available_seats']);
    if (freeSeats <= 0) {
      throw BookingException('No free seats available for this shuttle.');
    }

    final qrPayload = jsonEncode({
      'v': 1,
      'bookingId': bookingKey,
      'shuttleKey': shuttleKey,
      'userUid': userUid,
      'pickupIndex': pickupIndex,
      'destinationIndex': destinationIndex,
    });

    await bookingsRef.child(bookingKey).set(<String, Object?>{
      'booking_id': bookingKey,
      'shuttle_key': shuttleKey,
      'user_uid': userUid,
      'pickup_stop': pickupStop,
      'pickup_index': pickupIndex,
      'destination_stop': destinationStop,
      'destination_index': destinationIndex,
      'status': 'reserved',
      'qr_payload': qrPayload,
      'created_at': ServerValue.timestamp,
    });

    return BookingReceipt(
      bookingId: bookingKey,
      shuttleKey: shuttleKey,
      userUid: userUid,
      pickupStop: pickupStop,
      pickupIndex: pickupIndex,
      destinationStop: destinationStop,
      destinationIndex: destinationIndex,
      createdAt: null,
      qrPayload: qrPayload,
    );
  }

  static int _readInt(Object? value) {
    if (value is int) return value;
    if (value is double) return value.round();
    if (value is String) return int.tryParse(value) ?? 0;
    return 0;
  }
}
