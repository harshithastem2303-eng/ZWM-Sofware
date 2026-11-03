import React, { useCallback, useEffect, useState } from 'react';
import { Flag, X, Loader2 } from 'lucide-react';
import {
  fetchMyFeedback,
  fetchPrediction,
  fetchPredictionsForImage,
  submitPredictionFeedback,
  FeedbackSubmission,
  FeedbackType,
} from '../../services/api';

// Block A6.2: report an incorrect AI prediction for this image and follow the review.
// Every value shown comes from the backend. Confidence is shown only when the
// prediction record says it is a real model score (OpenCV / segmentation-assistant
// values are fixed numbers, not scores).

export interface FeedbackShape {
  label: string;
  geometry: FeedbackSubmission['suggested_geometry'] | null;   // original image pixels
}

interface CategoryOption {
  id?: number;
  category_id?: number;
  name?: string;
  class_name?: string;
}

interface Props {
  imageId: string;
  refreshKey: number;
  categories: CategoryOption[];
  shapes: FeedbackShape[];
}

const TYPES: { id: FeedbackType; label: string; detection: 'required' | 'optional' | 'forbidden';
  cls: 'required' | 'optional' | 'forbidden'; geometry: 'required' | 'optional' | 'forbidden' }[] = [
  { id: 'incorrect_class', label: 'Wrong class', detection: 'required', cls: 'required', geometry: 'optional' },
  { id: 'incorrect_geometry', label: 'Wrong box / outline', detection: 'required', cls: 'optional', geometry: 'required' },
  { id: 'missed_object', label: 'Missed an object', detection: 'forbidden', cls: 'required', geometry: 'required' },
  { id: 'false_detection', label: 'Not an object (false detection)', detection: 'required', cls: 'forbidden', geometry: 'forbidden' },
  { id: 'other', label: 'Other problem', detection: 'optional', cls: 'optional', geometry: 'optional' },
];

const STATUS_COLOR: Record<string, string> = { pending: '#a78bfa', approved: '#34d399', rejected: '#f87171' };
const SOURCE_LABEL: Record<string, string> = {
  ml_predict: 'Detector prediction', upload_validation: 'Upload check', ai_segment: 'AI auto-segment',
  ai_polygon_click: 'AI polygon click',
};

const field: React.CSSProperties = {
  padding: '7px 10px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.15)',
  backgroundColor: '#0f172a', color: '#f8fafc', fontSize: '0.8rem', width: '100%', boxSizing: 'border-box',
};
const when = (iso?: string) => (iso ? iso.replace('T', ' ').slice(0, 16) : '—');

const confidenceText = (det: any, isScore: boolean) =>
  isScore && typeof det?.confidence === 'number' ? `${(det.confidence * 100).toFixed(1)}%` : 'not a model score';

