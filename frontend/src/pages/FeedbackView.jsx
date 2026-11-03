import React, { useCallback, useEffect, useRef, useState } from 'react';
import { MessageSquareWarning, RefreshCw, CheckCircle2, XCircle } from 'lucide-react';
import {
  fetchFeedbackQueue, fetchFeedbackReview, approveFeedback, rejectFeedback,
  fetchRevisionQueue, fetchImageRevisionsAdmin, createRevisionFromFeedback, fetchActiveCategories,
} from '../services/api';
import LabelRevisionPanel from '../components/labelRevisions/LabelRevisionPanel';

// Block A6.2: administrator review of user reports about AI predictions. Every value
// comes from the backend. An approval only accepts a report for a later, governed
// correction workflow; it never changes labels, annotations or training eligibility.
// Block A6.3: an approved report can then be turned into a draft label revision.
// Confidence is shown only when the prediction record marks it as a model score.

const PAGE = 10;
const TYPE_LABEL = {
  incorrect_class: 'Wrong class', incorrect_geometry: 'Wrong box / outline', missed_object: 'Missed object',
  false_detection: 'False detection', other: 'Other',
};
const STATUS_COLOR = { pending: '#7c3aed', approved: '#15803d', rejected: '#b91c1c' };
const when = (iso) => (iso ? iso.replace('T', ' ').slice(0, 19) : '—');
const short = (id) => (id ? `${id.slice(0, 8)}…` : '—');
const conf = (det, isScore) => (isScore && typeof det?.confidence === 'number' ? `${(det.confidence * 100).toFixed(1)}%` : 'not a model score');
const geometryText = (g) => {
  if (!g) return '—';
  if (g.type === 'bbox') return `box [${g.bbox.map((v) => Math.round(v)).join(', ')}]`;
  return `polygon, ${g.points.length} points`;
};
const boxText = (d) => (d?.bbox ? `[${d.bbox.map((v) => Math.round(v)).join(', ')}]` : d?.polygon ? `polygon, ${d.polygon.length} points` : '—');

const Pill = ({ value }) => (
  <span style={{ fontSize: '11px', fontWeight: 700, color: STATUS_COLOR[value] || '#475569', backgroundColor: '#f1f5f9', padding: '2px 8px', borderRadius: '999px' }}>
    {value || '—'}
  </span>
);
const Row = ({ label, children }) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', fontSize: '13px' }}>
    <span style={{ color: '#786c5e' }}>{label}</span><strong style={{ textAlign: 'right', wordBreak: 'break-word' }}>{children}</strong>
  </div>
);
const smallBtn = { width: 'auto', padding: '6px 12px', fontSize: '12px', borderRadius: '8px' };
const input = { padding: '6px 8px', borderRadius: '8px', border: '1px solid #e7dccb', fontSize: '13px', backgroundColor: '#fff' };

