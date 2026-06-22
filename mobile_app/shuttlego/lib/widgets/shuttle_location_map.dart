import 'package:firebase_database/firebase_database.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/gestures.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart' as gmaps;
import 'package:latlong2/latlong.dart' as ll;
import 'dart:ui' as ui;

import '../models/shuttle_location.dart';
import '../models/shuttle_route_geometry.dart';
import '../models/shuttle_stop.dart';
import '../services/shuttle_location_service.dart';
import '../services/shuttle_route_geometry_service.dart';
import '../utils/google_maps_web_loader.dart';

class ShuttleLocationMap extends StatelessWidget {
  const ShuttleLocationMap({
    super.key,
    required this.shuttleKey,
    this.height = 260,
    this.locationService,
    this.routeService,
    this.targetLocation,
    this.onEtaToTarget,
    this.onEtaToNextStop,
    this.forceDisableOnAndroid = false,
  });

  final String shuttleKey;
  final double height;
  final ShuttleLocationService? locationService;
  final ShuttleRouteGeometryService? routeService;
  final gmaps.LatLng? targetLocation;
  final ValueChanged<int?>? onEtaToTarget;
  final ValueChanged<int?>? onEtaToNextStop;
  // Debug: when true the native Android map is disabled and a placeholder
  // is shown. Use this to confirm whether the platform map view is
  // intercepting touch events and preventing UI interaction.
  final bool forceDisableOnAndroid;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    final shuttleRef = FirebaseDatabase.instance
        .ref()
        .child('shuttles')
        .child(shuttleKey);

    // Optional fallback stop coordinate catalog.
    // Recommended shape:
    // stop_locations/{Stop Name}: {"lat":..., "lng":..., "index":...}
    final stopCatalogRef = FirebaseDatabase.instance.ref().child(
      'stop_locations',
    );

    final locSvc = locationService ?? ShuttleLocationService();
    final routeSvc = routeService ?? ShuttleRouteGeometryService();

