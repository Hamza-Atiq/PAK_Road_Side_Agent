import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'screens/history_screen.dart';
import 'screens/home_screen.dart';
import 'screens/incident_status_screen.dart';
import 'screens/landing_screen.dart';
import 'screens/login_screen.dart';
import 'screens/profile_screen.dart';
import 'screens/register_screen.dart';
import 'screens/sos_screen.dart';
import 'screens/verify_otp_screen.dart';
import 'services/providers.dart';
import 'theme/app_theme.dart';

class RoadsideApp extends ConsumerWidget {
  const RoadsideApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final auth = ref.watch(authUserProvider);

    final router = GoRouter(
      initialLocation: '/',
      refreshListenable: _RouterRefresh(ref),
      redirect: (ctx, state) {
        if (auth.loading) return null;
        final loggedIn = auth.user != null;
        final loc = state.matchedLocation;
        final publicRoutes = {'/', '/login', '/register', '/verify-otp'};
        final isPublic = publicRoutes.contains(loc);
        if (!loggedIn && !isPublic) return '/';
        if (loggedIn && (loc == '/' || loc == '/login')) return '/home';
        return null;
      },
      routes: [
        GoRoute(path: '/', builder: (_, __) => const LandingScreen()),
        GoRoute(path: '/login', builder: (_, __) => const LoginScreen()),
        GoRoute(path: '/register', builder: (_, __) => const RegisterScreen()),
        GoRoute(
          path: '/verify-otp',
          builder: (_, state) =>
              VerifyOtpScreen(phone: state.uri.queryParameters['phone'] ?? ''),
        ),
        GoRoute(path: '/home', builder: (_, __) => const HomeScreen()),
        GoRoute(path: '/sos', builder: (_, __) => const SosScreen()),
        GoRoute(path: '/history', builder: (_, __) => const HistoryScreen()),
        GoRoute(path: '/profile', builder: (_, __) => const ProfileScreen()),
        GoRoute(
          path: '/incidents/:id',
          builder: (_, state) =>
              IncidentStatusScreen(incidentId: state.pathParameters['id'] ?? ''),
        ),
      ],
    );

    return MaterialApp.router(
      title: 'RoadSide',
      debugShowCheckedModeBanner: false,
      theme: RsTheme.light,
      darkTheme: RsTheme.dark,
      themeMode: ThemeMode.system,
      routerConfig: router,
    );
  }
}

class _RouterRefresh extends ChangeNotifier {
  _RouterRefresh(WidgetRef ref) {
    ref.listen(authUserProvider, (_, __) => notifyListeners());
  }
}
