import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_database/firebase_database.dart';
import 'package:flutter/material.dart';

import 'dashboard/dashboard_home_tab.dart';
import 'dashboard/dashboard_profile_tab.dart';
import 'my_bookings_screen.dart';

class ShuttleOption {
  const ShuttleOption({required this.key, required this.name});
  final String key;
  final String name;
}

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  String _trackedShuttleKey = 'shuttle_001';
  List<ShuttleOption> _availableShuttles = [
    const ShuttleOption(key: 'shuttle_001', name: 'Shuttle 1'),
  ];
  int _tabIndex = 0;

  @override
  void initState() {
    super.initState();
    _loadShuttles();
  }

  Future<void> _loadShuttles() async {
    try {
      final snapshot =
          await FirebaseDatabase.instance.ref('shuttles').get();
      if (!mounted) return;

      debugPrint('=== SHUTTLE LOAD ===');
      debugPrint('snapshot.exists: ${snapshot.exists}');
      debugPrint('snapshot.value type: ${snapshot.value.runtimeType}');
      debugPrint('snapshot.value: ${snapshot.value}');

      if (snapshot.exists && snapshot.value is Map) {
        final raw = Map<String, Object?>.from(snapshot.value as Map);
        debugPrint('raw keys: ${raw.keys.toList()}');

        // Only include keys whose value is a Map (real shuttle nodes).
        // Skips stray string/number fields and test_ entries.
        final options = raw.entries
            .where((e) => e.value is Map && !e.key.startsWith('test_'))
            .map((e) {
          final node = e.value as Map;
          final name = (node['name'] is String)
              ? (node['name'] as String).trim()
              : _prettify(e.key);
          return ShuttleOption(key: e.key, name: name);
        }).toList()
          ..sort((a, b) => a.key.compareTo(b.key));

        debugPrint('shuttle options found: ${options.map((s) => s.key).toList()}');

        if (options.isNotEmpty) {
          setState(() {
            _availableShuttles = options;
            if (!options.any((s) => s.key == _trackedShuttleKey)) {
              _trackedShuttleKey = options.first.key;
            }
          });
        }
      } else {
        debugPrint('Snapshot missing or not a Map — staying on default.');
      }
    } catch (e, st) {
      debugPrint('_loadShuttles error: $e\n$st');
    }
  }

  /// "shuttle_001" → "Shuttle 1", "shuttle_010" → "Shuttle 10"
  static String _prettify(String key) {
    final match = RegExp(r'(\D+)_?0*(\d+)$').firstMatch(key);
    if (match != null) {
      final prefix = match.group(1)!.replaceAll('_', ' ').trim();
      final number = match.group(2)!;
      return '${prefix[0].toUpperCase()}${prefix.substring(1)} $number';
    }
    return key.replaceAll('_', ' ').trim();
  }

  @override
  Widget build(BuildContext context) {
    final user = FirebaseAuth.instance.currentUser;
    if (user == null) {
      return const Scaffold(body: Center(child: Text('Not signed in.')));
    }

    final scheme = Theme.of(context).colorScheme;
    const background = Colors.white;
    const bottomNavBg = Colors.white;

    return Scaffold(
      backgroundColor: background,
      body: SafeArea(
        child: IndexedStack(
          index: _tabIndex,
          children: [
            DashboardHomeTab(
              uid: user.uid,
              trackedShuttleKey: _trackedShuttleKey,
              availableShuttles: _availableShuttles,
              onShuttleChanged: (key) =>
                  setState(() => _trackedShuttleKey = key),
            ),
            const MyBookingsScreen(),
            const DashboardProfileTab(),
          ],
        ),
      ),
      bottomNavigationBar: BottomNavigationBar(
        backgroundColor: bottomNavBg,
        currentIndex: _tabIndex,
        onTap: (index) => setState(() => _tabIndex = index),
        type: BottomNavigationBarType.fixed,
        selectedItemColor: scheme.primary,
        unselectedItemColor: Colors.black54,
        items: const [
          BottomNavigationBarItem(
            icon: Icon(Icons.home_outlined),
            activeIcon: Icon(Icons.home),
            label: 'Home',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.confirmation_number_outlined),
            activeIcon: Icon(Icons.confirmation_number),
            label: 'Bookings',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.person_outline),
            activeIcon: Icon(Icons.person),
            label: 'Profile',
          ),
        ],
      ),
    );
  }
}