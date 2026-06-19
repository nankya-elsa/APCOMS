class ShuttleRoute {
  const ShuttleRoute._();

  static const List<String> stops = <String>[
    'Western Gate',
    'CEDAT',
    'CONAS',
    'Main Library',
    'Africa Hall',
    'Swimming Pool',
    'Mitchel Hall',
    'COCIS',
    'Complex Hall',
    'CEES',
    'Lumumba Hall',
  ];

  static bool isValidStopIndex(int index) => index >= 0 && index < stops.length;

  // Whether this route is circular (the bus repeats the same sequence).
  // When true, destinations may be any stop except the pickup (wrap-around
  // trips are allowed). Set to `false` for linear routes that only allow
  // destinations after the pickup stop.
  static const bool isCircular = true;

  static bool isValidTripSegment({
    required int pickupIndex,
    required int destinationIndex,
  }) {
    if (!isValidStopIndex(pickupIndex) || !isValidStopIndex(destinationIndex)) {
      return false;
    }
    if (isCircular) {
      return pickupIndex != destinationIndex;
    }
    return destinationIndex > pickupIndex;
  }

  static List<String> destinationChoicesForPickup(int pickupIndex) {
    if (!isValidStopIndex(pickupIndex)) return const <String>[];
    if (isCircular) {
      // All other stops are valid destinations for circular routes.
      final list = <String>[];
      for (var i = 0; i < stops.length; i++) {
        if (i == pickupIndex) continue;
        list.add(stops[i]);
      }
      return list;
    }
    if (pickupIndex + 1 >= stops.length) return const <String>[];
    return stops.sublist(pickupIndex + 1);
  }
}
