import 'dart:convert';

class BookingRecord {
  const BookingRecord({
    required this.bookingId,
    required this.shuttleKey,
    required this.userUid,
    required this.pickupStop,
    required this.pickupIndex,
    required this.destinationStop,
    required this.destinationIndex,
    required this.status,
    required this.qrPayload,
    this.createdAt,
    this.cancelledAt,
    this.cancelReason,
  });

  final String bookingId;
  final String shuttleKey;
  final String userUid;
  final String pickupStop;
  final int pickupIndex;
  final String destinationStop;
  final int destinationIndex;
  final String status;
  final String qrPayload;
  final int? createdAt;
  final int? cancelledAt;
  final String? cancelReason;

  bool get isActive => status == 'reserved';

  static BookingRecord? fromMap(Map<String, Object?> map) {
    final bookingId = (map['booking_id'] as String?)?.trim();
    final shuttleKey = (map['shuttle_key'] as String?)?.trim();
    final userUid = (map['user_uid'] as String?)?.trim();
    final pickupStop = (map['pickup_stop'] as String?)?.trim();
    final destinationStop = (map['destination_stop'] as String?)?.trim();
    final status = ((map['status'] as String?) ?? 'reserved').trim();
    final rawQr = map['qr_payload'];
    String? qrPayload;
    if (rawQr is String) {
      qrPayload = rawQr.trim();
    } else if (rawQr is Map) {
      try {
        qrPayload = jsonEncode(rawQr);
      } catch (_) {
        qrPayload = rawQr.toString();
      }
    } else if (rawQr != null) {
      qrPayload = rawQr.toString();
    }

    final pickupIndex = _readInt(map['pickup_index']);
    final destinationIndex = _readInt(map['destination_index']);

    if (bookingId == null ||
        bookingId.isEmpty ||
        shuttleKey == null ||
        shuttleKey.isEmpty ||
        userUid == null ||
        userUid.isEmpty ||
        pickupStop == null ||
        pickupStop.isEmpty ||
        destinationStop == null ||
        destinationStop.isEmpty ||
        pickupIndex == null ||
        destinationIndex == null ||
        qrPayload == null ||
        qrPayload.isEmpty) {
      return null;
    }

    return BookingRecord(
      bookingId: bookingId,
      shuttleKey: shuttleKey,
      userUid: userUid,
      pickupStop: pickupStop,
      pickupIndex: pickupIndex,
      destinationStop: destinationStop,
      destinationIndex: destinationIndex,
      status: status.isEmpty ? 'reserved' : status,
      qrPayload: qrPayload,
      createdAt: _readInt(map['created_at']),
      cancelledAt: _readInt(map['cancelled_at']),
      cancelReason: (map['cancel_reason'] as String?)?.trim(),
    );
  }

  static int? _readInt(Object? value) {
    if (value is int) return value;
    if (value is double) return value.round();
    if (value is String) return int.tryParse(value);
    return null;
  }
}
