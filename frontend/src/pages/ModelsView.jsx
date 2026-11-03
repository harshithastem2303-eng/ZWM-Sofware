import React, { useState, useEffect } from 'react';
import { Cpu, Check, X, Play, RotateCcw, AlertCircle, RefreshCw, History } from 'lucide-react';
import {
  fetchModelCandidates,
  fetchCandidateApproval,
  approveCandidate,
  rejectCandidate,
  activateModelVersion,
  fetchDeployments,
  fetchDeploymentEvents,
  rollbackDeployment,
} from '../services/api';

// Block A4: review evaluated candidates, approve/reject, activate and roll back.
// All authorization is enforced server-side; this view only reflects it.

const LIFECYCLE_STYLE = {
  awaiting_review: { label: 'Awaiting review', color: '#b45309', bg: '#fef3c7' },
  approved: { label: 'Approved', color: '#1d4ed8', bg: '#dbeafe' },
  rejected: { label: 'Rejected', color: '#b91c1c', bg: '#fee2e2' },
  activation_pending: { label: 'Activation pending', color: '#7c3aed', bg: '#ede9fe' },
  activating: { label: 'Activating', color: '#7c3aed', bg: '#ede9fe' },
  active: { label: 'Active', color: '#15803d', bg: '#dcfce7' },
  activation_failed: { label: 'Activation failed', color: '#b91c1c', bg: '#fee2e2' },
  rolled_back: { label: 'Rolled back', color: '#475569', bg: '#e2e8f0' },
  not_evaluated: { label: 'Not evaluated', color: '#475569', bg: '#f1f5f9' },
  evaluation_in_progress: { label: 'Evaluating', color: '#475569', bg: '#f1f5f9' },
  not_eligible: { label: 'Not eligible', color: '#b91c1c', bg: '#fef2f2' },
};

const pct = (v) => (v === null || v === undefined ? '—' : `${(v * 100).toFixed(1)}%`);
const short = (id) => (id ? `${id.slice(0, 8)}…` : '—');

const Badge = ({ state }) => {
  const s = LIFECYCLE_STYLE[state] || { label: state || '—', color: '#475569', bg: '#f1f5f9' };
  return (
    <span style={{ fontSize: '11px', fontWeight: 700, color: s.color, backgroundColor: s.bg, padding: '3px 10px', borderRadius: '999px', whiteSpace: 'nowrap' }}>
      {s.label}
    </span>
  );
};

