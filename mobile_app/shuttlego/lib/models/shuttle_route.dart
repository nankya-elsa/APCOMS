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

  static bool isValidTripSegment({
    required int pickupIndex,
    required int destinationIndex,
  }) {
    if (!isValidStopIndex(pickupIndex) || !isValidStopIndex(destinationIndex)) {
      return false;
    }
    return destinationIndex > pickupIndex;
  }

  static List<String> destinationChoicesForPickup(int pickupIndex) {
    if (!isValidStopIndex(pickupIndex)) return const <String>[];
    if (pickupIndex + 1 >= stops.length) return const <String>[];
    return stops.sublist(pickupIndex + 1);
  }
}