    // If requested, and running on Android (not web), render a lightweight
    // placeholder instead of the native platform view. This helps determine
    // whether the platform map is blocking touch/gesture interaction.
    if (!kIsWeb &&
        defaultTargetPlatform == TargetPlatform.android &&
        forceDisableOnAndroid) {
      return SizedBox(
        height: height,
        width: double.infinity,
        child: ClipRRect(
          borderRadius: BorderRadius.circular(14),
          child: ColoredBox(
            color: scheme.surface,
            child: Center(
              child: Padding(
                padding: const EdgeInsets.all(16.0),
                child: Text(
                  'Maps disabled (debug).',
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
              ),
            ),
          ),
        ),
      );
    }

    return SizedBox(
      height: height,
      width: double.infinity,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(14),
        child: StreamBuilder<ShuttleRouteGeometry?>(
          stream: routeSvc.watchRoute(shuttleKey: shuttleKey),
          builder: (context, routeSnapshot) {
            return StreamBuilder<DatabaseEvent>(
              stream: stopCatalogRef.onValue,
              builder: (context, stopCatalogSnapshot) {
                final catalogStops = _parseStopCatalog(
                  stopCatalogSnapshot.data?.snapshot.value,
                );

                return StreamBuilder<DatabaseEvent>(
                  stream: shuttleRef.onValue,
                  builder: (context, shuttleSnapshot) {
                    final shuttleRaw = shuttleSnapshot.data?.snapshot.value;
                    final shuttleData = shuttleRaw is Map
                        ? Map<String, Object?>.from(shuttleRaw)
                        : const <String, Object?>{};

                    final locationRaw = shuttleData['location'];
                    final location = locationRaw is Map
                        ? Map<String, Object?>.from(locationRaw)
                        : null;

                    final currentStop =
                        (((shuttleData['current_stop'] as String?) ??
                                    (location?['current_stop'] as String?)) ??
                                '')
                            .trim();
                    final nextStop =
                        (((shuttleData['next_stop'] as String?) ??
                                    (location?['next_stop'] as String?)) ??
                                '')
                            .trim();

                    return StreamBuilder<ShuttleLocation?>(
                      stream: locSvc.watchLocation(shuttleKey: shuttleKey),
                      builder: (context, locSnapshot) {
                        final route = routeSnapshot.data;
                        final loc = locSnapshot.data;

                        final hasErrors =
                            routeSnapshot.hasError ||
                            stopCatalogSnapshot.hasError ||
                            shuttleSnapshot.hasError ||
                            locSnapshot.hasError;

                        final errorLines = <String>[];
                        if (shuttleSnapshot.hasError) {
                          errorLines.add(
                            'shuttles/$shuttleKey: ${shuttleSnapshot.error}',
                          );
                        }
                        if (routeSnapshot.hasError) {
                          errorLines.add(
                            'routes/$shuttleKey: ${routeSnapshot.error}',
                          );
                        }
                        if (stopCatalogSnapshot.hasError) {
                          errorLines.add(
                            'stop_locations: ${stopCatalogSnapshot.error}',
                          );
                        }
                        if (locSnapshot.hasError) {
                          errorLines.add('location: ${locSnapshot.error}');
                        }
                        final errorText = errorLines.join('\n');

                        final polyline = route?.polyline ?? const <ll.LatLng>[];
                        final routeStops =
                            route?.stops ?? const <ShuttleStop>[];
                        final stops = routeStops.isNotEmpty
                            ? routeStops
                            : catalogStops;

                        final currentStopName =
                            (loc?.currentStop ?? currentStop).trim();
                        final nextStopName = (loc?.nextStop ?? nextStop).trim();

                        gmaps.LatLng? busPoint = loc == null
                            ? null
                            : gmaps.LatLng(loc.lat, loc.lng);
                        if (busPoint == null && currentStopName.isNotEmpty) {
                          final stop =
                              route?.findStopByName(currentStopName) ??
                              _findStopByNameInList(
                                catalogStops,
                                currentStopName,
                              );
                          if (stop != null) {
                            busPoint = gmaps.LatLng(stop.lat, stop.lng);
                          }
                        }

                        final nextStopStop = nextStopName.isEmpty
                            ? null
                            : (route?.findStopByName(nextStopName) ??
                                  _findStopByNameInList(
                                    catalogStops,
                                    nextStopName,
                                  ));
                        final nextStopPoint = nextStopStop == null
                            ? null
                            : gmaps.LatLng(nextStopStop.lat, nextStopStop.lng);

                        final currentStopStop = currentStopName.isEmpty
                            ? null
                            : (route?.findStopByName(currentStopName) ??
                                  _findStopByNameInList(
                                    catalogStops,
                                    currentStopName,
                                  ));
                        final currentStopPoint = currentStopStop == null
                            ? null
                            : gmaps.LatLng(
                                currentStopStop.lat,
                                currentStopStop.lng,
                              );

                        // Also compute ETA from bus to next stop and notify listener
                        if (busPoint != null && nextStopPoint != null) {
                          try {
                            double metersNext;
                            final polylineForEta =
                                route?.polyline ?? const <ll.LatLng>[];
                            if (polylineForEta.isNotEmpty) {
                              final startIdx = _closestPolylineIndex(
                                polylineForEta,
                                busPoint,
                              );
                              final endIdx = _closestPolylineIndex(
                                polylineForEta,
                                nextStopPoint,
                              );
                              if (startIdx != null && endIdx != null) {
                                metersNext = _distanceAlongPolylineMeters(
                                  polylineForEta,
                                  startIdx,
                                  endIdx,
                                );
                              } else {
                                metersNext = ll.Distance().as(
                                  ll.LengthUnit.Meter,
                                  ll.LatLng(
                                    busPoint.latitude,
                                    busPoint.longitude,
                                  ),
                                  ll.LatLng(
                                    nextStopPoint.latitude,
                                    nextStopPoint.longitude,
                                  ),
                                );
                              }
                            } else {
                              metersNext = ll.Distance().as(
                                ll.LengthUnit.Meter,
                                ll.LatLng(
                                  busPoint.latitude,
                                  busPoint.longitude,
                                ),
                                ll.LatLng(
                                  nextStopPoint.latitude,
                                  nextStopPoint.longitude,
                                ),
                              );
                            }
                            const speedMpsEta = 8.0;
                            final minsNext = (metersNext / speedMpsEta / 60)
                                .ceil();
                            if (onEtaToNextStop != null)
                              onEtaToNextStop!(minsNext);
                          } catch (_) {}
                        }

                        final center =
                            busPoint ??
                            (polyline.isNotEmpty
                                ? gmaps.LatLng(
                                    polyline.first.latitude,
                                    polyline.first.longitude,
                                  )
                                : (nextStopPoint ??
                                      const gmaps.LatLng(0.3334, 32.5683)));

                        final routePoints = polyline
                            .map((p) => gmaps.LatLng(p.latitude, p.longitude))
                            .toList(growable: false);

                        final highlightedOrigin = busPoint ?? currentStopPoint;
                        final highlightedPoints =
                            _computeHighlightedRoutePoints(
                              route: route,
                              busPoint: highlightedOrigin,
                              nextStopPoint: nextStopPoint,
                            );

                        final polylines = <gmaps.Polyline>{
                          if (routePoints.isNotEmpty)
                            gmaps.Polyline(
                              polylineId: const gmaps.PolylineId('route'),
                              points: routePoints,
                              color: scheme.outlineVariant,
                              width: 5,
                            ),
                          if (highlightedPoints.isNotEmpty)
                            gmaps.Polyline(
                              polylineId: const gmaps.PolylineId(
                                'route_highlight',
                              ),
                              points: highlightedPoints,
                              color: scheme.primary,
                              width: 7,
                            ),
                        };

                        final busIconFuture = _busMarkerIcon(
                          color: scheme.primary,
                        );

                        final showLoading =
                            (locSnapshot.connectionState ==
                                ConnectionState.waiting) &&
                            loc == null;

                        final routeHasAny =
                            polyline.isNotEmpty ||
                            routeStops.isNotEmpty ||
                            catalogStops.isNotEmpty;
                        final showRouteNotConfigured =
                            !hasErrors && !showLoading && !routeHasAny;

                        final isMissingCoords =
                            !hasErrors &&
                            !showLoading &&
                            busPoint == null &&
                            !showRouteNotConfigured;

                        final webApiKey = const String.fromEnvironment(
                          'GOOGLE_MAPS_API_KEY',
                        );

                        return Stack(
                          children: [
                            FutureBuilder<gmaps.BitmapDescriptor>(
                              future: busIconFuture,
                              builder: (context, busIconSnapshot) {
                                final busIcon =
                                    busIconSnapshot.data ??
                                    gmaps.BitmapDescriptor.defaultMarkerWithHue(
                                      gmaps.BitmapDescriptor.hueAzure,
                                    );

                                final markers = <gmaps.Marker>{
                                  if (busPoint != null)
                                    gmaps.Marker(
                                      markerId: const gmaps.MarkerId('bus'),
                                      position: busPoint,
                                      icon: busIcon,
                                      anchor: const Offset(0.5, 0.5),
                                      infoWindow: gmaps.InfoWindow(
                                        title: 'Bus',
                                        snippet: currentStopName.isEmpty
                                            ? null
                                            : 'At: $currentStopName',
                                      ),
                                    ),
                                  if (nextStopPoint != null)
                                    gmaps.Marker(
                                      markerId: const gmaps.MarkerId(
                                        'next_stop',
                                      ),
                                      position: nextStopPoint,
                                      icon:
                                          gmaps
                                              .BitmapDescriptor.defaultMarkerWithHue(
                                            gmaps.BitmapDescriptor.hueGreen,
                                          ),
                                      infoWindow: gmaps.InfoWindow(
                                        title: 'Next stop',
                                        snippet: nextStopName,
                                      ),
                                    ),
                                };

                                // Remove the confusing blue "current stop" marker
                                // — the bus marker and next-stop marker are sufficient.

                                if (kIsWeb) {
                                  return FutureBuilder<void>(
                                    future: ensureGoogleMapsLoaded(
                                      apiKey: webApiKey,
                                    ),
                                    builder: (context, mapsScriptSnapshot) {
                                      if (mapsScriptSnapshot.hasError) {
                                        return ColoredBox(
                                          color: scheme.surface,
                                          child: Center(
                                            child: Padding(
                                              padding: const EdgeInsets.all(16),
                                              child: Text(
                                                '${mapsScriptSnapshot.error}',
                                                style: Theme.of(context)
                                                    .textTheme
                                                    .bodySmall
                                                    ?.copyWith(
                                                      color: scheme
                                                          .onSurfaceVariant,
                                                    ),
                                                textAlign: TextAlign.center,
                                              ),
                                            ),
                                          ),
                                        );
                                      }

                                      if (mapsScriptSnapshot.connectionState !=
                                          ConnectionState.done) {
                                        return ColoredBox(
                                          color: scheme.surface,
                                          child: const Center(
                                            child: SizedBox(
                                              width: 22,
                                              height: 22,
                                              child: CircularProgressIndicator(
                                                strokeWidth: 2,
                                              ),
                                            ),
                                          ),
                                        );
                                      }

                                      return gmaps.GoogleMap(
                                        initialCameraPosition:
                                            gmaps.CameraPosition(
                                              target: center,
                                              zoom: 16,
                                            ),
                                        gestureRecognizers:
                                            <
                                              Factory<
                                                OneSequenceGestureRecognizer
                                              >
                                            >{},
                                        onMapCreated: (ctrl) async {
                                          try {
                                            final points = <gmaps.LatLng>[];
                                            if (busPoint != null)
                                              points.add(busPoint);
                                            if (nextStopPoint != null)
                                              points.add(nextStopPoint);
                                            if (targetLocation != null)
                                              points.add(targetLocation!);
                                            if (points.isNotEmpty) {
                                              var minLat =
                                                  points.first.latitude;
                                              var maxLat =
                                                  points.first.latitude;
                                              var minLng =
                                                  points.first.longitude;
                                              var maxLng =
                                                  points.first.longitude;
                                              for (final p in points) {
                                                minLat = p.latitude < minLat
                                                    ? p.latitude
                                                    : minLat;
                                                maxLat = p.latitude > maxLat
                                                    ? p.latitude
                                                    : maxLat;
                                                minLng = p.longitude < minLng
                                                    ? p.longitude
                                                    : minLng;
                                                maxLng = p.longitude > maxLng
                                                    ? p.longitude
                                                    : maxLng;
                                              }
                                              final bounds = gmaps.LatLngBounds(
                                                southwest: gmaps.LatLng(
                                                  minLat,
                                                  minLng,
                                                ),
                                                northeast: gmaps.LatLng(
                                                  maxLat,
                                                  maxLng,
                                                ),
                                              );
                                              await ctrl.moveCamera(
                                                gmaps
                                                    .CameraUpdate.newLatLngBounds(
                                                  bounds,
                                                  60,
                                                ),
                                              );
                                            }
                                          } catch (_) {}
                                        },
                                        markers: markers,
                                        polylines: polylines,
                                        myLocationButtonEnabled: false,
                                        compassEnabled: true,
                                        mapToolbarEnabled: false,
                                        zoomControlsEnabled: false,
                                      );
                                    },
                                  );
                                }

                                return gmaps.GoogleMap(
                                  initialCameraPosition: gmaps.CameraPosition(
                                    target: center,
                                    zoom: 16,
                                  ),
                                  gestureRecognizers:
                                      <Factory<OneSequenceGestureRecognizer>>{},
                                  onMapCreated: (ctrl) async {
                                    try {
                                      final points = <gmaps.LatLng>[];
                                      if (busPoint != null)
                                        points.add(busPoint);
                                      if (nextStopPoint != null)
                                        points.add(nextStopPoint);
                                      if (targetLocation != null)
                                        points.add(targetLocation!);
                                      if (points.isNotEmpty) {
                                        var minLat = points.first.latitude;
                                        var maxLat = points.first.latitude;
                                        var minLng = points.first.longitude;
                                        var maxLng = points.first.longitude;
                                        for (final p in points) {
                                          minLat = p.latitude < minLat
                                              ? p.latitude
                                              : minLat;
                                          maxLat = p.latitude > maxLat
                                              ? p.latitude
                                              : maxLat;
                                          minLng = p.longitude < minLng
                                              ? p.longitude
                                              : minLng;
                                          maxLng = p.longitude > maxLng
                                              ? p.longitude
                                              : maxLng;
                                        }
                                        final bounds = gmaps.LatLngBounds(
                                          southwest: gmaps.LatLng(
                                            minLat,
                                            minLng,
                                          ),
                                          northeast: gmaps.LatLng(
                                            maxLat,
                                            maxLng,
                                          ),
                                        );
                                        await ctrl.moveCamera(
                                          gmaps.CameraUpdate.newLatLngBounds(
                                            bounds,
                                            60,
                                          ),
                                        );
                                      }
                                    } catch (_) {}
                                  },
                                  markers: markers,
                                  polylines: polylines,
                                  myLocationButtonEnabled: false,
                                  compassEnabled: true,
                                  mapToolbarEnabled: false,
                                  zoomControlsEnabled: false,
                                );
                              },
                            ),
                            if (showLoading)
                              Positioned.fill(
                                child: ColoredBox(
                                  color: scheme.surface.withValues(alpha: 0.22),
                                  child: const Center(
                                    child: SizedBox(
                                      width: 22,
                                      height: 22,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                      ),
                                    ),
                                  ),
                                ),
                              ),
                            if (currentStop.isNotEmpty || nextStop.isNotEmpty)
                              Positioned(
                                left: 10,
                                right: 10,
                                top: 10,
                                child: Container(
                                  padding: const EdgeInsets.symmetric(
                                    horizontal: 10,
                                    vertical: 8,
                                  ),
                                  decoration: BoxDecoration(
                                    color: Color.alphaBlend(
                                      scheme.surface.withValues(alpha: 0.92),
                                      Colors.white,
                                    ),
                                    borderRadius: BorderRadius.circular(12),
                                    border: Border.all(
                                      color: scheme.outlineVariant.withValues(
                                        alpha: 0.35,
                                      ),
                                    ),
                                  ),
                                  child: Text(
                                    'Current: ${currentStop.isEmpty ? '—' : currentStop}  •  Next: ${nextStop.isEmpty ? '—' : nextStop}',
                                    style: Theme.of(context).textTheme.bodySmall
                                        ?.copyWith(
                                          color: scheme.onSurfaceVariant,
                                        ),
                                  ),
                                ),
                              ),
                            if (targetLocation != null && busPoint != null)
                              Positioned(
                                right: 10,
                                top: 10,
                                child: Builder(
                                  builder: (context) {
                                    final bp = busPoint;
                                    final tl = targetLocation;
                                    if (bp == null || tl == null)
                                      return const SizedBox.shrink();
                                    try {
                                      double meters;
                                      // Prefer along-route distance when polyline is available.
                                      final polyline =
                                          route?.polyline ??
                                          const <ll.LatLng>[];
                                      if (polyline.isNotEmpty) {
                                        final startIdx = _closestPolylineIndex(
                                          polyline,
                                          bp,
                                        );
                                        final endIdx = _closestPolylineIndex(
                                          polyline,
                                          gmaps.LatLng(
                                            tl.latitude,
                                            tl.longitude,
                                          ),
                                        );
                                        if (startIdx != null &&
                                            endIdx != null) {
                                          meters = _distanceAlongPolylineMeters(
                                            polyline,
                                            startIdx,
                                            endIdx,
                                          );
                                        } else {
                                          meters = ll.Distance().as(
                                            ll.LengthUnit.Meter,
                                            ll.LatLng(
                                              bp.latitude,
                                              bp.longitude,
                                            ),
                                            ll.LatLng(
                                              tl.latitude,
                                              tl.longitude,
                                            ),
                                          );
                                        }
                                      } else {
                                        meters = ll.Distance().as(
                                          ll.LengthUnit.Meter,
                                          ll.LatLng(bp.latitude, bp.longitude),
                                          ll.LatLng(tl.latitude, tl.longitude),
                                        );
                                      }
                                      const speedMps =
                                          8.0; // ~28.8 km/h estimate
                                      final mins = (meters / speedMps / 60)
                                          .ceil();
                                      // Notify listener about ETA to provided target (device / pickup)
                                      try {
                                        if (onEtaToTarget != null)
                                          onEtaToTarget!(mins);
                                      } catch (_) {}

                                      return Container(
                                        padding: const EdgeInsets.symmetric(
                                          horizontal: 10,
                                          vertical: 8,
                                        ),
                                        decoration: BoxDecoration(
                                          color: Color.alphaBlend(
                                            scheme.surface.withValues(
                                              alpha: 0.92,
                                            ),
                                            Colors.white,
                                          ),
                                          borderRadius: BorderRadius.circular(
                                            12,
                                          ),
                                          border: Border.all(
                                            color: scheme.outlineVariant
                                                .withValues(alpha: 0.35),
                                          ),
                                        ),
                                        child: Text(
                                          'Bus ≈ $mins min',
                                          style: Theme.of(context)
                                              .textTheme
                                              .bodySmall
                                              ?.copyWith(
                                                color: scheme.onSurfaceVariant,
                                              ),
                                        ),
                                      );
                                    } catch (_) {
                                      return const SizedBox.shrink();
                                    }
                                  },
                                ),
                              ),

                            if (hasErrors)
                              Positioned(
                                left: 10,
                                right: 10,
                                bottom: 10,
                                child: Container(
                                  padding: const EdgeInsets.symmetric(
                                    horizontal: 10,
                                    vertical: 8,
                                  ),
                                  decoration: BoxDecoration(
                                    color: Color.alphaBlend(
                                      scheme.errorContainer.withValues(
                                        alpha: 0.82,
                                      ),
                                      Colors.white,
                                    ),
                                    borderRadius: BorderRadius.circular(12),
                                    border: Border.all(
                                      color: scheme.error.withValues(
                                        alpha: 0.25,
                                      ),
                                    ),
                                  ),
                                  child: Text(
                                    errorText.isEmpty
                                        ? 'Map data failed to load. Most common cause: Realtime Database rules (permission-denied).'
                                        : 'Map data failed to load:\n$errorText\n\nMost common cause: Realtime Database rules (permission-denied).',
                                    style: Theme.of(context).textTheme.bodySmall
                                        ?.copyWith(
                                          color: scheme.onErrorContainer,
                                        ),
                                  ),
                                ),
                              ),
                            if (isMissingCoords)
                              Positioned(
                                left: 10,
                                right: 10,
                                bottom: 10,
                                child: Container(
                                  padding: const EdgeInsets.symmetric(
                                    horizontal: 10,
                                    vertical: 8,
                                  ),
                                  decoration: BoxDecoration(
                                    color: Color.alphaBlend(
                                      scheme.errorContainer.withValues(
                                        alpha: 0.82,
                                      ),
                                      Colors.white,
                                    ),
                                    borderRadius: BorderRadius.circular(12),
                                    border: Border.all(
                                      color: scheme.error.withValues(
                                        alpha: 0.25,
                                      ),
                                    ),
                                  ),
                                  child: Text(
                                    currentStopName.isEmpty
                                        ? 'Bus position unknown. Provide GPS (lat/lng) under shuttles/$shuttleKey/location, or provide a current_stop name.'
                                        : (stops.isEmpty
                                              ? 'Route has no stop coordinates. Add routes/$shuttleKey/stops so "$currentStopName" can be mapped to a lat/lng.'
                                              : 'No coordinates found for "$currentStopName". Add stop coordinates under routes/$shuttleKey/stops (and optional polyline under routes/$shuttleKey/polyline).'),
                                    style: Theme.of(context).textTheme.bodySmall
                                        ?.copyWith(
                                          color: scheme.onErrorContainer,
                                        ),
                                  ),
                                ),
                              ),
                            if (showRouteNotConfigured)
                              Positioned(
                                left: 10,
                                right: 10,
                                top:
                                    (currentStop.isNotEmpty ||
                                        nextStop.isNotEmpty)
                                    ? 54
                                    : 10,
                                child: Container(
                                  padding: const EdgeInsets.symmetric(
                                    horizontal: 10,
                                    vertical: 8,
                                  ),
                                  decoration: BoxDecoration(
                                    color: Color.alphaBlend(
                                      scheme.surface.withValues(alpha: 0.92),
                                      Colors.white,
                                    ),
                                    borderRadius: BorderRadius.circular(12),
                                    border: Border.all(
                                      color: scheme.outlineVariant.withValues(
                                        alpha: 0.35,
                                      ),
                                    ),
                                  ),
                                  child: Text(
                                    'Route not configured yet. Add stop coordinates under routes/$shuttleKey/stops or under stop_locations so stop names like "$currentStopName" can be mapped to lat/lng.',
                                    style: Theme.of(context).textTheme.bodySmall
                                        ?.copyWith(
                                          color: scheme.onSurfaceVariant,
                                        ),
                                  ),
                                ),
                              ),
                          ],
                        );
                      },
                    );
                  },
                );
              },
            );
          },
        ),
      ),
    );
  }
}

