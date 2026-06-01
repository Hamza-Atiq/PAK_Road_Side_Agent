import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../theme/colors.dart';

class LandingScreen extends StatelessWidget {
  const LandingScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const SizedBox(height: 16),
              _Wordmark(),
              const Spacer(),
              const Text(
                'Help on the road,',
                style: TextStyle(
                  fontSize: 36,
                  fontWeight: FontWeight.w800,
                  height: 1.1,
                  color: RsColors.textPrimary,
                ),
              ),
              const Text(
                'in minutes.',
                style: TextStyle(
                  fontSize: 36,
                  fontWeight: FontWeight.w800,
                  height: 1.1,
                  color: RsColors.brandPrimary,
                ),
              ),
              const SizedBox(height: 12),
              const Text(
                'Stranded? RoadSide\'s AI agents diagnose, dispatch, and track until help arrives.',
                style: TextStyle(fontSize: 16, color: RsColors.textMuted, height: 1.4),
              ),
              const Spacer(),
              ElevatedButton(
                onPressed: () => context.go('/register'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: RsColors.emergency,
                  padding: const EdgeInsets.symmetric(vertical: 18),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                ),
                child: const Text(
                  '🆘 Get help now',
                  style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700, color: Colors.white),
                ),
              ),
              const SizedBox(height: 12),
              TextButton(
                onPressed: () => context.go('/login'),
                child: const Text('I have an account'),
              ),
              const SizedBox(height: 8),
              const _TrustStrip(),
              const SizedBox(height: 8),
            ],
          ),
        ),
      ),
    );
  }
}

class _Wordmark extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Container(
          width: 36,
          height: 36,
          decoration: BoxDecoration(
            color: RsColors.brandPrimary,
            borderRadius: BorderRadius.circular(10),
          ),
          child: const Icon(Icons.warning_amber_rounded, color: RsColors.warning, size: 22),
        ),
        const SizedBox(width: 10),
        const Text(
          'RoadSide',
          style: TextStyle(
            fontSize: 22,
            fontWeight: FontWeight.w800,
            color: RsColors.textPrimary,
          ),
        ),
      ],
    );
  }
}

class _TrustStrip extends StatelessWidget {
  const _TrustStrip();

  @override
  Widget build(BuildContext context) {
    final items = [
      ('🛡️', 'Verified providers'),
      ('📍', 'Live tracking'),
      ('💳', 'No charge unless help arrives'),
    ];
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceAround,
      children: items
          .map(
            (it) => Expanded(
              child: Column(
                children: [
                  Text(it.$1, style: const TextStyle(fontSize: 20)),
                  const SizedBox(height: 4),
                  Text(
                    it.$2,
                    textAlign: TextAlign.center,
                    style: const TextStyle(fontSize: 10, color: RsColors.textMuted),
                  ),
                ],
              ),
            ),
          )
          .toList(),
    );
  }
}
