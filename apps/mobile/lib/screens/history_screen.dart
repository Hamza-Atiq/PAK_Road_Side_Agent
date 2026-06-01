import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../models/models.dart';
import '../services/providers.dart';
import '../theme/colors.dart';

class HistoryScreen extends ConsumerStatefulWidget {
  const HistoryScreen({super.key});

  @override
  ConsumerState<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends ConsumerState<HistoryScreen> {
  List<Incident>? _items;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final items = await ref.read(incidentsServiceProvider).listMine();
      if (mounted) setState(() => _items = items);
    } catch (_) {
      if (mounted) setState(() => _error = 'Could not load history.');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Your incidents')),
      body: RefreshIndicator(
        onRefresh: _load,
        child: _error != null
            ? ListView(children: [
                const SizedBox(height: 80),
                Center(child: Text(_error!)),
              ])
            : _items == null
                ? const Center(child: CircularProgressIndicator())
                : _items!.isEmpty
                    ? ListView(children: const [
                        SizedBox(height: 100),
                        Center(child: Text('No incidents yet.')),
                      ])
                    : ListView.separated(
                        padding: const EdgeInsets.all(16),
                        itemCount: _items!.length,
                        separatorBuilder: (_, __) => const SizedBox(height: 8),
                        itemBuilder: (_, i) {
                          final inc = _items![i];
                          return InkWell(
                            onTap: () => context.go('/incidents/${inc.id}'),
                            borderRadius: BorderRadius.circular(12),
                            child: Container(
                              padding: const EdgeInsets.all(14),
                              decoration: BoxDecoration(
                                color: Colors.white,
                                border: Border.all(color: const Color(0xFFE2E8F0)),
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: Row(
                                children: [
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Text(
                                          inc.serviceType ?? 'Incident',
                                          style: const TextStyle(
                                              fontWeight: FontWeight.w700, fontSize: 15),
                                        ),
                                        const SizedBox(height: 2),
                                        Text(
                                          inc.createdAt
                                              .toLocal()
                                              .toString()
                                              .substring(0, 16),
                                          style: const TextStyle(
                                              color: RsColors.textMuted, fontSize: 12),
                                        ),
                                      ],
                                    ),
                                  ),
                                  _StatusChip(status: inc.status),
                                ],
                              ),
                            ),
                          );
                        },
                      ),
      ),
    );
  }
}

class _StatusChip extends StatelessWidget {
  const _StatusChip({required this.status});
  final String status;

  @override
  Widget build(BuildContext context) {
    Color bg = const Color(0xFFE2E8F0);
    Color fg = RsColors.textPrimary;
    if (status == 'COMPLETED' || status == 'CLOSED') {
      bg = const Color(0xFFDCFCE7);
      fg = RsColors.success;
    } else if (status == 'EN_ROUTE' || status == 'ARRIVED') {
      bg = const Color(0xFFFFEDD5);
      fg = RsColors.warning;
    } else if (status == 'ANALYZING' || status == 'REPORTED') {
      bg = const Color(0xFFDBEAFE);
      fg = RsColors.brandPrimary;
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(20)),
      child: Text(status,
          style: TextStyle(color: fg, fontSize: 11, fontWeight: FontWeight.w700)),
    );
  }
}
