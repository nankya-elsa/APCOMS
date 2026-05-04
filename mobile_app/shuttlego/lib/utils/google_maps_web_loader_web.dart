// ignore_for_file: avoid_web_libraries_in_flutter, deprecated_member_use

import 'dart:async';
import 'dart:html' as html;
import 'dart:js_interop';
import 'dart:js_interop_unsafe';

Future<void> ensureGoogleMapsLoadedImpl({required String apiKey}) async {
  bool isGoogleMapsReady() {
    if (!globalContext.has('google')) {
      return false;
    }

    final googleAny = globalContext['google'];
    if (googleAny == null || !googleAny.isA<JSObject>()) {
      return false;
    }
    final googleObj = googleAny as JSObject;
    if (!googleObj.has('maps')) {
      return false;
    }

    final mapsAny = googleObj['maps'];
    if (mapsAny == null || !mapsAny.isA<JSObject>()) {
      return false;
    }
    final mapsObj = mapsAny as JSObject;
    if (!mapsObj.has('MapTypeId')) {
      return false;
    }

    final mapTypeAny = mapsObj['MapTypeId'];
    if (mapTypeAny == null || !mapTypeAny.isA<JSObject>()) {
      return false;
    }
    final mapTypeObj = mapTypeAny as JSObject;
    return mapTypeObj.has('ROADMAP');
  }

  if (apiKey.trim().isEmpty) {
    throw StateError(
      'Missing Google Maps API key for Web. Provide it via --dart-define=GOOGLE_MAPS_API_KEY=...'
      ' (and restrict the key to your web origin in Google Cloud Console).',
    );
  }

  // Already loaded?
  if (isGoogleMapsReady()) {
    return;
  }

  final existing = html.document.querySelector(
    'script[data-gmaps-loader="true"]',
  );
  if (existing != null) {
    // Another instance is loading; wait a moment for it to complete.
    // (No direct hook, so poll a few times.)
    for (var i = 0; i < 50; i++) {
      await Future<void>.delayed(const Duration(milliseconds: 100));
      if (isGoogleMapsReady()) {
        return;
      }
    }
    throw StateError('Google Maps JS API did not finish loading.');
  }

  final completer = Completer<void>();

  // Google Maps JS API calls this global when authentication fails.
  // See: https://developers.google.com/maps/documentation/javascript/events#auth-errors
  var authFailed = false;
  void handleAuthFailure() {
    authFailed = true;
    if (!completer.isCompleted) {
      completer.completeError(
        StateError(
          'Google Maps JS API authentication failed. Most common causes: invalid API key, '
          'Maps JavaScript API not enabled in Google Cloud, or HTTP referrer restrictions '
          'do not include this site origin. Check the browser DevTools Console for the '
          'exact Google Maps error (e.g., RefererNotAllowedMapError, ApiNotActivatedMapError).',
        ),
      );
    }
  }

  // Load completion callback; this is invoked when the API finishes initializing.
  final callbackName =
      '__flutterGMapsLoaded_${DateTime.now().microsecondsSinceEpoch}';
  var completionStarted = false;
  Future<void> completeWhenReady() async {
    // In theory, the callback means the API is ready. In practice we want to
    // ensure the plugin-required symbols exist (e.g. MapTypeId.ROADMAP).
    for (var i = 0; i < 40; i++) {
      if (completer.isCompleted) {
        return;
      }

      if (isGoogleMapsReady()) {
        completer.complete();
        return;
      }

      await Future<void>.delayed(const Duration(milliseconds: 50));
    }

    if (!completer.isCompleted) {
      completer.completeError(
        StateError(
          'Google Maps JS API callback fired but required symbols are still missing '
          '(expected `google.maps.MapTypeId.ROADMAP`). This usually indicates the API '
          'did not initialize correctly. Check the browser DevTools Console for the '
          'exact Google Maps error.',
        ),
      );
    }
  }

  void handleLoaded() {
    if (completer.isCompleted || completionStarted) {
      return;
    }
    completionStarted = true;
    unawaited(completeWhenReady());
  }

  // Register global hooks before inserting the <script>.
  globalContext['gm_authFailure'] = handleAuthFailure.toJS;
  globalContext[callbackName] = handleLoaded.toJS;
  final script = html.ScriptElement()
    ..type = 'text/javascript'
    ..async = true
    ..dataset['gmapsLoader'] = 'true'
    ..src =
        'https://maps.googleapis.com/maps/api/js?key=$apiKey&v=weekly&callback=$callbackName';

  script.onError.listen((_) {
    if (!completer.isCompleted) {
      completer.completeError(
        StateError(
          'Failed to load Google Maps JS API script. Check network access and whether '
          'your API key allows Maps JavaScript API for this origin.',
        ),
      );
    }
  });
  script.onLoad.listen((_) {
    // Do not complete here; the API may still fail auth after load.
    // We'll complete via callbackName or gm_authFailure.
  });

  html.document.head?.append(script);

  try {
    // If neither callback nor gm_authFailure triggers, time out with a helpful message.
    return await completer.future.timeout(
      const Duration(seconds: 12),
      onTimeout: () {
        if (authFailed) {
          throw StateError(
            'Google Maps JS API authentication failed. See DevTools Console for details.',
          );
        }
        throw StateError(
          'Timed out waiting for Google Maps JS API to initialize. This can happen if the '
          'script is blocked by CSP/adblock or the API key is rejected. Check DevTools Console.',
        );
      },
    );
  } finally {
    // Best-effort cleanup. Replace with a no-op so a late callback doesn't error.
    try {
      globalContext[callbackName] = (() {}).toJS;
    } catch (_) {}
  }
}
