import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Activity, AlertTriangle, AlertCircle, Info, RefreshCw, Database, Cpu, Server, Clock } from 'lucide-react';
import {
  fetchMonitoringSummary,
  fetchMonitoringTimeline,
  fetchTrainingJobsPage,
  fetchTrainingJobDetail,
  fetchEvaluationsPage,
  fetchDeploymentsPage,
  fetchApprovalsPage,
} from '../services/api';
import usePolling from '../hooks/usePolling';

// Block A5: read-only administrator monitoring. Every value shown comes from the
// backend; anything the backend does not report is shown as "Not available".

const PAGE = 10;
const NA = 'Not available';
const pct = (v) => (typeof v === 'number' ? `${(v * 100).toFixed(1)}%` : NA);
const short = (id) => (id ? `${id.slice(0, 8)}…` : '—');
const when = (iso) => (iso ? iso.replace('T', ' ').slice(0, 19) : '—');

const SEVERITY = {
  critical: { color: '#b91c1c', bg: '#fef2f2', border: '#fecaca', Icon: AlertCircle },
  warning: { color: '#b45309', bg: '#fffbeb', border: '#fde68a', Icon: AlertTriangle },
  info: { color: '#1d4ed8', bg: '#eff6ff', border: '#bfdbfe', Icon: Info },
};
const STATUS_COLOR = {
  queued: '#7c3aed', running: '#2563eb', completed: '#15803d', failed: '#b91c1c', passed: '#15803d',
  error: '#b91c1c', pending: '#7c3aed', approved: '#15803d', rejected: '#b91c1c', active: '#15803d', superseded: '#475569', rolled_back: '#475569',
  activating: '#7c3aed', reconciled: '#0f766e', ok: '#15803d',
};

const Pill = ({ value }) => (
  <span style={{ fontSize: '11px', fontWeight: 700, color: STATUS_COLOR[value] || '#475569', backgroundColor: '#f1f5f9', padding: '2px 8px', borderRadius: '999px', whiteSpace: 'nowrap' }}>
    {value || '—'}
  </span>
);

const Card = ({ title, icon: Icon, children, testId }) => (
  <div className="dashboard-card" data-testid={testId} style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '12px', minWidth: 0 }}>
    <h3 style={{ fontSize: '15px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
      {Icon && <Icon size={17} style={{ color: 'var(--color-primary)' }} />} {title}
    </h3>
    {children}
  </div>
);

const Stat = ({ label, value }) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', fontSize: '13px' }}>
    <span style={{ color: '#786c5e' }}>{label}</span><strong style={{ textAlign: 'right' }}>{value}</strong>
  </div>
);

const Pager = ({ offset, total, onChange, label }) => (
  <div style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '12px', color: '#786c5e' }} aria-label={label}>
    <button type="button" className="login-btn" style={{ width: 'auto', padding: '4px 10px', fontSize: '12px', borderRadius: '8px' }}
      disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - PAGE))}>Previous</button>
    <span>{total === 0 ? '0 of 0' : `${offset + 1}–${Math.min(offset + PAGE, total)} of ${total}`}</span>
    <button type="button" className="login-btn" style={{ width: 'auto', padding: '4px 10px', fontSize: '12px', borderRadius: '8px' }}
      disabled={offset + PAGE >= total} onClick={() => onChange(offset + PAGE)}>Next</button>
  </div>
);

const ErrorBox = ({ message }) => message ? (
  <div className="panel-alert panel-alert-error" role="alert" style={{ padding: '10px 12px', fontSize: '13px', color: '#dc2626', backgroundColor: '#fef2f2', border: '1px solid #fecaca', borderRadius: '8px' }}>
    {message}
  </div>
) : null;

