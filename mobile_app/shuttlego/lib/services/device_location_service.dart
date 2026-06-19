import 'dart:async';

import 'package:geolocator/geolocator.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart' as gmaps;

class DeviceLocationService {
  DeviceLocationService();

  Stream<gmaps.LatLng?> watchDeviceLocation({LocationAccuracy accuracy = LocationAccuracy.best}) async* {
    // Ensure permission
    final permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      final req = await Geolocator.requestPermission();
      if (req == LocationPermission.denied || req == LocationPermission.deniedForever) {
        yield null;
        return;
      }
    }

    final settings = LocationSettings(accuracy: accuracy, distanceFilter: 5);
    yield* Geolocator.getPositionStream(locationSettings: settings).map((pos) {
      return gmaps.LatLng(pos.latitude, pos.longitude);
    });
  }
}