// Block A6.3: turn an approved report into a draft label revision (reviewed separately).
const FeedbackCorrection = ({ feedback }) => {
  const imageId = feedback.prediction_reference?.image_id;
  const [existing, setExisting] = useState(undefined);
  const [objects, setObjects] = useState([]);
  const [categories, setCategories] = useState([]);
  const [form, setForm] = useState({ target: '', category: '', reason: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const type = feedback.feedback_type;
  const needsTarget = type === 'false_detection';
  const allowsTarget = ['incorrect_class', 'incorrect_geometry', 'false_detection'].includes(type);
  const needsCategory = !feedback.suggested_correction.category_id && type === 'incorrect_geometry' && !form.target;

  useEffect(() => {
    if (!imageId) return;
    let live = true;
    fetchRevisionQueue({ feedback_id: feedback.feedback_id }).then((r) => live && setExisting(r.items[0] || null))
      .catch((err) => live && setError(err.message));
    fetchImageRevisionsAdmin(imageId).then((h) => live && setObjects(h.annotations)).catch(() => {});
    fetchActiveCategories().then((c) => live && setCategories(c.categories || c.data || (Array.isArray(c) ? c : []))).catch(() => {});
    return () => { live = false; };
  }, [feedback.feedback_id, imageId]);

  if (type === 'other') return <span style={{ fontSize: '13px', color: '#786c5e' }}>This report type carries no structured correction.</span>;
  if (!imageId) return <span style={{ fontSize: '13px', color: '#786c5e' }}>The prediction has no stored image, so no label revision can be created from it.</span>;
  if (existing === undefined) return <span style={{ fontSize: '13px', color: '#786c5e' }}>Loading…</span>;
  if (existing) return <LabelRevisionPanel imageId={imageId} focusRevisionId={existing.revision_id} />;

  const create = async () => {
    if (form.reason.trim().length < 3) { setError('A reason of at least 3 characters is required.'); return; }
    if (needsTarget && !form.target) { setError('Choose the labelled object this report is about.'); return; }
    if (!window.confirm('Create a draft label revision from this report? Nothing changes until the revision is reviewed and activated.')) return;
    setBusy(true);
    setError('');
    try {
      const rev = await createRevisionFromFeedback(feedback.feedback_id, {
        reason: form.reason.trim(),
        ...(form.target ? { target_object_key: form.target } : {}),
        ...(needsCategory && form.category ? { category_id: Number(form.category) } : {}),
      });
      setExisting(rev);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }} data-testid="feedback-correction">
      {allowsTarget && (
        <label style={{ fontSize: '12px', display: 'flex', flexDirection: 'column', gap: '4px' }}>Labelled object to correct
          <select aria-label="Labelled object" style={input} value={form.target} onChange={(e) => setForm({ ...form, target: e.target.value })}>
            <option value="">{needsTarget ? 'Choose an object…' : 'None — add the corrected object as a new one'}</option>
            {objects.map((o, i) => <option key={o.key} value={o.key}>#{i + 1} {o.class_name || 'no class'} · {o.annotation_type}{o.ai_generated ? ' · AI' : ''}</option>)}
          </select>
        </label>
      )}
      {needsCategory && (
        <label style={{ fontSize: '12px', display: 'flex', flexDirection: 'column', gap: '4px' }}>Class for the new object
          <select aria-label="Revision class" style={input} value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
            <option value="">Choose a class…</option>
            {categories.map((c) => <option key={c.category_id} value={c.category_id}>{c.class_name}</option>)}
          </select>
        </label>
      )}
      <textarea aria-label="Revision reason" placeholder="Reason for the label revision" maxLength={2000} value={form.reason}
        onChange={(e) => setForm({ ...form, reason: e.target.value })} style={{ ...input, minHeight: '50px' }} />
      {error && <div role="alert" style={{ fontSize: '13px', color: '#dc2626' }}>{error}</div>}
      <button type="button" className="login-btn" style={smallBtn} disabled={busy} onClick={create}>Create label revision</button>
    </div>
  );
};

const FeedbackView = () => {
  const [filters, setFilters] = useState({ status: 'pending', feedback_type: '', from: '', to: '', order: 'oldest' });
  const [offset, setOffset] = useState(0);
  const [queue, setQueue] = useState({ items: [], total: 0, error: '', loading: true });
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState({ data: null, error: '' });
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState('');
  const latest = useRef(0);

  const load = useCallback(async () => {
    const seq = ++latest.current;
    try {
      const r = await fetchFeedbackQueue({
        status: filters.status, feedback_type: filters.feedback_type, order: filters.order, limit: PAGE, offset,
        submitted_from: filters.from ? `${filters.from}T00:00:00Z` : undefined,
        submitted_to: filters.to ? `${filters.to}T23:59:59Z` : undefined,
      });
      if (seq === latest.current) setQueue({ items: r.items, total: r.total, error: '', loading: false });
    } catch (err) {
      if (seq === latest.current) setQueue((q) => ({ ...q, error: err.message || 'Failed to load', loading: false }));
    }
  }, [filters, offset]);
  useEffect(() => { load(); }, [load]);

  const open = async (id) => {
    setSelected(id);
    setReason('');
    setActionError('');
    setDetail({ data: null, error: '' });
    try {
      setDetail({ data: await fetchFeedbackReview(id), error: '' });
    } catch (err) {
      setDetail({ data: null, error: err.message });
    }
  };

  const decide = async (kind) => {
    if (kind === 'reject' && reason.trim().length < 3) { setActionError('A reason of at least 3 characters is required to reject.'); return; }
    if (!window.confirm(kind === 'approve'
      ? 'Approve this report? It is accepted for a later correction workflow; no label or training data changes now.'
      : 'Reject this report? This decision is final.')) return;
    setBusy(true);
    setActionError('');
    try {
      const data = kind === 'approve' ? await approveFeedback(selected, reason.trim() || undefined) : await rejectFeedback(selected, reason.trim());
      setDetail({ data, error: '' });
      load();
    } catch (err) {
      setActionError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const setFilter = (k, v) => { setFilters((f) => ({ ...f, [k]: v })); setOffset(0); };
  const d = detail.data;
  const isScore = d?.prediction?.confidence_is_model_score;

  return (
    <div className="page-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px', flexWrap: 'wrap' }}>
        <div>
          <h1 style={{ fontSize: '32px', fontWeight: 800, color: '#38240d', fontFamily: 'var(--font-main)', lineHeight: '1.2' }}>AI Feedback</h1>
          <p style={{ fontSize: '14px', color: '#786c5e' }}>
            User reports about incorrect AI predictions. Approving accepts a report for a later correction workflow — it does not change labels or training data.
          </p>
        </div>
        <button type="button" className="login-btn" style={{ width: 'auto', padding: '10px 20px', fontSize: '14px', borderRadius: '12px' }} onClick={load}>
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      <div className="dashboard-card" style={{ padding: '16px', display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'flex-end' }} data-testid="feedback-filters">
        <label style={{ fontSize: '12px', display: 'flex', flexDirection: 'column', gap: '4px' }}>Status
          <select aria-label="Status filter" style={input} value={filters.status} onChange={(e) => setFilter('status', e.target.value)}>
            <option value="">All</option><option value="pending">Pending</option><option value="approved">Approved</option><option value="rejected">Rejected</option>
          </select>
        </label>
        <label style={{ fontSize: '12px', display: 'flex', flexDirection: 'column', gap: '4px' }}>Type
          <select aria-label="Type filter" style={input} value={filters.feedback_type} onChange={(e) => setFilter('feedback_type', e.target.value)}>
            <option value="">All</option>
            {Object.entries(TYPE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <label style={{ fontSize: '12px', display: 'flex', flexDirection: 'column', gap: '4px' }}>Submitted from
          <input aria-label="Submitted from" type="date" style={input} value={filters.from} onChange={(e) => setFilter('from', e.target.value)} />
        </label>
        <label style={{ fontSize: '12px', display: 'flex', flexDirection: 'column', gap: '4px' }}>Submitted to
          <input aria-label="Submitted to" type="date" style={input} value={filters.to} onChange={(e) => setFilter('to', e.target.value)} />
        </label>
        <label style={{ fontSize: '12px', display: 'flex', flexDirection: 'column', gap: '4px' }}>Order
          <select aria-label="Order" style={input} value={filters.order} onChange={(e) => setFilter('order', e.target.value)}>
            <option value="oldest">Oldest first</option><option value="newest">Newest first</option>
          </select>
        </label>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '16px', alignItems: 'start' }}>
        <div className="dashboard-card" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '10px', minWidth: 0 }} data-testid="feedback-queue">
          <h3 style={{ fontSize: '15px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <MessageSquareWarning size={17} style={{ color: 'var(--color-primary)' }} /> Reports ({queue.total})
          </h3>
          {queue.error && <div role="alert" style={{ fontSize: '13px', color: '#dc2626' }}>{queue.error}</div>}
          {queue.loading ? <span style={{ fontSize: '13px', color: '#786c5e' }}>Loading…</span>
            : queue.items.length === 0 ? <span style={{ fontSize: '13px', color: '#786c5e' }}>No reports match these filters.</span>
              : queue.items.map((f) => (
                <button key={f.feedback_id} type="button" data-testid="feedback-row" onClick={() => open(f.feedback_id)}
                  style={{ textAlign: 'left', padding: '10px 12px', borderRadius: '10px', cursor: 'pointer', fontSize: '13px',
                    border: selected === f.feedback_id ? '2px solid var(--color-primary)' : '1px solid #eee4d6', backgroundColor: '#fffdf9' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px' }}>
                    <strong>{TYPE_LABEL[f.feedback_type] || f.feedback_type}</strong><Pill value={f.status} />
                  </div>
                  <div style={{ color: '#786c5e', fontSize: '12px', marginTop: '2px' }}>
                    {when(f.submitted_at)} · by {short(f.submitted_by)} · {f.prediction_reference?.source}
                    {f.suggested_correction?.class_name ? ` · suggests ${f.suggested_correction.class_name}` : ''}
                  </div>
                </button>
              ))}
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '12px', color: '#786c5e' }}>
            <button type="button" className="login-btn" style={smallBtn} disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</button>
            <span>{queue.total === 0 ? '0 of 0' : `${offset + 1}–${Math.min(offset + PAGE, queue.total)} of ${queue.total}`}</span>
            <button type="button" className="login-btn" style={smallBtn} disabled={offset + PAGE >= queue.total} onClick={() => setOffset(offset + PAGE)}>Next</button>
          </div>
        </div>

        <div className="dashboard-card" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '10px', minWidth: 0 }} data-testid="feedback-detail">
          {!selected ? <span style={{ fontSize: '13px', color: '#786c5e' }}>Select a report to review it.</span>
            : detail.error ? <div role="alert" style={{ fontSize: '13px', color: '#dc2626' }}>{detail.error}</div>
              : !d ? <span style={{ fontSize: '13px', color: '#786c5e' }}>Loading…</span> : (
                <>
                  <h3 style={{ fontSize: '15px', fontWeight: 700 }}>Report {short(d.feedback_id)} <Pill value={d.status} /></h3>
                  <Row label="Type">{TYPE_LABEL[d.feedback_type] || d.feedback_type}</Row>
                  <Row label="Submitted">{when(d.submitted_at)} by {short(d.submitted_by)} ({d.submitter_role})</Row>
                  <Row label="Explanation">{d.explanation || '—'}</Row>

                  <h4 style={{ fontSize: '13px', fontWeight: 700, marginTop: '6px' }}>Suggested correction</h4>
                  <Row label="Target">{d.detection_index === null ? 'Whole prediction' : `Object #${d.detection_index + 1}`}</Row>
                  <Row label="Class">{d.suggested_correction.class_name || '—'}</Row>
                  <Row label="Outline">{geometryText(d.suggested_correction.geometry)}</Row>

                  <h4 style={{ fontSize: '13px', fontWeight: 700, marginTop: '6px' }}>Original prediction (immutable)</h4>
                  {d.prediction ? (
                    <>
                      <Row label="Prediction">{short(d.prediction.prediction_id)} · {d.prediction.source} · {when(d.prediction.created_at)}</Row>
                      <Row label="Model">{d.prediction.model.kind} · {d.prediction.model.attribution}</Row>
                      <Row label="Model version">{d.prediction.model.model_version || 'not a recorded deployment'}</Row>
                      <Row label="Artifact SHA-256">{d.prediction.model.sha256 ? `${d.prediction.model.sha256.slice(0, 16)}…` : 'Not available'}</Row>
                      {d.prediction.model.engine && <Row label="Engine">{d.prediction.model.engine}</Row>}
                      <div style={{ fontSize: '12px', display: 'flex', flexDirection: 'column', gap: '3px' }} data-testid="prediction-detections">
                        {d.prediction.detections.length === 0 ? <span style={{ color: '#786c5e' }}>No objects in this prediction.</span>
                          : d.prediction.detections.map((det, i) => (
                            <div key={i} style={{ padding: '4px 8px', borderRadius: '6px', backgroundColor: i === d.detection_index ? '#fef3c7' : '#f8f5ef' }}>
                              #{i + 1} {det.label || 'object'} · {boxText(det)} · confidence {conf(det, isScore)}
                            </div>
                          ))}
                      </div>
                    </>
                  ) : <span style={{ fontSize: '13px', color: '#786c5e' }}>Not available</span>}

                  <h4 style={{ fontSize: '13px', fontWeight: 700, marginTop: '6px' }}>Decision history</h4>
                  {d.decision_history.length === 0 ? <span style={{ fontSize: '13px', color: '#786c5e' }}>No decision yet.</span>
                    : d.decision_history.map((h) => (
                      <div key={h.decision_id} style={{ fontSize: '13px' }} data-testid="decision-entry">
                        <Pill value={h.decision} /> {when(h.decided_at)} by {h.reviewer_email || short(h.reviewer_id)}{h.reason ? ` — “${h.reason}”` : ''}
                      </div>
                    ))}

                  {d.status === 'approved' && (
                    <>
                      <h4 style={{ fontSize: '13px', fontWeight: 700, marginTop: '6px' }}>Label correction</h4>
                      <FeedbackCorrection key={d.feedback_id} feedback={d} />
                    </>
                  )}

                  {d.status === 'pending' && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '6px' }}>
                      <textarea aria-label="Decision reason" placeholder="Reason (required to reject)" maxLength={2000} value={reason}
                        onChange={(e) => setReason(e.target.value)} style={{ ...input, minHeight: '60px' }} />
                      {actionError && <div role="alert" style={{ fontSize: '13px', color: '#dc2626' }}>{actionError}</div>}
                      <div style={{ display: 'flex', gap: '8px' }}>
                        <button type="button" className="login-btn" style={{ ...smallBtn, backgroundColor: '#15803d' }} disabled={busy} onClick={() => decide('approve')}>
                          <CheckCircle2 size={14} /> Approve
                        </button>
                        <button type="button" className="login-btn" style={{ ...smallBtn, backgroundColor: '#b91c1c' }} disabled={busy} onClick={() => decide('reject')}>
                          <XCircle size={14} /> Reject
                        </button>
                      </div>
                    </div>
                  )}
                </>
              )}
        </div>
      </div>
    </div>
  );
};

export default FeedbackView;
