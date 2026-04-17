import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';

import '../services/auth_service.dart';
import '../widgets/app_buttons.dart';
import 'login_screen.dart';

enum AccountRole { student, staff }

class CreateAccountScreen extends StatefulWidget {
  const CreateAccountScreen({super.key});

  @override
  State<CreateAccountScreen> createState() => _CreateAccountScreenState();
}

class _CreateAccountScreenState extends State<CreateAccountScreen> {
  final _formKey = GlobalKey<FormState>();

  AccountRole _role = AccountRole.student;
  bool _isSubmitting = false;

  final _fullNameController = TextEditingController();
  final _emailController = TextEditingController();
  final _roleNumberController = TextEditingController();
  final _passwordController = TextEditingController();
  final _confirmPasswordController = TextEditingController();

  bool _obscurePassword = true;
  bool _obscureConfirmPassword = true;

  @override
  void dispose() {
    _fullNameController.dispose();
    _emailController.dispose();
    _roleNumberController.dispose();
    _passwordController.dispose();
    _confirmPasswordController.dispose();
    super.dispose();
  }

  String get _roleNumberLabel =>
      _role == AccountRole.student ? 'Student number' : 'Staff number';

  String get _roleNumberHint => _role == AccountRole.student
      ? 'Enter your Student number'
      : 'Enter your Staff number';

