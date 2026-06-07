// Auth API + Riverpod state controller.

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/models.dart';
import 'api_client.dart';
import 'providers.dart';

class AuthService {
  AuthService(this._api);
  final ApiClient _api;

  /// POST /api/auth/register. Server sends OTP via SMS.
  Future<String> register({
    required String phone,
    required String name,
    required String password,
    String role = 'customer',
  }) async {
    final r = await _api.dio.post('/api/auth/register', data: {
      'phone': phone,
      'name': name,
      'password': password,
      'role': role,
    });
    return r.data['user_id'] as String;
  }

  /// POST /api/auth/verify-otp → access_token + user.
  Future<AuthUser> verifyOtp({required String phone, required String code}) async {
    final r = await _api.dio
        .post('/api/auth/verify-otp', data: {'phone': phone, 'code': code});
    await _api.setSession(
      accessToken: r.data['access_token'] as String,
      refreshToken: r.data['refresh_token'] as String?,
    );
    return AuthUser.fromJson(r.data['user'] as Map<String, dynamic>);
  }

  /// POST /api/auth/login → access_token + user.
  Future<AuthUser> login({required String phone, required String password}) async {
    final r = await _api.dio
        .post('/api/auth/login', data: {'phone': phone, 'password': password});
    await _api.setSession(
      accessToken: r.data['access_token'] as String,
      refreshToken: r.data['refresh_token'] as String?,
    );
    return AuthUser.fromJson(r.data['user'] as Map<String, dynamic>);
  }

  Future<AuthUser?> me() async {
    try {
      final r = await _api.dio.get('/api/auth/me');
      return AuthUser.fromJson(r.data as Map<String, dynamic>);
    } on DioException catch (e) {
      if (e.response?.statusCode == 401) return null;
      rethrow;
    }
  }

  Future<void> logout() async {
    try {
      await _api.dio.post('/api/auth/logout');
    } catch (_) {/* still clear locally */}
    await _api.clear();
  }
}

class AuthUserState {
  const AuthUserState({this.user, this.loading = false, this.error});
  final AuthUser? user;
  final bool loading;
  final String? error;

  AuthUserState copyWith({AuthUser? user, bool? loading, String? error, bool clearUser = false}) =>
      AuthUserState(
        user: clearUser ? null : (user ?? this.user),
        loading: loading ?? this.loading,
        error: error,
      );
}

class AuthController extends Notifier<AuthUserState> {
  late final AuthService _svc;

  @override
  AuthUserState build() {
    _svc = ref.read(authServiceProvider);
    _bootstrap();
    return const AuthUserState(loading: true);
  }

  Future<void> _bootstrap() async {
    final me = await _svc.me();
    state = AuthUserState(user: me, loading: false);
  }

  Future<void> setUser(AuthUser user) async {
    state = AuthUserState(user: user);
  }

  Future<void> signOut() async {
    await _svc.logout();
    state = const AuthUserState();
  }
}