const usePaged = (loader, deps) => {
  const [state, setState] = useState({ items: [], total: 0, error: '', loading: true });
  const latest = useRef(0);
  const load = useCallback(async () => {
    const seq = ++latest.current;                // only the newest request may update the view
    try {
      const r = await loader();
      if (seq === latest.current) setState({ items: r.items, total: r.total, error: '', loading: false });
    } catch (err) {
      if (seq === latest.current) setState((s) => ({ ...s, error: err.message || 'Failed to load', loading: false }));
    }
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [load]);
  return [state, load];
};

const MonitoringView = () => {
  const { data: summary, error: summaryError, lastSuccess, nextDelay, refresh } = usePolling(fetchMonitoringSummary);

  const [jobStatus, setJobStatus] = useState('');
  const [jobOffset, setJobOffset] = useState(0);
  const [jobs, reloadJobs] = usePaged(async () => {
    const r = await fetchTrainingJobsPage({ limit: PAGE, offset: jobOffset, status: jobStatus });
    return { items: r.jobs, total: r.total };
  }, [jobOffset, jobStatus]);
  const [openJob, setOpenJob] = useState(null);
  const [jobHistory, setJobHistory] = useState({ id: null, items: [], error: '' });

  const [evalStatus, setEvalStatus] = useState('');
  const [evalOffset, setEvalOffset] = useState(0);
  const [evals, reloadEvals] = usePaged(async () => {
    const r = await fetchEvaluationsPage({ limit: PAGE, offset: evalOffset, status: evalStatus });
    return { items: r.evaluations, total: r.total };
  }, [evalOffset, evalStatus]);

  const [depOffset, setDepOffset] = useState(0);
  const [deps, reloadDeps] = usePaged(async () => {
    const r = await fetchDeploymentsPage({ limit: PAGE, offset: depOffset });
    return { items: r.history, total: r.total };
  }, [depOffset]);

  const [apDecision, setApDecision] = useState('');
  const [apOffset, setApOffset] = useState(0);
  const [approvalRows, reloadApprovals] = usePaged(async () => {
    const r = await fetchApprovalsPage({ limit: PAGE, offset: apOffset, decision: apDecision });
    return { items: r.approvals, total: r.total };
  }, [apOffset, apDecision]);

  const [tlSource, setTlSource] = useState('');
  const [tlOffset, setTlOffset] = useState(0);
  const [timeline, setTimeline] = useState({ items: [], hasMore: false, error: '' });
  useEffect(() => {
    let cancelled = false;
    fetchMonitoringTimeline({ limit: PAGE, offset: tlOffset, source: tlSource })
      .then((r) => { if (!cancelled) setTimeline({ items: r.items, hasMore: r.has_more, error: '' }); })
      .catch((err) => { if (!cancelled) setTimeline((t) => ({ ...t, error: err.message })); });
    return () => { cancelled = true; };
  }, [tlOffset, tlSource, summary?.generated_at]);

  useEffect(() => {
    if (!summary) return;
    reloadJobs(); reloadEvals(); reloadDeps(); reloadApprovals();
  }, [summary?.generated_at]); // eslint-disable-line react-hooks/exhaustive-deps

  const historyFor = useRef(null);                 // only the most recently opened job may fill the panel
  const toggleJob = async (jobId) => {
    if (openJob === jobId) { setOpenJob(null); historyFor.current = null; return; }
    setOpenJob(jobId);
    historyFor.current = jobId;
    setJobHistory({ id: null, items: [], error: '' });
    try {
      const detail = await fetchTrainingJobDetail(jobId);
      if (historyFor.current === jobId) setJobHistory({ id: jobId, items: detail.history || [], error: '' });
    } catch (err) {
      if (historyFor.current === jobId) setJobHistory({ id: jobId, items: [], error: err.message });
    }
  };
  const degraded = Boolean(summaryError);           // last summary request failed: health values are unknown

  const alerts = summary?.alerts || [];
  const training = summary?.training || {};
  const dataset = summary?.dataset || {};
  const evaluations = summary?.evaluations || {};
  const approvals = summary?.approvals || {};
  const deployment = summary?.deployment || {};
  const health = summary?.health || {};
  const stale = lastSuccess && Date.now() - lastSuccess.getTime() > 45000;

  return (
    <div className="page-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <h1 style={{ fontSize: '32px', fontWeight: 800, color: '#38240d', fontFamily: 'var(--font-main)', lineHeight: '1.2' }}>Monitoring</h1>
          <p style={{ fontSize: '14px', color: '#786c5e' }}>
            Training pipeline, evaluations, approvals, deployments and system health (read-only).
          </p>
          <span data-testid="poll-status" style={{ fontSize: '12px', color: stale || summaryError ? '#b45309' : '#786c5e' }}>
            {lastSuccess ? `Updated ${lastSuccess.toLocaleTimeString()}` : 'Loading…'}
            {summaryError ? ` · update failed, retrying in ${Math.round(nextDelay / 1000)}s` : ` · refreshes every ${Math.round(nextDelay / 1000)}s`}
            {stale ? ' · data may be stale' : ''}
          </span>
        </div>
        <button type="button" className="login-btn" style={{ width: 'auto', padding: '10px 20px', fontSize: '14px', borderRadius: '12px' }} onClick={refresh}>
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      <ErrorBox message={summaryError && `Monitoring summary unavailable: ${summaryError}`} />

      {/* Alerts */}
      <Card title={`Alerts (${alerts.length})`} icon={AlertTriangle} testId="alerts">
        {!summary ? <span style={{ fontSize: '13px', color: '#786c5e' }}>{summaryError ? NA : 'Loading…'}</span>
          : alerts.length === 0 ? <span style={{ fontSize: '13px', color: '#15803d' }}>No active alerts.</span>
            : alerts.map((a, i) => {
              const s = SEVERITY[a.severity] || SEVERITY.info;
              return (
                <div key={`${a.code}-${i}`} data-alert={a.code} style={{ display: 'flex', gap: '8px', alignItems: 'flex-start', padding: '8px 10px', borderRadius: '8px', color: s.color, backgroundColor: s.bg, border: `1px solid ${s.border}`, fontSize: '13px' }}>
                  <s.Icon size={16} style={{ flexShrink: 0, marginTop: '1px' }} />
                  <span><strong>{a.severity.toUpperCase()} · {a.code}</strong> — {a.message}</span>
                </div>
              );
            })}
      </Card>

      {/* Summary cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '16px' }}>
        <Card title="Training jobs" icon={Activity} testId="card-training">
          {['queued', 'running', 'completed', 'failed'].map((k) => <Stat key={k} label={k} value={summary ? (training.by_status?.[k] || 0) : '…'} />)}
          <Stat label="awaiting dispatch" value={summary ? training.undispatched : '…'} />
        </Card>
        <Card title="Dataset readiness" icon={Database} testId="card-dataset">
          <Stat label="eligible images" value={dataset.total_training_eligible_images ?? NA} />
          <Stat label="threshold" value={dataset.threshold ?? NA} />
          <Stat label="next milestone" value={dataset.next_milestone ?? NA} />
          <Stat label="remaining" value={dataset.remaining_to_next_milestone ?? NA} />
          <Stat label="snapshots" value={dataset.snapshot_count ?? NA} />
        </Card>
        <Card title="Evaluations & approvals" icon={Cpu} testId="card-evaluations">
          {['passed', 'failed', 'error', 'running', 'pending'].map((k) => <Stat key={k} label={k} value={summary ? (evaluations.by_status?.[k] || 0) : '…'} />)}
          <Stat label="awaiting approval" value={summary ? approvals.pending_count : '…'} />
        </Card>
        <Card title="Active model" icon={Server} testId="card-deployment">
          <Stat label="model" value={deployment.active_model ? `${deployment.active_model.version} (${short(deployment.active_model.model_id)})` : (summary ? 'None' : '…')} />
          <Stat label="consistency" value={<Pill value={deployment.consistency?.state} />} />
          <Stat label="in progress" value={deployment.in_progress ? `${deployment.in_progress.kind} ${deployment.in_progress.status}` : 'none'} />
          <Stat label="rollback target" value={deployment.rollback_target ? deployment.rollback_target.version : 'none'} />
        </Card>
        <Card title="System health" icon={Clock} testId="card-health">
          <Stat label="database" value={degraded ? 'unknown (update failed)' : (summary ? health.database : NA)} />
          <Stat label="workers" value={degraded ? 'unknown (update failed)' : (health.workers ? `${health.workers.status}${health.workers.workers?.length ? ` (${health.workers.workers.length})` : ''}` : NA)} />
          {(health.scheduler || []).map((h) => (
            <Stat key={h.job_name} label={`scheduler: ${h.job_name}`}
              value={<span><Pill value={h.stale ? 'stale' : h.last_status} /> {h.last_finished_at ? when(h.last_finished_at) : 'never'}</span>} />
          ))}
          {summary && (health.scheduler || []).length === 0 && <Stat label="scheduler" value="no heartbeat recorded" />}
        </Card>
      </div>

      {/* Training jobs */}
      <Card title="Training jobs" icon={Activity} testId="jobs">
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap', justifyContent: 'space-between' }}>
          <label style={{ fontSize: '13px' }}>Status{' '}
            <select aria-label="Job status filter" className="panel-input" style={{ width: 'auto', padding: '4px 8px' }} value={jobStatus}
              onChange={(e) => { setJobOffset(0); setJobStatus(e.target.value); }}>
              <option value="">all</option>{['queued', 'running', 'completed', 'failed'].map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <Pager offset={jobOffset} total={jobs.total} onChange={setJobOffset} label="Jobs pagination" />
        </div>
        <ErrorBox message={jobs.error} />
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
            <thead><tr style={{ textAlign: 'left', color: '#786c5e', borderBottom: '1.5px solid var(--color-border)' }}>
              {['Version', 'Trigger', 'Status', 'Attempts', 'Dispatches', 'Created', 'Lease expires', 'Last error'].map((h) => <th key={h} style={{ padding: '6px 8px' }}>{h}</th>)}
            </tr></thead>
            <tbody>
              {jobs.items.length === 0 && !jobs.loading && <tr><td colSpan={8} style={{ padding: '8px', color: '#786c5e' }}>No training jobs match this filter.</td></tr>}
              {jobs.items.map((j) => (
                <React.Fragment key={j.job_id}>
                  <tr data-job={j.version} style={{ borderBottom: '1px solid var(--color-border)', cursor: 'pointer' }} onClick={() => toggleJob(j.job_id)}>
                    <td style={{ padding: '6px 8px', fontWeight: 600 }}>{j.version}</td>
                    <td style={{ padding: '6px 8px' }}>{j.trigger}</td>
                    <td style={{ padding: '6px 8px' }}><Pill value={j.status} /></td>
                    <td style={{ padding: '6px 8px' }}>{j.attempt_count ?? 0}</td>
                    <td style={{ padding: '6px 8px' }}>{j.dispatch_attempts ?? 0}</td>
                    <td style={{ padding: '6px 8px' }}>{when(j.created_at)}</td>
                    <td style={{ padding: '6px 8px' }}>{when(j.lease_expires_at)}</td>
                    <td style={{ padding: '6px 8px', color: '#b91c1c', maxWidth: '280px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={j.error_message || ''}>{j.error_message || ''}</td>
                  </tr>
                  {openJob === j.job_id && (
                    <tr><td colSpan={8} style={{ padding: '8px 12px', background: '#fffbeb' }} data-testid="job-history">
                      <ErrorBox message={jobHistory.error} />
                      <strong style={{ fontSize: '12px' }}>Attempt history</strong>
                      {jobHistory.id !== j.job_id && <div style={{ fontSize: '12px', color: '#786c5e' }}>Loading…</div>}
                      {jobHistory.id === j.job_id && jobHistory.items.length === 0 && !jobHistory.error && <div style={{ fontSize: '12px', color: '#786c5e' }}>No history recorded.</div>}
                      {jobHistory.items.map((e) => (
                        <div key={e.event_id} style={{ fontSize: '12px' }}>
                          {when(e.created_at)} · <strong>{e.event_type}</strong> {e.status_before ? `${e.status_before} → ` : ''}{e.status_after}
                          {e.attempt ? ` · attempt ${e.attempt}` : ''}{e.message ? ` · ${e.message}` : ''}
                        </div>
                      ))}
                    </td></tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '16px', alignItems: 'start' }}>
        {/* Evaluations */}
        <Card title="Evaluation metrics" icon={Cpu} testId="evaluations">
          <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap', justifyContent: 'space-between' }}>
            <label style={{ fontSize: '13px' }}>Status{' '}
              <select aria-label="Evaluation status filter" className="panel-input" style={{ width: 'auto', padding: '4px 8px' }} value={evalStatus}
                onChange={(e) => { setEvalOffset(0); setEvalStatus(e.target.value); }}>
                <option value="">all</option>{['pending', 'running', 'passed', 'failed', 'error'].map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </label>
            <Pager offset={evalOffset} total={evals.total} onChange={setEvalOffset} label="Evaluations pagination" />
          </div>
          <ErrorBox message={evals.error} />
          {evals.items.length === 0 && !evals.loading && <span style={{ fontSize: '13px', color: '#786c5e' }}>No evaluations match this filter.</span>}
          {evals.items.map((e) => (
            <div key={e.evaluation_id} data-eval={e.model_version} style={{ fontSize: '13px', borderBottom: '1px solid var(--color-border)', paddingBottom: '6px' }}>
              <strong>{e.model_version}</strong> <Pill value={e.status} /> {e.gate_decision || ''}
              <div style={{ color: '#786c5e' }}>
                mAP50 {pct(e.metrics?.map50)} · precision {pct(e.metrics?.precision)} · recall {pct(e.metrics?.recall)} · {e.test_image_count ?? NA} test images
              </div>
              {e.error_message && <div style={{ color: '#b91c1c' }}>{e.error_message}</div>}
            </div>
          ))}
        </Card>

        {/* Deployment history */}
        <Card title="Deployment history" icon={Server} testId="deployments">
          <Pager offset={depOffset} total={deps.total} onChange={setDepOffset} label="Deployments pagination" />
          <ErrorBox message={deps.error} />
          {deps.items.length === 0 && !deps.loading && <span style={{ fontSize: '13px', color: '#786c5e' }}>No deployments yet.</span>}
          {deps.items.map((d) => (
            <div key={d.deployment_id} style={{ fontSize: '13px', display: 'flex', justifyContent: 'space-between', gap: '8px', borderBottom: '1px solid var(--color-border)', paddingBottom: '6px' }}>
              <span>{d.kind.replace('_', ' ')} → <strong>{d.model_version}</strong> <span style={{ color: '#786c5e' }}>{when(d.requested_at)}</span>
                {d.error_message && <span style={{ color: '#b91c1c' }}> — {d.error_message}</span>}</span>
              <Pill value={d.status} />
            </div>
          ))}
        </Card>
      </div>

      {/* Approval records */}
      <Card title="Approval records" icon={Cpu} testId="approvals">
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap', justifyContent: 'space-between' }}>
          <label style={{ fontSize: '13px' }}>Decision{' '}
            <select aria-label="Approval decision filter" className="panel-input" style={{ width: 'auto', padding: '4px 8px' }} value={apDecision}
              onChange={(e) => { setApOffset(0); setApDecision(e.target.value); }}>
              <option value="">all</option><option value="approved">approved</option><option value="rejected">rejected</option>
            </select>
          </label>
          <span style={{ fontSize: '12px', color: '#786c5e' }}>awaiting review: {summary ? approvals.pending_count : '…'}</span>
          <Pager offset={apOffset} total={approvalRows.total} onChange={setApOffset} label="Approvals pagination" />
        </div>
        <ErrorBox message={approvalRows.error} />
        {approvalRows.items.length === 0 && !approvalRows.loading && <span style={{ fontSize: '13px', color: '#786c5e' }}>No approval decisions recorded.</span>}
        {approvalRows.items.map((a) => (
          <div key={a.approval_id} data-approval={a.model_version} style={{ fontSize: '13px', borderBottom: '1px solid var(--color-border)', paddingBottom: '6px' }}>
            <strong>{a.model_version}</strong> <Pill value={a.decision} /> <span style={{ color: '#786c5e' }}>{when(a.decided_at)} · by {short(a.decided_by)} · gate {a.gate_decision || NA}</span>
            {a.reason && <div style={{ color: '#786c5e' }}>{a.reason}</div>}
          </div>
        ))}
      </Card>

      {/* Timeline */}
      <Card title="Activity timeline" icon={Clock} testId="timeline">
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap', justifyContent: 'space-between' }}>
          <label style={{ fontSize: '13px' }}>Source{' '}
            <select aria-label="Timeline source filter" className="panel-input" style={{ width: 'auto', padding: '4px 8px' }} value={tlSource}
              onChange={(e) => { setTlOffset(0); setTlSource(e.target.value); }}>
              <option value="">all</option><option value="training">training</option><option value="deployment">deployment</option><option value="evaluation">evaluation</option>
            </select>
          </label>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button type="button" className="login-btn" style={{ width: 'auto', padding: '4px 10px', fontSize: '12px', borderRadius: '8px' }} disabled={tlOffset === 0} onClick={() => setTlOffset(Math.max(0, tlOffset - PAGE))}>Newer</button>
            <button type="button" className="login-btn" style={{ width: 'auto', padding: '4px 10px', fontSize: '12px', borderRadius: '8px' }} disabled={!timeline.hasMore} onClick={() => setTlOffset(tlOffset + PAGE)}>Older</button>
          </div>
        </div>
        <ErrorBox message={timeline.error} />
        {timeline.items.length === 0 && !timeline.error && <span style={{ fontSize: '13px', color: '#786c5e' }}>No activity recorded.</span>}
        {timeline.items.map((t) => (
          <div key={`${t.source}-${t.id}`} data-timeline={t.type} style={{ fontSize: '12px', borderBottom: '1px solid var(--color-border)', paddingBottom: '4px' }}>
            <span style={{ color: '#786c5e' }}>{when(t.at)}</span> · <strong>{t.source}</strong> · {t.type.replaceAll('_', ' ')}
            {t.attempt ? ` · attempt ${t.attempt}` : ''}{t.status ? ` · ${t.status}` : ''}{t.message ? ` · ${t.message}` : ''}
          </div>
        ))}
      </Card>
    </div>
  );
};

export default MonitoringView;