  InputDecoration _decoration(BuildContext context, {required String hint}) {
    final scheme = Theme.of(context).colorScheme;
    final borderColor = Colors.grey.shade300;
    return InputDecoration(
      hintText: hint,
      isDense: true,
      filled: true,
      // Keep input surfaces neutral (avoid seed-color tint).
      fillColor: Colors.grey.shade100,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(8),
        borderSide: BorderSide(color: borderColor),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(8),
        borderSide: BorderSide(color: borderColor),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(8),
        borderSide: BorderSide(color: scheme.primary, width: 1.5),
      ),
      contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
    );
  }

  Widget _requiredLabel(String text) {
    final scheme = Theme.of(context).colorScheme;
    final style = Theme.of(
      context,
    ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600);
    return RichText(
      text: TextSpan(
        style: style?.copyWith(color: scheme.onSurface),
        children: [
          TextSpan(text: text),
          TextSpan(
            text: ' *',
            style: TextStyle(color: scheme.error),
          ),
        ],
      ),
    );
  }

  Future<void> _submit() async {
    FocusScope.of(context).unfocus();

    final isValid = _formKey.currentState?.validate() ?? false;
    if (!isValid) return;

    setState(() => _isSubmitting = true);

    try {
      await const AuthService().signUpWithProfile(
        email: _emailController.text,
        password: _passwordController.text,
        fullName: _fullNameController.text,
        role: _role.name,
        roleNumber: _roleNumberController.text,
      );

      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Account created successfully.')),
      );

      // Return to the AuthGate so it can show the Dashboard.
      Navigator.of(context).popUntil((route) => route.isFirst);
    } on Exception catch (e) {
      if (!mounted) return;
      if (kDebugMode) {
        debugPrint('CreateAccountScreen signUp error: $e');
        if (e is FirebaseAuthException) {
          debugPrint(
            'FirebaseAuthException(code=${e.code}, message=${e.message})',
          );
        }
        debugPrintStack(stackTrace: StackTrace.current);
      }
      final message = _friendlyErrorMessage(e);
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(message)));
    } finally {
      if (mounted) setState(() => _isSubmitting = false);
    }
  }

  String _friendlyErrorMessage(Object error) {
    if (error is FirebaseAuthException) {
      final code = error.code.startsWith('auth/')
          ? error.code.substring('auth/'.length)
          : error.code;

      return switch (code) {
        'email-already-in-use' => 'This email is already in use.',
        'invalid-email' => 'Please enter a valid email address.',
        'weak-password' => 'Password is too weak.',
        'missing-email' => 'Please enter your email address.',
        'missing-password' => 'Please enter your password.',
        'configuration-not-found' =>
          'Firebase Authentication is not set up for this project. In Firebase Console → Authentication, click Get started and enable Email/Password.',
        'operation-not-allowed' =>
          'Email/Password sign-up is not enabled for this Firebase project. Go to Firebase Console → Authentication → Sign-in method and enable Email/Password.',
        'profile-write-failed' =>
          error.message ??
              'Account was created, but we could not save your profile. Check Realtime Database rules and try again.',
        _ =>
          (error.message == null || error.message!.trim().isEmpty)
              ? 'Sign up failed ($code).'
              : 'Sign up failed ($code). ${error.message}',
      };
    }

    // If something else throws, show at least the type in debug builds.
    if (kDebugMode) {
      return 'Sign up failed (${error.runtimeType}). Check debug console.';
    }

    return 'Could not create account.';
  }

  @override
  Widget build(BuildContext context) {
    final baseTheme = Theme.of(context);
    final scheme = baseTheme.colorScheme;
    final whiteScheme = scheme.copyWith(
      // Prevent Material 3 surface tinting from the green seed color.
      surface: Colors.white,
      surfaceTint: Colors.transparent,
    );

    return Theme(
      data: baseTheme.copyWith(
        scaffoldBackgroundColor: Colors.white,
        colorScheme: whiteScheme,
      ),
      child: Scaffold(
        backgroundColor: Colors.white,
        body: SafeArea(
          child: CustomScrollView(
            physics: const ClampingScrollPhysics(),
            slivers: [
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(20, 14, 20, 18),
                sliver: SliverFillRemaining(
                  hasScrollBody: false,
                  child: Form(
                    key: _formKey,
                    autovalidateMode: AutovalidateMode.onUserInteraction,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Create account',
                          style: Theme.of(context).textTheme.headlineSmall
                              ?.copyWith(
                                fontWeight: FontWeight.w700,
                                color: scheme.onSurface,
                              ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          'Select your role and fill in the details',
                          style: Theme.of(context).textTheme.bodySmall
                              ?.copyWith(color: scheme.onSurfaceVariant),
                        ),
                        const SizedBox(height: 12),
                        Row(
                          children: [
                            Expanded(
                              child: _RoleCard(
                                title: 'Student',
                                subtitle: 'Enrolled student',
                                icon: Icons.school_outlined,
                                selected: _role == AccountRole.student,
                                onTap: () {
                                  if (_role == AccountRole.student) {
                                    return;
                                  }
                                  setState(() {
                                    _role = AccountRole.student;
                                    _roleNumberController.clear();
                                  });
                                },
                              ),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: _RoleCard(
                                title: 'Staff',
                                subtitle: 'University Staff',
                                icon: Icons.work_outline,
                                selected: _role == AccountRole.staff,
                                onTap: () {
                                  if (_role == AccountRole.staff) {
                                    return;
                                  }
                                  setState(() {
                                    _role = AccountRole.staff;
                                    _roleNumberController.clear();
                                  });
                                },
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),

                        _requiredLabel('Full name'),
                        const SizedBox(height: 4),
                        TextFormField(
                          controller: _fullNameController,
                          textInputAction: TextInputAction.next,
                          decoration: _decoration(
                            context,
                            hint: 'Enter your Full name',
                          ),
                          validator: (value) {
                            final v = value?.trim() ?? '';
                            if (v.isEmpty) return 'Full name is required.';
                            return null;
                          },
                        ),
                        const SizedBox(height: 10),

                        _requiredLabel('Email'),
                        const SizedBox(height: 4),
                        TextFormField(
                          controller: _emailController,
                          keyboardType: TextInputType.emailAddress,
                          textInputAction: TextInputAction.next,
                          decoration: _decoration(
                            context,
                            hint: 'Enter your email',
                          ),
                          validator: (value) {
                            final v = (value ?? '').trim();
                            if (v.isEmpty) return 'Email is required.';
                            final looksValid = RegExp(
                              r'^[^@\s]+@[^@\s]+\.[^@\s]+$',
                            ).hasMatch(v);
                            if (!looksValid) {
                              return 'Enter a valid email address.';
                            }
                            return null;
                          },
                        ),
                        const SizedBox(height: 10),

                        _requiredLabel(_roleNumberLabel),
                        const SizedBox(height: 4),
                        TextFormField(
                          controller: _roleNumberController,
                          textInputAction: TextInputAction.next,
                          decoration: _decoration(
                            context,
                            hint: _roleNumberHint,
                          ),
                          validator: (value) {
                            final v = value?.trim() ?? '';
                            if (v.isEmpty) {
                              return '$_roleNumberLabel is required.';
                            }
                            return null;
                          },
                        ),
                        const SizedBox(height: 10),

                        _requiredLabel('Password'),
                        const SizedBox(height: 4),
                        TextFormField(
                          controller: _passwordController,
                          obscureText: _obscurePassword,
                          textInputAction: TextInputAction.next,
                          decoration:
                              _decoration(
                                context,
                                hint: 'create password',
                              ).copyWith(
                                suffixIcon: IconButton(
                                  visualDensity: VisualDensity.compact,
                                  onPressed: () => setState(
                                    () => _obscurePassword = !_obscurePassword,
                                  ),
                                  icon: Icon(
                                    _obscurePassword
                                        ? Icons.visibility_off_outlined
                                        : Icons.visibility_outlined,
                                  ),
                                ),
                              ),
                          validator: (value) {
                            final v = value ?? '';
                            if (v.isEmpty) return 'Password is required.';
                            if (v.length < 6) {
                              return 'Password must be at least 6 characters.';
                            }
                            return null;
                          },
                        ),
                        const SizedBox(height: 10),

                        _requiredLabel('Confirm Password'),
                        const SizedBox(height: 4),
                        TextFormField(
                          controller: _confirmPasswordController,
                          obscureText: _obscureConfirmPassword,
                          textInputAction: TextInputAction.done,
                          decoration:
                              _decoration(
                                context,
                                hint: 'confirm password',
                              ).copyWith(
                                suffixIcon: IconButton(
                                  visualDensity: VisualDensity.compact,
                                  onPressed: () => setState(
                                    () => _obscureConfirmPassword =
                                        !_obscureConfirmPassword,
                                  ),
                                  icon: Icon(
                                    _obscureConfirmPassword
                                        ? Icons.visibility_off_outlined
                                        : Icons.visibility_outlined,
                                  ),
                                ),
                              ),
                          validator: (value) {
                            final v = value ?? '';
                            if (v.isEmpty) {
                              return 'Confirm password is required.';
                            }
                            if (v != _passwordController.text) {
                              return 'Passwords do not match.';
                            }
                            return null;
                          },
                          onFieldSubmitted: (_) =>
                              _isSubmitting ? null : _submit(),
                        ),

                        const Spacer(),

                        AppPrimaryButton(
                          label: 'Sign Up',
                          onPressed: _isSubmitting ? null : _submit,
                          isLoading: _isSubmitting,
                        ),

                        const SizedBox(height: 10),
                        Center(
                          child: Wrap(
                            alignment: WrapAlignment.center,
                            crossAxisAlignment: WrapCrossAlignment.center,
                            spacing: 4,
                            children: [
                              Text(
                                'Already have an account?',
                                style: Theme.of(context).textTheme.bodySmall,
                              ),
                              TextButton(
                                style: TextButton.styleFrom(
                                  visualDensity: VisualDensity.compact,
                                  padding: const EdgeInsets.symmetric(
                                    horizontal: 8,
                                  ),
                                ),
                                onPressed: () {
                                  Navigator.of(context).pushReplacement(
                                    MaterialPageRoute(
                                      builder: (_) => const LoginScreen(),
                                    ),
                                  );
                                },
                                child: const Text('login'),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _RoleCard extends StatelessWidget {
  const _RoleCard({
    required this.title,
    required this.subtitle,
    required this.icon,
    required this.selected,
    required this.onTap,
  });

  final String title;
  final String subtitle;
  final IconData icon;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final borderColor = selected ? scheme.primary : scheme.outlineVariant;
    final titleColor = selected ? scheme.primary : scheme.onSurface;

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(10),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: borderColor, width: selected ? 1.6 : 1),
          color: scheme.surface,
        ),
        child: Row(
          children: [
            Icon(icon, color: titleColor, size: 20),
            const SizedBox(width: 8),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.titleSmall?.copyWith(
                      fontWeight: FontWeight.w600,
                      color: titleColor,
                    ),
                  ),
                  const SizedBox(height: 1),
                  Text(
                    subtitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
