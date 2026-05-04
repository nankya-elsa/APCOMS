# shuttlego

A new Flutter project.

## Google Maps (Web)

This app loads the Google Maps JavaScript API on Flutter Web. You must provide a key at build/run time.

- Run in Chrome:
	- `flutter run -d chrome --dart-define=GOOGLE_MAPS_API_KEY=YOUR_KEY`
- Build for web:
	- `flutter build web --dart-define=GOOGLE_MAPS_API_KEY=YOUR_KEY`

In Google Cloud Console, restrict the key to your site origin (HTTP referrers) and enable the required Maps APIs.

### Windows (PowerShell) recommended setup

To avoid committing keys into the repo, set environment variables locally and use the VS Code launch config in [.vscode/launch.json](.vscode/launch.json).

- Set the Web key for the current terminal session:
	- `$env:GOOGLE_MAPS_API_KEY_WEB = "<your web maps js api key>"`
- Run web:
	- `flutter run -d chrome --dart-define=GOOGLE_MAPS_API_KEY=$env:GOOGLE_MAPS_API_KEY_WEB`

For Android, the Gradle build reads `GOOGLE_MAPS_API_KEY` from (first match wins):
- `-PGOOGLE_MAPS_API_KEY=...` (Gradle property)
- `$env:GOOGLE_MAPS_API_KEY_ANDROID` or `$env:GOOGLE_MAPS_API_KEY`
- `android/local.properties` (`GOOGLE_MAPS_API_KEY=...`)

## No Billing / No Google Key (Use OpenStreetMap)

If you don't want to use Google Maps keys/billing, you can run the app with an OpenStreetMap-based map instead:

- `flutter run -d chrome --dart-define=USE_OPENSTREETMAP=true`
- `flutter run -d android --dart-define=USE_OPENSTREETMAP=true`
