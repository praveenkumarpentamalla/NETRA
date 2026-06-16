import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../providers/camera_provider.dart';
import '../../providers/notification_provider.dart';
import '../../models/camera.dart';
import '../../widgets/camera_status_badge.dart';
import '../../widgets/revoke_confirm_sheet.dart';
import '../../theme/app_theme.dart';

class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final camerasAsync = ref.watch(citizenCamerasProvider);
    final unreadCount = ref.watch(unreadNotificationCountProvider);

    return Scaffold(
      backgroundColor: AppTheme.background,
      appBar: AppBar(
        backgroundColor: AppTheme.surface,
        title: const Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('NETRA', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700, color: AppTheme.primary, letterSpacing: 1)),
            Text('My cameras', style: TextStyle(fontSize: 12, color: AppTheme.textMuted, fontWeight: FontWeight.w400)),
          ],
        ),
        actions: [
          IconButton(
            icon: Badge(
              isLabelVisible: unreadCount > 0,
              label: Text('$unreadCount'),
              child: const Icon(Icons.notifications_outlined),
            ),
            onPressed: () => context.go('/transparency'),
          ),
          IconButton(
            icon: const Icon(Icons.settings_outlined),
            onPressed: () => context.go('/settings'),
          ),
        ],
      ),
      body: camerasAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Error: $e')),
        data: (cameras) => cameras.isEmpty
            ? _EmptyState(onAdd: () => context.go('/camera/register'))
            : _CameraList(cameras: cameras),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => context.go('/camera/register'),
        backgroundColor: AppTheme.primary,
        icon: const Icon(Icons.add),
        label: const Text('Add camera'),
      ),
    );
  }
}

class _CameraList extends ConsumerWidget {
  final List<CitizenCamera> cameras;
  const _CameraList({required this.cameras});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return RefreshIndicator(
      onRefresh: () => ref.refresh(citizenCamerasProvider.future),
      child: ListView.separated(
        padding: const EdgeInsets.all(16),
        itemCount: cameras.length,
        separatorBuilder: (_, __) => const SizedBox(height: 10),
        itemBuilder: (_, i) => _CameraCard(camera: cameras[i]),
      ),
    );
  }
}

class _CameraCard extends ConsumerWidget {
  final CitizenCamera camera;
  const _CameraCard({required this.camera});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isRevoked = camera.status == CameraStatus.revoked;

