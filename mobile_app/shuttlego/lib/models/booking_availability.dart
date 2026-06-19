class BookingAvailability {
  const BookingAvailability({
    required this.reportedAvailableSeats,
    required this.occupiedSeats,
    required this.reservedSeats,
    this.lastComputedAt,
    this.isStale = false,
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
  /// A reservation does not mean the seat is occupied yet, so we subtract
  /// active reservations from the camera-reported unoccupied seats.
  int get freeSeats {
    final seats = reportedAvailableSeats - reservedSeats;
    return seats < 0 ? 0 : seats;
  }

  int get capacity => reportedAvailableSeats + occupiedSeats;

  bool get canBook => freeSeats > 0;

  /// Milliseconds-since-epoch when this availability was computed locally.
  /// When data is loaded from cache, this can be used to indicate staleness.
  final int? lastComputedAt;

  /// When true the availability was loaded from cache (connection lost)
  /// and should be displayed as not recent.
  final bool isStale;
}
