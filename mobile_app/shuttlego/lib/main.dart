import 'dart:async';

import 'package:flutter/material.dart';
import 'package:firebase_core/firebase_core.dart';
import 'firebase_options.dart'; // Make sure to import your generated options
import 'screens/auth_gate.dart';
import 'theme/app_theme.dart';

Future<void> main() async {
  await runZonedGuarded<Future<void>>(() async {
    WidgetsFlutterBinding.ensureInitialized();
    await Firebase.initializeApp(
      options: DefaultFirebaseOptions.currentPlatform,
    );

    FlutterError.onError = (details) {
      // Preserve default behavior
      FlutterError.presentError(details);
      // Print the error and stack for diagnostics
      try {
        debugPrint('FlutterError: ${details.exceptionAsString()}');
        debugPrint(details.stack?.toString() ?? '<no stack>');
      } catch (_) {}
    };

    runApp(const MainApp());
  }, (error, stack) {
    try {
      debugPrint('Uncaught zone error: $error');
      debugPrint(stack.toString());
    } catch (_) {}
  });
}

class MainApp extends StatelessWidget {
  const MainApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(seedColor: const Color(0xFF0B3D2E)),
      home: const AuthGate(),
    );
  }
}