    return Container(
      decoration: BoxDecoration(
        color: AppTheme.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: isRevoked ? AppTheme.error.withOpacity(0.3) : AppTheme.border,
          width: 0.5,
        ),
      ),
      child: Column(
        children: [
          // Header
          Padding(
            padding: const EdgeInsets.all(14),
            child: Row(
              children: [
                Container(
                  width: 40, height: 40,
                  decoration: BoxDecoration(
                    color: AppTheme.primary.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Icon(_cameraIcon(camera.cameraClass), color: AppTheme.primary, size: 20),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        camera.label ?? camera.cameraId,
                        style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: AppTheme.textPrimary),
                      ),
                      Text(
                        camera.addressArea ?? camera.cameraClass.displayName,
                        style: const TextStyle(fontSize: 11, color: AppTheme.textMuted),
                      ),
                    ],
                  ),
                ),
                CameraStatusBadge(status: camera.status),
              ],
            ),
          ),
          // Stats row
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14),
            child: Row(
              children: [
                _StatChip(icon: Icons.videocam, label: '${camera.clipCountToday} clips today'),
                const SizedBox(width: 8),
                _StatChip(
                  icon: Icons.schedule,
                  label: camera.lastSeenAt != null
                      ? 'Last: ${DateFormat.Hm().format(camera.lastSeenAt!)}'
                      : 'Never seen',
                ),
              ],
            ),
          ),
          // Consent mode chip
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
            child: Row(
              children: [
                _ConsentChip(mode: camera.consentMode),
                const Spacer(),
                if (camera.awayModeEnabled)
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(
                      color: Colors.orange.withOpacity(0.1),
                      borderRadius: BorderRadius.circular(4),
                      border: Border.all(color: Colors.orange.withOpacity(0.3), width: 0.5),
                    ),
                    child: const Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.home_outlined, size: 11, color: Colors.orange),
                        SizedBox(width: 3),
                        Text('Away mode', style: TextStyle(fontSize: 10, color: Colors.orange)),
                      ],
                    ),
                  ),
              ],
            ),
          ),
          const Divider(height: 1, thickness: 0.5),
          // Action buttons
          if (!isRevoked)
            Padding(
              padding: const EdgeInsets.all(8),
              child: Row(
                children: [
                  _ActionButton(
                    icon: camera.status == CameraStatus.paused
                        ? Icons.play_arrow_outlined
                        : Icons.pause_outlined,
                    label: camera.status == CameraStatus.paused ? 'Resume' : 'Pause',
                    color: AppTheme.textMuted,
                    onTap: () => _togglePause(context, ref, camera),
                  ),
                  _ActionButton(
                    icon: Icons.privacy_tip_outlined,
                    label: 'Privacy zones',
                    color: AppTheme.textMuted,
                    onTap: () => context.go('/camera/${camera.id}/privacy-zones'),
                  ),
                  _ActionButton(
                    icon: Icons.delete_outline,
                    label: 'Revoke',
                    color: AppTheme.error,
                    onTap: () => _confirmRevoke(context, ref, camera),
                  ),
                ],
              ),
            )
          else
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              child: Row(
                children: [
                  const Icon(Icons.info_outline, size: 14, color: AppTheme.error),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      'Revoked on ${DateFormat('dd MMM yyyy').format(camera.revokedAt!)}. '
                      'Archive deletion scheduled.',
                      style: const TextStyle(fontSize: 11, color: AppTheme.error),
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  IconData _cameraIcon(CameraClass cls) {
    return switch (cls) {
      CameraClass.onvif || CameraClass.rtsp => Icons.videocam,
      CameraClass.vendorCloud => Icons.cloud,
      CameraClass.phoneCamera => Icons.smartphone,
      CameraClass.dashcam => Icons.directions_car,
      _ => Icons.security,
    };
  }

  Future<void> _togglePause(BuildContext ctx, WidgetRef ref, CitizenCamera cam) async {
    final repo = ref.read(cameraRepositoryProvider);
    if (cam.status == CameraStatus.paused) {
      await repo.resume(cam.id);
    } else {
      await repo.pause(cam.id, reason: 'Manual pause');
    }
    ref.invalidate(citizenCamerasProvider);
  }

  Future<void> _confirmRevoke(BuildContext ctx, WidgetRef ref, CitizenCamera cam) async {
    final confirmed = await showModalBottomSheet<bool>(
      context: ctx,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => RevokeConfirmSheet(camera: cam),
    );
    if (confirmed == true) {
      final repo = ref.read(cameraRepositoryProvider);
      await repo.revoke(cam.id, reason: 'Citizen revocation');
      ref.invalidate(citizenCamerasProvider);
      if (ctx.mounted) {
        ScaffoldMessenger.of(ctx).showSnackBar(
          const SnackBar(
            content: Text('Camera revoked — ingestion stopped within 60 seconds'),
            backgroundColor: Colors.green,
          ),
        );
      }
    }
  }
}

class _StatChip extends StatelessWidget {
  final IconData icon;
  final String label;
  const _StatChip({required this.icon, required this.label});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 12, color: AppTheme.textMuted),
        const SizedBox(width: 3),
        Text(label, style: const TextStyle(fontSize: 11, color: AppTheme.textMuted)),
      ],
    );
  }
}

class _ConsentChip extends StatelessWidget {
  final ConsentMode mode;
  const _ConsentChip({required this.mode});

  @override
  Widget build(BuildContext context) {
    final isLivePull = mode == ConsentMode.livePullEnabled;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: (isLivePull ? Colors.blue : Colors.green).withOpacity(0.1),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(
          color: (isLivePull ? Colors.blue : Colors.green).withOpacity(0.3),
          width: 0.5,
        ),
      ),
      child: Text(
        isLivePull ? 'Event + live pull' : 'Event clips only',
        style: TextStyle(
          fontSize: 10,
          color: isLivePull ? Colors.blue.shade300 : Colors.green.shade400,
        ),
      ),
    );
  }
}

class _ActionButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;
  const _ActionButton({required this.icon, required this.label, required this.color, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(8),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 6),
          child: Column(
            children: [
              Icon(icon, size: 18, color: color),
              const SizedBox(height: 2),
              Text(label, style: TextStyle(fontSize: 10, color: color)),
            ],
          ),
        ),
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  final VoidCallback onAdd;
  const _EmptyState({required this.onAdd});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.videocam_off_outlined, size: 64, color: AppTheme.textMuted.withOpacity(0.4)),
            const SizedBox(height: 16),
            const Text(
              'No cameras registered',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600, color: AppTheme.textPrimary),
            ),
            const SizedBox(height: 8),
            const Text(
              'Register your home or business camera to help\nyour community stay safe.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 13, color: AppTheme.textMuted),
            ),
            const SizedBox(height: 24),
            FilledButton.icon(
              onPressed: onAdd,
              icon: const Icon(Icons.add),
              label: const Text('Register a camera'),
              style: FilledButton.styleFrom(backgroundColor: AppTheme.primary),
            ),
          ],
        ),
      ),
    );
  }
}
