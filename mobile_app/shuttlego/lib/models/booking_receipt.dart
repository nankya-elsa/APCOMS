class BookingReceipt {
  const BookingReceipt({
    required this.bookingId,
    required this.shuttleKey,
    required this.userUid,
    required this.pickupStop,
    required this.pickupIndex,
    required this.destinationStop,
    required this.destinationIndex,
    required this.createdAt,
    required this.qrPayload,
  });

  final String bookingId;
  final String shuttleKey;
  final String userUid;

  final String pickupStop;
  final int pickupIndex;

  final String destinationStop;
  final int destinationIndex;

  /// Unix epoch millis if known (may be null if using ServerValue.timestamp).
  final int? createdAt;

  /// The exact string encoded into the QR code.
  final String qrPayload;
}
