import React, { useCallback, useEffect, useRef, useState } from 'react';
import { History, RefreshCw } from 'lucide-react';
import { fetchRevisionQueue } from '../services/api';
import LabelRevisionPanel, { Pill } from '../components/labelRevisions/LabelRevisionPanel';

// Block A6.3: administrator queue of immutable label revisions. Reviewing or activating
// a revision never trains a model or changes a frozen training snapshot.

const PAGE = 10;
const SOURCE_LABEL = { human_annotation: 'Recorded labels', approved_feedback: 'From approved feedback', admin_correction: 'Administrator correction' };
const when = (iso) => (iso ? iso.replace('T', ' ').slice(0, 19) : '—');
const short = (id) => (id ? `${id.slice(0, 8)}…` : '—');
const smallBtn = { width: 'auto', padding: '6px 12px', fontSize: '12px', borderRadius: '8px' };
const input = { padding: '6px 8px', borderRadius: '8px', border: '1px solid #e7dccb', fontSize: '13px', backgroundColor: '#fff' };

const LabelRevisionsView = () => {
  const [status, setStatus] = useState('submitted');
  const [offset, setOffset] = useState(0);
  const [queue, setQueue] = useState({ items: [], total: 0, error: '', loading: true });
  const [selected, setSelected] = useState(null);
  const latest = useRef(0);

  const load = useCallback(async () => {
    const seq = ++latest.current;
    try {
      const r = await fetchRevisionQueue({ status: status || undefined, limit: PAGE, offset });
      if (seq === latest.current) setQueue({ items: r.items, total: r.total, error: '', loading: false });
    } catch (err) {
      if (seq === latest.current) setQueue((q) => ({ ...q, error: err.message || 'Failed to load', loading: false }));
    }
  }, [status, offset]);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="page-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px', flexWrap: 'wrap' }}>
        <div>
          <h1 style={{ fontSize: '32px', fontWeight: 800, color: '#38240d', fontFamily: 'var(--font-main)', lineHeight: '1.2' }}>Label Revisions</h1>
          <p style={{ fontSize: '14px', color: '#786c5e' }}>
            Immutable label versions proposed from approved AI feedback. An activated revision still needs the regular label review before it can be used for training.
          </p>
        </div>
        <button type="button" className="login-btn" style={{ width: 'auto', padding: '10px 20px', fontSize: '14px', borderRadius: '12px' }} onClick={load}>
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      <div className="dashboard-card" style={{ padding: '16px', display: 'flex', gap: '12px', alignItems: 'flex-end' }}>
        <label style={{ fontSize: '12px', display: 'flex', flexDirection: 'column', gap: '4px' }}>Status
          <select aria-label="Revision status filter" style={input} value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); }}>
            <option value="">All</option><option value="draft">Draft</option><option value="submitted">Pending review</option>
            <option value="approved">Approved</option><option value="rejected">Rejected</option><option value="active">Active</option>
            <option value="recorded">Recorded labels</option>
          </select>
        </label>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '16px', alignItems: 'start' }}>
        <div className="dashboard-card" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '10px', minWidth: 0 }} data-testid="revision-queue">
          <h3 style={{ fontSize: '15px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <History size={17} style={{ color: 'var(--color-primary)' }} /> Revisions ({queue.total})
          </h3>
          {queue.error && <div role="alert" style={{ fontSize: '13px', color: '#dc2626' }}>{queue.error}</div>}
          {queue.loading ? <span style={{ fontSize: '13px', color: '#786c5e' }}>Loading…</span>
            : queue.items.length === 0 ? <span style={{ fontSize: '13px', color: '#786c5e' }}>No revisions match this filter.</span>
              : queue.items.map((r) => (
                <button key={r.revision_id} type="button" data-testid="revision-queue-row" onClick={() => setSelected(r)}
                  style={{ textAlign: 'left', padding: '10px 12px', borderRadius: '10px', cursor: 'pointer', fontSize: '13px',
                    border: selected?.revision_id === r.revision_id ? '2px solid var(--color-primary)' : '1px solid #eee4d6', backgroundColor: '#fffdf9' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px' }}>
                    <strong>Image {short(r.image_id)} · #{r.revision_number}</strong>
                    <span style={{ display: 'flex', gap: '4px' }}>{r.is_active && <Pill value="active" />}<Pill value={r.status} /></span>
                  </div>
                  <div style={{ color: '#786c5e', fontSize: '12px', marginTop: '2px' }}>
                    {when(r.created_at)} · {SOURCE_LABEL[r.source]} · {r.object_count} object(s)
                  </div>
                </button>
              ))}
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '12px', color: '#786c5e' }}>
            <button type="button" className="login-btn" style={smallBtn} disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</button>
            <span>{queue.total === 0 ? '0 of 0' : `${offset + 1}–${Math.min(offset + PAGE, queue.total)} of ${queue.total}`}</span>
            <button type="button" className="login-btn" style={smallBtn} disabled={offset + PAGE >= queue.total} onClick={() => setOffset(offset + PAGE)}>Next</button>
          </div>
        </div>

        <div className="dashboard-card" style={{ padding: '20px', minWidth: 0 }} data-testid="revision-queue-detail">
          {selected ? <LabelRevisionPanel key={selected.image_id} imageId={selected.image_id} focusRevisionId={selected.revision_id} onChange={load} />
            : <span style={{ fontSize: '13px', color: '#786c5e' }}>Select a revision to see the image's label history.</span>}
        </div>
      </div>
    </div>
  );
};

export default LabelRevisionsView;
