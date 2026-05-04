import 'package:firebase_database/firebase_database.dart';

import '../models/shuttle_route_geometry.dart';

class ShuttleRouteGeometryService {
  ShuttleRouteGeometryService({FirebaseDatabase? database})
    : _database = database ?? FirebaseDatabase.instance;

  final FirebaseDatabase _database;

  /// Watches route geometry for a shuttle.
  ///
  /// Recommended RTDB path:
  /// `routes/{shuttleKey}`:
  /// {
  ///   "stops": [ {"name":"CEDAT","lat":...,"lng":...,"index":1}, ... ],
  ///   "polyline": [ {"lat":...,"lng":...}, ... ]
  /// }
  Stream<ShuttleRouteGeometry?> watchRoute({required String shuttleKey}) {
    final routeRef = _database.ref().child('routes').child(shuttleKey);

    return routeRef.onValue.map((event) {
      final raw = event.snapshot.value;
      if (raw == null) return null;

      // Supported shapes:
      // 1) routes/{shuttleKey}: {"stops": [...], "polyline": [...]}
      // 2) routes/{shuttleKey}: [ {name,lat,lng,index}, ... ]  (stops list directly)
      // 3) routes/{shuttleKey}: {"0": {name,lat,lng}, "1": {...} } (stops map directly)
      if (raw is List) {
        return ShuttleRouteGeometry.fromMap(<String, Object?>{'stops': raw});
      }

      if (raw is Map) {
        final map = Map<String, Object?>.from(raw);

        final hasGeometryKeys =
            map.containsKey('stops') ||
            map.containsKey('route_stops') ||
            map.containsKey('polyline') ||
            map.containsKey('points') ||
            map.containsKey('route');

        if (hasGeometryKeys) {
          return ShuttleRouteGeometry.fromMap(map);
        }

        // If the root map looks like a stop-map (numeric keys or ids -> stop objects),
        // treat it as stops.
        final firstValue = map.values.isEmpty ? null : map.values.first;
        if (firstValue is Map) {
          final firstStop = Map<String, Object?>.from(firstValue);
          final looksLikeStop =
              (firstStop['name'] is String) &&
              (firstStop.containsKey('lat') ||
                  firstStop.containsKey('latitude')) &&
              (firstStop.containsKey('lng') ||
                  firstStop.containsKey('lon') ||
                  firstStop.containsKey('longitude'));
          if (looksLikeStop) {
            return ShuttleRouteGeometry.fromMap(<String, Object?>{
              'stops': map,
            });
          }
        }
      }

      return null;
    });
  }
}
