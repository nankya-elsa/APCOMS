import 'dart:async';
import 'dart:convert';
import 'dart:math';

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

  /// Generate a short random token to embed in the QR and store with the
  /// booking. This helps prevent trivial guessing of booking IDs.
  static String _generateQrToken([int length = 16]) {
    const chars =
        'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    final rnd = Random.secure();
    final buffer = StringBuffer();
    for (var i = 0; i < length; i++) {
      buffer.write(chars[rnd.nextInt(chars.length)]);
    }
    return buffer.toString();
  }

  /// Validate a scanned QR payload and, if valid, mark the booking as
  /// completed. Expects the payload produced in [createBooking].
  Future<void> completeBookingFromQr({required String qrPayload}) async {
    Object? raw;
    try {
      raw = jsonDecode(qrPayload);
    } catch (e) {
      throw BookingException('Invalid QR payload');
    }

    if (raw is! Map) throw BookingException('Invalid QR payload');
    final map = Map<String, Object?>.from(raw);
    final version = map['v'] is int
        ? (map['v'] as int)
        : int.tryParse('${map['v']}');
    if (version == null || version != 1) {
      throw BookingException('Unsupported QR version');
    }

    final bookingId = map['bookingId'] as String?;
    final token = map['t'] as String?;
    if (bookingId == null || token == null) {
      throw BookingException('Missing booking data in QR');
    }

    final snap = await _database.ref().child('bookings').child(bookingId).get();
    final data = snap.value;
    if (data is! Map) throw BookingException('Booking not found');
    final db = Map<String, Object?>.from(data);

    final storedToken = db['qr_token'] as String?;
    final status = ((db['status'] as String?) ?? '').trim().toLowerCase();
    if (status != 'reserved') throw BookingException('Booking not active');
    if (storedToken == null || storedToken != token) {
      throw BookingException('Invalid QR token');
    }

    final userUid = db['user_uid'] as String?;
    await _database.ref().update(<String, Object?>{
      'bookings/$bookingId/status': 'completed',
      'bookings/$bookingId/completed_at': ServerValue.timestamp,
      if (userUid != null)
        'user_bookings/$userUid/$bookingId/status': 'completed',
      if (userUid != null)
        'user_bookings/$userUid/$bookingId/completed_at': ServerValue.timestamp,
    });
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
    // Prevent users from creating a second active reservation while one
    // already exists for them.
    final hasActiveUserBooking = await _hasActiveUserBooking(userUid);
    if (hasActiveUserBooking) {
      throw BookingException(
        'You already have an active booking. Cancel or complete it before creating another.',
      );
    }

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

    final qrToken = _generateQrToken();

    final qrPayload = jsonEncode({
      'v': 1,
      'bookingId': bookingKey,
      't': qrToken,
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
      'qr_token': qrToken,
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

    final updates = <String, Object?>{
      'user_bookings/${booking.userUid}/${booking.bookingId}/status':
          'cancelled',
      'user_bookings/${booking.userUid}/${booking.bookingId}/cancel_reason':
          reason.trim(),
      'user_bookings/${booking.userUid}/${booking.bookingId}/cancelled_at':
          ServerValue.timestamp,
    };

    final bookingRef = _database.ref().child('bookings').child(booking.bookingId);
    try {
      final snap = await bookingRef.get();
      if (snap.value == null) {
        // Global booking entry missing — create a minimal cancelled record so
        // the system remains consistent and the user can re-book.
        final minimal = <String, Object?>{
          'booking_id': booking.bookingId,
          'user_uid': booking.userUid,
          'shuttle_key': booking.shuttleKey,
          'pickup_stop': booking.pickupStop,
          'pickup_index': booking.pickupIndex,
          'destination_stop': booking.destinationStop,
          'destination_index': booking.destinationIndex,
          'status': 'cancelled',
          'cancel_reason': reason.trim(),
          'cancelled_at': ServerValue.timestamp,
          'created_at': booking.createdAt ?? ServerValue.timestamp,
        };
        updates['bookings/${booking.bookingId}'] = minimal;
      } else {
        updates['bookings/${booking.bookingId}/status'] = 'cancelled';
        updates['bookings/${booking.bookingId}/cancel_reason'] = reason.trim();
        updates['bookings/${booking.bookingId}/cancelled_at'] =
            ServerValue.timestamp;
      }
    } catch (_) {
      // If reading the global booking fails for any reason, still ensure the
      // user's copy is updated so they can make new bookings; create a minimal
      // global entry as a best-effort.
      updates['bookings/${booking.bookingId}'] = <String, Object?>{
        'booking_id': booking.bookingId,
        'user_uid': booking.userUid,
        'shuttle_key': booking.shuttleKey,
        'pickup_stop': booking.pickupStop,
        'pickup_index': booking.pickupIndex,
        'destination_stop': booking.destinationStop,
        'destination_index': booking.destinationIndex,
        'status': 'cancelled',
        'cancel_reason': reason.trim(),
        'cancelled_at': ServerValue.timestamp,
        'created_at': booking.createdAt ?? ServerValue.timestamp,
      };
    }

    await _database.ref().update(updates);
  }

  /// Permanently delete a past booking from both the global `bookings`
  /// collection and the user's `user_bookings` entry.
  Future<void> deleteBooking({required BookingRecord booking}) async {
    if (booking.isActive) {
      throw BookingException('Only past bookings can be deleted.');
    }

    await _database.ref().update(<String, Object?>{
      'bookings/${booking.bookingId}': null,
      'user_bookings/${booking.userUid}/${booking.bookingId}': null,
    });
  }

  /// Recover missing `bookings/$bookingId` entries by copying data from
  /// `user_bookings`. If `userUid` is provided only that user's bookings are
  /// processed; otherwise all users are scanned. Returns the number of
  /// booking entries created or updated.
  

  Future<int> _fetchActiveReservationCount(String shuttleKey) async {
    final snapshot = await _database
        .ref()
        .child('bookings')
        .orderByChild('shuttle_key')
        .equalTo(shuttleKey)
        .get();

    return _countActiveReservations(snapshot.value);
  }

  Future<bool> _hasActiveUserBooking(String userUid) async {
    // Query the user's bookings for any entry with status == 'reserved'.
    try {
      final snapshot = await _database
          .ref()
          .child('user_bookings')
          .child(userUid)
          .orderByChild('status')
          .equalTo('reserved')
          .get();

      final val = snapshot.value;
      if (val == null) return false;
      if (val is Map) return _countActiveReservations(val) > 0;
      if (val is List) {
        for (final v in val) {
          if (v is Map) {
            final status = ((v['status'] as String?) ?? '')
                .trim()
                .toLowerCase();
            if (status == 'reserved') return true;
          }
        }
      }
    } catch (_) {
      // On error, be conservative and assume no active booking so callers
      // can surface a clearer error from the DB update if necessary.
      return false;
    }

    return false;
  }

  static int _readInt(Object? value) {
    if (value is int) return value;
    if (value is double) return value.round();
    if (value is String) return int.tryParse(value) ?? 0;
    return 0;
  }
}
