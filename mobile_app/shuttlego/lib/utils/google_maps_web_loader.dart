import 'google_maps_web_loader_stub.dart'
    if (dart.library.html) 'google_maps_web_loader_web.dart';

/// Ensures the Google Maps JavaScript API is available on Flutter Web.
///
/// On non-web platforms, this is a no-op.
Future<void> ensureGoogleMapsLoaded({required String apiKey}) async {
  return ensureGoogleMapsLoadedImpl(apiKey: apiKey);
}
