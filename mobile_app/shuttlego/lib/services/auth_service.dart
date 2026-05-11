import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_database/firebase_database.dart';

import '../models/user_profile.dart';

class AuthService {
  const AuthService({FirebaseAuth? auth, FirebaseDatabase? database})
    : _auth = auth,
      _database = database;

  final FirebaseAuth? _auth;
  final FirebaseDatabase? _database;

  FirebaseAuth get auth => _auth ?? FirebaseAuth.instance;
  FirebaseDatabase get database => _database ?? FirebaseDatabase.instance;

  DatabaseReference get _usersRef => database.ref().child('users');

  Future<UserCredential> signInWithEmailAndPassword({
    required String email,
    required String password,
  }) {
    return auth.signInWithEmailAndPassword(
      email: email.trim(),
      password: password,
    );
  }

  Future<void> signOut() => auth.signOut();

  /// Fetches a profile once from `users/{uid}`.
  Future<UserProfile?> getUserProfile(String uid) async {
    final snapshot = await _usersRef.child(uid).get();
    final value = snapshot.value;
    if (value is! Map) return null;
    return UserProfile.fromMap(Map<String, Object?>.from(value));
  }

  /// Realtime stream of `users/{uid}` updates.
  Stream<UserProfile?> watchUserProfile(String uid) {
    return _usersRef.child(uid).onValue.map((event) {
      final value = event.snapshot.value;
      if (value is! Map) return null;
      return UserProfile.fromMap(Map<String, Object?>.from(value));
    });
  }

  /// Creates a Firebase Auth user and stores additional profile details in
  /// Realtime Database at `users/{uid}`.
  Future<void> signUpWithProfile({
    required String email,
    required String password,
    required String fullName,
    required String role,
    required String roleNumber,
  }) async {
    final credential = await auth.createUserWithEmailAndPassword(
      email: email.trim(),
      password: password,
    );

    final user = credential.user;
    if (user == null) {
      throw FirebaseAuthException(
        code: 'unknown',
        message: 'Account creation failed. Please try again.',
      );
    }

    try {
      await _usersRef.child(user.uid).set({
        'uid': user.uid,
        'role': role,
        'fullName': fullName.trim(),
        'email': email.trim(),
        'roleNumber': roleNumber.trim(),
        'createdAt': ServerValue.timestamp,
      });
    } on FirebaseException catch (e) {
      // If the profile cannot be saved, roll back the auth user creation to
      // avoid leaving a "half-created" account.
      try {
        await user.delete();
      } catch (_) {
        // Ignore rollback failures.
      }

      final details = (e.message == null || e.message!.trim().isEmpty)
          ? ''
          : ' ${e.message}';

      final message = switch (e.code) {
        'permission-denied' =>
          'Sign up failed because the database denied access. Update your Realtime Database rules to allow authenticated users to write to users/{uid}.',
        _ =>
          'Sign up failed while saving your profile to the database (${e.code}).$details',
      };

      throw FirebaseAuthException(
        code: 'profile-write-failed',
        message: message,
      );
    }
  }

  /// Update fields on an existing user profile at `users/{uid}`.
  Future<void> updateUserProfile({
    required String uid,
    String? fullName,
    String? role,
    String? roleNumber,
    String? email,
  }) async {
    final updates = <String, Object?>{};
    if (fullName != null) updates['fullName'] = fullName.trim();
    if (role != null) updates['role'] = role.trim();
    if (roleNumber != null) updates['roleNumber'] = roleNumber.trim();
    if (email != null) updates['email'] = email.trim();

    if (updates.isEmpty) return;

    await _usersRef.child(uid).update(updates);

    // Optionally update FirebaseAuth profile email/displayName when
    // appropriate (best-effort; ignore failures here).
    try {
      final current = auth.currentUser;
      if (current != null) {
        if (email != null && email.trim().isNotEmpty && current.email != email.trim()) {
          await current.updateEmail(email.trim());
        }
        if (fullName != null && fullName.trim().isNotEmpty && current.displayName != fullName.trim()) {
          await current.updateDisplayName(fullName.trim());
        }
      }
    } catch (_) {
      // Ignore - database was updated and that's the source of truth for profile.
    }
  }
}
