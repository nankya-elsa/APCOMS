import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';

import '../widgets/app_buttons.dart';
import '../services/auth_service.dart';
import 'create_account_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();

  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();

  bool _obscurePassword = true;
  bool _isSubmitting = false;
  int _failedAttempts = 0;
  DateTime? _lockoutUntil;
  static const _maxAttempts = 5;
  static const _lockoutSeconds = 60;

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  InputDecoration _decoration(BuildContext context, {required String hint}) {
    final borderColor = Colors.grey.shade300;
    return InputDecoration(
      hintText: hint,
      isDense: true,
      filled: true,
      // Keep the input background neutral (no seed-color tint).
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
        // Keep focus styling neutral too.
        borderSide: const BorderSide(color: Colors.black, width: 1.5),
      ),
      contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
    );
  }

  Future<void> _submit() async {
    FocusScope.of(context).unfocus();

    final isValid = _formKey.currentState?.validate() ?? false;
    if (!isValid) return;

    final now = DateTime.now();
    if (_lockoutUntil != null && now.isBefore(_lockoutUntil!)) {
      final remain = _lockoutUntil!.difference(now).inSeconds;
      await showDialog<void>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Too many attempts'),
          content: Text(
            'Too many failed login attempts. Try again in ${remain}s.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('OK'),
            ),
          ],
        ),
      );
      return;
    }

    setState(() => _isSubmitting = true);
    try {
      await const AuthService().signInWithEmailAndPassword(
        email: _emailController.text,
        password: _passwordController.text,
      );

      if (!mounted) return;
      // Reset failed attempts on successful login
      _failedAttempts = 0;
      _lockoutUntil = null;
      Navigator.of(context).popUntil((route) => route.isFirst);
    } on Exception catch (e) {
      if (!mounted) return;
      // Increment failed attempts and trigger lockout if limit reached.
      _failedAttempts++;
      if (_failedAttempts >= _maxAttempts) {
        _lockoutUntil = DateTime.now().add(
          const Duration(seconds: _lockoutSeconds),
        );
      }
      await showDialog<void>(
        context: context,
        builder: (context) => AlertDialog(
          content: Text(_friendlyErrorMessage(e), textAlign: TextAlign.center),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('OK'),
            ),
          ],
        ),
      );
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
        'user-not-found' => 'No account found for this email.',
        'wrong-password' => 'Incorrect password. Please try again.',
        'invalid-email' => 'Please enter a valid email address.',
        'invalid-credential' => 'Invalid login details. Please try again.',
        'configuration-not-found' =>
          'Firebase Authentication is not set up for this project. In Firebase Console → Authentication, click Get started and enable Email/Password.',
        _ =>
          ((error.message?.trim().isEmpty) ?? true)
              ? 'Login failed ($code).'
              : 'Login failed ($code). ${error.message}',
      };
    }
    return 'Login failed. Please try again.';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.white,
      body: SafeArea(
        child: CustomScrollView(
          physics: const ClampingScrollPhysics(),
          slivers: [
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(20, 18, 20, 18),
              sliver: SliverFillRemaining(
                hasScrollBody: false,
                child: Form(
                  key: _formKey,
                  autovalidateMode: AutovalidateMode.onUserInteraction,
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Center(
                        child: Image.asset(
                          'assets/images/logo.png',
                          height: 74,
                          fit: BoxFit.contain,
                        ),
                      ),
                      const SizedBox(height: 12),
                      Text(
                        'Welcome back!',
                        style: Theme.of(
                          context,
                        ).textTheme.bodyMedium?.copyWith(color: Colors.black54),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        'Login',
                        style: Theme.of(context).textTheme.headlineSmall
                            ?.copyWith(
                              fontWeight: FontWeight.w700,
                              color: Colors.black,
                            ),
                      ),
                      const SizedBox(height: 18),

                      Text(
                        'Email',
                        style: Theme.of(context).textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.w600,
                          color: Colors.black,
                        ),
                      ),
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
                      const SizedBox(height: 12),

                      Text(
                        'Password',
                        style: Theme.of(context).textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.w600,
                          color: Colors.black,
                        ),
                      ),
                      const SizedBox(height: 4),
                      TextFormField(
                        controller: _passwordController,
                        obscureText: _obscurePassword,
                        textInputAction: TextInputAction.done,
                        decoration:
                            _decoration(
                              context,
                              hint: 'Enter your password',
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
                                  color: Colors.black54,
                                ),
                              ),
                            ),
                        validator: (value) {
                          final v = value ?? '';
                          if (v.isEmpty) return 'Password is required.';
                          return null;
                        },
                        onFieldSubmitted: (_) =>
                            _isSubmitting ? null : _submit(),
                      ),
                      Align(
                        alignment: Alignment.centerRight,
                        child: TextButton(
                          style: TextButton.styleFrom(
                            visualDensity: VisualDensity.compact,
                            padding: const EdgeInsets.symmetric(horizontal: 8),
                            foregroundColor: Colors.black54,
                          ),
                          onPressed: () async {
                            final email = _emailController.text.trim();
                            if (email.isEmpty) {
                              await showDialog<void>(
                                context: context,
                                builder: (context) {
                                  final _dialogEmail = TextEditingController();
                                  return AlertDialog(
                                    title: const Text('Reset password'),
                                    content: TextField(
                                      controller: _dialogEmail,
                                      keyboardType: TextInputType.emailAddress,
                                      decoration: const InputDecoration(
                                        hintText: 'Enter your account email',
                                      ),
                                    ),
                                    actions: [
                                      TextButton(
                                        onPressed: () =>
                                            Navigator.of(context).pop(),
                                        child: const Text('Cancel'),
                                      ),
                                      TextButton(
                                        onPressed: () async {
                                          final e = _dialogEmail.text.trim();
                                          Navigator.of(context).pop();
                                          if (e.isEmpty) return;
                                          final messenger =
                                              ScaffoldMessenger.of(
                                                this.context,
                                              );
                                          messenger.hideCurrentMaterialBanner();
                                          messenger.showMaterialBanner(
                                            MaterialBanner(
                                              backgroundColor: Colors.black,
                                              content: const Text(
                                                'Sending password reset email...',
                                                style: TextStyle(
                                                  color: Colors.white,
                                                ),
                                              ),
                                              leading: const Icon(
                                                Icons.email,
                                                color: Colors.white,
                                              ),
                                              actions: [
                                                TextButton(
                                                  style: TextButton.styleFrom(
                                                    foregroundColor:
                                                        Colors.white,
                                                  ),
                                                  onPressed: () => messenger
                                                      .hideCurrentMaterialBanner(),
                                                  child: const Text('OK'),
                                                ),
                                              ],
                                            ),
                                          );
                                          try {
                                            await const AuthService()
                                                .sendPasswordResetEmail(
                                                  email: e,
                                                );
                                            if (!mounted) return;
                                            messenger
                                                .hideCurrentMaterialBanner();
                                            messenger.showMaterialBanner(
                                              MaterialBanner(
                                                backgroundColor: Colors.black,
                                                content: const Text(
                                                  'Password reset email sent to your inbox. Check your email inbox or spam folder.',
                                                  style: TextStyle(
                                                    color: Colors.white,
                                                  ),
                                                ),
                                                leading: const Icon(
                                                  Icons.email,
                                                  color: Colors.white,
                                                ),
                                                actions: [
                                                  TextButton(
                                                    style: TextButton.styleFrom(
                                                      foregroundColor:
                                                          Colors.white,
                                                    ),
                                                    onPressed: () => messenger
                                                        .hideCurrentMaterialBanner(),
                                                    child: const Text('OK'),
                                                  ),
                                                ],
                                              ),
                                            );
                                            // Persist until user dismisses by tapping OK.
                                          } on FirebaseAuthException catch (
                                            err
                                          ) {
                                            messenger
                                                .hideCurrentMaterialBanner();
                                            if (!mounted) return;
                                            await showDialog<void>(
                                              context: context,
                                              builder: (context) => AlertDialog(
                                                content: Text(
                                                  _friendlyErrorMessage(err),
                                                ),
                                                actions: [
                                                  TextButton(
                                                    onPressed: () =>
                                                        Navigator.of(
                                                          context,
                                                        ).pop(),
                                                    child: const Text('OK'),
                                                  ),
                                                ],
                                              ),
                                            );
                                          }
                                        },
                                        child: const Text('Send'),
                                      ),
                                    ],
                                  );
                                },
                              );
                            } else {
                              final messenger = ScaffoldMessenger.of(
                                this.context,
                              );
                              messenger.hideCurrentMaterialBanner();
                              messenger.showMaterialBanner(
                                MaterialBanner(
                                  backgroundColor: Colors.black,
                                  content: const Text(
                                    'Sending password reset email...',
                                    style: TextStyle(color: Colors.white),
                                  ),
                                  leading: const Icon(
                                    Icons.email,
                                    color: Colors.white,
                                  ),
                                  actions: [
                                    TextButton(
                                      style: TextButton.styleFrom(
                                        foregroundColor: Colors.white,
                                      ),
                                      onPressed: () =>
                                          messenger.hideCurrentMaterialBanner(),
                                      child: const Text('OK'),
                                    ),
                                  ],
                                ),
                              );
                              try {
                                await const AuthService()
                                    .sendPasswordResetEmail(email: email);
                                if (!mounted) return;
                                messenger.hideCurrentMaterialBanner();
                                messenger.showMaterialBanner(
                                  MaterialBanner(
                                    backgroundColor: Colors.black,
                                    content: const Text(
                                      'Password reset email sent to your email. Check your inbox.',
                                      style: TextStyle(color: Colors.white),
                                    ),
                                    leading: const Icon(
                                      Icons.email,
                                      color: Colors.white,
                                    ),
                                    actions: [
                                      TextButton(
                                        style: TextButton.styleFrom(
                                          foregroundColor: Colors.white,
                                        ),
                                        onPressed: () => messenger
                                            .hideCurrentMaterialBanner(),
                                        child: const Text('OK'),
                                      ),
                                    ],
                                  ),
                                );
                                // Persistent banner: remain visible until user taps OK.
                              } on FirebaseAuthException catch (err) {
                                messenger.hideCurrentMaterialBanner();
                                if (!mounted) return;
                                await showDialog<void>(
                                  context: context,
                                  builder: (context) => AlertDialog(
                                    content: Text(_friendlyErrorMessage(err)),
                                    actions: [
                                      TextButton(
                                        onPressed: () =>
                                            Navigator.of(context).pop(),
                                        child: const Text('OK'),
                                      ),
                                    ],
                                  ),
                                );
                              }
                            }
                          },
                          child: const Text('Forgot Password?'),
                        ),
                      ),
                      const SizedBox(height: 6),

                      AppPrimaryButton(
                        label: 'Login',
                        onPressed: _isSubmitting ? null : _submit,
                        isLoading: _isSubmitting,
                      ),

                      const SizedBox(height: 18),

                      Center(
                        child: Wrap(
                          alignment: WrapAlignment.center,
                          crossAxisAlignment: WrapCrossAlignment.center,
                          spacing: 4,
                          children: [
                            Text(
                              "Don't have an account?",
                              style: Theme.of(context).textTheme.bodySmall,
                            ),
                            TextButton(
                              style: TextButton.styleFrom(
                                visualDensity: VisualDensity.compact,
                                padding: const EdgeInsets.symmetric(
                                  horizontal: 8,
                                ),
                                foregroundColor: Colors.black,
                              ),
                              onPressed: () {
                                Navigator.of(context).pushReplacement(
                                  MaterialPageRoute(
                                    builder: (_) => const CreateAccountScreen(),
                                  ),
                                );
                              },
                              child: const Text('Sign up'),
                            ),
                          ],
                        ),
                      ),

                      const SizedBox(height: 12),
                    ],
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
