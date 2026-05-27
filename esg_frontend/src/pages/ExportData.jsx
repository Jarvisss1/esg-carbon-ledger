import { useState, useEffect } from 'react';
import { exportAPI, ingestionAPI } from '../lib/api';
import { useAuth } from '../context/AuthContext';
import {
  Download, Mail, FileSpreadsheet, FileText, Send, CheckCircle2,
  AlertCircle, Loader2, Lock, Clock, ChevronDown, RefreshCw, Shield
} from 'lucide-react';

function ExportLogs() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);

  const load = () => {
    setLoading(true);
    exportAPI.logs()
      .then(r => setLogs(r.data?.results || r.data || []))
      .catch(() => setLogs([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  return (
    <div className="glass rounded-2xl p-6">
      <div onClick={() => setOpen(o => !o)} className="w-full flex items-center gap-2 text-base font-semibold text-white cursor-pointer select-none">
        <Clock className="w-5 h-5 text-emerald-400" />
        Export History
        <ChevronDown className={`w-4 h-4 text-zinc-500 ml-auto transition-transform ${open ? 'rotate-180' : ''}`} />
        <button onClick={(e) => { e.stopPropagation(); load(); }} className="p-1 text-zinc-500 hover:text-zinc-300 transition-colors">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {open && (
        <div className="mt-4">
          {loading ? (
            <div className="flex items-center gap-2 text-zinc-500 py-6 justify-center">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span className="text-sm">Loading logs…</span>
            </div>
          ) : logs.length === 0 ? (
            <div className="text-center py-8">
              <Download className="w-7 h-7 text-zinc-700 mx-auto mb-2" />
              <p className="text-zinc-500 text-sm">No exports yet.</p>
            </div>
          ) : (
            <div className="divide-y divide-zinc-800/50">
              {logs.map((log, i) => (
                <div key={i} className="flex items-center gap-4 py-3.5">
                  <div className={`w-2 h-2 rounded-full shrink-0 ${log.success ? 'bg-emerald-400' : 'bg-red-400'}`} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-zinc-200 truncate">{log.format?.toUpperCase() || 'EXPORT'} · {log.rows_exported ?? '—'} approved rows</p>
                    <p className="text-xs text-zinc-500">{log.delivery_method || 'download'} · {log.exported_at ? new Date(log.exported_at).toLocaleString() : '—'}</p>
                  </div>
                  {log.email_recipient && (
                    <span className="text-xs text-zinc-400 font-mono truncate max-w-[140px]">{log.email_recipient}</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function ExportData() {
  const { user } = useAuth();
  const [format, setFormat] = useState('csv'); // csv | xlsx
  const [delivery, setDelivery] = useState('download'); // download | email
  const [email, setEmail] = useState(user?.email || '');
  const [batches, setBatches] = useState([]);
  const [selectedBatchId, setSelectedBatchId] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null); // { success, message }
  const [approvedOnly] = useState(true); // Always export approved only

  useEffect(() => {
    ingestionAPI.batches()
      .then(res => setBatches(res.data?.results || res.data || []))
      .catch(() => setBatches([]));
  }, []);

  const handleExport = async () => {
    setLoading(true);
    setResult(null);
    try {
      const params = { approved_only: true };
      if (selectedBatchId) {
        params.batch_id = selectedBatchId;
      }

      if (delivery === 'download') {
        let res;
        if (format === 'csv') res = await exportAPI.csv(params);
        else res = await exportAPI.xlsx(params);

        // Trigger browser download
        const blob = new Blob([res.data], {
          type: format === 'csv' ? 'text/csv' : 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `esg_export_${new Date().toISOString().slice(0, 10)}.${format}`;
        a.click();
        URL.revokeObjectURL(url);
        setResult({ success: true, message: `${format.toUpperCase()} downloaded successfully!` });
      } else {
        // Email delivery
        await exportAPI.email({ format, email_to: email, approved_only: true, batch_id: selectedBatchId });
        setResult({ success: true, message: `Export sent to ${email}. Check your inbox (or sent_emails/ in dev mode).` });
      }
    } catch (err) {
      const msg = err?.response?.data?.detail || err?.response?.data?.error || 'Export failed. Ensure approved records exist.';
      setResult({ success: false, message: msg });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-8 space-y-8 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-white tracking-tight">Export Data</h1>
        <p className="text-zinc-400 text-sm mt-1">Download or email your approved emission records for reporting.</p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* Export Card */}
        <div className="xl:col-span-2">
          <div className="glass rounded-2xl p-7 space-y-6">
            {/* Compliance Notice */}
            <div className="flex items-start gap-3 bg-emerald-500/8 border border-emerald-500/15 rounded-xl p-4">
              <Shield className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-semibold text-emerald-300">Approved Records Only</p>
                <p className="text-xs text-zinc-400 mt-0.5">
                  This platform enforces strict export compliance — only analyst-approved, locked rows are included in any export.
                  Pending or excluded records are never exported.
                </p>
              </div>
            </div>

            {/* Scope / Batch selection */}
            <div>
              <p className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Data Scope (Uploaded File)</p>
              <div className="relative">
                <select
                  id="export-batch-select"
                  value={selectedBatchId}
                  onChange={e => setSelectedBatchId(e.target.value)}
                  className="w-full bg-zinc-900/50 border border-zinc-800 rounded-xl px-4 py-3 text-sm text-zinc-100 placeholder:text-zinc-650 focus:outline-none focus:border-emerald-500/50 focus:ring-1 focus:ring-emerald-500/30 transition-all appearance-none cursor-pointer"
                >
                  <option value="">All Uploaded Files (Entire Ledger)</option>
                  {batches.map(b => (
                    <option key={b.id} value={b.id} className="bg-zinc-950">
                      {b.file_name || b.filename || `Batch #${b.id.substring(0, 8)}`} ({b.source_type} · {new Date(b.uploaded_at).toLocaleDateString()})
                    </option>
                  ))}
                </select>
                <ChevronDown className="absolute right-4 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500 pointer-events-none" />
              </div>
            </div>

            {/* Format Selection */}
            <div>
              <p className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-3">Export Format</p>
              <div className="grid grid-cols-2 gap-3">
                {[
                  { val: 'csv', label: 'CSV', icon: FileText, desc: 'Universal spreadsheet format. Works with Excel, Google Sheets, and any BI tool.' },
                  { val: 'xlsx', label: 'Excel XLSX', icon: FileSpreadsheet, desc: 'Native Excel format with styling, multiple sheets, and formula support.' },
                ].map(({ val, label, icon: Icon, desc }) => (
                  <label key={val}
                    className={`flex flex-col gap-2 p-4 rounded-xl border cursor-pointer transition-all ${
                      format === val
                        ? 'border-emerald-500/40 bg-emerald-500/8'
                        : 'border-zinc-800 bg-zinc-900/50 hover:border-zinc-700'
                    }`}>
                    <input type="radio" name="format" value={val} checked={format === val} onChange={() => setFormat(val)} className="sr-only" />
                    <div className="flex items-center gap-2.5">
                      <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${format === val ? 'bg-emerald-500/15' : 'bg-zinc-800'}`}>
                        <Icon className={`w-4 h-4 ${format === val ? 'text-emerald-400' : 'text-zinc-500'}`} />
                      </div>
                      <span className={`text-sm font-semibold ${format === val ? 'text-emerald-300' : 'text-zinc-300'}`}>{label}</span>
                      <div className={`ml-auto w-4 h-4 rounded-full border-2 flex items-center justify-center ${format === val ? 'border-emerald-400' : 'border-zinc-600'}`}>
                        {format === val && <div className="w-2 h-2 rounded-full bg-emerald-400" />}
                      </div>
                    </div>
                    <p className="text-xs text-zinc-500">{desc}</p>
                  </label>
                ))}
              </div>
            </div>

            {/* Delivery Method */}
            <div>
              <p className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-3">Delivery Method</p>
              <div className="grid grid-cols-2 gap-3">
                {[
                  { val: 'download', label: 'Direct Download', icon: Download, desc: 'Instantly download to your browser.' },
                  { val: 'email', label: 'Send via Email', icon: Mail, desc: 'Attach and send to your inbox.' },
                ].map(({ val, label, icon: Icon, desc }) => (
                  <label key={val}
                    className={`flex flex-col gap-2 p-4 rounded-xl border cursor-pointer transition-all ${
                      delivery === val
                        ? 'border-emerald-500/40 bg-emerald-500/8'
                        : 'border-zinc-800 bg-zinc-900/50 hover:border-zinc-700'
                    }`}>
                    <input type="radio" name="delivery" value={val} checked={delivery === val} onChange={() => setDelivery(val)} className="sr-only" />
                    <div className="flex items-center gap-2.5">
                      <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${delivery === val ? 'bg-emerald-500/15' : 'bg-zinc-800'}`}>
                        <Icon className={`w-4 h-4 ${delivery === val ? 'text-emerald-400' : 'text-zinc-500'}`} />
                      </div>
                      <span className={`text-sm font-semibold ${delivery === val ? 'text-emerald-300' : 'text-zinc-300'}`}>{label}</span>
                      <div className={`ml-auto w-4 h-4 rounded-full border-2 flex items-center justify-center ${delivery === val ? 'border-emerald-400' : 'border-zinc-600'}`}>
                        {delivery === val && <div className="w-2 h-2 rounded-full bg-emerald-400" />}
                      </div>
                    </div>
                    <p className="text-xs text-zinc-500">{desc}</p>
                  </label>
                ))}
              </div>
            </div>

            {/* Email input */}
            {delivery === 'email' && (
              <div className="animate-fade-in">
                <label htmlFor="export-email" className="text-xs font-semibold text-zinc-400 uppercase tracking-wider block mb-2">
                  Recipient Email
                </label>
                <div className="relative">
                  <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
                  <input
                    id="export-email"
                    type="email"
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                    placeholder="you@organisation.com"
                    className="w-full bg-zinc-900/50 border border-zinc-800 rounded-xl pl-10 pr-4 py-3 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-emerald-500/50 focus:ring-1 focus:ring-emerald-500/30 transition-all"
                  />
                </div>
              </div>
            )}

            {/* Result feedback */}
            {result && (
              <div className={`flex items-center gap-3 rounded-xl px-4 py-3.5 border animate-fade-in ${
                result.success
                  ? 'bg-emerald-500/10 border-emerald-500/20'
                  : 'bg-red-500/10 border-red-500/20'
              }`}>
                {result.success
                  ? <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
                  : <AlertCircle className="w-5 h-5 text-red-400 shrink-0" />}
                <p className={`text-sm ${result.success ? 'text-emerald-300' : 'text-red-400'}`}>{result.message}</p>
              </div>
            )}

            {/* Export Button */}
            <button
              id="export-submit-btn"
              onClick={handleExport}
              disabled={loading || (delivery === 'email' && !email.trim())}
              className="w-full flex items-center justify-center gap-2.5 bg-emerald-500 hover:bg-emerald-400 disabled:bg-emerald-500/40 disabled:cursor-not-allowed text-zinc-950 font-semibold rounded-xl py-3.5 text-sm transition-all shadow-[0_0_20px_rgba(16,185,129,0.2)]"
            >
              {loading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : delivery === 'email' ? (
                <><Send className="w-4 h-4" /> Send {format.toUpperCase()} via Email</>
              ) : (
                <><Download className="w-4 h-4" /> Download {format.toUpperCase()}</>
              )}
            </button>
          </div>
        </div>

        {/* Info Panel */}
        <div className="space-y-5">
          <div className="glass rounded-2xl p-5 space-y-4">
            <h3 className="text-sm font-semibold text-white flex items-center gap-2">
              <Lock className="w-4 h-4 text-emerald-400" /> Export Policy
            </h3>
            <ul className="text-xs text-zinc-400 space-y-2.5">
              <li className="flex items-start gap-2"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 mt-0.5 shrink-0" /> Only approved & locked records exported</li>
              <li className="flex items-start gap-2"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 mt-0.5 shrink-0" /> Pending / excluded rows never included</li>
              <li className="flex items-start gap-2"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 mt-0.5 shrink-0" /> All exports logged for audit trail</li>
              <li className="flex items-start gap-2"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 mt-0.5 shrink-0" /> Email uses secure file-based backend (dev)</li>
            </ul>
          </div>

          <div className="glass rounded-2xl p-5 space-y-3">
            <h3 className="text-sm font-semibold text-white">Included Fields</h3>
            <div className="flex flex-wrap gap-1.5">
              {[
                'id', 'emission_date', 'source_type', 'facility_name', 'vendor',
                'country', 'city', 'co2e_kg', 'distance_km', 'origin_iata',
                'destination_iata', 'approved_by', 'approved_at',
              ].map(f => (
                <span key={f} className="text-[10px] font-mono bg-zinc-800 text-zinc-400 px-1.5 py-0.5 rounded border border-zinc-700">
                  {f}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Export Logs */}
      <ExportLogs />
    </div>
  );
}
