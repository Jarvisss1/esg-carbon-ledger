import { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { recordsAPI, ingestionAPI } from '../lib/api';
import { useAuth } from '../context/AuthContext';
import {
  CheckCircle2, XCircle, AlertTriangle, ChevronLeft, ChevronRight,
  Filter, Search, Lock, RefreshCw, UserCheck, SlidersHorizontal,
  Eye, FileText, Pencil, Send, X, ShieldCheck, Info, Database, Trash2, Clock
} from 'lucide-react';

// ─── Normalized Category Mapping ────────────────────────────────────────────────
const SCOPE_CATEGORY_LABELS = {
  'SCOPE_1_STATIONARY': 'Scope 1: Fuel',
  'SCOPE_2_ELECTRICITY': 'Scope 2: Electricity',
  'SCOPE_3_TRAVEL': 'Scope 3: Travel',
  'SCOPE_3_PROCUREMENT': 'Scope 3: Procurement',
  'EXCLUDED_LOGISTICS': 'Logistics (Excluded)',
  'EXCLUDED_AVOIDED': 'Solar Export (Excluded)'
};

export function getNormalizedLabel(rec) {
  if (!rec) return '—';
  return SCOPE_CATEGORY_LABELS[rec.scope_category] || rec.scope_category || rec.category || rec.source_type || '—';
}

// ─── Pill badge ────────────────────────────────────────────────────────────────
function Badge({ children, variant = 'default' }) {
  const styles = {
    default: 'bg-zinc-800 text-zinc-300 border-zinc-700',
    success: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20',
    warning: 'bg-amber-500/15 text-amber-400 border-amber-500/20',
    danger: 'bg-red-500/15 text-red-400 border-red-500/20',
    locked: 'bg-violet-500/15 text-violet-400 border-violet-500/20',
  };
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full border ${styles[variant]}`}>
      {children}
    </span>
  );
}

// ─── Record status badge ────────────────────────────────────────────────────────
function RecordBadge({ record }) {
  if (record.approved) return <Badge variant="success"><ShieldCheck className="w-2.5 h-2.5" /> Approved</Badge>;
  if (record.excluded) return <Badge variant="danger"><XCircle className="w-2.5 h-2.5" /> Excluded</Badge>;
  if (record.is_outlier) return <Badge variant="warning"><AlertTriangle className="w-2.5 h-2.5" /> Outlier</Badge>;
  return <Badge variant="default"><RefreshCw className="w-2.5 h-2.5 animate-spin" /> Pending Review</Badge>;
}

function RecordModal({ record, onClose, onApprove, onExclude, onDelegate, onOverride }) {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState('normalized');
  const [excludeReason, setExcludeReason] = useState('');
  const [delegateTo, setDelegateTo] = useState('');
  const [mode, setMode] = useState(null); // 'exclude' | 'delegate' | 'override'
  const [busy, setBusy] = useState(false);
  const [auditLogs, setAuditLogs] = useState([]);
  const [loadingLogs, setLoadingLogs] = useState(false);

  // Edit fields state
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState('');
  const [editFacility, setEditFacility] = useState('');
  const [editCountry, setEditCountry] = useState('');
  const [editVendor, setEditVendor] = useState('');
  const [editDistance, setEditDistance] = useState('');
  const [editNotes, setEditNotes] = useState('');

  useEffect(() => {
    // Disable background scrolling when modal is open
    document.body.style.overflow = 'hidden';
    return () => {
      // Re-enable background scrolling on unmount
      document.body.style.overflow = 'unset';
    };
  }, []);

  useEffect(() => {
    if (activeTab === 'audit' && record?.id) {
      setLoadingLogs(true);
      recordsAPI.auditLogs(record.id)
        .then(res => setAuditLogs(res.data || []))
        .catch(() => setAuditLogs([]))
        .finally(() => setLoadingLogs(false));
    }
  }, [activeTab, record?.id]);

  // Initialize editable fields on record switch
  useEffect(() => {
    if (record) {
      setEditValue(record.co2e_kg || '');
      setEditFacility(record.facility_name || '');
      setEditCountry(record.country || '');
      setEditVendor(record.vendor || '');
      setEditDistance(record.distance_km || '');
      setEditNotes('');
      setIsEditing(false);
      setMode(null);
    }
  }, [record]);

  if (!record) return null;
  const locked = record.approved || record.excluded;

  const act = async (fn) => {
    setBusy(true);
    try { await fn(); onClose(); } catch (e) {
      alert(e?.response?.data?.detail || 'Action failed');
    } finally { setBusy(false); }
  };

  const handleSaveEdit = async () => {
    if (editNotes.trim().length < 5) {
      alert("Please provide a detailed audit explanation (minimum 5 characters) explaining the corrections.");
      return;
    }
    const payload = {
      normalized_value: editValue !== '' ? parseFloat(editValue) : null,
      resolved_facility_id: editFacility || null,
      resolved_facility_country: editCountry || null,
      vendor: editVendor || null,
      distance_km: editDistance !== '' ? parseFloat(editDistance) : null,
      analyst_notes: editNotes,
      note: editNotes
    };
    await onOverride(record.id, payload);
    setIsEditing(false);
    setEditNotes('');
  };

  // Safe robust parsing for raw evidence data
  let rawContent = 'No raw data available.';
  if (record.raw_data) {
    if (typeof record.raw_data === 'string') {
      try {
        rawContent = JSON.stringify(JSON.parse(record.raw_data), null, 2);
      } catch {
        rawContent = record.raw_data;
      }
    } else {
      rawContent = JSON.stringify(record.raw_data, null, 2);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/75 backdrop-blur-md z-50 flex items-center justify-center p-4 animate-fade-in">
      <div className="bg-zinc-950/95 border border-zinc-850 w-[580px] max-w-full rounded-2xl flex flex-col shadow-2xl overflow-hidden glass max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-850 bg-zinc-900/40">
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-white truncate">
              Record #{record.id} — {getNormalizedLabel(record)}
            </p>
            <p className="text-xs text-zinc-500">{record.emission_date || '—'}</p>
          </div>
          <div className="flex items-center gap-3">
            <RecordBadge record={record} />
            <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition-all">
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-zinc-850 bg-zinc-900/20">
          {[
            { id: 'normalized', label: 'Normalized Data', icon: Eye },
            { id: 'raw', label: 'Raw Evidence', icon: FileText },
            { id: 'audit', label: 'Audit Trail', icon: Clock },
          ].map(({ id, label, icon: Icon }) => (
            <button key={id} onClick={() => setActiveTab(id)}
              className={`flex-1 flex items-center justify-center gap-2 py-3 text-sm font-medium transition-all ${
                activeTab === id
                  ? 'text-emerald-400 border-b-2 border-emerald-500 bg-emerald-500/5'
                  : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-900/10'
               }`}>
              <Icon className="w-4 h-4" /> {label}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {activeTab === 'normalized' ? (
            <>
              {record.is_outlier && (
                <div className="flex items-start gap-2.5 bg-amber-500/10 border border-amber-500/20 rounded-xl p-3.5 animate-pulse">
                  <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                  <div>
                    <p className="text-xs font-semibold text-amber-400">Outlier Detected</p>
                    <p className="text-xs text-zinc-400 mt-0.5">
                      This record&apos;s emission value deviates significantly from the dataset mean or has validation anomalies.
                    </p>
                  </div>
                </div>
              )}

              {/* Normalized fields grid */}
              <div className="grid grid-cols-2 gap-3">
                {[
                  { 
                    label: 'CO₂e (kg)', 
                    value: isEditing ? (
                      <input
                        type="number"
                        step="any"
                        value={editValue}
                        onChange={e => setEditValue(e.target.value)}
                        className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-2 py-0.5 text-xs text-emerald-400 font-mono focus:outline-none focus:border-emerald-500/50"
                      />
                    ) : record.co2e_kg ? parseFloat(record.co2e_kg).toFixed(4) : '—' 
                  },
                  { label: 'CO₂e (tonnes)', value: isEditing ? (editValue ? (parseFloat(editValue)/1000).toFixed(4) : '0.0000') : record.co2e_kg ? (parseFloat(record.co2e_kg)/1000).toFixed(4) : '—' },
                  { label: 'Source Type', value: record.source_type || '—' },
                  { label: 'Emission Date', value: record.emission_date || '—' },
                  { 
                    label: 'Facility', 
                    value: isEditing ? (
                      <input
                        type="text"
                        value={editFacility}
                        onChange={e => setEditFacility(e.target.value)}
                        className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-2 py-0.5 text-xs text-zinc-300 focus:outline-none focus:border-emerald-500/50"
                      />
                    ) : record.facility_name || '—' 
                  },
                  { 
                    label: 'Country', 
                    value: isEditing ? (
                      <input
                        type="text"
                        maxLength={2}
                        value={editCountry}
                        onChange={e => setEditCountry(e.target.value)}
                        className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-2 py-0.5 text-xs text-zinc-300 focus:outline-none focus:border-emerald-500/50 uppercase"
                      />
                    ) : record.country || '—' 
                  },
                  { label: 'City', value: record.city || '—' },
                  { 
                    label: 'Vendor', 
                    value: isEditing ? (
                      <input
                        type="text"
                        value={editVendor}
                        onChange={e => setEditVendor(e.target.value)}
                        className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-2 py-0.5 text-xs text-zinc-300 focus:outline-none focus:border-emerald-500/50"
                      />
                    ) : record.vendor || '—' 
                  },
                  { label: 'Origin Airport', value: record.origin_iata || '—' },
                  { label: 'Dest. Airport', value: record.destination_iata || '—' },
                  { 
                    label: 'Distance (km)', 
                    value: isEditing ? (
                      <input
                        type="number"
                        step="any"
                        value={editDistance}
                        onChange={e => setEditDistance(e.target.value)}
                        className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-2 py-0.5 text-xs text-zinc-300 focus:outline-none focus:border-emerald-500/50"
                      />
                    ) : record.distance_km ? parseFloat(record.distance_km).toFixed(1) : '—' 
                  },
                  { label: 'Uplift Applied', value: record.uplift_applied ? '8% (DEFRA)' : 'No' },
                ].map(({ label, value }) => (
                  <div key={label} className="bg-zinc-900/60 rounded-xl p-3 border border-zinc-800">
                    <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">{label}</p>
                    <div className="text-sm font-medium text-zinc-200 font-mono break-all">{value}</div>
                  </div>
                ))}
              </div>

              {/* Override note display */}
              {record.override_note && record.override_note !== '—' && (
                <div className="bg-zinc-800/40 rounded-xl p-3.5 border border-zinc-700">
                  <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Override / Audit Note</p>
                  <p className="text-xs text-zinc-300">{record.override_note}</p>
                </div>
              )}

              {/* Lock info */}
              {locked && (
                <div className="flex items-center gap-2.5 bg-violet-500/10 border border-violet-500/20 rounded-xl p-3.5">
                  <Lock className="w-4 h-4 text-violet-400 shrink-0" />
                  <p className="text-xs text-violet-300">
                    This record is <strong>locked</strong>. {record.approved ? 'Approved and audit-ready.' : 'Excluded from carbon accounting.'}
                  </p>
                </div>
              )}
            </>
          ) : activeTab === 'raw' ? (
            <>
              <div className="flex items-center gap-2 mb-2">
                <Info className="w-4 h-4 text-zinc-500" />
                <p className="text-xs text-zinc-500">Original parsed row from uploaded file. This data is read-only and preserved for audit.</p>
              </div>
              <pre className="bg-zinc-900/80 rounded-xl p-4 text-xs text-zinc-300 font-mono overflow-auto leading-relaxed whitespace-pre-wrap break-all max-h-[300px]">
                {rawContent}
              </pre>
            </>
          ) : (
            <div className="space-y-4 animate-fade-in">
              {loadingLogs ? (
                <div className="flex items-center gap-2 text-zinc-550 py-12 justify-center">
                  <RefreshCw className="w-4 h-4 animate-spin text-emerald-400" />
                  <span className="text-xs text-zinc-500">Loading audit history…</span>
                </div>
              ) : auditLogs.length === 0 ? (
                <div className="text-center py-10 bg-zinc-900/20 rounded-xl border border-zinc-850">
                  <Info className="w-8 h-8 text-zinc-600 mx-auto mb-2.5" />
                  <p className="text-zinc-400 text-sm font-medium">No modifications recorded</p>
                  <p className="text-zinc-650 text-xs mt-1">This record remains in its original ingested state.</p>
                </div>
              ) : (
                <div className="relative border-l border-zinc-850 ml-3.5 pl-5 space-y-5 py-1">
                  {auditLogs.map((log) => {
                    let badgeColor = 'bg-zinc-800 text-zinc-300 border-zinc-700';
                    let dotColor = 'bg-zinc-700 ring-zinc-950';
                    let actionText = log.action;
                    
                    if (log.action === 'CREATE') {
                      badgeColor = 'bg-emerald-500/10 text-emerald-400 border-emerald-500/15';
                      dotColor = 'bg-emerald-400 ring-zinc-950';
                      actionText = 'System Ingested';
                    } else if (log.action === 'EDIT') {
                      badgeColor = 'bg-amber-500/10 text-amber-400 border-amber-500/15';
                      dotColor = 'bg-amber-400 ring-zinc-950';
                      actionText = 'Analyst Override';
                    } else if (log.action === 'APPROVE') {
                      badgeColor = 'bg-emerald-500/10 text-emerald-400 border-emerald-500/15';
                      dotColor = 'bg-emerald-400 ring-zinc-950';
                      actionText = 'Approved';
                    } else if (log.action === 'REJECT') {
                      badgeColor = 'bg-red-500/10 text-red-400 border-red-500/15';
                      dotColor = 'bg-red-400 ring-zinc-950';
                      actionText = 'Excluded';
                    } else if (log.action === 'LOCK') {
                      badgeColor = 'bg-violet-500/10 text-violet-400 border-violet-500/15';
                      dotColor = 'bg-violet-400 ring-zinc-950';
                      actionText = 'Audit Locked';
                    }

                    const dateStr = log.changed_at
                      ? new Date(log.changed_at).toLocaleString('en-IN', {
                          day: '2-digit',
                          month: 'short',
                          year: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit',
                        })
                      : '—';

                    return (
                      <div key={log.id} className="relative group">
                        {/* Timeline Node */}
                        <div className={`absolute -left-[26px] top-1.5 w-2 h-2 rounded-full ring-4 ${dotColor} transition-all`} />

                        {/* Audit Card */}
                        <div className="bg-zinc-900/40 border border-zinc-850 rounded-xl p-3.5 space-y-2.5 hover:border-zinc-800 transition-all">
                          <div className="flex items-center justify-between gap-3">
                            <div className="flex items-center gap-2 min-w-0">
                              <span className={`text-[9px] font-bold px-2 py-0.5 rounded-full border shrink-0 ${badgeColor}`}>
                                {actionText}
                              </span>
                              <span className="text-xs text-zinc-300 font-medium truncate">
                                {log.changed_by || 'System'}
                              </span>
                            </div>
                            <span className="text-[10px] text-zinc-500 font-mono shrink-0">
                              {dateStr}
                            </span>
                          </div>

                          {/* Reason */}
                          {log.reason && (
                            <div className="bg-zinc-950/20 rounded-lg px-3 py-2 border border-zinc-850">
                              <p className="text-[9px] text-zinc-500 uppercase tracking-wider mb-0.5 font-medium">Override Reason</p>
                              <p className="text-xs text-zinc-300 italic font-medium leading-relaxed">&ldquo;{log.reason}&rdquo;</p>
                            </div>
                          )}

                          {/* Delta Grid */}
                          {log.previous_values && Object.keys(log.previous_values).length > 0 && (
                            <div className="space-y-1">
                              <p className="text-[9px] text-zinc-500 uppercase tracking-wider font-medium">Fields Adjusted</p>
                              <div className="grid grid-cols-1 gap-1">
                                {Object.entries(log.previous_values).map(([field, oldVal]) => {
                                  const newVal = log.new_values?.[field] ?? '—';
                                  const fieldLabel = field.replace(/_/g, ' ');
                                  return (
                                    <div key={field} className="grid grid-cols-3 gap-1 bg-zinc-950/40 border border-zinc-850/30 rounded-lg px-2.5 py-1.5 text-[11px] items-center">
                                      <span className="text-zinc-500 font-medium capitalize truncate">{fieldLabel}</span>
                                      <span className="text-red-400/80 font-mono truncate line-through decoration-red-500/20">{String(oldVal)}</span>
                                      <span className="text-emerald-400 font-mono truncate font-semibold">&rarr; {String(newVal)}</span>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Action Footer */}
        {!locked ? (
          <div className="border-t border-zinc-850 p-4 space-y-3 bg-zinc-900/20">
            {/* Inline forms */}
            {mode === 'exclude' && (
              <div className="bg-zinc-900/80 rounded-xl p-3 border border-red-500/20 space-y-2">
                <p className="text-xs text-zinc-400 font-medium">Reason for exclusion:</p>
                <textarea
                  value={excludeReason}
                  onChange={e => setExcludeReason(e.target.value)}
                  rows={2}
                  placeholder="e.g. Duplicate entry, data quality issue…"
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-zinc-200 placeholder:text-zinc-650 focus:outline-none focus:border-red-500/50 resize-none"
                />
                <div className="flex gap-2">
                  <button onClick={() => act(() => onExclude(record.id, excludeReason))} disabled={busy || !excludeReason.trim()}
                    className="flex-1 bg-red-500/20 hover:bg-red-500/30 border border-red-500/30 text-red-400 text-xs font-semibold rounded-lg py-2 transition-all disabled:opacity-40">
                    Confirm Exclude
                  </button>
                  <button onClick={() => setMode(null)} className="px-3 text-xs text-zinc-500 hover:text-zinc-300 transition-colors">Cancel</button>
                </div>
              </div>
            )}

            {mode === 'delegate' && (
              <div className="bg-zinc-900/80 rounded-xl p-3 border border-blue-500/20 space-y-2">
                <p className="text-xs text-zinc-400 font-medium">Reassign to (email / username):</p>
                <input
                  value={delegateTo}
                  onChange={e => setDelegateTo(e.target.value)}
                  placeholder="colleague@org.com"
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-zinc-200 placeholder:text-zinc-650 focus:outline-none focus:border-blue-500/50"
                />
                <div className="flex gap-2">
                  <button onClick={() => act(() => onDelegate(record.id, { assigned_to: delegateTo }))} disabled={busy || !delegateTo.trim()}
                    className="flex-1 bg-blue-500/20 hover:bg-blue-500/30 border border-blue-500/30 text-blue-400 text-xs font-semibold rounded-lg py-2 transition-all disabled:opacity-40">
                    Reassign
                  </button>
                  <button onClick={() => setMode(null)} className="px-3 text-xs text-zinc-500 hover:text-zinc-300 transition-colors">Cancel</button>
                </div>
              </div>
            )}

            {isEditing && (
              <div className="bg-zinc-900/80 rounded-xl p-4 border border-emerald-500/20 space-y-3">
                <p className="text-xs text-emerald-400 font-semibold uppercase tracking-wider">Override / Edit Data Mode</p>
                <div className="space-y-1.5">
                  <label className="text-[10px] text-zinc-400 font-medium">Mandatory Audit Explanation (min 5 chars):</label>
                  <textarea
                    value={editNotes}
                    onChange={e => setEditNotes(e.target.value)}
                    rows={2}
                    placeholder="Provide a detailed audit explanation for the adjustments..."
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-emerald-500/50 resize-none"
                  />
                </div>
                <div className="flex gap-2">
                  <button onClick={() => act(handleSaveEdit)} disabled={busy || editNotes.trim().length < 5}
                    className="flex-1 bg-emerald-500 hover:bg-emerald-400 disabled:bg-emerald-500/20 disabled:text-zinc-650 disabled:cursor-not-allowed text-zinc-950 text-xs font-semibold rounded-lg py-2.5 transition-all">
                    Save Adjustments
                  </button>
                  <button onClick={() => { setIsEditing(false); setEditNotes(''); }} className="px-4 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded-lg transition-all">
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {/* Primary actions */}
            {!mode && !isEditing && (
              <div className="grid grid-cols-2 gap-2">
                <button
                  id={`approve-record-${record.id}`}
                  onClick={() => act(() => onApprove(record.id))}
                  disabled={busy}
                  className="flex items-center justify-center gap-2 bg-emerald-500 hover:bg-emerald-400 text-zinc-950 text-sm font-semibold rounded-xl py-2.5 transition-all disabled:opacity-50"
                >
                  {busy ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                  Approve & Lock
                </button>
                <button onClick={() => setMode('exclude')}
                  className="flex items-center justify-center gap-2 bg-red-500/10 hover:bg-red-500/20 border border-red-500/20 text-red-400 text-sm font-semibold rounded-xl py-2.5 transition-all">
                  <XCircle className="w-4 h-4" /> Exclude
                </button>
                <button onClick={() => setMode('delegate')}
                  className="flex items-center justify-center gap-2 bg-zinc-800/80 hover:bg-zinc-700/80 text-zinc-300 text-sm font-medium rounded-xl py-2.5 transition-all border border-zinc-700/50">
                  <UserCheck className="w-4 h-4" /> Reassign
                </button>
                <button onClick={() => { setIsEditing(true); setMode(null); }}
                  className="flex items-center justify-center gap-2 bg-zinc-800/80 hover:bg-zinc-700/80 text-zinc-300 text-sm font-medium rounded-xl py-2.5 transition-all border border-zinc-700/50">
                  <Pencil className="w-4 h-4" /> Override & Edit
                </button>
              </div>
            )}
          </div>
        ) : (
          <div className="border-t border-zinc-850 p-4 flex justify-end bg-zinc-900/20">
            <button onClick={onClose} className="px-5 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-sm font-semibold rounded-xl transition-all">
              Close
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Uploaded Files Tab ──────────────────────────────────────────────────
function UploadedFilesTab({ onSelectFile }) {
  const [batches, setBatches] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    ingestionAPI.batches()
      .then(res => setBatches(res.data?.results || res.data || []))
      .catch(() => setBatches([]))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-zinc-500 gap-2">
        <RefreshCw className="w-5 h-5 animate-spin text-emerald-400" />
        <span>Loading uploaded files…</span>
      </div>
    );
  }

  if (batches.length === 0) {
    return (
      <div className="glass rounded-2xl p-16 text-center">
        <Database className="w-12 h-12 text-zinc-700 mx-auto mb-4" />
        <h3 className="text-lg font-semibold text-white">No files uploaded yet</h3>
        <p className="text-zinc-500 text-sm mt-1 max-w-sm mx-auto">
          Please upload emission data files in the Ingestion Center first to view their breakdown here.
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {batches.map((b) => (
        <div key={b.id} 
          onClick={() => onSelectFile(b)}
          className="glass rounded-2xl p-5 border border-zinc-800 hover:border-zinc-750 transition-all cursor-pointer group flex flex-col justify-between hover:shadow-xl hover:shadow-emerald-500/5 relative overflow-hidden"
        >
          {/* Accent decoration */}
          <div className="absolute top-0 left-0 w-full h-[2px] bg-gradient-to-r from-transparent via-emerald-500/20 to-transparent group-hover:via-emerald-500/40 transition-all" />

          <div className="space-y-4">
            <div className="flex items-start justify-between">
              <div className="w-10 h-10 rounded-xl bg-zinc-900 border border-zinc-800 flex items-center justify-center group-hover:border-zinc-700 transition-all">
                <FileText className="w-5 h-5 text-emerald-400" />
              </div>
              <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${
                b.status === 'SUCCESS' ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20' :
                b.status === 'ERROR'   ? 'bg-red-500/15 text-red-400 border-red-500/20' :
                'bg-amber-500/15 text-amber-400 border-amber-500/20'
              }`}>
                {b.status || 'SUCCESS'}
              </span>
            </div>

            <div>
              <h3 className="text-sm font-semibold text-white group-hover:text-emerald-400 transition-all truncate pr-2">
                {b.file_name || b.filename || `Batch #${b.id.substring(0, 8)}`}
              </h3>
              <p className="text-xs text-zinc-500 mt-1">
                Uploaded {b.uploaded_at ? new Date(b.uploaded_at).toLocaleDateString() : '—'}
              </p>
            </div>
          </div>

          <div className="flex items-center justify-between border-t border-zinc-800/50 mt-4 pt-3 text-xs text-zinc-400">
            <span className="font-mono text-emerald-400/90 font-semibold">
              {b.row_count || 0} rows
            </span>
            <span className="flex items-center gap-1 text-[10px] font-semibold tracking-wider uppercase text-zinc-500 group-hover:text-zinc-300 transition-all">
              Inspect Data <ChevronRight className="w-3.5 h-3.5" />
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Batch File Details View ──────────────────────────────────────────────
function BatchFileDetailView({ batch, onBack, onOpenRecord, refreshKey, onRefresh }) {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);

  const [busy, setBusy] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const handleDelete = async () => {
    if (!window.confirm("Are you sure you want to delete this batch and all of its associated emission records? This action is completely irreversible!")) {
      return;
    }
    setDeleting(true);
    try {
      await ingestionAPI.deleteBatch(batch.id);
      onBack();
    } catch {
      alert("Failed to delete file.");
    } finally {
      setDeleting(false);
    }
  };

  useEffect(() => {
    if (!batch?.id) return;
    if (records.length === 0) {
      setLoading(true);
    }
    const params = { page, page_size: 15 };
    if (filter === 'pending') { params.approved = false; params.excluded = false; }
    if (filter === 'outlier') params.is_outlier = true;
    if (filter === 'approved') params.approved = true;
    if (filter === 'excluded') params.excluded = true;
    if (search.trim()) params.search = search.trim();

    ingestionAPI.batchDetail(batch.id, params)
      .then(res => {
        const data = res.data;
        setRecords(data.results ?? data ?? []);
        setTotal(data.count ?? (data.results ?? data ?? []).length);
      })
      .catch(() => {
        setRecords([]);
        setTotal(0);
      })
      .finally(() => setLoading(false));
  }, [batch, page, filter, search, refreshKey]);

  // Reset selected checkboxes on file/batch or refresh key/filter/search change
  useEffect(() => {
    setSelectedIds(new Set());
  }, [batch, refreshKey, filter, search]);

  const filteredRecords = records;
  const eligibleFiltered = filteredRecords.filter(r => !r.approved && !r.excluded);
  const allEligibleSelected = eligibleFiltered.length > 0 && eligibleFiltered.every(r => selectedIds.has(r.id));

  const toggleSelect = (id) => {
    const next = new Set(selectedIds);
    next.has(id) ? next.delete(id) : next.add(id);
    setSelectedIds(next);
  };

  const toggleAll = () => {
    if (allEligibleSelected) {
      const next = new Set(selectedIds);
      eligibleFiltered.forEach(r => next.delete(r.id));
      setSelectedIds(next);
    } else {
      const next = new Set(selectedIds);
      eligibleFiltered.forEach(r => next.add(r.id));
      setSelectedIds(next);
    }
  };

  const bulkApprove = async () => {
    if (!selectedIds.size) return;
    setBusy(true);
    try {
      await recordsAPI.bulkApprove([...selectedIds]);
      setSelectedIds(new Set());
      onRefresh?.();
    } catch {
      alert("Failed to approve selected records.");
    } finally {
      setBusy(false);
    }
  };

  const FILTER_OPTS = [
    { val: 'all', label: 'All Records' },
    { val: 'pending', label: 'Pending' },
    { val: 'outlier', label: 'Outliers' },
    { val: 'approved', label: 'Approved' },
    { val: 'excluded', label: 'Excluded' },
  ];

  return (
    <div className="space-y-6">
      {/* Back Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button onClick={onBack} className="p-2 rounded-xl bg-zinc-800/50 border border-zinc-700/50 hover:bg-zinc-700/50 hover:text-white text-zinc-300 transition-all cursor-pointer">
            <ChevronLeft className="w-4 h-4" />
          </button>
          <div>
            <div className="flex items-center gap-2.5">
              <h2 className="text-xl font-bold text-white tracking-tight">{batch.file_name || batch.filename}</h2>
              <span className="text-[10px] font-bold px-2 py-0.5 rounded-full border bg-emerald-500/15 text-emerald-400 border-emerald-500/20">
                {batch.source_type}
              </span>
            </div>
            <p className="text-zinc-400 text-sm mt-0.5">
              Showing {records.length} of {total} records processed from this upload. Flagged rows are highlighted in amber.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <p className="text-xs text-zinc-500">Uploaded by {batch.uploaded_by}</p>
            <p className="text-xs text-zinc-500 mt-0.5">{batch.uploaded_at ? new Date(batch.uploaded_at).toLocaleString() : '—'}</p>
          </div>
          {selectedIds.size > 0 && (
            <button
              onClick={bulkApprove}
              disabled={busy}
              id="batch-bulk-approve-btn"
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 disabled:bg-emerald-500/20 disabled:text-zinc-600 disabled:cursor-not-allowed text-zinc-950 text-sm font-semibold transition-all shadow-[0_0_15px_rgba(16,185,129,0.2)] cursor-pointer animate-fade-in animate-pulse-subtle"
            >
              {busy ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
              Approve {selectedIds.size} selected
            </button>
          )}
          <button
            onClick={handleDelete}
            disabled={deleting}
            className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold bg-red-500/10 border border-red-500/15 hover:bg-red-500 disabled:bg-red-550/20 disabled:text-zinc-600 disabled:cursor-not-allowed text-red-400 hover:text-zinc-950 transition-all shadow-[0_0_15px_rgba(239,68,68,0.1)] cursor-pointer"
            title="Delete this file and all its records"
          >
            {deleting ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-4 h-4" />}
            Delete File
          </button>
        </div>
      </div>

      {/* Toolbar for Search & Filters */}
      <div className="glass rounded-2xl p-4 flex flex-wrap items-center gap-3">
        {/* Search */}
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
          <input
            id="batch-search"
            type="text"
            placeholder="Search vendor, facility, date…"
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(1); }}
            className="w-full bg-zinc-900/50 border border-zinc-800 rounded-xl pl-9 pr-4 py-2.5 text-sm text-zinc-100 placeholder:text-zinc-650 focus:outline-none focus:border-emerald-500/50 focus:ring-1 focus:ring-emerald-500/30 transition-all"
          />
        </div>

        {/* Filters */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <Filter className="w-4 h-4 text-zinc-500 shrink-0" />
          {FILTER_OPTS.map(({ val, label }) => (
            <button key={val} onClick={() => { setFilter(val); setPage(1); }}
              id={`batch-filter-${val}`}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                filter === val
                  ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/20'
                  : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800'
              }`}>
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Records Table */}
      <div className="glass rounded-2xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-800/50 bg-zinc-900/10">
                <th className="w-10 px-5 py-3.5">
                  <input type="checkbox"
                    checked={allEligibleSelected}
                    onChange={toggleAll}
                    className="accent-emerald-500 cursor-pointer"
                  />
                </th>
                {['ID', 'Date', 'Normalized Category', 'Facility / Vendor', 'CO₂e (kg)', 'Country', 'Status', ''].map(h => (
                  <th key={h} className="px-5 py-3.5 text-left text-[11px] font-semibold text-zinc-500 uppercase tracking-wider whitespace-nowrap">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={9} className="py-20 text-center text-zinc-500">
                    <div className="flex items-center justify-center gap-2">
                      <RefreshCw className="w-4 h-4 animate-spin text-emerald-400" />
                      <span>Loading file data…</span>
                    </div>
                  </td>
                </tr>
              ) : records.length === 0 ? (
                <tr>
                  <td colSpan={9} className="py-20 text-center text-zinc-500">
                    <SlidersHorizontal className="w-8 h-8 mx-auto mb-2 text-zinc-700" />
                    <p className="text-sm">This file contains no records.</p>
                  </td>
                </tr>
              ) : filteredRecords.length === 0 ? (
                <tr>
                  <td colSpan={9} className="py-20 text-center text-zinc-500">
                    <SlidersHorizontal className="w-8 h-8 mx-auto mb-2 text-zinc-700" />
                    <p className="text-sm">No records match your search or filter.</p>
                  </td>
                </tr>
              ) : filteredRecords.map((rec) => {
                const flagged = rec.is_outlier;
                return (
                  <tr key={rec.id}
                    className={`border-b border-zinc-800/30 hover:bg-zinc-800/30 transition-all cursor-pointer relative ${
                      flagged 
                        ? 'bg-amber-500/8 border-l-4 border-l-amber-500 hover:bg-amber-500/12'
                        : ''
                    }`}
                  >
                    <td className="px-5 py-3.5" onClick={e => e.stopPropagation()}>
                      {!rec.approved && !rec.excluded && (
                        <input type="checkbox"
                          checked={selectedIds.has(rec.id)}
                          onChange={() => toggleSelect(rec.id)}
                          className="accent-emerald-500 cursor-pointer"
                        />
                      )}
                    </td>
                    <td className="px-5 py-3.5 font-mono text-xs text-zinc-500" onClick={() => onOpenRecord(rec)}>#{rec.id}</td>
                    <td className="px-5 py-3.5 text-zinc-300 whitespace-nowrap" onClick={() => onOpenRecord(rec)}>{rec.emission_date || '—'}</td>
                    <td className="px-5 py-3.5 text-zinc-300 whitespace-nowrap" onClick={() => onOpenRecord(rec)}>{getNormalizedLabel(rec)}</td>
                    <td className="px-5 py-3.5 text-zinc-300 max-w-[200px] truncate" onClick={() => onOpenRecord(rec)}>
                      {rec.facility_name || rec.vendor || '—'}
                    </td>
                    <td className="px-5 py-3.5 font-mono text-zinc-200 whitespace-nowrap font-bold" onClick={() => onOpenRecord(rec)}>
                      {rec.co2e_kg ? parseFloat(rec.co2e_kg).toFixed(3) : '—'}
                    </td>
                    <td className="px-5 py-3.5 text-zinc-400 whitespace-nowrap" onClick={() => onOpenRecord(rec)}>{rec.country || '—'}</td>
                    <td className="px-5 py-3.5" onClick={() => onOpenRecord(rec)}>
                      <RecordBadge record={rec} />
                    </td>
                    <td className="px-5 py-3.5 text-right pr-6" onClick={() => onOpenRecord(rec)}>
                      <ChevronRight className="w-4 h-4 text-zinc-500 ml-auto" />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {/* Pagination */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-zinc-800/50">
          <p className="text-xs text-zinc-500">
            Page {page} of {Math.max(1, Math.ceil(total / 15))} · {total} records
          </p>
          <div className="flex items-center gap-2">
            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
              className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed transition-all">
              <ChevronLeft className="w-4 h-4" />
            </button>
            {Array.from({ length: Math.min(5, Math.max(1, Math.ceil(total / 15))) }, (_, i) => {
              const totalPages = Math.max(1, Math.ceil(total / 15));
              const p = Math.max(1, Math.min(page - 2, totalPages - 4)) + i;
              if (p < 1 || p > totalPages) return null;
              return (
                <button key={p} onClick={() => setPage(p)}
                  className={`w-7 h-7 rounded-lg text-xs font-medium transition-all ${
                    p === page ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/20' : 'text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800'
                  }`}>
                  {p}
                </button>
              );
            })}
            <button onClick={() => setPage(p => Math.min(Math.max(1, Math.ceil(total / 15)), p + 1))} disabled={page === Math.max(1, Math.ceil(total / 15))}
              className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed transition-all">
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Main Ledger Page ──────────────────────────────────────────────────────────
const PAGE_SIZE = 15;

export default function CarbonLedger() {
  const [records, setRecords] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all'); // all | pending | outlier | approved | excluded
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [activeRecord, setActiveRecord] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [activeTab, setActiveTab] = useState('ledger');
  const [selectedBatch, setSelectedBatch] = useState(null);

  const refresh = useCallback(() => setRefreshKey(k => k + 1), []);

  useEffect(() => {
    if (records.length === 0) {
      setLoading(true);
    }
    const params = { page, page_size: PAGE_SIZE };
    if (filter === 'pending') { params.approved = false; params.excluded = false; }
    if (filter === 'outlier') params.is_outlier = true;
    if (filter === 'approved') params.approved = true;
    if (filter === 'excluded') params.excluded = true;
    if (search.trim()) params.search = search.trim();

    recordsAPI.list(params)
      .then(r => {
        const data = r.data;
        setRecords(data.results ?? data ?? []);
        setTotal(data.count ?? (data.results ?? data ?? []).length);
      })
      .catch(() => { setRecords([]); setTotal(0); })
      .finally(() => setLoading(false));
  }, [page, filter, search, refreshKey]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const toggleSelect = (id) => {
    const next = new Set(selectedIds);
    next.has(id) ? next.delete(id) : next.add(id);
    setSelectedIds(next);
  };

  const toggleAll = () => {
    if (selectedIds.size === records.length) setSelectedIds(new Set());
    else setSelectedIds(new Set(records.filter(r => !r.approved && !r.excluded).map(r => r.id)));
  };

  const [bulkApproving, setBulkApproving] = useState(false);
  const bulkApprove = async () => {
    if (!selectedIds.size) return;
    const idsToApprove = new Set(selectedIds);
    setSelectedIds(new Set());
    
    // Optimistic Update
    setRecords(prev => prev.map(r => idsToApprove.has(r.id) ? { ...r, approved: true, excluded: false, workflow_status: 'APPROVED', status: 'APPROVED' } : r));
    
    setBulkApproving(true);
    try {
      await recordsAPI.bulkApprove([...idsToApprove]);
      refresh();
    } catch {
      alert("Failed to bulk approve records.");
      refresh();
    } finally {
      setBulkApproving(false);
    }
  };

  const approve = async (id) => {
    // Optimistic Update
    setRecords(prev => prev.map(r => r.id === id ? { ...r, approved: true, excluded: false, workflow_status: 'APPROVED', status: 'APPROVED' } : r));
    setSelectedIds(prev => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
    try {
      await recordsAPI.approve(id);
      refresh();
    } catch {
      alert("Failed to approve record.");
      refresh();
    }
  };

  const exclude = async (id, reason) => {
    // Optimistic Update
    setRecords(prev => prev.map(r => r.id === id ? { ...r, approved: false, excluded: true, workflow_status: 'REJECTED', status: 'REJECTED' } : r));
    setSelectedIds(prev => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
    try {
      await recordsAPI.exclude(id, reason);
      refresh();
    } catch {
      alert("Failed to exclude record.");
      refresh();
    }
  };

  const delegate = async (id, data) => {
    // Optimistic Update: append analyst note
    setRecords(prev => prev.map(r => r.id === id ? { ...r, override_note: `Delegated to: ${data.assigned_to}`, analyst_notes: `Delegated to: ${data.assigned_to}` } : r));
    try {
      await recordsAPI.delegate(id, data);
      refresh();
    } catch {
      alert("Failed to delegate record.");
      refresh();
    }
  };

  const override = async (id, data) => {
    // Optimistic Update
    setRecords(prev => prev.map(r => r.id === id ? { ...r, ...data, approved: false, excluded: false, workflow_status: 'PENDING_REVIEW', status: 'PENDING_REVIEW' } : r));
    try {
      await recordsAPI.override(id, data);
      refresh();
    } catch {
      alert("Failed to override record.");
      refresh();
    }
  };

  const FILTER_OPTS = [
    { val: 'all', label: 'All Records' },
    { val: 'pending', label: 'Pending' },
    { val: 'outlier', label: 'Outliers' },
    { val: 'approved', label: 'Approved' },
    { val: 'excluded', label: 'Excluded' },
  ];

  return (
    <div className="p-8 space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Carbon Ledger</h1>
          <p className="text-zinc-400 text-sm mt-1">
            {activeTab === 'ledger' 
              ? `${total} total emission records · review, approve, and lock.`
              : 'Audit & inspect your uploaded files and ingestion history.'}
          </p>
        </div>
        <button onClick={refresh} className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium text-zinc-300 bg-zinc-800/50 hover:bg-zinc-700/50 border border-zinc-700/50 transition-all">
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </div>

      {/* Tab Switcher */}
      <div className="flex border-b border-zinc-800/50 gap-6 mb-4">
        <button 
          onClick={() => { setActiveTab('ledger'); setSelectedBatch(null); }}
          className={`pb-3 text-sm font-semibold transition-all relative ${
            activeTab === 'ledger' ? 'text-emerald-400 font-bold' : 'text-zinc-500 hover:text-zinc-300'
          }`}
        >
          Emissions Ledger
          {activeTab === 'ledger' && (
            <div className="absolute bottom-0 left-0 w-full h-[2px] bg-emerald-500" />
          )}
        </button>
        <button 
          onClick={() => setActiveTab('files')}
          className={`pb-3 text-sm font-semibold transition-all relative ${
            activeTab === 'files' ? 'text-emerald-400 font-bold' : 'text-zinc-500 hover:text-zinc-300'
          }`}
        >
          Uploaded Files
          {activeTab === 'files' && (
            <div className="absolute bottom-0 left-0 w-full h-[2px] bg-emerald-500" />
          )}
        </button>
      </div>

      {activeTab === 'ledger' ? (
        <>
          {/* Toolbar */}
          <div className="glass rounded-2xl p-4 flex flex-wrap items-center gap-3">
            {/* Search */}
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
              <input
                id="ledger-search"
                type="text"
                placeholder="Search vendor, facility, date…"
                value={search}
                onChange={e => { setSearch(e.target.value); setPage(1); }}
                className="w-full bg-zinc-900/50 border border-zinc-800 rounded-xl pl-9 pr-4 py-2.5 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-emerald-500/50 focus:ring-1 focus:ring-emerald-500/30 transition-all"
              />
            </div>

            {/* Filters */}
            <div className="flex items-center gap-1.5 flex-wrap">
              <Filter className="w-4 h-4 text-zinc-500 shrink-0" />
              {FILTER_OPTS.map(({ val, label }) => (
                <button key={val} onClick={() => { setFilter(val); setPage(1); }}
                  id={`filter-${val}`}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                    filter === val
                      ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/20'
                      : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800'
                  }`}>
                  {label}
                </button>
              ))}
            </div>

            {/* Bulk approve */}
            {selectedIds.size > 0 && (
              <button onClick={bulkApprove}
                disabled={bulkApproving}
                id="bulk-approve-btn"
                className="flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 disabled:bg-emerald-500/20 disabled:text-zinc-650 disabled:cursor-not-allowed text-zinc-950 text-sm font-semibold transition-all shadow-[0_0_15px_rgba(16,185,129,0.2)] cursor-pointer"
              >
                {bulkApproving ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                Approve {selectedIds.size} selected
              </button>
            )}
          </div>

          {/* Table */}
          <div className="glass rounded-2xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-800/50">
                    <th className="w-10 px-4 py-3">
                      <input type="checkbox"
                        checked={selectedIds.size > 0 && selectedIds.size === records.filter(r => !r.approved && !r.excluded).length}
                        onChange={toggleAll}
                        className="accent-emerald-500 cursor-pointer"
                      />
                    </th>
                    {['ID', 'Date', 'Normalized Category', 'Facility / Vendor', 'CO₂e (kg)', 'Country', 'Status', ''].map(h => (
                      <th key={h} className="px-4 py-3 text-left text-[11px] font-semibold text-zinc-500 uppercase tracking-wider whitespace-nowrap">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr><td colSpan={9} className="py-16 text-center text-zinc-500">
                      <div className="flex items-center justify-center gap-2">
                        <RefreshCw className="w-4 h-4 animate-spin text-emerald-400" />
                        <span className="text-sm">Loading records…</span>
                      </div>
                    </td></tr>
                  ) : records.length === 0 ? (
                    <tr><td colSpan={9} className="py-16 text-center text-zinc-500">
                      <SlidersHorizontal className="w-8 h-8 mx-auto mb-2 text-zinc-700" />
                      <p className="text-sm">No records match your current filters.</p>
                    </td></tr>
                  ) : records.map((rec, idx) => (
                    <tr key={rec.id}
                      className={`border-b border-zinc-800/30 hover:bg-zinc-800/20 transition-all cursor-pointer ${
                        activeRecord?.id === rec.id ? 'bg-emerald-500/5' : ''
                      }`}
                      style={{ animationDelay: `${idx * 20}ms` }}
                    >
                      <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                        {!rec.approved && !rec.excluded && (
                          <input type="checkbox"
                            checked={selectedIds.has(rec.id)}
                            onChange={() => toggleSelect(rec.id)}
                            className="accent-emerald-500 cursor-pointer"
                          />
                        )}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-zinc-500" onClick={() => setActiveRecord(rec)}>#{rec.id}</td>
                      <td className="px-4 py-3 text-zinc-300 whitespace-nowrap" onClick={() => setActiveRecord(rec)}>
                        {rec.emission_date || '—'}
                      </td>
                      <td className="px-4 py-3 text-zinc-300 whitespace-nowrap" onClick={() => setActiveRecord(rec)}>
                        {getNormalizedLabel(rec)}
                      </td>
                      <td className="px-4 py-3 text-zinc-300 max-w-[160px] truncate" onClick={() => setActiveRecord(rec)}>
                        {rec.facility_name || rec.vendor || '—'}
                      </td>
                      <td className="px-4 py-3 font-mono text-zinc-200 whitespace-nowrap" onClick={() => setActiveRecord(rec)}>
                        {rec.co2e_kg ? parseFloat(rec.co2e_kg).toFixed(3) : '—'}
                      </td>
                      <td className="px-4 py-3 text-zinc-400 whitespace-nowrap" onClick={() => setActiveRecord(rec)}>
                        {rec.country || '—'}
                      </td>
                      <td className="px-4 py-3" onClick={() => setActiveRecord(rec)}>
                        <RecordBadge record={rec} />
                      </td>
                      <td className="px-4 py-3">
                        <button onClick={() => setActiveRecord(rec)}
                          className="text-zinc-500 hover:text-emerald-400 transition-colors p-1 rounded-lg hover:bg-emerald-500/10">
                          <ChevronRight className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div className="flex items-center justify-between px-6 py-4 border-t border-zinc-800/50">
              <p className="text-xs text-zinc-500">
                Page {page} of {totalPages} · {total} records
              </p>
              <div className="flex items-center gap-2">
                <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                  className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed transition-all">
                  <ChevronLeft className="w-4 h-4" />
                </button>
                {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                  const p = Math.max(1, Math.min(page - 2, totalPages - 4)) + i;
                  return (
                    <button key={p} onClick={() => setPage(p)}
                      className={`w-7 h-7 rounded-lg text-xs font-medium transition-all ${
                        p === page ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/20' : 'text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800'
                      }`}>
                      {p}
                    </button>
                  );
                })}
                <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}
                  className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed transition-all">
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        </>
      ) : selectedBatch ? (
        <BatchFileDetailView 
          batch={selectedBatch} 
          onBack={() => setSelectedBatch(null)} 
          onOpenRecord={setActiveRecord}
          refreshKey={refreshKey}
          onRefresh={refresh}
        />
      ) : (
        <UploadedFilesTab onSelectFile={setSelectedBatch} />
      )}

      {/* Centered Modal */}
      {activeRecord && createPortal(
        <RecordModal
          record={activeRecord}
          onClose={() => setActiveRecord(null)}
          onApprove={approve}
          onExclude={exclude}
          onDelegate={delegate}
          onOverride={override}
        />,
        document.body
      )}
    </div>
  );
}
