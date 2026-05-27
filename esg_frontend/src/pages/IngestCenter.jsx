import { useState, useRef, useCallback, useEffect } from 'react';
import { ingestionAPI } from '../lib/api';
import api from '../lib/api';
import {
  Upload, FileUp, X, CheckCircle2, AlertCircle, Download,
  ChevronDown, ChevronRight, Loader2, FileSpreadsheet, Database, Trash2
} from 'lucide-react';

const SOURCE_TYPES = [
  { value: 'SAP',     label: 'SAP / ERP',          desc: 'Electricity, gas, fuel from SAP' },
  { value: 'UTILITY', label: 'Utility Bills',       desc: 'Grid electricity & water meters' },
  { value: 'TRAVEL',  label: 'Business Travel',     desc: 'Flights, road, rail bookings' },
];

const TEMPLATE_FILES = [
  {
    id: 'sap',
    name: 'SAP / ERP Utility Data',
    description: 'Electricity, gas, and fuel consumption from SAP or utility bills.',
    columns: ['date', 'facility_name', 'country', 'city', 'source_type', 'quantity', 'unit', 'vendor'],
    filename: 'sap_template.csv',
  },
  {
    id: 'travel',
    name: 'Business Travel Log',
    description: 'Air, road, and rail travel emissions from expense reports.',
    columns: ['date', 'origin', 'destination', 'distance_km', 'transport_mode', 'passengers', 'travel_class'],
    filename: 'travel_template.csv',
  },
  {
    id: 'waste',
    name: 'Waste & Refrigerants',
    description: 'Waste-to-landfill and refrigerant leak records.',
    columns: ['date', 'facility_name', 'waste_type', 'quantity_kg', 'disposal_method', 'vendor'],
    filename: 'waste_template.csv',
  },
];