List<ShuttleStop> _parseStopCatalog(Object? raw) {
  if (raw == null) return const <ShuttleStop>[];

  final stops = <ShuttleStop>[];

  if (raw is List) {
    for (final item in raw) {
      if (item is! Map) continue;
      final stop = ShuttleStop.fromMap(Map<String, Object?>.from(item));
      if (stop != null) stops.add(stop);
    }
  } else if (raw is Map) {
    // Support map keyed by stop name.
    for (final entry in raw.entries) {
      final value = entry.value;
      if (value is! Map) continue;
      final map = Map<String, Object?>.from(value);
      map.putIfAbsent('name', () => entry.key.toString());
      final stop = ShuttleStop.fromMap(map);
      if (stop != null) stops.add(stop);
    }
  }

  stops.sort((a, b) {
    final ai = a.index;
    final bi = b.index;
    if (ai == null && bi == null) return a.name.compareTo(b.name);
    if (ai == null) return 1;
    if (bi == null) return -1;
    return ai.compareTo(bi);
  });

  return stops;
}

ShuttleStop? _findStopByNameInList(List<ShuttleStop> stops, String name) {
  final normalized = name.trim().toLowerCase();
  for (final stop in stops) {
    if (stop.name.trim().toLowerCase() == normalized) return stop;
  }
  return null;
}

