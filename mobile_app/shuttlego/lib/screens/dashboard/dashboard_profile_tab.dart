import 'dart:ui';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';

import '../../models/user_profile.dart';
import '../../services/auth_service.dart';

class DashboardProfileTab extends StatefulWidget {
  const DashboardProfileTab({super.key});

  @override
  State<DashboardProfileTab> createState() => _DashboardProfileTabState();
}

class _DashboardProfileTabState extends State<DashboardProfileTab> {
  final _service = const AuthService();
  bool _editing = false;
  bool _saving = false;

  final _fullNameCtl = TextEditingController();
  final _emailCtl = TextEditingController();
  final _roleNumberCtl = TextEditingController();

  @override
  void dispose() {
    _fullNameCtl.dispose();
    _emailCtl.dispose();
    _roleNumberCtl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final user = FirebaseAuth.instance.currentUser;
    if (user == null) return const Center(child: Text('Not signed in'));

    final bgStart = const Color(0xFFF6FFFA); // very soft green-white
    final bgEnd = const Color(0xFFFFFFFF);
    final accent = const Color(0xFF2EA86E); // soft green

    return StreamBuilder<UserProfile?>(
      stream: _service.watchUserProfile(user.uid),
      builder: (context, snapshot) {
        final profile = snapshot.data;
        if (snapshot.connectionState == ConnectionState.waiting && profile == null) {
          return const Center(child: CircularProgressIndicator());
        }

        // Populate controllers only when not actively editing to avoid
        // clobbering user input while they edit.
        if (!_editing) {
          _fullNameCtl.text = profile?.fullName ?? user.displayName ?? '';
          _emailCtl.text = profile?.email ?? user.email ?? '';
          _roleNumberCtl.text = profile?.roleNumber ?? '';
        }

        return Container(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [bgStart, bgEnd],
            ),
          ),
          child: SafeArea(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 18),
              child: Column(
                children: [
                  // Header area
                  _buildHeader(context, profile, user.photoURL, accent),
                  const SizedBox(height: 18),

                  // Cards area
                  Expanded(
                    child: ListView(
                      children: [
                        _glassCard(
                          child: _buildAccountSection(context, profile),
                        ),
                        const SizedBox(height: 12),
                        
                        _glassCard(
                          child: _buildActionsSection(context),
                        ),
                        const SizedBox(height: 32),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildHeader(BuildContext context, UserProfile? profile, String? photoUrl, Color accent) {
    return Stack(
      children: [
        // Edit button overlayed top-right
        Positioned(
          right: 0,
          top: 0,
          child: IconButton(
            onPressed: () => setState(() => _editing = !_editing),
            icon: Icon(_editing ? Icons.close : Icons.edit, color: accent),
          ),
        ),
        // Centered avatar + name + role
        Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const SizedBox(height: 8),
            Container(
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withOpacity(0.08),
                    blurRadius: 18,
                    offset: const Offset(0, 8),
                  ),
                ],
              ),
              child: CircleAvatar(
                radius: 40,
                backgroundColor: accent.withOpacity(0.12),
                foregroundImage: photoUrl != null ? NetworkImage(photoUrl) : null,
                child: photoUrl == null
                    ? Text(
                        (profile?.firstName.isNotEmpty == true ? profile!.firstName.characters.first : 'U').toUpperCase(),
                        style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700),
                      )
                    : null,
              ),
            ),
            const SizedBox(height: 14),
            Text(
              profile?.fullName.isNotEmpty == true ? profile!.fullName : (FirebaseAuth.instance.currentUser?.displayName ?? 'User'),
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 8),
            if (profile?.role.isNotEmpty == true)
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                decoration: BoxDecoration(
                  color: Colors.white.withOpacity(0.7),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(profile!.role, style: Theme.of(context).textTheme.labelLarge?.copyWith(fontWeight: FontWeight.w700)),
              ),
            if (profile?.roleNumber.isNotEmpty == true) ...[
              const SizedBox(height: 6),
              Text('#${profile!.roleNumber}', style: Theme.of(context).textTheme.bodySmall?.copyWith(color: Colors.black54)),
            ],
          ],
        ),
      ],
    );
  }

  Widget _glassCard({required Widget child}) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(16),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 8, sigmaY: 8),
        child: Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: Colors.white.withOpacity(0.75),
            borderRadius: BorderRadius.circular(16),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withOpacity(0.06),
                blurRadius: 18,
                offset: const Offset(0, 8),
              ),
            ],
            border: Border.all(color: Colors.white.withOpacity(0.6)),
          ),
          child: child,
        ),
      ),
    );
  }

  Widget _buildAccountSection(BuildContext context, UserProfile? profile) {
    final scheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Account', style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
        const SizedBox(height: 8),
        TextField(
          controller: _fullNameCtl,
          enabled: false,
          readOnly: true,
          decoration: InputDecoration(
            labelText: 'Full name',
            prefixIcon: const Icon(Icons.person_outline),
            filled: true,
            fillColor: Colors.white,
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
          ),
        ),
        const SizedBox(height: 10),
        TextField(
          controller: _emailCtl,
          enabled: _editing,
          keyboardType: TextInputType.emailAddress,
          decoration: InputDecoration(
            labelText: 'Email',
            prefixIcon: const Icon(Icons.email_outlined),
            filled: true,
            fillColor: Colors.white,
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
          ),
        ),
        const SizedBox(height: 10),
        TextField(
          controller: _roleNumberCtl,
          enabled: false,
          readOnly: true,
          decoration: InputDecoration(
            labelText: 'Role number',
            prefixIcon: const Icon(Icons.badge_outlined),
            filled: true,
            fillColor: Colors.white,
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
          ),
        ),
        const SizedBox(height: 14),
        if (_editing)
          Row(
            children: [
              Expanded(
                child: FilledButton(
                  onPressed: _saving ? null : _saveProfile,
                  child: _saving ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2)) : const Text('Save'),
                ),
              ),
              const SizedBox(width: 10),
              OutlinedButton(
                onPressed: _saving ? null : () => setState(() => _editing = false),
                child: const Text('Cancel'),
              ),
            ],
          ),
      ],
    );
  }

  

  Widget _buildActionsSection(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Actions', style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
        const SizedBox(height: 8),
        ListTile(
          contentPadding: EdgeInsets.zero,
          leading: const Icon(Icons.logout_outlined, color: Colors.redAccent),
          title: const Text('Sign out'),
          onTap: () async {
            await _service.signOut();
          },
        ),
        ListTile(
          contentPadding: EdgeInsets.zero,
          leading: const Icon(Icons.delete_outline, color: Colors.redAccent),
          title: const Text('Delete account'),
          onTap: () {},
        ),
      ],
    );
  }

  Future<void> _saveProfile() async {
    final user = FirebaseAuth.instance.currentUser;
    if (user == null) return;

    setState(() => _saving = true);
    try {
      await _service.updateUserProfile(
        uid: user.uid,
        email: _emailCtl.text.trim(),
      );

      if (!mounted) return;
      setState(() {
        _editing = false;
      });
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Profile saved.')));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Save failed: ${e.toString()}')));
    } finally {
      if (!mounted) return;
      setState(() => _saving = false);
    }
  }
}