function downloadCsv(columns, filename) {
  const header = columns.join(',');
  const row = columns.map(() => '').join(',');
  const blob = new Blob([header + '\n' + row], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

/** Fetches /api/tenants/ and returns the first tenant id, or null */
async function fetchFirstTenantId() {
  try {
    const res = await api.get('/api/tenants/');
    const tenants = res.data?.results ?? res.data ?? [];
    return tenants[0]?.id ?? null;
  } catch {
    return null;
  }
}

function UploadZone({ onUploaded }) {
  const [dragActive, setDragActive]   = useState(false);
  const [file, setFile]               = useState(null);
  const [sourceType, setSourceType]   = useState('SAP');
  const [uploading, setUploading]     = useState(false);
  const [result, setResult]           = useState(null);
  const [error, setError]             = useState('');
  const inputRef = useRef(null);

  const processFile = useCallback(async (f) => {
    if (!f) return;
    if (!f.name.match(/\.(csv|xls|xlsx|xml|json|idoc|txt)$/i)) {
      setError('Please upload a valid data file (CSV, Excel, XML, JSON, IDoc, or TXT).');
      return;
    }
    setFile(f);
    setError('');
    setResult(null);
    setUploading(true);

    try {
      // Resolve tenant_id from the backend
      const tenantId = await fetchFirstTenantId();
      if (!tenantId) {
        setError('No tenant found. Please ask your admin to create an organisation in the backend first.');
        setUploading(false);
        return;
      }

      const fd = new FormData();
      fd.append('file', f);
      fd.append('tenant_id', tenantId);
      fd.append('source_type', sourceType);   // SAP | UTILITY | TRAVEL

      const res = await ingestionAPI.upload(fd);
      setResult(res.data);
      onUploaded?.();
    } catch (err) {
      setError(
        err?.response?.data?.detail ||
        err?.response?.data?.error ||
        'Upload failed. Check the file format and try again.'
      );
    } finally {
      setUploading(false);
    }
  }, [sourceType, onUploaded]);

  const onDrop = (e) => {
    e.preventDefault();
    setDragActive(false);
    const f = e.dataTransfer.files?.[0];
    if (f) processFile(f);
  };

  const onInputChange = (e) => {
    if (e.target.files?.[0]) processFile(e.target.files[0]);
  };

  const reset = () => { setFile(null); setResult(null); setError(''); };

  return (
    <div className="glass rounded-2xl p-6">
      <h2 className="text-base font-semibold text-white mb-4 flex items-center gap-2">
        <FileUp className="w-5 h-5 text-emerald-400" />
        Upload Emissions Data
      </h2>

      {!result ? (
        <>
          {/* ── Source type selector ───────────────────────────────────── */}
          <div className="mb-4">
            <p className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">
              Data Source Type
            </p>
            <div className="grid grid-cols-3 gap-2">
              {SOURCE_TYPES.map(({ value, label, desc }) => (
                <button
                  key={value}
                  type="button"
                  id={`source-type-${value.toLowerCase()}`}
                  onClick={() => setSourceType(value)}
                  className={`flex flex-col gap-1 p-3 rounded-xl border text-left transition-all ${
                    sourceType === value
                      ? 'border-emerald-500/40 bg-emerald-500/8 text-emerald-300'
                      : 'border-zinc-800 bg-zinc-900/50 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200'
                  }`}
                >
                  <span className="text-xs font-semibold">{label}</span>
                  <span className="text-[10px] leading-tight opacity-70">{desc}</span>
                </button>
              ))}
            </div>
          </div>

          {/* ── Drop zone ─────────────────────────────────────────────── */}
          <div
            id="upload-dropzone"
            onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
            onDragLeave={() => setDragActive(false)}
            onDrop={onDrop}
            onClick={() => !uploading && inputRef.current?.click()}
            className={`relative rounded-xl border-2 border-dashed cursor-pointer transition-all duration-200 p-10 flex flex-col items-center text-center gap-3 ${
              dragActive
                ? 'border-emerald-500 bg-emerald-500/5'
                : 'border-zinc-700 hover:border-emerald-500/50 hover:bg-zinc-800/20'
            } ${uploading ? 'pointer-events-none' : ''}`}
          >
            <input
              ref={inputRef}
              type="file"
              accept=".csv,.xls,.xlsx,.xml,.json,.idoc,.txt"
              onChange={onInputChange}
              className="hidden"
              id="file-upload-input"
            />
            <div className={`w-14 h-14 rounded-2xl flex items-center justify-center transition-all ${dragActive ? 'bg-emerald-500/20' : 'bg-zinc-800'}`}>
              <Upload className={`w-7 h-7 ${dragActive ? 'text-emerald-400' : 'text-zinc-500'}`} />
            </div>

            {uploading ? (
              <div className="flex items-center gap-2 text-emerald-400">
                <Loader2 className="w-4 h-4 animate-spin" />
                <span className="text-sm">Processing {file?.name}…</span>
              </div>
            ) : file ? (
              <div className="flex items-center gap-2 text-zinc-300">
                <FileSpreadsheet className="w-4 h-4 text-emerald-400" />
                <span className="text-sm font-medium">{file.name}</span>
                <button
                  onClick={(e) => { e.stopPropagation(); reset(); }}
                  className="text-zinc-500 hover:text-red-400 transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <div>
                <p className="text-sm font-medium text-zinc-200">Drag & drop or click to upload</p>
                <p className="text-xs text-zinc-500 mt-1">
                  CSV, XLS, XLSX, XML, JSON, IDoc, TXT · Max 25 MB · Source: <span className="text-emerald-400 font-semibold">{sourceType}</span>
                </p>
              </div>
            )}
          </div>

          {error && (
            <div className="flex items-start gap-2.5 mt-3 bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3">
              <AlertCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
              <p className="text-red-400 text-sm">{error}</p>
            </div>
          )}
        </>
      ) : (
        /* ── Success state ─────────────────────────────────────────────── */
        <div className="animate-fade-in">
          <div className="flex items-center gap-3 bg-emerald-500/10 border border-emerald-500/20 rounded-xl px-4 py-3.5 mb-4">
            <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
            <div>
              <p className="text-sm font-semibold text-emerald-300">File processed successfully</p>
              <p className="text-xs text-zinc-400 mt-0.5">
                {result.records_created ?? result.rows_processed ?? '—'} records ingested
                {result.parser_errors ? ` · ${result.parser_errors} parse errors` : ''}
              </p>
            </div>
            <button onClick={reset} className="ml-auto text-zinc-500 hover:text-zinc-300 transition-colors">
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Parse log */}
          <details className="group">
            <summary className="flex items-center gap-2 text-xs text-zinc-400 cursor-pointer select-none hover:text-zinc-200 transition-colors py-2">
              <ChevronRight className="w-3.5 h-3.5 group-open:rotate-90 transition-transform" />
              View parse log
            </summary>
            <pre className="mt-2 bg-zinc-900/80 rounded-xl p-4 text-xs text-zinc-400 font-mono overflow-auto max-h-48 leading-relaxed">
              {JSON.stringify(result, null, 2)}
            </pre>
          </details>

          <button onClick={reset} className="mt-4 text-sm text-emerald-400 hover:text-emerald-300 transition-colors flex items-center gap-1.5">
            <Upload className="w-3.5 h-3.5" /> Upload another file
          </button>
        </div>
      )}
    </div>
  );
}

function BatchHistory({ refreshKey }) {
  const [batches, setBatches]   = useState([]);
  const [loading, setLoading]   = useState(true);
  const [expanded, setExpanded] = useState(null);

  const loadBatches = useCallback(() => {
    setLoading(true);
    ingestionAPI.batches()
      .then(r => setBatches(r.data?.results || r.data || []))
      .catch(() => setBatches([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    loadBatches();
  }, [refreshKey, loadBatches]);

  const handleDeleteBatch = async (e, id) => {
    e.stopPropagation();
    if (!window.confirm("Are you sure you want to delete this batch and all of its associated emission records? This action is completely irreversible!")) {
      return;
    }
    try {
      await ingestionAPI.deleteBatch(id);
      loadBatches();
    } catch (err) {
      alert("Failed to delete batch.");
    }
  };

  return (
    <div className="glass rounded-2xl p-6">
      <h2 className="text-base font-semibold text-white mb-4 flex items-center gap-2">
        <Database className="w-5 h-5 text-emerald-400" />
        Ingestion History
      </h2>

      {loading ? (
        <div className="flex items-center gap-2 text-zinc-500 py-8 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span className="text-sm">Loading batches…</span>
        </div>
      ) : batches.length === 0 ? (
        <div className="text-center py-10">
          <Upload className="w-8 h-8 text-zinc-700 mx-auto mb-3" />
          <p className="text-zinc-500 text-sm">No uploads yet — upload your first file above.</p>
        </div>
      ) : (
        <div className="divide-y divide-zinc-800/50">
          {batches.map((b) => (
            <div key={b.id}>
              <div
                onClick={() => setExpanded(expanded === b.id ? null : b.id)}
                className="w-full flex items-center gap-4 py-3.5 hover:bg-zinc-800/20 rounded-xl px-2 transition-all text-left cursor-pointer select-none"
              >
                <div className={`w-2 h-2 rounded-full shrink-0 ${
                  b.status === 'SUCCESS' ? 'bg-emerald-400' :
                  b.status === 'ERROR'   ? 'bg-red-400'    : 'bg-amber-400'
                }`} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-zinc-200 font-medium truncate">
                    {b.file_name || b.filename || `Batch #${b.id}`}
                  </p>
                  <p className="text-xs text-zinc-500">
                    {b.source_type || '—'} · {b.uploaded_at ? new Date(b.uploaded_at).toLocaleString() : '—'}
                  </p>
                </div>
                <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${
                  b.status === 'SUCCESS' ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20' :
                  b.status === 'ERROR'   ? 'bg-red-500/15 text-red-400 border-red-500/20' :
                  'bg-amber-500/15 text-amber-400 border-amber-500/20'
                }`}>
                  {(b.status || 'DONE')}
                </span>

                <button 
                  onClick={(e) => handleDeleteBatch(e, b.id)}
                  className="p-1.5 rounded-lg bg-red-500/10 border border-red-500/15 hover:bg-red-500/20 text-red-400 transition-all shrink-0 ml-2"
                  title="Delete batch and all its records"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>

                <ChevronDown className={`w-4 h-4 text-zinc-500 transition-transform ${expanded === b.id ? 'rotate-180' : ''} ml-1`} />
              </div>

              {expanded === b.id && (
                <pre className="mx-2 mb-3 bg-zinc-900/80 rounded-xl p-4 text-xs text-zinc-400 font-mono overflow-auto max-h-40 leading-relaxed">
                  {b.parse_log
                    ? (typeof b.parse_log === 'string' ? b.parse_log : JSON.stringify(b.parse_log, null, 2))
                    : `File: ${b.file_name || b.filename || '—'}\nSource: ${b.source_type || '—'}\nUploaded by: ${b.uploaded_by || '—'}`}
                </pre>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function IngestCenter() {
  const [refreshKey, setRefreshKey] = useState(0);

  return (
    <div className="p-8 space-y-8 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-white tracking-tight">Ingestion Center</h1>
        <p className="text-zinc-400 text-sm mt-1">
          Upload emission data files for automated normalisation and carbon accounting.
        </p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-5 gap-6">
        <div className="xl:col-span-3 space-y-6">
          <UploadZone onUploaded={() => setRefreshKey(k => k + 1)} />
          <BatchHistory refreshKey={refreshKey} />
        </div>

        {/* ── Templates Panel ───────────────────────────────────────────── */}
        <div className="xl:col-span-2">
          <div className="glass rounded-2xl p-6">
            <h2 className="text-base font-semibold text-white mb-1 flex items-center gap-2">
              <Download className="w-5 h-5 text-emerald-400" />
              Download Templates
            </h2>
            <p className="text-xs text-zinc-500 mb-5">
              Use these templates to ensure your data is formatted correctly before uploading.
            </p>
            <div className="flex flex-col gap-3">
              {TEMPLATE_FILES.map((t) => (
                <div key={t.id} className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 hover:border-zinc-700 transition-all">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1">
                      <p className="text-sm font-medium text-zinc-200">{t.name}</p>
                      <p className="text-xs text-zinc-500 mt-0.5">{t.description}</p>
                      <div className="flex flex-wrap gap-1 mt-2.5">
                        {t.columns.map(c => (
                          <span key={c} className="text-[10px] font-mono bg-zinc-800 text-zinc-400 px-1.5 py-0.5 rounded">
                            {c}
                          </span>
                        ))}
                      </div>
                    </div>
                    <button
                      id={`download-template-${t.id}`}
                      onClick={() => downloadCsv(t.columns, t.filename)}
                      className="shrink-0 p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/15 text-emerald-400 hover:bg-emerald-500/20 transition-all"
                      title={`Download ${t.filename}`}
                    >
                      <Download className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-5 rounded-xl bg-zinc-800/30 border border-zinc-700/50 p-4">
              <p className="text-xs font-semibold text-zinc-300 mb-2">Supported Formats</p>
              <ul className="text-xs text-zinc-500 space-y-1.5">
                <li>• CSV (comma-separated, UTF-8)</li>
                <li>• Excel XLS / XLSX</li>
                <li>• Column headers auto-resolved (fuzzy matching)</li>
                <li>• Units auto-normalised (kWh, MJ, litres, km, miles…)</li>
                <li>• Z-score outliers flagged automatically</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
