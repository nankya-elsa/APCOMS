class BookingAvailability {
  const BookingAvailability({
    required this.reportedAvailableSeats,
    required this.occupiedSeats,
    required this.reservedSeats,
  });

  /// Physical seats reported as unoccupied by the shuttle/ML simulation.
  ///
  /// Backed by Realtime Database: `shuttles/{shuttleKey}/available_seats`.
  final int reportedAvailableSeats;

  /// Seats currently occupied by people physically on the shuttle.
  ///
  /// Backed by Realtime Database: `shuttles/{shuttleKey}/current_count`.
  final int occupiedSeats;

  /// Seats held by active user reservations.
  ///
  /// Computed from active records in `bookings`.
  final int reservedSeats;

  /// Seats users can still reserve.
  ///
  /// In the soft-hold model, reportedAvailableSeats is maintained
  /// by the shuttle's SeatPoolManager on every book/cancel/no-show/
  /// alight event, so it already equals what's free to book. No
  /// further subtraction needed.
  int get freeSeats =>
      reportedAvailableSeats < 0 ? 0 : reportedAvailableSeats;

  int get capacity =>
      reportedAvailableSeats + reservedSeats + occupiedSeats;

  bool get canBook => freeSeats > 0;
}
