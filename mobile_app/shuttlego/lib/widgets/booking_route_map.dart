import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

class BookingRouteMap extends StatelessWidget {
  const BookingRouteMap({super.key, this.height = 380});

  final double height;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: height,
      width: double.infinity,
      child: FlutterMap(
        options: const MapOptions(
          initialCenter: LatLng(0.3334, 32.5683),
          initialZoom: 16,
          interactionOptions: InteractionOptions(
            flags:
                InteractiveFlag.pinchZoom |
                InteractiveFlag.drag |
                InteractiveFlag.doubleTapZoom,
          ),
        ),
        children: [
          TileLayer(
            urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
            userAgentPackageName: 'com.example.shuttlego',
          ),
          RichAttributionWidget(
            alignment: AttributionAlignment.bottomRight,
            attributions: [
              TextSourceAttribution('OpenStreetMap contributors', onTap: () {}),
            ],
          ),
        ],
      ),
    );
  }
}
