// Riverpod providers for app-wide services.

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../config.dart';
import 'api_client.dart';
import 'auth_service.dart';
import 'incidents_service.dart';

final apiClientProvider = Provider<ApiClient>((ref) {
  return ApiClient(baseUrl: RsConfig.apiBaseUrl);
});

final authServiceProvider = Provider<AuthService>((ref) {
  return AuthService(ref.watch(apiClientProvider));
});

final incidentsServiceProvider = Provider<IncidentsService>((ref) {
  return IncidentsService(ref.watch(apiClientProvider));
});

/// Current user, null when signed out. Refreshed via [AuthController].
final authUserProvider =
    NotifierProvider<AuthController, AuthUserState>(AuthController.new);
