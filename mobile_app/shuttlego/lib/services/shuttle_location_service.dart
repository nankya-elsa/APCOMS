import 'package:firebase_database/firebase_database.dart';

import '../models/shuttle_location.dart';

class ShuttleLocationService {
  ShuttleLocationService({FirebaseDatabase? database})
    : _database = database ?? FirebaseDatabase.instance;

  final FirebaseDatabase _database;

  /// Watches live location for a shuttle.
  ///
  /// Expected RTDB shape (recommended):
  /// `shuttles/{shuttleKey}/location`:
  /// {
  ///   "lat": 0.3334,
  ///   "lng": 32.5683,
  ///   "heading": 120,
  ///   "current_stop": "CEDAT",
  ///   "next_stop": "CONAS",
  ///   "updated_at": 1710000000000
  /// }
  Stream<ShuttleLocation?> watchLocation({required String shuttleKey}) {
    final shuttleRef = _database.ref().child('shuttles').child(shuttleKey);

    return shuttleRef.onValue.map((event) {
      final raw = event.snapshot.value;
      if (raw is! Map) return null;

      final shuttleMap = Map<String, Object?>.from(raw);

      // Prefer nested location values for coordinates while keeping root fields
      // (like current_stop/next_stop) available when location doesn't include
      // them.
      final nestedRaw = shuttleMap['location'];
      final nested = nestedRaw is Map
          ? Map<String, Object?>.from(nestedRaw)
          : null;

      final effective = <String, Object?>{...shuttleMap};
      if (nested != null) {
        effective.addAll(nested);
      }

      // If coordinates are missing everywhere, this returns null.
      return ShuttleLocation.fromMap(effective);
    });
  }
}
