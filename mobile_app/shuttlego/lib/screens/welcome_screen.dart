import 'package:flutter/material.dart';

import 'create_account_screen.dart';
import 'login_screen.dart';
import '../widgets/app_buttons.dart';

class WelcomeScreen extends StatelessWidget {
  const WelcomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Stack(
        children: [
          Positioned.fill(
            child: Image.asset(
              'assets/images/backgroundimage.png',
              fit: BoxFit.cover,
            ),
          ),
          Positioned.fill(
            child: ColoredBox(color: Colors.white.withValues(alpha: 0.85)),
          ),
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(24, 0, 24, 30),
              child: LayoutBuilder(
                builder: (context, constraints) {
                  final logoBoxHeight = (constraints.maxWidth * 0.54).clamp(
                    160.0,
                    220.0,
                  );

                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const SizedBox(height: 40),
                      SizedBox(
                        width: double.infinity,
                        height: logoBoxHeight,
                        child: ClipRect(
                          child: Align(
                            alignment: const Alignment(0.0, -0.35),
                            child: Image.asset(
                              'assets/images/logo.png',
                              width: constraints.maxWidth * 1.55,
                              fit: BoxFit.cover,
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        'Smart Campus\nShuttle Booking',
                        style: Theme.of(context).textTheme.headlineMedium
                            ?.copyWith(
                              fontWeight: FontWeight.w700,
                              fontSize: 30,
                              height: 1.15,
                              color: Colors.black,
                            ),
                      ),
                      const SizedBox(height: 18),
                      ConstrainedBox(
                        constraints: BoxConstraints(
                          maxWidth: constraints.maxWidth * 0.8,
                        ),
                        child: Text(
                          'Book seats, track shuttles in\nreal time and travel smart\nacross campus',
                          style: Theme.of(context).textTheme.bodyMedium
                              ?.copyWith(
                                fontSize: 14,
                                color: const Color(0xFF555555),
                                height: 1.4,
                              ),
                        ),
                      ),
                      const SizedBox(height: 40),
                      AppPrimaryButton(
                        label: 'Login',
                        onPressed: () {
                          Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) => const LoginScreen(),
                            ),
                          );
                        },
                      ),
                      const SizedBox(height: 12),
                      AppSecondaryButton(
                        label: 'Sign Up',
                        onPressed: () {
                          Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) => const CreateAccountScreen(),
                            ),
                          );
                        },
                      ),
                      const Spacer(),
                    ],
                  );
                },
              ),
            ),
          ),
        ],
      ),
    );
  }
}
