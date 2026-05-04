class ShuttleLocation {
  const ShuttleLocation({
    required this.lat,
    required this.lng,
    this.heading,
    this.speed,
    this.currentStop,
    this.nextStop,
    this.updatedAtMillis,
  });

  final double lat;
  final double lng;
  final double? heading;
  final double? speed;
  final String? currentStop;
  final String? nextStop;
  final int? updatedAtMillis;

  static ShuttleLocation? fromMap(Map<String, Object?> map) {
    final lat = _readDouble(map['lat'] ?? map['latitude']);
    final lng = _readDouble(map['lng'] ?? map['lon'] ?? map['longitude']);
    if (lat == null || lng == null) return null;

    return ShuttleLocation(
      lat: lat,
      lng: lng,
      heading: _readDouble(map['heading'] ?? map['bearing']),
      speed: _readDouble(map['speed']),
      currentStop: (map['current_stop'] as String?)?.trim(),
      nextStop: (map['next_stop'] as String?)?.trim(),
      updatedAtMillis: _readInt(map['updated_at'] ?? map['updatedAt']),
    );
  }

  static double? _readDouble(Object? value) {
    if (value is double) return value;
    if (value is int) return value.toDouble();
    if (value is String) return double.tryParse(value);
    return null;
  }

  static int? _readInt(Object? value) {
    if (value is int) return value;
    if (value is double) return value.round();
    if (value is String) return int.tryParse(value);
    return null;
  }
}