final Map<int, Future<gmaps.BitmapDescriptor>> _busIconCache =
    <int, Future<gmaps.BitmapDescriptor>>{};

Future<gmaps.BitmapDescriptor> _busMarkerIcon({required Color color}) {
  // google_maps_flutter_web can be picky about fromBytes; avoid surprises.
  if (kIsWeb) {
    return Future.value(
      gmaps.BitmapDescriptor.defaultMarkerWithHue(
        gmaps.BitmapDescriptor.hueAzure,
      ),
    );
  }

  final key = color.toARGB32();
  return _busIconCache.putIfAbsent(key, () async {
    try {
      // Render a small circular marker with a bus glyph.
      // (Bitmap size directly affects how big it appears on the map.)
      const size = 48.0;
      const iconSize = 26.0;

      final recorder = ui.PictureRecorder();
      final canvas = Canvas(recorder);
      final center = const Offset(size / 2, size / 2);

      // Background circle
      final bgPaint = Paint()..color = color;
      canvas.drawCircle(center, size / 2, bgPaint);

      // White bus glyph
      final textPainter = TextPainter(
        textDirection: TextDirection.ltr,
        textAlign: TextAlign.center,
      );
      final icon = Icons.directions_bus;
      textPainter.text = TextSpan(
        text: String.fromCharCode(icon.codePoint),
        style: TextStyle(
          fontSize: iconSize,
          fontFamily: icon.fontFamily,
          package: icon.fontPackage,
          color: Colors.white,
        ),
      );
      textPainter.layout();
      final offset = Offset(
        center.dx - textPainter.width / 2,
        center.dy - textPainter.height / 2,
      );
      textPainter.paint(canvas, offset);

      final picture = recorder.endRecording();
      final image = await picture.toImage(size.toInt(), size.toInt());
      final bytes = (await image.toByteData(
        format: ui.ImageByteFormat.png,
      ))?.buffer.asUint8List();
      if (bytes == null) {
        return gmaps.BitmapDescriptor.defaultMarkerWithHue(
          gmaps.BitmapDescriptor.hueAzure,
        );
      }
      return gmaps.BitmapDescriptor.bytes(bytes);
    } catch (_) {
      return gmaps.BitmapDescriptor.defaultMarkerWithHue(
        gmaps.BitmapDescriptor.hueAzure,
      );
    }
  });
}

