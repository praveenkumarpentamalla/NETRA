'use client';

import React, { useState, useCallback, useRef, useEffect } from 'react';
import Map, {
  NavigationControl, FullscreenControl, ScaleControl,
  Marker, Popup, Layer, Source,
} from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';

import { useAppDispatch, useAppSelector } from '@/store/hooks';
import { fetchCamerasInBounds, selectCameras } from '@/store/slices/cameraSlice';
import { selectActiveAlerts } from '@/store/slices/alertSlice';
import { openInvestigation } from '@/store/slices/investigationSlice';

import { CameraPin } from '@/components/map/CameraPin';
import { CameraCard } from '@/components/map/CameraCard';
import { AlertHeatmap } from '@/components/map/AlertHeatmap';
import { GeofenceDrawer } from '@/components/map/GeofenceDrawer';
import { AlertSidebar } from '@/components/alerts/AlertSidebar';
import { InvestigationPanel } from '@/components/investigation/InvestigationPanel';
import { SearchBar } from '@/components/search/SearchBar';
import { LivePullModal } from '@/components/live-pull/LivePullModal';
import { MapToolbar } from '@/components/map/MapToolbar';
import { StatusBar } from '@/components/shared/StatusBar';

import type { Camera, ViewState, GeoBounds } from '@/types';

const INDIA_CENTER: [number, number] = [78.96, 20.59];
const DEFAULT_ZOOM = 5;

export default function MapPage() {
  const dispatch = useAppDispatch();
  const cameras = useAppSelector(selectCameras);
  const activeAlerts = useAppSelector(selectActiveAlerts);

  const [viewState, setViewState] = useState({
    longitude: INDIA_CENTER[0],
    latitude: INDIA_CENTER[1],
    zoom: DEFAULT_ZOOM,
  });

  const [selectedCamera, setSelectedCamera] = useState<Camera | null>(null);
  const [showHeatmap, setShowHeatmap] = useState(false);
  const [showGeofenceTool, setShowGeofenceTool] = useState(false);
  const [livePullCamera, setLivePullCamera] = useState<Camera | null>(null);
  const [rightPanel, setRightPanel] = useState<'alerts' | 'investigation' | null>('alerts');
  const mapRef = useRef<any>(null);

  // Fetch cameras when map bounds change
  const handleMoveEnd = useCallback(() => {
    if (!mapRef.current) return;
    const bounds = mapRef.current.getBounds();
    const geoBounds: GeoBounds = {
      north: bounds.getNorth(),
      south: bounds.getSouth(),
      east: bounds.getEast(),
      west: bounds.getWest(),
    };
    if (viewState.zoom >= 12) {
      dispatch(fetchCamerasInBounds(geoBounds));
    }
  }, [dispatch, viewState.zoom]);

  // Camera pin colour by status
  const getCameraColour = (status: string): string => ({
    ONLINE: '#22c55e',
    OFFLINE: '#94a3b8',
    PAUSED: '#f59e0b',
    EVENT_FLAGGED: '#ef4444',
    REVOKED: '#334155',
  }[status] ?? '#94a3b8');

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-slate-950 text-white">
      {/* ── Left sidebar — Search + toolbar ── */}
      <div className="flex flex-col w-80 border-r border-slate-800 z-10 bg-slate-900">
        <div className="p-3 border-b border-slate-800">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-blue-400 font-bold text-lg tracking-wide">NETRA</span>
            <span className="text-slate-400 text-xs">PCR Console</span>
          </div>
          <SearchBar />
        </div>
        <MapToolbar
          showHeatmap={showHeatmap}
          onToggleHeatmap={() => setShowHeatmap(h => !h)}
          showGeofence={showGeofenceTool}
          onToggleGeofence={() => setShowGeofenceTool(g => !g)}
          onOpenInvestigation={() => setRightPanel('investigation')}
        />
        <div className="flex-1 overflow-y-auto p-2">
          {/* Quick stats */}
          <div className="grid grid-cols-2 gap-2 mb-3">
            <StatCard label="Online Cameras" value={cameras.filter(c => c.status === 'ONLINE').length} color="green" />
            <StatCard label="Active Alerts" value={activeAlerts.length} color="red" />
          </div>
          {/* Alert list */}
          <AlertMiniList alerts={activeAlerts.slice(0, 8)} />
        </div>
      </div>

      {/* ── Main map ── */}
      <div className="flex-1 relative">
        <Map
          ref={mapRef}
          {...viewState}
          onMove={e => setViewState(e.viewState)}
          onMoveEnd={handleMoveEnd}
          mapStyle="/map-style.json"
          style={{ width: '100%', height: '100%' }}
          attributionControl={false}
        >
          <NavigationControl position="bottom-right" />
          <FullscreenControl position="bottom-right" />
          <ScaleControl position="bottom-left" />

          {/* Camera pins */}
          {cameras.map(camera => (
            <Marker
              key={camera.id}
              longitude={camera.longitude}
              latitude={camera.latitude}
              anchor="bottom"
              onClick={() => setSelectedCamera(camera)}
            >
              <CameraPin
                status={camera.status}
                hasAlert={activeAlerts.some(a => a.cameraId === camera.id)}
                colour={getCameraColour(camera.status)}
              />
            </Marker>
          ))}

          {/* Selected camera popup */}
          {selectedCamera && (
            <Popup
              longitude={selectedCamera.longitude}
              latitude={selectedCamera.latitude}
              anchor="bottom"
              onClose={() => setSelectedCamera(null)}
              closeButton
              maxWidth="340px"
            >
              <CameraCard
                camera={selectedCamera}
                onRequestLivePull={() => setLivePullCamera(selectedCamera)}
                onViewTimeline={() => {
                  setRightPanel('investigation');
                }}
              />
            </Popup>
          )}

          {/* Alert heatmap layer */}
          {showHeatmap && <AlertHeatmap alerts={activeAlerts} />}

          {/* Geofence drawing tool */}
          {showGeofenceTool && (
            <GeofenceDrawer
              onComplete={(polygon) => {
                setShowGeofenceTool(false);
                dispatch(openInvestigation({ geofence: polygon }));
              }}
              onCancel={() => setShowGeofenceTool(false)}
            />
          )}
        </Map>

        {/* Zoom hint */}
        {viewState.zoom < 12 && (
          <div className="absolute top-4 left-1/2 -translate-x-1/2 bg-slate-800/90 text-slate-300 text-xs px-3 py-1 rounded-full pointer-events-none">
            Zoom in to see cameras
          </div>
        )}
      </div>

      {/* ── Right panel ── */}
      {rightPanel && (
        <div className="w-96 border-l border-slate-800 bg-slate-900 overflow-y-auto z-10">
          {rightPanel === 'alerts' ? (
            <AlertSidebar onClose={() => setRightPanel(null)} />
          ) : (
            <InvestigationPanel onClose={() => setRightPanel(null)} />
          )}
        </div>
      )}

      {/* ── Live pull modal ── */}
      {livePullCamera && (
        <LivePullModal
          camera={livePullCamera}
          onClose={() => setLivePullCamera(null)}
        />
      )}

      {/* ── Status bar ── */}
      <StatusBar />
    </div>
  );
}

