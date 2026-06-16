import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:hive_flutter/hive_flutter.dart';

import 'providers/auth_provider.dart';
import 'theme/app_theme.dart';
import 'screens/onboarding/splash_screen.dart';
import 'screens/onboarding/welcome_screen.dart';
import 'screens/onboarding/otp_screen.dart';
import 'screens/dashboard/dashboard_screen.dart';
import 'screens/camera/camera_registration_screen.dart';
import 'screens/camera/fov_validation_screen.dart';
import 'screens/camera/privacy_zone_editor_screen.dart';
import 'screens/transparency/transparency_feed_screen.dart';
import 'screens/settings/settings_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Lock to portrait mode for consistent FOV editor experience
  await SystemChrome.setPreferredOrientations([
    DeviceOrientation.portraitUp,
    DeviceOrientation.portraitDown,
  ]);

  // Initialise Hive for local storage
  await Hive.initFlutter();

  SystemChrome.setSystemUIOverlayStyle(
    const SystemUiOverlayStyle(
      statusBarColor: Colors.transparent,
      statusBarIconBrightness: Brightness.light,
    ),
  );

  runApp(
    const ProviderScope(
      child: NetraCitizenApp(),
    ),
  );
}

class NetraCitizenApp extends ConsumerWidget {
  const NetraCitizenApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(routerProvider);

    return MaterialApp.router(
      title: 'NETRA',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light,
      darkTheme: AppTheme.dark,
      themeMode: ThemeMode.system,
      routerConfig: router,
    );
  }
}

// ─── Router ──────────────────────────────────────────────────

final routerProvider = Provider<GoRouter>((ref) {
  final authState = ref.watch(authStateProvider);

  return GoRouter(
    initialLocation: '/splash',
    redirect: (context, state) {
      final isAuthenticated = authState.value?.isAuthenticated ?? false;
      final isOnboarding = state.matchedLocation.startsWith('/onboarding');
      final isSplash = state.matchedLocation == '/splash';

      if (isSplash) return null;
      if (!isAuthenticated && !isOnboarding) return '/onboarding/welcome';
      if (isAuthenticated && isOnboarding) return '/dashboard';
      return null;
    },
    routes: [
      GoRoute(path: '/splash', builder: (_, __) => const SplashScreen()),
      GoRoute(
        path: '/onboarding',
        redirect: (_, __) => '/onboarding/welcome',
        routes: [
          GoRoute(path: 'welcome', builder: (_, __) => const WelcomeScreen()),
          GoRoute(
            path: 'otp',
            builder: (_, state) => OtpScreen(
              phone: state.uri.queryParameters['phone'] ?? '',
            ),
          ),
        ],
      ),
      ShellRoute(
        builder: (context, state, child) => DashboardShell(child: child),
        routes: [
          GoRoute(path: '/dashboard', builder: (_, __) => const DashboardScreen()),
          GoRoute(
            path: '/camera/register',
            builder: (_, __) => const CameraRegistrationScreen(),
          ),
          GoRoute(
            path: '/camera/:id/fov',
            builder: (_, state) => FovValidationScreen(
              cameraId: state.pathParameters['id']!,
            ),
          ),
          GoRoute(
            path: '/camera/:id/privacy-zones',
            builder: (_, state) => PrivacyZoneEditorScreen(
              cameraId: state.pathParameters['id']!,
            ),
          ),
          GoRoute(
            path: '/transparency',
            builder: (_, __) => const TransparencyFeedScreen(),
          ),
          GoRoute(
            path: '/settings',
            builder: (_, __) => const SettingsScreen(),
          ),
        ],
      ),
    ],
  );
});
