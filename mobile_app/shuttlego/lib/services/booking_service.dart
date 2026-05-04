import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:firebase_database/firebase_database.dart';

import '../models/booking_availability.dart';
import '../models/booking_record.dart';
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
    final controller = StreamController<BookingAvailability>();
    final shuttleRef = _database.ref().child('shuttles').child(shuttleKey);
    final bookingsRef = _database.ref().child('bookings');

    Map<String, Object?> shuttleData = const <String, Object?>{};
    var activeReservations = 0;
    var hasShuttleData = false;

    void emitIfReady() {
      if (!hasShuttleData || controller.isClosed) return;

      controller.add(
        BookingAvailability(
          reportedAvailableSeats: _readInt(shuttleData['available_seats']),
          occupiedSeats: _readInt(shuttleData['current_count']),
          reservedSeats: activeReservations,
        ),
      );
    }

    final shuttleSub = shuttleRef.onValue.listen((event) {
      final raw = event.snapshot.value;
      shuttleData = raw is Map
          ? Map<String, Object?>.from(raw)
          : const <String, Object?>{};
      hasShuttleData = true;
      emitIfReady();
    }, onError: controller.addError);

    final bookingsSub = bookingsRef
        .orderByChild('shuttle_key')
        .equalTo(shuttleKey)
        .onValue
        .listen(
          (event) {
            activeReservations = _countActiveReservations(event.snapshot.value);
            emitIfReady();
          },
          onError: (Object error, StackTrace stackTrace) {
            // Keep shuttle availability visible even if booking reads are
            // temporarily blocked. Creating/cancelling still reports its own
            // database errors when the user acts.
            activeReservations = 0;
            emitIfReady();
          },
        );

    controller.onCancel = () async {
      await shuttleSub.cancel();
      await bookingsSub.cancel();
    };

    return controller.stream;
  }

  static int _countActiveReservations(Object? raw) {
    if (raw is! Map) return 0;

    var count = 0;
    for (final value in raw.values) {
      if (value is! Map) continue;
      final map = Map<String, Object?>.from(value);
      final status = ((map['status'] as String?) ?? '').trim().toLowerCase();
      if (status == 'reserved') count++;
    }

    return count;
  }

  Stream<List<BookingRecord>> watchUserBookings({required String userUid}) {
    final ref = _database.ref().child('user_bookings').child(userUid);

    // Make the controller broadcast-capable so multiple listeners (debug
    // subscribers + UI) won't compete for a single-subscription stream.
    final controller = StreamController<List<BookingRecord>>.broadcast();
    String? lastSnapshotStr;

    final sub = ref.onValue.listen((event) {
      final raw = event.snapshot.value;
      final snapshotStr = raw?.toString() ?? 'null';
      // De-duplicate identical consecutive snapshots to avoid rapid rebuilds
      if (snapshotStr == lastSnapshotStr) return;
      lastSnapshotStr = snapshotStr;

      // Defensive handling: sometimes snapshots can be List or Map depending
      // on how data was written. Normalize to a Map<String, Object?>.
      Map<String, Object?> rawMap;
      if (raw is Map) {
        rawMap = Map<String, Object?>.from(raw);
      } else if (raw is List) {
        rawMap = <String, Object?>{};
        for (var i = 0; i < raw.length; i++) {
          final v = raw[i];
          if (v != null) rawMap[i.toString()] = v;
        }
      } else {
        controller.add(const <BookingRecord>[]);
        return;
      }

      final bookings = <BookingRecord>[];
      var parseNullCount = 0;
      for (final entry in rawMap.entries) {
        final value = entry.value;
        if (value is! Map) continue;

        final map = Map<String, Object?>.from(value);
        map.putIfAbsent('booking_id', () => entry.key.toString());
        final booking = BookingRecord.fromMap(map);
        if (booking != null) {
          bookings.add(booking);
        } else {
          parseNullCount++;
        }
      }

      bookings.sort((a, b) => (b.createdAt ?? 0).compareTo(a.createdAt ?? 0));
      controller.add(bookings);
    }, onError: controller.addError);

    controller.onCancel = () async {
      await sub.cancel();
      await controller.close();
    };

    return controller.stream;
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

    final shuttleSnapshot = await shuttleRef.get();
    final shuttleRaw = shuttleSnapshot.value;
    final shuttleData = shuttleRaw is Map
        ? Map<String, Object?>.from(shuttleRaw)
        : const <String, Object?>{};
    final cameraAvailableSeats = _readInt(shuttleData['available_seats']);
    final reservedSeats = await _fetchActiveReservationCount(shuttleKey);
    final bookableSeats = cameraAvailableSeats - reservedSeats;
    if (bookableSeats <= 0) {
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

    final bookingData = <String, Object?>{
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
    };

    await _database.ref().update(<String, Object?>{
      'bookings/$bookingKey': bookingData,
      'user_bookings/$userUid/$bookingKey': bookingData,
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

  Future<void> cancelBooking({
    required BookingRecord booking,
    required String reason,
  }) async {
    if (!booking.isActive) {
      throw BookingException('Only active reservations can be cancelled.');
    }

    await _database.ref().update(<String, Object?>{
      'bookings/${booking.bookingId}/status': 'cancelled',
      'bookings/${booking.bookingId}/cancel_reason': reason.trim(),
      'bookings/${booking.bookingId}/cancelled_at': ServerValue.timestamp,
      'user_bookings/${booking.userUid}/${booking.bookingId}/status':
          'cancelled',
      'user_bookings/${booking.userUid}/${booking.bookingId}/cancel_reason':
          reason.trim(),
      'user_bookings/${booking.userUid}/${booking.bookingId}/cancelled_at':
          ServerValue.timestamp,
    });
  }

  Future<int> _fetchActiveReservationCount(String shuttleKey) async {
    final snapshot = await _database
        .ref()
        .child('bookings')
        .orderByChild('shuttle_key')
        .equalTo(shuttleKey)
        .get();

    return _countActiveReservations(snapshot.value);
  }

  static int _readInt(Object? value) {
    if (value is int) return value;
    if (value is double) return value.round();
    if (value is String) return int.tryParse(value) ?? 0;
    return 0;
  }
}
