import React, { useCallback, useEffect, useState } from 'react';
import { History, CheckCircle2, XCircle, Send, Power, RotateCcw } from 'lucide-react';
import {
  fetchImageRevisionsAdmin, fetchRevisionAdmin, submitRevision, approveRevision, rejectRevision,
  activateRevision, restoreRevision,
} from '../../services/api';

// Block A6.3: immutable label revision history of one image (administrator view).
// Every value comes from the backend. Activation rewrites the image's annotations and
// label only; the A6.0 label review still decides training eligibility.

const STATUS_COLOR = {
  recorded: '#475569', draft: '#a16207', submitted: '#7c3aed', approved: '#15803d', rejected: '#b91c1c', active: '#0369a1',
};
const SOURCE_LABEL = { human_annotation: 'Recorded labels', approved_feedback: 'From approved feedback', admin_correction: 'Administrator correction' };
const when = (iso) => (iso ? iso.replace('T', ' ').slice(0, 19) : '—');
const short = (id) => (id ? `${id.slice(0, 8)}…` : '—');
const shape = (o) => {
  const pts = o?.label_data?.points;
  if (o?.annotation_type === 'rectangle' && pts?.length === 2) return `box [${[pts[0].x, pts[0].y, pts[1].x, pts[1].y].map((v) => Math.round(v)).join(', ')}]`;
  if (pts) return `${o.annotation_type}, ${pts.length} points`;
  return o?.annotation_type || '—';
};
const objText = (o) => `${o.class_name || 'no class'} · ${shape(o)}${o.ai_generated ? ' · AI geometry' : ''}`;

export const Pill = ({ value }) => (
  <span data-testid="revision-status" style={{ fontSize: '11px', fontWeight: 700, color: STATUS_COLOR[value] || '#475569', backgroundColor: '#f1f5f9', padding: '2px 8px', borderRadius: '999px' }}>
    {value}
  </span>
);
const Row = ({ label, children }) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', fontSize: '13px' }}>
    <span style={{ color: '#786c5e' }}>{label}</span><strong style={{ textAlign: 'right', wordBreak: 'break-word' }}>{children}</strong>
  </div>
);
const smallBtn = { width: 'auto', padding: '6px 12px', fontSize: '12px', borderRadius: '8px' };
const input = { padding: '6px 8px', borderRadius: '8px', border: '1px solid #e7dccb', fontSize: '13px', backgroundColor: '#fff' };

