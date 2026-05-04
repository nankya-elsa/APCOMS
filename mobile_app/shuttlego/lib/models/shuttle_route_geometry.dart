import 'package:latlong2/latlong.dart';

import 'shuttle_stop.dart';

class ShuttleRouteGeometry {
  const ShuttleRouteGeometry({required this.polyline, required this.stops});

  final List<LatLng> polyline;
  final List<ShuttleStop> stops;

  ShuttleStop? findStopByName(String name) {
    final normalized = name.trim().toLowerCase();
    for (final stop in stops) {
      if (stop.name.trim().toLowerCase() == normalized) return stop;
    }
    return null;
  }

  static ShuttleRouteGeometry? fromMap(Map<String, Object?> map) {
    final polylineRaw = map['polyline'] ?? map['points'] ?? map['route'];
    final stopsRaw = map['stops'] ?? map['route_stops'];

    final polyline = _parsePolyline(polylineRaw);
    final stops = _parseStops(stopsRaw);

    if (polyline == null && stops == null) return null;

    return ShuttleRouteGeometry(
      polyline: polyline ?? const <LatLng>[],
      stops: stops ?? const <ShuttleStop>[],
    );
  }

  static List<LatLng>? _parsePolyline(Object? raw) {
    if (raw == null) return null;

    if (raw is List) {
      final points = <LatLng>[];
      for (final item in raw) {
        final p = _parsePoint(item);
        if (p != null) points.add(p);
      }
      return points;
    }

    if (raw is Map) {
      // Support maps like {"0": {lat,lng}, "1": {lat,lng}}
      final points = <LatLng>[];
      for (final entry in raw.entries) {
        final p = _parsePoint(entry.value);
        if (p != null) points.add(p);
      }
      return points;
    }

    return null;
  }

  static LatLng? _parsePoint(Object? raw) {
    if (raw is Map) {
      final map = Map<String, Object?>.from(raw);
      final lat = _readDouble(map['lat'] ?? map['latitude']);
      final lng = _readDouble(map['lng'] ?? map['lon'] ?? map['longitude']);
      if (lat == null || lng == null) return null;
      return LatLng(lat, lng);
    }

    if (raw is List && raw.length >= 2) {
      final lat = _readDouble(raw[0]);
      final lng = _readDouble(raw[1]);
      if (lat == null || lng == null) return null;
      return LatLng(lat, lng);
    }

    return null;
  }

  static List<ShuttleStop>? _parseStops(Object? raw) {
    if (raw == null) return null;

    final stops = <ShuttleStop>[];

    if (raw is List) {
      for (final item in raw) {
        if (item is! Map) continue;
        final stop = ShuttleStop.fromMap(Map<String, Object?>.from(item));
        if (stop != null) stops.add(stop);
      }
    } else if (raw is Map) {
      for (final entry in raw.entries) {
        final value = entry.value;
        if (value is! Map) continue;
        final stop = ShuttleStop.fromMap(Map<String, Object?>.from(value));
        if (stop != null) stops.add(stop);
      }
    } else {
      return null;
    }

    stops.sort((a, b) {
      final ai = a.index;
      final bi = b.index;
      if (ai == null && bi == null) return 0;
      if (ai == null) return 1;
      if (bi == null) return -1;
      return ai.compareTo(bi);
    });

    return stops;
  }

  static double? _readDouble(Object? value) {
    if (value is double) return value;
    if (value is int) return value.toDouble();
    if (value is String) return double.tryParse(value);
    return null;
  }
}
