import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'dart:io';
import 'package:path_provider/path_provider.dart';
import 'package:path/path.dart' as p;
import 'package:firebase_database/firebase_database.dart';
import 'database_adapter.dart';

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
  BookingService({FirebaseDatabase? database, DatabaseAdapter? adapter})
    : _databaseAdapter =
          adapter ??
          FirebaseDatabaseAdapter(database ?? FirebaseDatabase.instance);

  final DatabaseAdapter _databaseAdapter;

  Stream<BookingAvailability> watchAvailability({
    required String shuttleKey,
    bool persistDerived = false,
  }) {
    final controller = StreamController<BookingAvailability>.broadcast();
    final shuttlePath = 'shuttles/$shuttleKey';
    final bookingsPath = 'bookings';

    Map<String, Object?> shuttleData = const <String, Object?>{};
    var activeReservations = 0;
    var hasShuttleData = false;

    StreamSubscription? shuttleSub;
    StreamSubscription? bookingsSub;

    void emitIfReady() {
      if (!hasShuttleData || controller.isClosed) return;

      final now = DateTime.now().millisecondsSinceEpoch;
      final availability = BookingAvailability(
        reportedAvailableSeats: _readInt(shuttleData['available_seats']),
        occupiedSeats: _readInt(shuttleData['current_count']),
        reservedSeats: activeReservations,
        lastComputedAt: now,
        isStale: false,
      );

      controller.add(availability);

      // Persist a local cached copy so the UI can show stale data if
      // connectivity to the database is lost.
      unawaited(_cacheAvailability(shuttleKey, availability));

      if (persistDerived) {
        try {
          _databaseAdapter
              .update(<String, Object?>{
                '$shuttlePath/derived/reported_available_seats':
                    availability.reportedAvailableSeats,
                '$shuttlePath/derived/occupied_seats':
                    availability.occupiedSeats,
                '$shuttlePath/derived/reserved_seats':
                    availability.reservedSeats,
                '$shuttlePath/derived/free_seats': availability.freeSeats,
                '$shuttlePath/derived/capacity': availability.capacity,
                '$shuttlePath/derived/last_computed_at': ServerValue.timestamp,
              })
              .catchError((error, stack) {
                if (!controller.isClosed) controller.addError(error);
              });
        } catch (e) {
          if (!controller.isClosed) controller.addError(e);
        }
      }
    }

    // Subscribe to real-time updates if adapter supports it (default
    // DatabaseAdapter provides a single-shot stream but Firebase adapter
    // overrides to return onValue streams).
    try {
      shuttleSub = _databaseAdapter
          .onValue(shuttlePath)
          .listen(
            (raw) {
              shuttleData = raw is Map
                  ? Map<String, Object?>.from(raw as Map)
                  : const <String, Object?>{};
              hasShuttleData = true;
              emitIfReady();
            },
            onError: (_) async {
              // On error, try to load cached availability
              final cached = await _loadCachedAvailability(shuttleKey);
              if (cached != null && !controller.isClosed)
                controller.add(cached);
            },
          );

      bookingsSub = _databaseAdapter
          .queryOnValue(
            bookingsPath,
            orderByChild: 'shuttle_key',
            equalTo: shuttleKey,
          )
          .listen(
            (val) {
              activeReservations = _countActiveReservations(val);
              emitIfReady();
            },
            onError: (_) {
              activeReservations = 0;
              // emit whatever shuttle data we have (cached or fresh)
              _loadCachedAvailability(shuttleKey)
                  .then((cached) {
                    if (cached != null && !controller.isClosed)
                      controller.add(cached);
                    else
                      emitIfReady();
                  })
                  .catchError((_) => emitIfReady());
            },
          );
    } catch (e) {
      // Fallback to single-shot reads if streaming is not available.
      _databaseAdapter
          .get(shuttlePath)
          .then((raw) {
            shuttleData = raw is Map
                ? Map<String, Object?>.from(raw as Map)
                : const <String, Object?>{};
            hasShuttleData = true;
            _databaseAdapter
                .queryGet(
                  bookingsPath,
                  orderByChild: 'shuttle_key',
                  equalTo: shuttleKey,
                )
                .then((val) {
                  activeReservations = _countActiveReservations(val);
                  emitIfReady();
                })
                .catchError((_) {
                  activeReservations = 0;
                  _loadCachedAvailability(shuttleKey)
                      .then((cached) {
                        if (cached != null && !controller.isClosed) {
                          controller.add(cached);
                        } else {
                          emitIfReady();
                        }
                      })
                      .catchError((_) => emitIfReady());
                });
          })
          .catchError((Object error, StackTrace stack) {
            if (!controller.isClosed) {
              _loadCachedAvailability(shuttleKey)
                  .then((cached) {
                    if (cached != null && !controller.isClosed) {
                      controller.add(cached);
                    }
                  })
                  .catchError((_) {});
            }
          });
    }

    controller.onCancel = () async {
      await shuttleSub?.cancel();
      await bookingsSub?.cancel();
      await controller.close();
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

    final data = await _databaseAdapter.get('bookings/$bookingId');
    if (data is! Map) throw BookingException('Booking not found');
    final db = Map<String, Object?>.from(data);

    final storedToken = db['qr_token'] as String?;
    var status = ((db['status'] as String?) ?? '').trim().toLowerCase();
    if (storedToken == null || storedToken != token) {
      throw BookingException('Invalid QR token');
    }

    final userUid = db['user_uid'] as String?;

    // If the booking is still reserved, the first scan marks it active
    // (journey started). If it's already active, a subsequent scan marks
    // it completed (journey finished). This makes the operation
    // idempotent and supports both start/finish flows.
    if (status == 'reserved') {
      status = 'active';
      await _databaseAdapter.update(<String, Object?>{
        'bookings/$bookingId/status': 'active',
        'bookings/$bookingId/started_at': ServerValue.timestamp,
        if (userUid != null)
          'user_bookings/$userUid/$bookingId/status': 'active',
        if (userUid != null)
          'user_bookings/$userUid/$bookingId/started_at': ServerValue.timestamp,
      });
      // Update derived availability for this shuttle so reservation changes
      // are recorded.
      try {
        final shuttleKey = db['shuttle_key'] as String?;
        if (shuttleKey != null && shuttleKey.trim().isNotEmpty) {
          _writeDerivedAvailability(shuttleKey);
        }
      } catch (_) {}
      return;
    }

    if (status == 'active') {
      // Complete the booking
      await _databaseAdapter.update(<String, Object?>{
        'bookings/$bookingId/status': 'completed',
        'bookings/$bookingId/completed_at': ServerValue.timestamp,
        if (userUid != null)
          'user_bookings/$userUid/$bookingId/status': 'completed',
        if (userUid != null)
          'user_bookings/$userUid/$bookingId/completed_at':
              ServerValue.timestamp,
      });
      try {
        final shuttleKey = db['shuttle_key'] as String?;
        if (shuttleKey != null && shuttleKey.trim().isNotEmpty) {
          _writeDerivedAvailability(shuttleKey);
        }
      } catch (_) {}
      return;
    }

    // Any other status is not valid for a scan operation.
    throw BookingException('Booking not active');
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
    final controller = StreamController<List<BookingRecord>>.broadcast();
    StreamSubscription? sub;

    void processRaw(Object? raw) {
      // Defensive handling: sometimes snapshots can be List or Map depending
      // on how data was written. Normalize to a Map<String, Object?>.
      Map<String, Object?> rawMap;
      if (raw is Map) {
        rawMap = Map<String, Object?>.from(raw as Map);
      } else if (raw is List) {
        rawMap = <String, Object?>{};
        for (var i = 0; i < (raw as List).length; i++) {
          final v = raw[i];
          if (v != null) rawMap[i.toString()] = v;
        }
      } else {
        if (!controller.isClosed) controller.add(const <BookingRecord>[]);
        return;
      }

      final bookings = <BookingRecord>[];
      for (final entry in rawMap.entries) {
        final value = entry.value;
        if (value is! Map) continue;
        final map = Map<String, Object?>.from(value);
        map.putIfAbsent('booking_id', () => entry.key.toString());
        final booking = BookingRecord.fromMap(map);
        if (booking != null) bookings.add(booking);
      }

      bookings.sort((a, b) => (b.createdAt ?? 0).compareTo(a.createdAt ?? 0));
      if (!controller.isClosed) controller.add(bookings);
    }

    try {
      sub = _databaseAdapter.onValue('user_bookings/$userUid').listen((raw) {
        processRaw(raw);
      }, onError: (e) => controller.addError(e));
    } catch (e) {
      // Fallback to single-shot read
      _databaseAdapter
          .get('user_bookings/$userUid')
          .then((raw) {
            processRaw(raw);
          })
          .catchError((e) => controller.addError(e));
    }

    controller.onCancel = () async {
      await sub?.cancel();
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

    final bookingKey = await _databaseAdapter.pushKey('bookings');
    if (bookingKey == null || bookingKey.trim().isEmpty) {
      throw BookingException('Failed to allocate a booking id.');
    }

    final shuttleRaw = await _databaseAdapter.get('shuttles/$shuttleKey');
    final shuttleData = shuttleRaw is Map
        ? Map<String, Object?>.from(shuttleRaw as Map)
        : const <String, Object?>{};
    // Enforce service hours if configured on the shuttle. If start/end are
    // missing or unparsable, allow booking (don't block).
    try {
      _ensureWithinServiceHours(shuttleData);
    } catch (e) {
      throw BookingException(e.toString());
    }
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

    await _databaseAdapter.update(<String, Object?>{
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
    String reason = 'Cancelled by user',
  }) async {
    // Only bookings that are still 'reserved' can be cancelled by users.
    final status = booking.status.trim().toLowerCase();
    if (status != 'reserved') {
      throw BookingException('Only reserved bookings can be cancelled.');
    }

    // Empty/whitespace reasons collapse to the default so the shuttle
    // listener never mistakes a user cancellation for a no-show.
    final effectiveReason = reason.trim().isEmpty
        ? 'Cancelled by user'
        : reason.trim();

    final updates = <String, Object?>{
      'user_bookings/${booking.userUid}/${booking.bookingId}/status':
          'cancelled',
      'user_bookings/${booking.userUid}/${booking.bookingId}/cancel_reason':
          effectiveReason,
      'user_bookings/${booking.userUid}/${booking.bookingId}/cancelled_at':
          ServerValue.timestamp,
    };

    try {
      final snap = await _databaseAdapter.get('bookings/${booking.bookingId}');
      if (snap == null) {
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
          'cancel_reason': effectiveReason,
          'cancelled_at': ServerValue.timestamp,
          'created_at': booking.createdAt ?? ServerValue.timestamp,
        };
        updates['bookings/${booking.bookingId}'] = minimal;
      } else {
        updates['bookings/${booking.bookingId}/status'] = 'cancelled';
        updates['bookings/${booking.bookingId}/cancel_reason'] =
            effectiveReason;
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
        'cancel_reason': effectiveReason,
        'cancelled_at': ServerValue.timestamp,
        'created_at': booking.createdAt ?? ServerValue.timestamp,
      };
    }

    await _databaseAdapter.update(updates);
    // After cancelling, update derived availability for the shuttle.
    try {
      final shuttleKey = booking.shuttleKey;
      if (shuttleKey.trim().isNotEmpty) {
        _writeDerivedAvailability(shuttleKey);
      }
    } catch (_) {}
  }

  /// Permanently delete a past booking from both the global `bookings`
  /// collection and the user's `user_bookings` entry.
  Future<void> deleteBooking({required BookingRecord booking}) async {
    if (booking.isActive) {
      throw BookingException('Only past bookings can be deleted.');
    }

    await _databaseAdapter.update(<String, Object?>{
      'bookings/${booking.bookingId}': null,
      'user_bookings/${booking.userUid}/${booking.bookingId}': null,
    });
  }

  Future<int> _fetchActiveReservationCount(String shuttleKey) async {
    final val = await _databaseAdapter.queryGet(
      'bookings',
      orderByChild: 'shuttle_key',
      equalTo: shuttleKey,
    );
    return _countActiveReservations(val);
  }

  // Parse a time string like "06:00" into minutes since midnight.
  static int? _parseTimeToMinutes(Object? value) {
    if (value == null) return null;
    final s = value is String ? value.trim() : value.toString();
    final match = RegExp(r'^(\d{1,2}):(\d{2})').firstMatch(s);
    if (match == null) return null;
    final h = int.tryParse(match.group(1) ?? '');
    final m = int.tryParse(match.group(2) ?? '');
    if (h == null || m == null) return null;
    if (h < 0 || h > 23 || m < 0 || m > 59) return null;
    return h * 60 + m;
  }

  void _ensureWithinServiceHours(Map<String, Object?> shuttleData) {
    final startMins = _parseTimeToMinutes(shuttleData['service_start_time']);
    final endMins = _parseTimeToMinutes(shuttleData['service_end_time']);
    if (startMins == null || endMins == null) return; // no restriction

    final now = DateTime.now();
    final nowMins = now.hour * 60 + now.minute;

    final within = startMins <= endMins
        ? (nowMins >= startMins && nowMins <= endMins)
        : (nowMins >= startMins || nowMins <= endMins); // overnight range

    if (!within) {
      final custom = shuttleData['service_block_message'];
      final startStr = shuttleData['service_start_time']?.toString() ?? '';
      final endStr = shuttleData['service_end_time']?.toString() ?? '';
      final defaultMsg = startStr.isNotEmpty && endStr.isNotEmpty
          ? 'Shuttle not available at this time. The shuttle will operate from $startStr to $endStr today.'
          : 'Shuttle not available at this time.';
      final msg = (custom is String && custom.trim().isNotEmpty)
          ? custom.trim()
          : defaultMsg;
      throw BookingException(msg);
    }
  }

  /// Compute derived availability and persist it in a dedicated top-level
  /// path so other services can query it easily. This is triggered after
  /// booking create/cancel/complete operations which change reserved seats.
  Future<void> _writeDerivedAvailability(String shuttleKey) async {
    try {
      final raw = await _databaseAdapter.get('shuttles/$shuttleKey');
      final shuttleData = raw is Map
          ? Map<String, Object?>.from(raw as Map)
          : <String, Object?>{};

      final reportedAvailableSeats = _readInt(shuttleData['available_seats']);
      final occupiedSeats = _readInt(shuttleData['current_count']);
      final reservedSeats = await _fetchActiveReservationCount(shuttleKey);

      final availability = BookingAvailability(
        reportedAvailableSeats: reportedAvailableSeats,
        occupiedSeats: occupiedSeats,
        reservedSeats: reservedSeats,
      );

      await _databaseAdapter.update(<String, Object?>{
        'derived_availability/$shuttleKey/reported_available_seats':
            availability.reportedAvailableSeats,
        'derived_availability/$shuttleKey/occupied_seats':
            availability.occupiedSeats,
        'derived_availability/$shuttleKey/reserved_seats':
            availability.reservedSeats,
        'derived_availability/$shuttleKey/free_seats': availability.freeSeats,
        'derived_availability/$shuttleKey/capacity': availability.capacity,
        'derived_availability/$shuttleKey/last_computed_at':
            ServerValue.timestamp,
      });
    } catch (_) {
      // Best-effort; don't let persistence failures block the booking flow.
    }
  }

  Future<bool> _hasActiveUserBooking(String userUid) async {
    try {
      final raw = await _databaseAdapter.get('user_bookings/$userUid');
      if (raw == null) return false;

      if (raw is Map) {
        for (final v in raw.values) {
          if (v is! Map) continue;
          final map = Map<String, Object?>.from(v);
          final status = ((map['status'] as String?) ?? '')
              .trim()
              .toLowerCase();
          if (status == 'reserved' || status == 'active') return true;
        }
        return false;
      }

      if (raw is List) {
        for (final v in raw) {
          if (v is! Map) continue;
          final status = ((v['status'] as String?) ?? '').trim().toLowerCase();
          if (status == 'reserved' || status == 'active') return true;
        }
        return false;
      }
    } catch (_) {
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

  Future<void> _cacheAvailability(
    String shuttleKey,
    BookingAvailability availability,
  ) async {
    try {
      final dir = await getApplicationDocumentsDirectory();
      final file = File(p.join(dir.path, 'availability_$shuttleKey.json'));
      final map = <String, Object?>{
        'reportedAvailableSeats': availability.reportedAvailableSeats,
        'occupiedSeats': availability.occupiedSeats,
        'reservedSeats': availability.reservedSeats,
        'lastComputedAt': availability.lastComputedAt,
      };
      await file.writeAsString(jsonEncode(map));
    } catch (_) {
      // Best-effort caching; ignore failures.
    }
  }

  Future<BookingAvailability?> _loadCachedAvailability(
    String shuttleKey,
  ) async {
    try {
      final dir = await getApplicationDocumentsDirectory();
      final file = File(p.join(dir.path, 'availability_$shuttleKey.json'));
      if (!await file.exists()) return null;
      final txt = await file.readAsString();
      final raw = jsonDecode(txt) as Map<String, dynamic>;
      final reported = (raw['reportedAvailableSeats'] as num?)?.toInt() ?? 0;
      final occupied = (raw['occupiedSeats'] as num?)?.toInt() ?? 0;
      final reserved = (raw['reservedSeats'] as num?)?.toInt() ?? 0;
      final last = (raw['lastComputedAt'] as num?)?.toInt();
      return BookingAvailability(
        reportedAvailableSeats: reported,
        occupiedSeats: occupied,
        reservedSeats: reserved,
        lastComputedAt: last,
        isStale: true,
      );
    } catch (_) {
      return null;
    }
  }
}