List<gmaps.LatLng> _computeHighlightedRoutePoints({
  required ShuttleRouteGeometry? route,
  required gmaps.LatLng? busPoint,
  required gmaps.LatLng? nextStopPoint,
}) {
  if (route == null) return const <gmaps.LatLng>[];
  if (busPoint == null || nextStopPoint == null) {
    return const <gmaps.LatLng>[];
  }

  final polyline = route.polyline;
  if (polyline.isEmpty) {
    return <gmaps.LatLng>[busPoint, nextStopPoint];
  }

  final startIdx = _closestPolylineIndex(polyline, busPoint);
  final endIdx = _closestPolylineIndex(polyline, nextStopPoint);
  if (startIdx == null || endIdx == null) return const <gmaps.LatLng>[];
  if (startIdx == endIdx) return <gmaps.LatLng>[busPoint, nextStopPoint];

  final points = <gmaps.LatLng>[];
  if (startIdx < endIdx) {
    for (var i = startIdx; i <= endIdx; i++) {
      final p = polyline[i];
      points.add(gmaps.LatLng(p.latitude, p.longitude));
    }
  } else {
    // Loop route: go to end then wrap to start.
    for (var i = startIdx; i < polyline.length; i++) {
      final p = polyline[i];
      points.add(gmaps.LatLng(p.latitude, p.longitude));
    }
    for (var i = 0; i <= endIdx; i++) {
      final p = polyline[i];
      points.add(gmaps.LatLng(p.latitude, p.longitude));
    }
  }

  if (points.isEmpty) return const <gmaps.LatLng>[];

  // Ensure endpoints match what we show as markers.
  points[0] = busPoint;
  points[points.length - 1] = nextStopPoint;
  return points;
}

