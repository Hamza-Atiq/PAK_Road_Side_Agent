import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../services/providers.dart';
import '../theme/colors.dart';

class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(authUserProvider).user;
    return Scaffold(
      appBar: AppBar(title: const Text('Profile')),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const SizedBox(height: 12),
              CircleAvatar(
                radius: 40,
                backgroundColor: RsColors.brandPrimary.withOpacity(0.12),
                child: const Icon(Icons.person, size: 44, color: RsColors.brandPrimary),
              ),
              const SizedBox(height: 12),
              Center(
                child: Text(
                  user?.name ?? 'Roadside member',
                  style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800),
                ),
              ),
              Center(
                child: Text(
                  user?.phone ?? '',
                  style: const TextStyle(color: RsColors.textMuted),
                ),
              ),
              const SizedBox(height: 28),
              const _Item(icon: Icons.shield_outlined, label: 'Account verified'),
              const _Item(icon: Icons.privacy_tip_outlined, label: 'Privacy policy'),
              const _Item(icon: Icons.help_outline, label: 'Help & support'),
              const Spacer(),
              OutlinedButton.icon(
                onPressed: () async {
                  await ref.read(authUserProvider.notifier).signOut();
                  if (context.mounted) context.go('/');
                },
                icon: const Icon(Icons.logout, color: RsColors.emergency),
                label: const Text('Sign out',
                    style: TextStyle(color: RsColors.emergency)),
                style: OutlinedButton.styleFrom(
                  side: const BorderSide(color: RsColors.emergency),
                  padding: const EdgeInsets.symmetric(vertical: 14),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Item extends StatelessWidget {
  const _Item({required this.icon, required this.label});
  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: Icon(icon, color: RsColors.textMuted),
      title: Text(label),
      trailing: const Icon(Icons.chevron_right, color: RsColors.textMuted),
      contentPadding: EdgeInsets.zero,
    );
  }
}
