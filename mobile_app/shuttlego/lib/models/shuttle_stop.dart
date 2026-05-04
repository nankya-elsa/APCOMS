class ShuttleStop {
  const ShuttleStop({
    required this.name,
    required this.lat,
    required this.lng,
    this.index,
  });

  final String name;
  final double lat;
  final double lng;
  final int? index;

  static ShuttleStop? fromMap(Map<String, Object?> map) {
    final name = (map['name'] as String?)?.trim();
    final lat = _readDouble(map['lat'] ?? map['latitude']);
    final lng = _readDouble(map['lng'] ?? map['lon'] ?? map['longitude']);
    if (name == null || name.isEmpty || lat == null || lng == null) return null;

    return ShuttleStop(
      name: name,
      lat: lat,
      lng: lng,
      index: _readInt(map['index'] ?? map['order']),
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