int? _closestPolylineIndex(List<ll.LatLng> polyline, gmaps.LatLng target) {
  if (polyline.isEmpty) return null;

  final dist = ll.Distance();
  var bestIdx = 0;
  var bestMeters = double.infinity;

  for (var i = 0; i < polyline.length; i++) {
    final p = polyline[i];
    final meters = dist(
      ll.LatLng(p.latitude, p.longitude),
      ll.LatLng(target.latitude, target.longitude),
    );
    if (meters < bestMeters) {
      bestMeters = meters;
      bestIdx = i;
    }
  }

  return bestIdx;
}

double _distanceAlongPolylineMeters(
  List<ll.LatLng> polyline,
  int startIdx,
  int endIdx,
) {
  final dist = ll.Distance();
  double sum = 0.0;
  if (polyline.isEmpty) return 0.0;

  if (startIdx <= endIdx) {
    for (var i = startIdx; i < endIdx; i++) {
      final a = polyline[i];
      final b = polyline[i + 1];
      sum += dist(
        ll.LatLng(a.latitude, a.longitude),
        ll.LatLng(b.latitude, b.longitude),
      );
    }
  } else {
    // wrap-around route
    for (var i = startIdx; i < polyline.length - 1; i++) {
      final a = polyline[i];
      final b = polyline[i + 1];
      sum += dist(
        ll.LatLng(a.latitude, a.longitude),
        ll.LatLng(b.latitude, b.longitude),
      );
    }
    for (var i = 0; i < endIdx; i++) {
      final a = polyline[i];
      final b = polyline[i + 1];
      sum += dist(
        ll.LatLng(a.latitude, a.longitude),
        ll.LatLng(b.latitude, b.longitude),
      );
    }
  }

  return sum;
}
