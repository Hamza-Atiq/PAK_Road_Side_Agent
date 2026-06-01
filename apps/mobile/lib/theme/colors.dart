// Design tokens — kept in sync with packages/ui/src/tokens.ts by hand
// (Dart can't import TypeScript). See V2_PLAN.md §3.2 for the source of truth.

import 'package:flutter/material.dart';

class RsColors {
  RsColors._();

  // Customer (mobile is customer-only at v2.0)
  static const Color brandPrimary = Color(0xFF2473EB); // trust blue
  static const Color brandPrimaryDark = Color(0xFF1E4DAF);

  // Universal status
  static const Color emergency = Color(0xFFDC2626); // SOS button only
  static const Color warning = Color(0xFFFF6600); // safety orange — EN_ROUTE
  static const Color success = Color(0xFF16A34A);

  // Surfaces
  static const Color surface = Color(0xFFFFFFFF);
  static const Color surfaceDark = Color(0xFF0B1220);

  // Text
  static const Color textPrimary = Color(0xFF0B1220);
  static const Color textInverse = Color(0xFFF8FAFC);
  static const Color textMuted = Color(0xFF64748B);
}
