class BookingAvailability {
  const BookingAvailability({
    required this.freeSeats,
    required this.occupiedSeats,
  });

  /// Seats that are currently free.
  ///
  /// Backed by Realtime Database: `shuttles/{shuttleKey}/available_seats`.
  final int freeSeats;

  /// Seats that are currently occupied.
  ///
  /// Backed by Realtime Database: `shuttles/{shuttleKey}/current_count`.
  final int occupiedSeats;

  int get totalSeats => freeSeats + occupiedSeats;

  bool get canBook => freeSeats > 0;
}