const ModelsView = () => {
  const [candidates, setCandidates] = useState([]);
  const [statusById, setStatusById] = useState({});
  const [deployments, setDeployments] = useState(null);
  const [events, setEvents] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [successMsg, setSuccessMsg] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  const loadData = async () => {
    try {
      const [candData, depData, evData] = await Promise.all([
        fetchModelCandidates(),
        fetchDeployments(),
        fetchDeploymentEvents(),
      ]);
      const list = candData.candidates || [];
      const statuses = await Promise.all(list.map((c) => fetchCandidateApproval(c.model_id).catch(() => null)));
      const byId = {};
      list.forEach((c, i) => { byId[c.model_id] = statuses[i]; });
      setCandidates(list);
      setStatusById(byId);
      setDeployments(depData);
      setEvents((evData.events || []).slice(0, 25));
    } catch (err) {
      setErrorMsg(err.message || 'Failed to load model deployment data.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const runAction = async (action, successText) => {
    setBusy(true);
    setSuccessMsg('');
    setErrorMsg('');
    try {
      await action();
      setSuccessMsg(successText);
    } catch (err) {
      setErrorMsg(err.message || 'Action failed.');
    } finally {
      setBusy(false);
      await loadData();
    }
  };

  const handleApprove = (status) => {
    if (!window.confirm(`Approve candidate ${status.version} based on evaluation ${short(status.latest_evaluation_id)}?`)) return;
    const reason = window.prompt('Optional approval note:') || undefined;
    runAction(() => approveCandidate(status.model_id, status.latest_evaluation_id, reason), `Candidate ${status.version} approved.`);
  };

  const handleReject = (status) => {
    const reason = window.prompt(`Reason for rejecting ${status.version} (required):`);
    if (!reason || reason.trim().length < 3) return;
    runAction(() => rejectCandidate(status.model_id, status.latest_evaluation_id, reason.trim()), `Candidate ${status.version} rejected.`);
  };

  const handleActivate = (status) => {
    const current = deployments?.active_model?.version || 'none';
    if (!window.confirm(`Activate ${status.version}? It will replace the current active model (${current}) for all predictions.`)) return;
    runAction(() => activateModelVersion(status.model_id), `Model ${status.version} is now active.`);
  };

  const handleRollback = () => {
    const target = deployments?.rollback_target;
    if (!target) return;
    const reason = window.prompt(`Reason for rolling back to ${target.version} (required):`);
    if (!reason || reason.trim().length < 3) return;
    if (!window.confirm(`Roll back the active model to ${target.version}?`)) return;
    runAction(() => rollbackDeployment(reason.trim(), target.model_id), `Rolled back to ${target.version}.`);
  };

  if (loading) {
    return (
      <div className="page-fade-in" style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '32px' }}>
        <div className="spinner" style={{ borderTopColor: 'var(--color-primary)' }} />
        <span>Loading model deployments...</span>
      </div>
    );
  }

  const active = deployments?.active_deployment;
  const inProgress = deployments?.in_progress;
  const rollbackTarget = deployments?.rollback_target;
  const detail = selected ? statusById[selected] : null;

  return (
    <div className="page-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <h1 style={{ fontSize: '32px', fontWeight: 800, color: '#38240d', fontFamily: 'var(--font-main)', lineHeight: '1.2' }}>
            Models
          </h1>
          <p style={{ fontSize: '14px', color: '#786c5e' }}>
            Review evaluated candidates, approve or reject them, activate approved models and roll back.
          </p>
        </div>
        <button type="button" className="login-btn" style={{ width: 'auto', padding: '10px 20px', fontSize: '14px', borderRadius: '12px' }} onClick={loadData} disabled={busy}>
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      {successMsg && (
        <div className="panel-alert panel-alert-success" style={{ padding: '16px', fontSize: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Check size={18} /> {successMsg}
        </div>
      )}
      {errorMsg && (
        <div className="panel-alert panel-alert-error" style={{ padding: '16px', fontSize: '14px', display: 'flex', alignItems: 'center', gap: '8px', color: '#dc2626', backgroundColor: '#fef2f2', border: '1px solid #fecaca', borderRadius: '8px' }}>
          <AlertCircle size={18} /> {errorMsg}
        </div>
      )}
      {inProgress && (
        <div className="panel-alert" style={{ padding: '16px', fontSize: '14px', color: '#7c3aed', backgroundColor: '#f5f3ff', border: '1px solid #ddd6fe', borderRadius: '8px' }}>
          {inProgress.kind.replace('_', ' ')} of {inProgress.model_version} is {inProgress.status}…
        </div>
      )}

      {/* Active deployment + rollback */}
      <div className="dashboard-card" style={{ padding: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '24px', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <h3 style={{ fontSize: '16px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Cpu size={18} style={{ color: 'var(--color-primary)' }} /> Current active model
          </h3>
          {deployments?.active_model ? (
            <span style={{ fontSize: '14px' }}>
              <strong>{deployments.active_model.version}</strong> ({short(deployments.active_model.model_id)})
              {active && <> — deployed {active.finished_at?.slice(0, 19)} by {short(active.requested_by)}, SHA-256 {active.weights_sha256.slice(0, 12)}…</>}
            </span>
          ) : (
            <span style={{ fontSize: '14px', color: '#786c5e' }}>No active model.</span>
          )}
          <span style={{ fontSize: '13px', color: '#786c5e' }}>
            Previous deployed model: {rollbackTarget ? `${rollbackTarget.version} (${short(rollbackTarget.model_id)})${rollbackTarget.artifact_retained ? '' : ' — artifact not retained'}` : 'none'}
          </span>
        </div>
        <button type="button" className="login-btn" style={{ width: 'auto', padding: '10px 20px', fontSize: '14px', borderRadius: '12px', backgroundColor: '#475569' }}
          onClick={handleRollback} disabled={busy || !rollbackTarget || !rollbackTarget.artifact_retained || !!inProgress}>
          <RotateCcw size={16} /> Roll back
        </button>
      </div>

      {/* Candidates */}
      <div className="dashboard-card" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <h3 style={{ fontSize: '16px', fontWeight: 700 }}>Candidate models</h3>
        {candidates.length === 0 ? (
          <span style={{ fontSize: '14px', color: '#786c5e' }}>No snapshot-trained candidates yet.</span>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead>
                <tr style={{ textAlign: 'left', color: '#786c5e', borderBottom: '1.5px solid var(--color-border)' }}>
                  <th style={{ padding: '8px' }}>Version</th>
                  <th style={{ padding: '8px' }}>Quality gate</th>
                  <th style={{ padding: '8px' }}>mAP50</th>
                  <th style={{ padding: '8px' }}>Precision</th>
                  <th style={{ padding: '8px' }}>Recall</th>
                  <th style={{ padding: '8px' }}>Status</th>
                  <th style={{ padding: '8px' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {candidates.map((c) => {
                  const st = statusById[c.model_id];
                  const metrics = st?.evaluation?.metrics || {};
                  const lifecycle = st?.lifecycle;
                  return (
                    <tr key={c.model_id} style={{ borderBottom: '1px solid var(--color-border)', backgroundColor: selected === c.model_id ? '#fffbeb' : 'transparent' }}>
                      <td style={{ padding: '8px', cursor: 'pointer', fontWeight: 600 }} onClick={() => setSelected(selected === c.model_id ? null : c.model_id)}>
                        {c.version} <span style={{ color: '#786c5e', fontWeight: 400 }}>({short(c.model_id)})</span>
                      </td>
                      <td style={{ padding: '8px' }}>{st?.evaluation?.gate_decision || st?.evaluation?.status || '—'}</td>
                      <td style={{ padding: '8px' }}>{pct(metrics.map50)}</td>
                      <td style={{ padding: '8px' }}>{pct(metrics.precision)}</td>
                      <td style={{ padding: '8px' }}>{pct(metrics.recall)}</td>
                      <td style={{ padding: '8px' }}><Badge state={lifecycle} /></td>
                      <td style={{ padding: '8px', display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                        {st && lifecycle === 'awaiting_review' && (
                          <>
                            <button type="button" className="login-btn" style={{ width: 'auto', padding: '6px 12px', fontSize: '12px', borderRadius: '8px' }} disabled={busy} onClick={() => handleApprove(st)}>
                              <Check size={14} /> Approve
                            </button>
                            <button type="button" className="login-btn" style={{ width: 'auto', padding: '6px 12px', fontSize: '12px', borderRadius: '8px', backgroundColor: '#dc2626' }} disabled={busy} onClick={() => handleReject(st)}>
                              <X size={14} /> Reject
                            </button>
                          </>
                        )}
                        {st && st.deployable && (
                          <button type="button" className="login-btn" style={{ width: 'auto', padding: '6px 12px', fontSize: '12px', borderRadius: '8px', backgroundColor: '#15803d' }} disabled={busy || !!inProgress} onClick={() => handleActivate(st)}>
                            <Play size={14} /> Activate
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {detail && (
          <div style={{ borderTop: '1.5px solid var(--color-border)', paddingTop: '16px', display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '13px' }}>
            <strong>Candidate {detail.version} — evaluation {short(detail.latest_evaluation_id)}</strong>
            <span>Review: {detail.review_state} · Deployment: {detail.deployment_state || 'never deployed'}</span>
            {detail.latest_deployment?.error_message && (
              <span style={{ color: '#b91c1c' }}>Last activation failure: {detail.latest_deployment.error_message}</span>
            )}
            {detail.blocking_reasons?.length > 0 && !detail.is_current && (
              <span style={{ color: '#b45309' }}>Not deployable: {detail.blocking_reasons.join('; ')}</span>
            )}
            {detail.evaluation?.gate_results && (
              <span>Gates: {detail.evaluation.gate_results.map((g) => `${g.gate}${g.class_index !== undefined ? `[${g.class_index}]` : ''}=${g.outcome}`).join(', ')}</span>
            )}
            {detail.evaluation?.metrics?.per_class && (
              <span>Per class: {detail.evaluation.metrics.per_class.map((r) => `${r.class_name}: AP50 ${pct(r.ap50)}, recall ${pct(r.recall)}`).join(' · ')}</span>
            )}
            {detail.decisions?.length > 0 && (
              <span>Decisions: {detail.decisions.map((d) => `${d.decision} by ${short(d.decided_by)} at ${d.decided_at?.slice(0, 19)}${d.reason ? ` ("${d.reason}")` : ''}`).join(' · ')}</span>
            )}
          </div>
        )}
      </div>

      {/* Deployment history + audit */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px', alignItems: 'start' }}>
        <div className="dashboard-card" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '12px', fontSize: '13px' }}>
          <h3 style={{ fontSize: '16px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <History size={18} style={{ color: 'var(--color-primary)' }} /> Deployment history
          </h3>
          {(deployments?.history || []).length === 0 ? (
            <span style={{ color: '#786c5e' }}>No deployments yet.</span>
          ) : (
            deployments.history.slice(0, 15).map((d) => (
              <div key={d.deployment_id} style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', borderBottom: '1px solid var(--color-border)', paddingBottom: '6px' }}>
                <span>{d.kind.replace('_', ' ')} → <strong>{d.model_version}</strong> <span style={{ color: '#786c5e' }}>{d.requested_at?.slice(0, 19)}</span>
                  {d.error_message && <span style={{ color: '#b91c1c' }}> — {d.error_message}</span>}
                </span>
                <Badge state={d.status === 'failed' ? 'activation_failed' : d.status === 'pending' ? 'activation_pending' : d.status} />
              </div>
            ))
          )}
        </div>
        <div className="dashboard-card" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '12px', fontSize: '13px' }}>
          <h3 style={{ fontSize: '16px', fontWeight: 700 }}>Audit trail</h3>
          {events.length === 0 ? (
            <span style={{ color: '#786c5e' }}>No events yet.</span>
          ) : (
            events.map((e) => (
              <div key={e.event_id} style={{ borderBottom: '1px solid var(--color-border)', paddingBottom: '6px' }}>
                <strong>{e.event_type.replaceAll('_', ' ')}</strong> · model {short(e.model_id)} · by {short(e.actor_id)}
                <span style={{ color: '#786c5e' }}> · {e.created_at?.slice(0, 19)}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};

export default ModelsView;