const LabelRevisionPanel = ({ imageId, focusRevisionId, onChange }) => {
  const [history, setHistory] = useState({ data: null, error: '' });
  const [selected, setSelected] = useState(focusRevisionId || null);
  const [rev, setRev] = useState({ data: null, error: '' });
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState({ text: '', error: false });

  const loadHistory = useCallback(async () => {
    try {
      const data = await fetchImageRevisionsAdmin(imageId);
      setHistory({ data, error: '' });
      setSelected((s) => s || focusRevisionId || data.current?.revision_id || data.items[0]?.revision_id || null);
    } catch (err) {
      setHistory({ data: null, error: err.message });
    }
  }, [imageId, focusRevisionId]);
  useEffect(() => { loadHistory(); }, [loadHistory]);
  useEffect(() => { if (focusRevisionId) setSelected(focusRevisionId); }, [focusRevisionId]);

  useEffect(() => {
    if (!selected) return;
    let live = true;
    setRev({ data: null, error: '' });
    fetchRevisionAdmin(selected).then((data) => live && setRev({ data, error: '' }))
      .catch((err) => live && setRev({ data: null, error: err.message }));
    return () => { live = false; };
  }, [selected]);

  const act = async (kind) => {
    const r = rev.data;
    if ((kind === 'reject' || kind === 'restore') && reason.trim().length < 3) {
      setMessage({ text: 'A reason of at least 3 characters is required.', error: true }); return;
    }
    const prompts = {
      submit: 'Submit this revision for administrator review?',
      approve: 'Approve this label revision? It does not change any label until it is activated.',
      reject: 'Reject this label revision? A rejected revision can never become active.',
      activate: 'Activate this revision? The image\'s annotations and label file are rewritten to it; the image then needs the regular label review before it can be used for training.',
      restore: 'Create a new draft revision with the contents of this one?',
    };
    if (!window.confirm(prompts[kind])) return;
    setBusy(true);
    setMessage({ text: '', error: false });
    try {
      let out;
      if (kind === 'submit') out = await submitRevision(r.revision_id);
      if (kind === 'approve') out = await approveRevision(r.revision_id, reason.trim() || undefined);
      if (kind === 'reject') out = await rejectRevision(r.revision_id, reason.trim());
      if (kind === 'restore') { out = await restoreRevision(r.revision_id, reason.trim()); setSelected(out.revision_id); }
      if (kind === 'activate') {
        out = await activateRevision(r.revision_id);
        setMessage({
          text: out.training_eligible ? 'Revision is active and the image is training eligible.'
            : out.awaiting_label_review ? 'Revision is active. Its label is finalized and awaits the regular label review before training.'
              : `Revision is active. The label was not finalized${out.finalize?.reason ? ` (${out.finalize.reason})` : ''}.`,
          error: false,
        });
      } else {
        setMessage({ text: out.idempotent_replay ? 'Nothing changed: this was already recorded.' : 'Saved.', error: false });
      }
      setReason('');
      await loadHistory();
      if (kind !== 'restore') setRev({ data: await fetchRevisionAdmin(r.revision_id), error: '' });
      if (onChange) onChange();
    } catch (err) {
      setMessage({ text: err.message, error: true });
    } finally {
      setBusy(false);
    }
  };

  const h = history.data;
  const r = rev.data;
  const locked = h?.training_locked;
  const cmp = r?.comparison;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }} data-testid="label-revision-panel">
      <h4 style={{ fontSize: '13px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '6px' }}>
        <History size={15} /> Label revisions
      </h4>
      {history.error && <div role="alert" style={{ fontSize: '13px', color: '#dc2626' }}>{history.error}</div>}
      {h && (
        <>
          <div style={{ fontSize: '12px', color: '#786c5e' }} data-testid="current-revision">
            Current: {h.current.revision_id ? `#${h.current.revision_number} (${SOURCE_LABEL[h.current.source]})` : 'none recorded'}
            {h.current.revision_id && !h.current.in_sync_with_annotations && ' · annotations changed since then'}
            {locked && ' · labels locked (training eligible or in a frozen snapshot)'}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            {h.items.map((i) => (
              <button key={i.revision_id} type="button" data-testid="revision-row" onClick={() => setSelected(i.revision_id)}
                style={{ textAlign: 'left', padding: '6px 10px', borderRadius: '8px', cursor: 'pointer', fontSize: '12px',
                  border: selected === i.revision_id ? '2px solid var(--color-primary)' : '1px solid #eee4d6', backgroundColor: '#fffdf9',
                  display: 'flex', justifyContent: 'space-between', gap: '8px' }}>
                <span>#{i.revision_number} · {SOURCE_LABEL[i.source]} · {i.object_count} object(s)</span>
                <span style={{ display: 'flex', gap: '4px' }}>{i.is_active && <Pill value="active" />}<Pill value={i.status} /></span>
              </button>
            ))}
          </div>
        </>
      )}

      {rev.error && <div role="alert" style={{ fontSize: '13px', color: '#dc2626' }}>{rev.error}</div>}
      {r && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', borderTop: '1px solid #eee4d6', paddingTop: '8px' }} data-testid="revision-detail">
          <div style={{ fontSize: '13px', fontWeight: 700 }}>
            Revision #{r.revision_number} <Pill value={r.status} /> {r.is_active && <Pill value="active" />}
          </div>
          <Row label="Source">{SOURCE_LABEL[r.source]}{r.feedback_id ? ` · feedback ${short(r.feedback_id)}` : ''}</Row>
          <Row label="Created">{when(r.created_at)} by {r.created_by_email || short(r.created_by)}</Row>
          <Row label="Reason">{r.reason || '—'}</Row>
          <Row label="Content hash">{r.hashes.content_sha256.slice(0, 16)}… {r.integrity_ok ? '(verified)' : '(MISMATCH)'}</Row>
          <Row label="Label hash">{r.hashes.label_sha256.slice(0, 16)}…</Row>
          {cmp ? (
            <div style={{ fontSize: '12px', display: 'flex', flexDirection: 'column', gap: '3px' }} data-testid="revision-comparison">
              <span style={{ color: '#786c5e' }}>Compared with revision #{cmp.parent_revision_number}:</span>
              {cmp.added.map((o) => <div key={o.key} style={{ color: '#15803d' }}>+ {objText(o)}</div>)}
              {cmp.removed.map((o) => <div key={o.key} style={{ color: '#b91c1c' }}>− {objText(o)}</div>)}
              {cmp.changed.map((c) => <div key={c.key} style={{ color: '#a16207' }}>~ {objText(c.before)} → {objText(c.after)}</div>)}
              {cmp.added.length + cmp.removed.length + cmp.changed.length === 0 && <span>No object changes.</span>}
            </div>
          ) : (
            <div style={{ fontSize: '12px' }} data-testid="revision-objects">
              {r.contents.objects.length === 0 ? 'No objects.' : r.contents.objects.map((o) => <div key={o.key}>{objText(o)}</div>)}
            </div>
          )}
          <div style={{ fontSize: '12px', display: 'flex', flexDirection: 'column', gap: '2px' }}>
            {r.events.map((e) => (
              <div key={e.event_id} data-testid="revision-event">
                {when(e.created_at)} · {e.event} by {e.actor_email || short(e.actor_id)}{e.reason ? ` — “${e.reason}”` : ''}
              </div>
            ))}
          </div>

          {r.source !== 'human_annotation' && ['draft', 'submitted', 'approved'].includes(r.status) && !(r.activated) && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {r.status === 'submitted' && (
                <textarea aria-label="Revision decision reason" placeholder="Reason (required to reject)" maxLength={2000} value={reason}
                  onChange={(e) => setReason(e.target.value)} style={{ ...input, minHeight: '50px' }} />
              )}
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                {r.status === 'draft' && (
                  <button type="button" className="login-btn" style={smallBtn} disabled={busy} onClick={() => act('submit')}><Send size={14} /> Submit for review</button>
                )}
                {r.status === 'submitted' && (
                  <>
                    <button type="button" className="login-btn" style={{ ...smallBtn, backgroundColor: '#15803d' }} disabled={busy} onClick={() => act('approve')}>
                      <CheckCircle2 size={14} /> Approve revision
                    </button>
                    <button type="button" className="login-btn" style={{ ...smallBtn, backgroundColor: '#b91c1c' }} disabled={busy} onClick={() => act('reject')}>
                      <XCircle size={14} /> Reject revision
                    </button>
                  </>
                )}
                {r.status === 'approved' && (
                  <button type="button" className="login-btn" style={{ ...smallBtn, backgroundColor: '#0369a1' }} disabled={busy || locked} onClick={() => act('activate')}
                    title={locked ? 'Labels of training-eligible or snapshotted images are locked' : undefined}>
                    <Power size={14} /> Activate revision
                  </button>
                )}
              </div>
            </div>
          )}
          {!r.is_active && !locked && (r.status === 'recorded' || r.status === 'rejected' || r.activated) && (
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <input aria-label="Restore reason" placeholder="Reason to restore" style={{ ...input, flex: 1 }} value={reason} onChange={(e) => setReason(e.target.value)} />
              <button type="button" className="login-btn" style={smallBtn} disabled={busy} onClick={() => act('restore')}><RotateCcw size={14} /> Restore as new draft</button>
            </div>
          )}
          {message.text && <div role={message.error ? 'alert' : 'status'} style={{ fontSize: '13px', color: message.error ? '#dc2626' : '#15803d' }}>{message.text}</div>}
        </div>
      )}
    </div>
  );
};

export default LabelRevisionPanel;