export const PredictionFeedbackPanel: React.FC<Props> = ({ imageId, refreshKey, categories, shapes }) => {
  const [open, setOpen] = useState(false);
  const [predictions, setPredictions] = useState<any[]>([]);
  const [feedback, setFeedback] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [predictionId, setPredictionId] = useState<string>('');
  const [prediction, setPrediction] = useState<any | null>(null);
  const [type, setType] = useState<FeedbackType>('incorrect_class');
  const [detection, setDetection] = useState<string>('');
  const [categoryId, setCategoryId] = useState<string>('');
  const [shapeIndex, setShapeIndex] = useState<string>('');
  const [explanation, setExplanation] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    try {
      const [p, f] = await Promise.all([fetchPredictionsForImage(imageId), fetchMyFeedback({ image_id: imageId })]);
      const usable = (p.items || []).filter((i: any) => i.status !== 'failed');
      setPredictions(usable);
      setFeedback(f.items || []);
      setPredictionId((cur) => (cur && usable.some((i: any) => i.prediction_id === cur) ? cur : usable[0]?.prediction_id || ''));
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Could not load AI feedback.');
    }
  }, [imageId]);

  useEffect(() => { load(); }, [load, refreshKey]);

  useEffect(() => {
    if (!predictionId) { setPrediction(null); return; }
    let live = true;
    fetchPrediction(predictionId).then((p) => live && setPrediction(p)).catch(() => live && setPrediction(null));
    return () => { live = false; };
  }, [predictionId]);

  const rule = TYPES.find((t) => t.id === type)!;
  const detections: any[] = prediction?.detections || [];

  const submit = async () => {
    setError(null);
    setNotice(null);
    const body: FeedbackSubmission = { feedback_type: type };
    if (rule.detection !== 'forbidden' && detection !== '') body.detection_index = Number(detection);
    if (rule.cls !== 'forbidden' && categoryId !== '') body.suggested_category_id = Number(categoryId);
    if (rule.geometry !== 'forbidden' && shapeIndex !== '') {
      const g = shapes[Number(shapeIndex)]?.geometry;
      if (g) body.suggested_geometry = g;
    }
    if (explanation.trim()) body.explanation = explanation.trim();
    setSubmitting(true);
    try {
      await submitPredictionFeedback(predictionId, body);
      setNotice('Thank you — your report is pending administrator review. It does not change your labels.');
      setExplanation('');
      setShapeIndex('');
      await load();
    } catch (err: any) {
      setError(err.message || 'Feedback could not be submitted.');
    } finally {
      setSubmitting(false);
    }
  };

  const missing =
    !predictionId ||
    (rule.detection === 'required' && detection === '') ||
    (rule.cls === 'required' && categoryId === '') ||
    (rule.geometry === 'required' && (shapeIndex === '' || !shapes[Number(shapeIndex)]?.geometry)) ||
    (type === 'other' && explanation.trim().length < 3);

  return (
    <div data-testid="ai-feedback-panel" style={{
      position: 'fixed', left: '16px', bottom: '16px', zIndex: 60, width: open ? '360px' : 'auto',
      maxHeight: '75vh', overflowY: 'auto', backgroundColor: 'rgba(30, 41, 59, 0.92)', backdropFilter: 'blur(16px)',
      border: '1px solid rgba(255,255,255,0.12)', borderRadius: '14px', boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
      color: '#f8fafc', fontSize: '0.8rem',
    }}>
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
        style={{ display: 'flex', alignItems: 'center', gap: '8px', width: '100%', padding: '10px 14px', background: 'none',
          border: 'none', color: '#f8fafc', cursor: 'pointer', fontWeight: 700, fontSize: '0.82rem' }}>
        <Flag size={15} color="#f59e0b" /> Report AI issue
        {feedback.length > 0 && <span style={{ color: '#94a3b8', fontWeight: 500 }}>({feedback.length} sent)</span>}
        {open && <X size={14} style={{ marginLeft: 'auto' }} />}
      </button>

      {open && (
        <div style={{ padding: '0 14px 14px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {error && <div role="alert" style={{ color: '#fca5a5' }}>{error}</div>}
          {notice && <div role="status" style={{ color: '#6ee7b7' }}>{notice}</div>}

          {predictions.length === 0 ? (
            <div style={{ color: '#94a3b8' }}>No AI predictions have been made for this image yet.</div>
          ) : (
            <>
              <label>AI result
                <select aria-label="AI result" style={field} value={predictionId}
                  onChange={(e) => { setPredictionId(e.target.value); setDetection(''); }}>
                  {predictions.map((p) => (
                    <option key={p.prediction_id} value={p.prediction_id}>
                      {SOURCE_LABEL[p.source] || p.source} · {when(p.created_at)} · {p.detection_count} object(s)
                    </option>
                  ))}
                </select>
              </label>
              <label>Problem
                <select aria-label="Problem" style={field} value={type} onChange={(e) => setType(e.target.value as FeedbackType)}>
                  {TYPES.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
                </select>
              </label>
              {rule.detection !== 'forbidden' && (
                <label>Object{rule.detection === 'optional' ? ' (optional)' : ''}
                  <select aria-label="Object" style={field} value={detection} onChange={(e) => setDetection(e.target.value)}>
                    <option value="">{rule.detection === 'optional' ? 'Whole result' : 'Choose…'}</option>
                    {detections.map((d, i) => (
                      <option key={i} value={i}>
                        #{i + 1} {d.label || 'object'} — confidence {confidenceText(d, !!prediction?.confidence_is_model_score)}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {rule.cls !== 'forbidden' && (
                <label>Correct class{rule.cls === 'optional' ? ' (optional)' : ''}
                  <select aria-label="Correct class" style={field} value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
                    <option value="">Choose…</option>
                    {categories.map((c) => (
                      <option key={c.category_id || c.id} value={c.category_id || c.id}>{c.class_name || c.name}</option>
                    ))}
                  </select>
                </label>
              )}
              {rule.geometry !== 'forbidden' && (
                <label>Correct outline{rule.geometry === 'optional' ? ' (optional)' : ''}
                  <select aria-label="Correct outline" style={field} value={shapeIndex} onChange={(e) => setShapeIndex(e.target.value)}>
                    <option value="">{shapes.some((s) => s.geometry) ? 'Choose a shape you drew…' : 'Draw a shape on the image first'}</option>
                    {shapes.map((s, i) => s.geometry && (
                      <option key={i} value={i}>Shape #{i + 1} {s.label} ({s.geometry.type})</option>
                    ))}
                  </select>
                </label>
              )}
              <label>Explanation{type === 'other' ? '' : ' (optional)'}
                <textarea aria-label="Explanation" style={{ ...field, minHeight: '56px', resize: 'vertical' }} maxLength={2000}
                  value={explanation} onChange={(e) => setExplanation(e.target.value)} />
              </label>
              <button type="button" onClick={submit} disabled={missing || submitting}
                style={{ padding: '8px 12px', borderRadius: '8px', border: 'none', fontWeight: 700, cursor: missing ? 'not-allowed' : 'pointer',
                  background: missing ? '#334155' : 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)', color: '#fff',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px' }}>
                {submitting && <Loader2 size={14} className="animate-spin" />} Submit report
              </button>
            </>
          )}

          {feedback.length > 0 && (
            <div>
              <div style={{ fontWeight: 700, margin: '4px 0 6px' }}>Your reports for this image</div>
              {feedback.map((f) => (
                <div key={f.feedback_id} data-testid="my-feedback-item"
                  style={{ padding: '6px 8px', borderRadius: '8px', backgroundColor: 'rgba(15,23,42,0.5)', marginBottom: '4px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '6px' }}>
                    <span>{TYPES.find((t) => t.id === f.feedback_type)?.label || f.feedback_type}</span>
                    <strong style={{ color: STATUS_COLOR[f.status] || '#94a3b8' }}>{f.status}</strong>
                  </div>
                  <div style={{ color: '#94a3b8', fontSize: '0.72rem' }}>
                    Sent {when(f.submitted_at)}
                    {f.decision && <> · {f.decision.decision} {when(f.decision.decided_at)}{f.decision.reason ? ` — “${f.decision.reason}”` : ''}</>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
