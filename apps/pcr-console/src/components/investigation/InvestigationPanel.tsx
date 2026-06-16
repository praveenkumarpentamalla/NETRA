'use client';

import React, { useState, useRef, useCallback, useEffect } from 'react';
import { useAppDispatch, useAppSelector } from '@/store/hooks';
import {
  selectCurrentInvestigation, createInvestigation,
  addCameraToInvestigation, searchEvents,
} from '@/store/slices/investigationSlice';
import { useQuery, useMutation } from '@tanstack/react-query';
import { investigationApi } from '@/services/investigation.api';
import { formatDistanceToNow, format } from 'date-fns';
import {
  FolderOpen, Search, Camera, Clock, AlertTriangle,
  User, Car, Volume2, Shield, ChevronRight, X, Plus,
  Eye, Check, AlertCircle,
} from 'lucide-react';
import type { Investigation, Event, SearchQuery } from '@/types';

interface Props {
  onClose: () => void;
}

export function InvestigationPanel({ onClose }: Props) {
  const dispatch = useAppDispatch();
  const investigation = useAppSelector(selectCurrentInvestigation);
  const [activeTab, setActiveTab] = useState<'overview' | 'timeline' | 'search'>('overview');
  const [searchQuery, setSearchQuery] = useState<SearchQuery>({
    type: 'attribute',
    filters: {},
  });

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-slate-700">
        <div className="flex items-center gap-2">
          <FolderOpen className="w-4 h-4 text-blue-400" />
          <span className="font-medium text-sm">
            {investigation ? investigation.caseReference : 'Investigation'}
          </span>
          {investigation && (
            <span className={`text-xs px-2 py-0.5 rounded-full ${
              investigation.status === 'OPEN' ? 'bg-green-900 text-green-300' : 'bg-slate-700 text-slate-400'
            }`}>
              {investigation.status}
            </span>
          )}
        </div>
        <button onClick={onClose} className="text-slate-400 hover:text-white">
          <X className="w-4 h-4" />
        </button>
      </div>

      {!investigation ? (
        <CreateInvestigationForm />
      ) : (
        <>
          {/* Tabs */}
          <div className="flex border-b border-slate-700">
            {(['overview', 'timeline', 'search'] as const).map(tab => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`flex-1 py-2 text-xs capitalize transition-colors ${
                  activeTab === tab
                    ? 'text-blue-400 border-b-2 border-blue-400'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                {tab}
              </button>
            ))}
          </div>

          <div className="flex-1 overflow-y-auto">
            {activeTab === 'overview' && <InvestigationOverview investigation={investigation} />}
            {activeTab === 'timeline' && <MultiCameraTimeline investigation={investigation} />}
            {activeTab === 'search' && (
              <InvestigationSearch investigation={investigation} query={searchQuery} onQueryChange={setSearchQuery} />
            )}
          </div>
        </>
      )}
    </div>
  );
}

// ── Create Investigation Form ─────────────────────────────────

function CreateInvestigationForm() {
  const dispatch = useAppDispatch();
  const [caseRef, setCaseRef] = useState('');
  const [type, setType] = useState<'FIR' | 'PCR_CALL' | 'MISSING_PERSON'>('FIR');
  const [title, setTitle] = useState('');
  const [error, setError] = useState('');

  const handleCreate = async () => {
    if (!caseRef.trim() || !title.trim()) {
      setError('Case reference and title are required');
      return;
    }
    setError('');
    dispatch(createInvestigation({ caseReference: caseRef, type, title }));
  };

  return (
    <div className="p-4 space-y-4">
      <p className="text-xs text-slate-400">
        All camera searches and archive access must be linked to an investigation.
      </p>
      {error && (
        <div className="flex items-center gap-2 bg-red-900/40 border border-red-700 rounded-lg p-3">
          <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
          <span className="text-xs text-red-300">{error}</span>
        </div>
      )}
      <div>
        <label className="text-xs text-slate-400 block mb-1">Investigation Type</label>
        <select
          value={type}
          onChange={e => setType(e.target.value as any)}
          className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white"
        >
          <option value="FIR">FIR</option>
          <option value="PCR_CALL">PCR Call</option>
          <option value="MISSING_PERSON">Missing Person</option>
          <option value="BOLO">BOLO</option>
        </select>
      </div>
      <div>
        <label className="text-xs text-slate-400 block mb-1">Case Reference *</label>
        <input
          value={caseRef}
          onChange={e => setCaseRef(e.target.value)}
          placeholder="FIR/2026/0001 or PCR-12345/2026"
          className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500"
        />
      </div>
      <div>
        <label className="text-xs text-slate-400 block mb-1">Title *</label>
        <input
          value={title}
          onChange={e => setTitle(e.target.value)}
          placeholder="Brief description of incident"
          className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500"
        />
      </div>
      <button
        onClick={handleCreate}
        className="w-full bg-blue-600 hover:bg-blue-500 text-white rounded-lg py-2 text-sm font-medium transition-colors flex items-center justify-center gap-2"
      >
        <Plus className="w-4 h-4" />
        Create Investigation
      </button>
    </div>
  );
}

// ── Investigation Overview ────────────────────────────────────

function InvestigationOverview({ investigation }: { investigation: Investigation }) {
  const { data: cameras } = useQuery({
    queryKey: ['investigation-cameras', investigation.id],
    queryFn: () => investigationApi.getCameras(investigation.id),
  });

  return (
    <div className="p-4 space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <InfoItem label="Case Ref" value={investigation.caseReference} />
        <InfoItem label="Type" value={investigation.investigationType} />
        <InfoItem label="Lead Officer" value={investigation.leadOfficerName ?? 'Unassigned'} />
        <InfoItem
          label="Opened"
          value={formatDistanceToNow(new Date(investigation.openedAt), { addSuffix: true })}
        />
      </div>

      <div>
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-slate-400">Cameras in scope ({cameras?.length ?? 0})</span>
          <button className="text-xs text-blue-400 hover:text-blue-300">+ Add camera</button>
        </div>
        <div className="space-y-1">
          {cameras?.map(cam => (
            <div key={cam.id} className="flex items-center gap-2 p-2 rounded-lg bg-slate-800">
              <Camera className="w-3 h-3 text-slate-400" />
              <span className="text-xs text-white flex-1">{cam.cameraId}</span>
              <span className="text-xs text-slate-500">{cam.addressArea}</span>
              <span className={`w-1.5 h-1.5 rounded-full ${cam.status === 'ONLINE' ? 'bg-green-400' : 'bg-slate-500'}`} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Multi-Camera Timeline ─────────────────────────────────────

function MultiCameraTimeline({ investigation }: { investigation: Investigation }) {
  const [selectedTime, setSelectedTime] = useState<Date | null>(null);
  const { data: events, isLoading } = useQuery({
    queryKey: ['investigation-events', investigation.id],
    queryFn: () => investigationApi.getEvents(investigation.id),
    refetchInterval: 30_000,
  });

  const eventsByCamera = React.useMemo(() => {
    if (!events) return {};
    return events.reduce<Record<string, any[]>>((acc, event) => {
      if (!acc[event.cameraId]) acc[event.cameraId] = [];
      acc[event.cameraId].push(event);
      return acc;
    }, {});
  }, [events]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-32">
        <div className="text-xs text-slate-400">Loading timeline…</div>
      </div>
    );
  }

  return (
    <div className="p-4">
      <div className="space-y-4">
        {Object.entries(eventsByCamera).map(([camId, camEvents]) => (
          <div key={camId}>
            <div className="flex items-center gap-2 mb-2">
              <Camera className="w-3 h-3 text-slate-400" />
              <span className="text-xs text-slate-400 font-mono">{camId}</span>
            </div>
            <div className="relative ml-4">
              <div className="absolute left-0 top-0 bottom-0 w-px bg-slate-700" />
              <div className="space-y-2 pl-4">
                {camEvents.map(event => (
                  <EventTimelineItem key={event.id} event={event} />
                ))}
              </div>
            </div>
          </div>
        ))}
        {Object.keys(eventsByCamera).length === 0 && (
          <p className="text-slate-500 text-xs text-center py-8">No events in investigation scope yet</p>
        )}
      </div>
    </div>
  );
}

function EventTimelineItem({ event }: { event: any }) {
  const [expanded, setExpanded] = useState(false);
  const iconMap: Record<string, React.ReactNode> = {
    person_detected: <User className="w-3 h-3" />,
    vehicle_detected: <Car className="w-3 h-3" />,
    audio_anomaly: <Volume2 className="w-3 h-3" />,
    away_mode_motion: <AlertTriangle className="w-3 h-3" />,
    loitering: <Clock className="w-3 h-3" />,
  };

  return (
    <div
      className="flex items-start gap-2 cursor-pointer group"
      onClick={() => setExpanded(e => !e)}
    >
      <div className="w-5 h-5 rounded-full bg-slate-700 group-hover:bg-slate-600 flex items-center justify-center flex-shrink-0 text-slate-300 mt-0.5">
        {iconMap[event.eventType] ?? <AlertTriangle className="w-3 h-3" />}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-xs text-white capitalize">{event.eventType.replace(/_/g, ' ')}</span>
          <span className="text-xs text-slate-500">
            {format(new Date(event.occurredAt), 'HH:mm:ss')}
          </span>
          {event.triggerConfidence && (
            <span className="text-xs text-slate-500">
              {Math.round(event.triggerConfidence * 100)}%
            </span>
          )}
        </div>
        {expanded && (
          <div className="mt-2 space-y-1">
            {event.clipPath && (
              <button className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1">
                <Eye className="w-3 h-3" />
                View clip
              </button>
            )}
            {event.edgeDetections?.length > 0 && (
              <div className="text-xs text-slate-400">
                Detections: {event.edgeDetections.map((d: any) => `${d.class} (${Math.round(d.confidence * 100)}%)`).join(', ')}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Investigation Search ──────────────────────────────────────

function InvestigationSearch({
  investigation, query, onQueryChange,
}: {
  investigation: Investigation;
  query: SearchQuery;
  onQueryChange: (q: SearchQuery) => void;
}) {
  const [results, setResults] = useState<any[]>([]);
  const [searching, setSearching] = useState(false);

  const runSearch = async () => {
    if (!investigation.id) return;
    setSearching(true);
    try {
      const res = await investigationApi.search(investigation.id, query);
      setResults(res);
    } catch (e) {
      console.error('Search error', e);
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="p-4 space-y-4">
      {/* Search type selector */}
      <div>
        <label className="text-xs text-slate-400 block mb-1">Search Type</label>
        <div className="grid grid-cols-2 gap-1">
          {(['attribute', 'plate', 'face', 'reid'] as const).map(type => (
            <button
              key={type}
              onClick={() => onQueryChange({ ...query, type })}
              className={`py-1.5 rounded text-xs capitalize transition-colors ${
                query.type === type
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-800 text-slate-400 hover:text-white'
              }`}
            >
              {type === 'reid' ? 'Person Re-ID' : type.replace(/_/g, ' ')}
            </button>
          ))}
        </div>
      </div>

      {/* Dynamic filters */}
      {query.type === 'attribute' && (
        <AttributeFilters filters={query.filters} onChange={f => onQueryChange({ ...query, filters: f })} />
      )}
      {query.type === 'plate' && (
        <PlateFilter value={query.filters.plate ?? ''} onChange={v => onQueryChange({ ...query, filters: { ...query.filters, plate: v } })} />
      )}
      {query.type === 'face' && (
        <FaceCropUpload onUpload={data => onQueryChange({ ...query, filters: { ...query.filters, faceData: data } })} />
      )}
      {query.type === 'reid' && (
        <PersonCropUpload onUpload={data => onQueryChange({ ...query, filters: { ...query.filters, personData: data } })} />
      )}

      <button
        onClick={runSearch}
        disabled={searching}
        className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 text-white rounded-lg py-2 text-sm font-medium transition-colors flex items-center justify-center gap-2"
      >
        <Search className="w-4 h-4" />
        {searching ? 'Searching…' : 'Search within Investigation'}
      </button>

      {/* Results */}
      {results.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-slate-400">{results.length} result{results.length !== 1 ? 's' : ''}</p>
          {results.map((r, i) => (
            <SearchResultItem key={i} result={r} investigationId={investigation.id} />
          ))}
        </div>
      )}
    </div>
  );
}

function AttributeFilters({ filters, onChange }: { filters: any; onChange: (f: any) => void }) {
  return (
    <div className="space-y-2">
      <input
        placeholder="Vehicle type or colour (e.g. red SUV)"
        value={filters.vehicleDesc ?? ''}
        onChange={e => onChange({ ...filters, vehicleDesc: e.target.value })}
        className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500"
      />
      <input
        placeholder="Clothing description (e.g. white shirt)"
        value={filters.clothingDesc ?? ''}
        onChange={e => onChange({ ...filters, clothingDesc: e.target.value })}
        className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500"
      />
      <div className="grid grid-cols-2 gap-2">
        <input
          type="time"
          value={filters.timeStart ?? ''}
          onChange={e => onChange({ ...filters, timeStart: e.target.value })}
          className="bg-slate-800 border border-slate-700 rounded-lg px-2 py-2 text-sm text-white"
        />
        <input
          type="time"
          value={filters.timeEnd ?? ''}
          onChange={e => onChange({ ...filters, timeEnd: e.target.value })}
          className="bg-slate-800 border border-slate-700 rounded-lg px-2 py-2 text-sm text-white"
        />
      </div>
    </div>
  );
}

function PlateFilter({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <input
      value={value}
      onChange={e => onChange(e.target.value.toUpperCase())}
      placeholder="MH01AB1234 (partial OK)"
      className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white font-mono placeholder-slate-500"
    />
  );
}

function FaceCropUpload({ onUpload }: { onUpload: (data: string) => void }) {
  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => onUpload(reader.result as string);
    reader.readAsDataURL(file);
  };
  return (
    <div className="border-2 border-dashed border-slate-700 rounded-lg p-4 text-center">
      <User className="w-6 h-6 text-slate-500 mx-auto mb-2" />
      <p className="text-xs text-slate-400 mb-2">Upload face crop for recognition</p>
      <p className="text-xs text-amber-400 mb-2">⚠ Requires investigation scope + officer attestation</p>
      <input type="file" accept="image/*" onChange={handleFile} className="hidden" id="face-upload" />
      <label htmlFor="face-upload" className="text-xs text-blue-400 hover:text-blue-300 cursor-pointer">
        Choose image
      </label>
    </div>
  );
}

function PersonCropUpload({ onUpload }: { onUpload: (data: string) => void }) {
  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => onUpload(reader.result as string);
    reader.readAsDataURL(file);
  };
  return (
    <div className="border-2 border-dashed border-slate-700 rounded-lg p-4 text-center">
      <Shield className="w-6 h-6 text-slate-500 mx-auto mb-2" />
      <p className="text-xs text-slate-400 mb-2">Upload person crop for Re-ID</p>
      <p className="text-xs text-slate-500 mb-2">Searches only within investigation cameras + time window</p>
      <input type="file" accept="image/*" onChange={handleFile} className="hidden" id="person-upload" />
      <label htmlFor="person-upload" className="text-xs text-blue-400 hover:text-blue-300 cursor-pointer">
        Choose image
      </label>
    </div>
  );
}

function SearchResultItem({ result, investigationId }: { result: any; investigationId: string }) {
  return (
    <div className="p-3 bg-slate-800 rounded-lg space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-xs text-white">{result.cameraId}</span>
        <span className="text-xs text-slate-500">{format(new Date(result.occurredAt), 'dd/MM HH:mm')}</span>
      </div>
      {result.confidence && (
        <div className="flex items-center gap-1">
          <div className="flex-1 bg-slate-700 rounded-full h-1">
            <div
              className="bg-blue-500 h-1 rounded-full"
              style={{ width: `${Math.round(result.confidence * 100)}%` }}
            />
          </div>
          <span className="text-xs text-slate-400">{Math.round(result.confidence * 100)}%</span>
        </div>
      )}
      {result.matchCandidates && (
        <div className="mt-2">
          <p className="text-xs text-amber-400 mb-1">⚠ Top-{result.matchCandidates.length} candidates — officer attestation required</p>
          {result.matchCandidates.slice(0, 3).map((c: any, i: number) => (
            <div key={i} className="flex items-center gap-2 text-xs text-slate-300">
              <span className="w-4">#{c.rank}</span>
              <span className="flex-1">{c.watchlistEntryId}</span>
              <span>{Math.round(c.calibratedProbability * 100)}%</span>
              <button className="text-green-400 hover:text-green-300 text-xs">
                <Check className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function InfoItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="text-xs text-white mt-0.5 font-medium">{value}</dd>
    </div>
  );
}
