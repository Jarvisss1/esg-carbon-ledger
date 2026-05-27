import axios from 'axios';

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
});

// Attach token to every request if present
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('esg_token');
  if (token) {
    config.headers['Authorization'] = `Token ${token}`;
  }
  return config;
});

const mapRecord = (r) => {
  if (!r) return r;
  const approved = r.workflow_status === 'APPROVED' || r.workflow_status === 'LOCKED_FOR_AUDIT' || r.is_locked || r.status === 'APPROVED';
  const excluded = r.workflow_status === 'REJECTED' || r.status === 'REJECTED';
  return {
    ...r,
    approved,
    excluded,
    is_outlier: r.is_suspicious || r.status === 'FLAGGED',
    co2e_kg: r.normalized_value,
    emission_date: r.start_date ? r.start_date.substring(0, 10) : '—',
    source_type: r.source_system || 'SAP',
    facility_name: r.resolved_facility_id || '—',
    country: r.resolved_facility_country || '—',
    vendor: r.vendor || r.raw_data?.vendor || r.raw_data?.Vendor || '—',
    city: r.city || r.raw_data?.city || r.raw_data?.City || '—',
    origin_iata: r.origin_iata || r.raw_data?.origin_iata || r.raw_data?.origin || '—',
    destination_iata: r.destination_iata || r.raw_data?.destination_iata || r.raw_data?.destination || '—',
    distance_km: r.distance_km || r.raw_data?.distance_km || r.raw_data?.distance || '—',
    uplift_applied: r.uplift_applied || r.raw_data?.uplift_applied || false,
    z_score: r.z_score || (r.is_suspicious ? 3.5 : 0),
    override_note: r.override_note || r.analyst_notes || '—'
  };
};

// ─── Auth ──────────────────────────────────────────────────────────────────────
export const authAPI = {
  // POST /api/auth/register/  { username, email, password, first_name, last_name }
  register: (data) => api.post('/api/auth/register/', data),
  // POST /api/auth/token/     { username, password }
  login: (data) => api.post('/api/auth/token/', data),
  // GET  /api/auth/me/
  me: () => api.get('/api/auth/me/'),
};

// ─── Records (Carbon Ledger) ────────────────────────────────────────────────────
export const recordsAPI = {
  // GET  /api/records/   ?workflow_status=&is_suspicious=&tenant_id=
  list: (params) => api.get('/api/records/', { params }).then(res => {
    if (res.data && Array.isArray(res.data)) {
      res.data = res.data.map(mapRecord);
    } else if (res.data && Array.isArray(res.data.results)) {
      res.data.results = res.data.results.map(mapRecord);
    }
    return res;
  }),

  // PATCH /api/records/{id}/approve/
  approve: (id) => api.patch(`/api/records/${id}/approve/`).then(res => {
    res.data = mapRecord(res.data);
    return res;
  }),

  // PATCH /api/records/{id}/reject/    { reason }
  exclude: (id, reason) => api.patch(`/api/records/${id}/reject/`, { reason, flag_reason: reason }).then(res => {
    res.data = mapRecord(res.data);
    return res;
  }),

  // POST  /api/activities/bulk-action/  { ids: [...], action: 'bulk-approve' }
  bulkApprove: (ids) => api.post('/api/activities/bulk-action/', { ids, action: 'bulk-approve' }),

  // PUT   /api/activities/{id}/   { analyst_notes, override fields }
  delegate: (id, data) => api.put(`/api/activities/${id}/`, { analyst_notes: `Delegated to: ${data.assigned_to}`, note: `Delegated to: ${data.assigned_to}` }).then(res => {
    res.data = mapRecord(res.data);
    return res;
  }),

  // PUT   /api/activities/{id}/   { analyst_notes, edited fields }
  override: (id, data) => api.put(`/api/activities/${id}/`, data).then(res => {
    res.data = mapRecord(res.data);
    return res;
  }),
};

// ─── Ingestion ─────────────────────────────────────────────────────────────────
export const ingestionAPI = {
  // POST /api/batches/upload/   multipart: file, tenant_id, source_type
  upload: (formData) => api.post('/api/batches/upload/', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }),

  // GET  /api/batches/
  batches: () => api.get('/api/batches/'),

  // GET  /api/batches/{id}/records/
  batchDetail: (id, params) => api.get(`/api/batches/${id}/records/`, { params }).then(res => {
    if (res.data && Array.isArray(res.data)) {
      res.data = res.data.map(mapRecord);
    } else if (res.data && Array.isArray(res.data.results)) {
      res.data.results = res.data.results.map(mapRecord);
    }
    return res;
  }),

  // DELETE /api/batches/{id}/
  deleteBatch: (id) => api.delete(`/api/batches/${id}/`),
};

// ─── Export ────────────────────────────────────────────────────────────────────
// The backend uses POST /api/records/export/ with { format, delivery, email }
// and returns the file directly for 'download' delivery.
export const exportAPI = {
  // CSV download
  csv: (params) => api.post('/api/records/export/', { format: 'CSV', delivery: 'download', ...params }, { responseType: 'blob' }),

  // XLSX download
  xlsx: (params) => api.post('/api/records/export/', { format: 'XLSX', delivery: 'download', ...params }, { responseType: 'blob' }),

  // Email delivery
  email: (data) => api.post('/api/records/export/', {
    format: (data.format || 'csv').toUpperCase(),
    delivery: 'email',
    email: data.email_to,
    batch_id: data.batch_id,
  }),

  // GET /api/records/exports/
  logs: () => api.get('/api/records/exports/'),
};

// ─── Dashboard ─────────────────────────────────────────────────────────────────
export const dashboardAPI = {
  // GET /api/records/summary/
  stats: () => api.get('/api/records/summary/'),
};

export default api;
