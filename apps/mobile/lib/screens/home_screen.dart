import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../services/providers.dart';
import '../theme/colors.dart';

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(authUserProvider).user;
    return Scaffold(
      appBar: AppBar(
        title: const Text('RoadSide'),
        actions: [
          IconButton(
            tooltip: 'History',
            onPressed: () => context.push('/history'),
            icon: const Icon(Icons.history),
          ),
          IconButton(
            tooltip: 'Profile',
            onPressed: () => context.push('/profile'),
            icon: const Icon(Icons.person_outline),
          ),
        ],
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (user?.name != null) ...[
                Text(
                  'Hi, ${user!.name!.split(' ').first} 👋',
                  style: const TextStyle(
                      fontSize: 26, fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 4),
                const Text(
                  'Help is one tap away.',
                  style: TextStyle(color: RsColors.textMuted, fontSize: 15),
                ),
                const SizedBox(height: 20),
              ],
              Expanded(
                child: Center(
                  child: GestureDetector(
                    onTap: () => context.push('/sos'),
                    child: Container(
                      width: 240,
                      height: 240,
                      decoration: BoxDecoration(
                        color: RsColors.emergency,
                        shape: BoxShape.circle,
                        boxShadow: [
                          BoxShadow(
                            color: RsColors.emergency.withOpacity(0.35),
                            blurRadius: 36,
                            spreadRadius: 6,
                          ),
                        ],
                      ),
                      child: const Center(
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text('🚗', style: TextStyle(fontSize: 60)),
                            SizedBox(height: 8),
                            Text(
                              'Get Help',
                              style: TextStyle(
                                color: Colors.white,
                                fontSize: 26,
                                fontWeight: FontWeight.w800,
                                letterSpacing: 1,
                              ),
                            ),
                            SizedBox(height: 2),
                            Text(
                              'Tap to request assistance',
                              style: TextStyle(color: Colors.white70, fontSize: 12),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ),
              const _QuickRow(),
              const SizedBox(height: 8),
            ],
          ),
        ),
      ),
    );
  }
}

class _QuickRow extends StatelessWidget {
  const _QuickRow();

  @override
  Widget build(BuildContext context) {
    final items = [
      ('🛡️', 'Verified'),
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
                  Text(it.$1, style: const TextStyle(fontSize: 22)),
                  const SizedBox(height: 4),
                  Text(it.$2,
                      textAlign: TextAlign.center,
                      style:
                          const TextStyle(fontSize: 11, color: RsColors.textMuted)),
                ],
              ),
            ),
          )
          .toList(),
    );
  }
}
