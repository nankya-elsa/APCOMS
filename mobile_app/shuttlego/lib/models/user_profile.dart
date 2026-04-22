class UserProfile {
  const UserProfile({
    required this.uid,
    required this.fullName,
    required this.email,
    required this.role,
    required this.roleNumber,
    required this.createdAt,
  });

  final String uid;
  final String fullName;
  final String email;
  final String role;
  final String roleNumber;
  final int? createdAt;

  String get firstName {
    final trimmed = fullName.trim();
    if (trimmed.isEmpty) return '';
    final parts = trimmed.split(RegExp(r'\s+'));
    return parts.isEmpty ? '' : parts.first;
  }

  factory UserProfile.fromMap(Map<String, Object?> map) {
    return UserProfile(
      uid: (map['uid'] as String?) ?? '',
      fullName: (map['fullName'] as String?) ?? '',
      email: (map['email'] as String?) ?? '',
      role: (map['role'] as String?) ?? '',
      roleNumber: (map['roleNumber'] as String?) ?? '',
      createdAt: (map['createdAt'] as int?),
    );
  }
}