// Small helper components ──────────────────────────────────────

function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  const colorMap: Record<string, string> = {
    green: 'text-green-400',
    red: 'text-red-400',
    blue: 'text-blue-400',
    amber: 'text-amber-400',
  };
  return (
    <div className="bg-slate-800 rounded-lg p-3">
      <div className={`text-2xl font-bold ${colorMap[color] ?? 'text-white'}`}>{value}</div>
      <div className="text-xs text-slate-400 mt-0.5">{label}</div>
    </div>
  );
}

function AlertMiniList({ alerts }: { alerts: any[] }) {
  if (alerts.length === 0) {
    return <p className="text-slate-500 text-xs text-center py-4">No active alerts</p>;
  }
  return (
    <div className="space-y-1">
      {alerts.map(alert => (
        <div key={alert.id} className="flex items-center gap-2 p-2 rounded-lg bg-slate-800 hover:bg-slate-700 cursor-pointer transition-colors">
          <span className={`w-2 h-2 rounded-full flex-shrink-0 ${
            alert.alertType === 'PERSON_OF_INTEREST' ? 'bg-red-500' :
            alert.alertType === 'AUDIO_ANOMALY' ? 'bg-orange-500' :
            'bg-yellow-500'
          }`} />
          <div className="flex-1 min-w-0">
            <p className="text-xs text-white truncate">{alert.title}</p>
            <p className="text-xs text-slate-400">{alert.alertType}</p>
          </div>
          <span className="text-xs text-slate-500 flex-shrink-0">
            {new Date(alert.createdAt).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>
      ))}
    </div>
  );
}
