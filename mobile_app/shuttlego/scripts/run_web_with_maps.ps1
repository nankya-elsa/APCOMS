param(
  [string]$WebKey = ''
)

Write-Host "Running Flutter web with Google Maps API key (web)..."
flutter run -d chrome --dart-define=GOOGLE_MAPS_API_KEY=$WebKey
