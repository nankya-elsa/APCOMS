Future<void> ensureGoogleMapsLoadedImpl({required String apiKey}) async {
  // Non-web platforms: google_maps_flutter uses native SDKs.
  return;
}
