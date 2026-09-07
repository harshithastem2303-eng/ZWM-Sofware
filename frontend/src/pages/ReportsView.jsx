import React from 'react';
import { BarChart3, Cpu, Layers, Download, TrendingUp, CheckCircle, Clock, AlertTriangle, Users, Image as ImageIcon } from 'lucide-react';
import CountUp from '../components/CountUp';
import useInView from '../hooks/useInView';

const ReportsView = ({ analytics }) => {
  // Scroll In-View Animation Refs
  const [funnelRef, funnelInView] = useInView({ threshold: 0.15 });
  const [categoriesRef, categoriesInView] = useInView({ threshold: 0.15 });

  // Extract details safely
  const summary = analytics?.summary || {};
  const totalUsers = summary.total_users || 0;
  const totalImages = summary.total_images || 0;
  const validatedImages = summary.validated_images || 0;
  const pendingImages = summary.pending_images || 0;
  const rejectedImages = summary.rejected_images || 0;
  const totalAnnotations = summary.total_annotations || 0;

  const categoryBreakdown = analytics?.category_breakdown || [];
  const training = analytics?.training || {};
  const statusCounts = training.status_counts || {};
  const avgTrainingDuration = training.average_duration_minutes || 0;

  // Calculate percentages
  const validationRate = totalImages > 0 ? parseFloat(((validatedImages / totalImages) * 100).toFixed(1)) : 0;
  const pendingRate = totalImages > 0 ? parseFloat(((pendingImages / totalImages) * 100).toFixed(1)) : 0;
  const rejectionRate = totalImages > 0 ? parseFloat(((rejectedImages / totalImages) * 100).toFixed(1)) : 0;

  // Calculate category totals
  const totalCategoryImages = categoryBreakdown.reduce((sum, cat) => sum + cat.count, 0);

  // Trigger download of analytics payload as a beautifully formatted PDF report
  const handleExportPDF = () => {
    const printWindow = window.open('', '_blank');
    if (!printWindow) {
      alert('Pop-up blocked! Please allow popups to export the PDF report.');
      return;
    }

    const categoriesTableHtml = categoryBreakdown.map(cat => {
      const catPct = totalCategoryImages > 0 ? ((cat.count / totalCategoryImages) * 100).toFixed(1) : 0;
      return `
        <tr>
          <td><strong>${cat.category}</strong></td>
          <td>${cat.count.toLocaleString()}</td>
          <td>${catPct}%</td>
        </tr>
      `;
    }).join('');

    printWindow.document.write(`
      <!DOCTYPE html>
      <html>
        <head>
          <title>ZWM System Report - ${new Date().toISOString().slice(0,10)}</title>
          <style>
            @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap');
            body {
              font-family: 'Outfit', -apple-system, sans-serif;
              color: #0f172a;
              padding: 40px;
              line-height: 1.5;
              background-color: #ffffff;
            }
            .header-container {
              display: flex;
              justify-content: space-between;
              align-items: flex-start;
              border-bottom: 2px solid #15803d;
              padding-bottom: 24px;
              margin-bottom: 32px;
            }
            .brand-title {
              font-size: 26px;
              font-weight: 700;
              color: #15803d;
              letter-spacing: -0.5px;
            }
            .brand-subtitle {
              font-size: 13px;
              font-weight: 500;
              color: #64748b;
              text-transform: uppercase;
              letter-spacing: 0.5px;
              margin-top: 4px;
            }
            .report-meta {
              font-size: 12px;
              color: #64748b;
              text-align: right;
            }
            .report-section-title {
              font-size: 16px;
              font-weight: 700;
              color: #0f172a;
              margin: 32px 0 16px 0;
              border-bottom: 1.5px solid #e2e8f0;
              padding-bottom: 8px;
              text-transform: uppercase;
              letter-spacing: 0.5px;
            }
            .metrics-grid {
              display: grid;
              grid-template-columns: repeat(3, 1fr);
              gap: 20px;
              margin-bottom: 32px;
            }
            .metric-card-box {
              border: 1.5px solid #e2e8f0;
              border-radius: 12px;
              padding: 20px;
              background-color: #f8fafc;
            }
            .metric-card-label {
              font-size: 11px;
              font-weight: 600;
              color: #64748b;
              text-transform: uppercase;
              letter-spacing: 0.5px;
            }
            .metric-card-value {
              font-size: 24px;
              font-weight: 700;
              color: #0f172a;
              margin-top: 6px;
            }
            table {
              width: 100%;
              border-collapse: collapse;
              margin-top: 8px;
              margin-bottom: 32px;
            }
            th {
              background-color: #f1f5f9;
              font-weight: 600;
              color: #334155;
              border-bottom: 2px solid #cbd5e1;
            }
            th, td {
              text-align: left;
              padding: 12px 16px;
              border-bottom: 1.5px solid #e2e8f0;
              font-size: 13px;
            }
            tr:last-child td {
              border-bottom: none;
            }
            .footer {
              margin-top: 60px;
              border-top: 1px solid #e2e8f0;
              padding-top: 16px;
              font-size: 11px;
              color: #94a3b8;
              text-align: center;
            }
            @media print {
              body {
                padding: 0;
              }
              .no-print {
                display: none;
              }
            }
          </style>
        </head>
        <body>
          <div class="header-container">
            <div>
              <div class="brand-title">Zero Waste Management System</div>
              <div class="brand-subtitle">AI Waste Analytics Report</div>
            </div>
            <div class="report-meta">
              <div><strong>Document ID:</strong> ZWM-REP-${new Date().getTime().toString().slice(-6)}</div>
              <div><strong>Generated:</strong> ${new Date().toLocaleString()}</div>
              <div><strong>Scope:</strong> Master Dataset Registry</div>
            </div>
          </div>

          <div class="report-section-title">1. Dataset Summary & Funnel</div>
          <div class="metrics-grid">
            <div class="metric-card-box">
              <div class="metric-card-label">Total Images Collected</div>
              <div class="metric-card-value">${totalImages.toLocaleString()}</div>
            </div>
            <div class="metric-card-box">
              <div class="metric-card-label">Approved & Validated</div>
              <div class="metric-card-value">${validatedImages.toLocaleString()} (${validationRate}%)</div>
            </div>
            <div class="metric-card-box">
              <div class="metric-card-label">Pending Review</div>
              <div class="metric-card-value">${pendingImages.toLocaleString()} (${pendingRate}%)</div>
            </div>
          </div>

          <div class="report-section-title">2. Class Distribution Registry</div>
          <table>
            <thead>
              <tr>
                <th>Waste Category</th>
                <th>Annotated Images</th>
                <th>Percentage share</th>
              </tr>
            </thead>
            <tbody>
              ${categoriesTableHtml || '<tr><td colspan="3" style="text-align:center;">No category breakdown details available.</td></tr>'}
            </tbody>
          </table>

          <div class="report-section-title">3. ML Pipelines & Execution Durations</div>
          <table>
            <thead>
              <tr>
                <th>ML pipeline Job Metrics</th>
                <th>Execution stats</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Completed Retraining Jobs</td>
                <td><strong>${statusCounts.completed || 0}</strong></td>
              </tr>
              <tr>
                <td>Active Retraining Pipelines</td>
                <td><strong>${statusCounts.running || statusCounts.training || 0}</strong></td>
              </tr>
              <tr>
                <td>Queued Retraining Jobs</td>
                <td><strong>${statusCounts.pending || 0}</strong></td>
              </tr>
              <tr>
                <td>Failed Retraining Pipeline Runs</td>
                <td><strong>${statusCounts.failed || 0}</strong></td>
              </tr>
              <tr>
                <td>Average Training Speed (Celery Worker)</td>
                <td><strong>${avgTrainingDuration > 0 ? `${avgTrainingDuration.toFixed(1)} mins` : 'N/A'}</strong></td>
              </tr>
            </tbody>
          </table>

          <div class="footer">
            Zero Waste Management Platform (ZWM) &bull; Confidential Internal Admin Console Document
          </div>

          <script>
            window.onload = function() {
              window.print();
              setTimeout(function() { window.close(); }, 500);
            };
          </script>
        </body>
      </html>
    `);
    printWindow.document.close();
  };

  return (
    <div className="page-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
      
      {/* Page Heading */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '28px' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <h1 style={{ fontSize: '32px', fontWeight: 800, color: '#38240d', fontFamily: 'var(--font-main)', lineHeight: '1.2' }}>
            Reports
          </h1>
          <p style={{ fontSize: '14px', fontWeight: 400, color: '#786c5e', fontFamily: 'var(--font-main)' }}>
            Analyze dataset growth, validation performance, and system activity.
          </p>
        </div>
        
        <button className="login-btn" style={{ width: 'auto', padding: '10px 18px', fontSize: '14px', borderRadius: '12px', marginTop: '4px' }} onClick={handleExportPDF}>
          <Download size={16} />
          Export System Report (PDF)
        </button>
      </div>

      {/* Grid of Metric Blocks with Scroll CountUp Animations */}
      <section className="metrics-row" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
        {/* Core Collection Card */}
        <div className="metric-card" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: '12px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%' }}>
            <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--color-text-muted)' }}>COLLECTION SUMMARY</span>
            <div className="metric-icon-box" style={{ width: '38px', height: '38px' }}><ImageIcon size={18} /></div>
          </div>
          <div>
            <h3 style={{ fontSize: '28px', fontWeight: 700, color: 'var(--color-text-main)' }}>
              <CountUp end={totalImages} duration={1000} />
            </h3>
            <p style={{ fontSize: '12px', color: 'var(--color-text-muted)', marginTop: '4px' }}>Total images submitted by contributors.</p>
          </div>
          <div style={{ width: '100%', borderTop: '1px solid var(--color-border)', paddingTop: '8px', marginTop: '4px', display: 'flex', gap: '16px', fontSize: '12px' }}>
            <span><strong><CountUp end={totalUsers} duration={800} /></strong> Users</span>
            <span><strong><CountUp end={totalAnnotations} duration={800} /></strong> Object Annotations</span>
          </div>
        </div>

        {/* Validation Funnel Card */}
        <div ref={funnelRef} className="metric-card" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: '12px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%' }}>
            <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--color-text-muted)' }}>VALIDATION FUNNEL</span>
            <div className="metric-icon-box" style={{ width: '38px', height: '38px', color: '#10b981', backgroundColor: '#ecfdf5' }}><CheckCircle size={18} /></div>
          </div>
          <div>
            <h3 style={{ fontSize: '28px', fontWeight: 700, color: '#10b981' }}>
              <CountUp end={validationRate} decimals={1} suffix="%" duration={1000} />
            </h3>
            <p style={{ fontSize: '12px', color: 'var(--color-text-muted)', marginTop: '4px' }}>Approved dataset classification rate.</p>
          </div>
          <div style={{ width: '100%', height: '6px', backgroundColor: '#f1f5f9', borderRadius: '3px', display: 'flex', overflow: 'hidden', margin: '4px 0' }}>
            <div style={{ background: '#10b981', width: funnelInView ? `${validationRate}%` : '0%', transition: 'width 1s cubic-bezier(0.34, 1.56, 0.64, 1)' }} />
            <div style={{ background: '#f97316', width: funnelInView ? `${pendingRate}%` : '0%', transition: 'width 1s cubic-bezier(0.34, 1.56, 0.64, 1)' }} />
            <div style={{ background: '#ef4444', width: funnelInView ? `${rejectionRate}%` : '0%', transition: 'width 1s cubic-bezier(0.34, 1.56, 0.64, 1)' }} />
          </div>
          <div style={{ width: '100%', display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--color-text-muted)' }}>
            <span>Approved: <CountUp end={validatedImages} duration={800} /></span>
            <span>Pending: <CountUp end={pendingImages} duration={800} /></span>
            <span>Rejected: <CountUp end={rejectedImages} duration={800} /></span>
          </div>
        </div>

        {/* Model Accuracy Card */}
        <div className="metric-card" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: '12px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%' }}>
            <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--color-text-muted)' }}>NEURAL MODEL TELEMETRY</span>
            <div className="metric-icon-box" style={{ width: '38px', height: '38px', color: '#3b82f6', backgroundColor: '#eff6ff' }}><Cpu size={18} /></div>
          </div>
          <div>
            <h3 style={{ fontSize: '28px', fontWeight: 700, color: '#3b82f6' }}>YOLOv8-m (v2.4)</h3>
            <p style={{ fontSize: '12px', color: 'var(--color-text-muted)', marginTop: '4px' }}>Active ML Waste Classification Model.</p>
          </div>
          <div style={{ width: '100%', borderTop: '1px solid var(--color-border)', paddingTop: '8px', marginTop: '4px', display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
            <span>mAP50 Accuracy: <strong><CountUp end={94.6} decimals={1} suffix="%" duration={1000} /></strong></span>
            <span style={{ color: '#10b981', fontWeight: 600 }}>Active production model</span>
          </div>
        </div>
      </section>

      {/* Main Breakdown Section */}
      <section className="dashboard-grid">
        
        {/* Category Breakdown (Class Distribution with Scroll Growth Animation) */}
        <div ref={categoriesRef} className="dashboard-card" style={{ padding: '28px' }}>
          <div className="card-header-flex">
            <h2 className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Layers size={18} style={{ color: 'var(--color-primary)' }} />
              Dataset Distribution Across Classes
            </h2>
          </div>
          
          <p style={{ color: 'var(--color-text-muted)', fontSize: '13px', marginBottom: '24px' }}>
            Breakdown of validated object types collected. These numbers reflect distinct annotations matched with checked categories.
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            {categoryBreakdown.map((cat, idx) => {
              const catPct = totalCategoryImages > 0 ? parseFloat(((cat.count / totalCategoryImages) * 100).toFixed(1)) : 0;
              
              let color = '#3b82f6';
              if (cat.category.toLowerCase() === 'plastic') color = 'var(--color-primary)';
              if (cat.category.toLowerCase() === 'paper') color = '#f59e0b';
              if (cat.category.toLowerCase() === 'metal') color = '#ef4444';
              if (cat.category.toLowerCase() === 'glass') color = '#06b6d4';

              return (
                <div key={idx} style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '14px', fontWeight: 600 }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ width: '10px', height: '10px', borderRadius: '50%', backgroundColor: color }} />
                      {cat.category}
                    </span>
                    <span>
                      <CountUp end={cat.count} duration={1000} /> images (<CountUp end={catPct} decimals={1} suffix="%" duration={1000} />)
                    </span>
                  </div>
                  
                  <div style={{ width: '100%', height: '10px', backgroundColor: '#f1f5f9', borderRadius: '5px', overflow: 'hidden' }}>
                    <div style={{
                      height: '100%',
                      backgroundColor: color,
                      width: categoriesInView ? `${catPct}%` : '0%',
                      borderRadius: '5px',
                      transition: `width 1s cubic-bezier(0.34, 1.56, 0.64, 1) ${idx * 100}ms`
                    }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* ML Model Training Jobs Summary */}
        <div className="dashboard-card" style={{ padding: '28px' }}>
          <div className="card-header-flex">
            <h2 className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Cpu size={18} style={{ color: '#3b82f6' }} />
              Model Training Jobs
            </h2>
          </div>
          
          <p style={{ color: 'var(--color-text-muted)', fontSize: '13px', marginBottom: '20px' }}>
            Review Celery background workers model training jobs status.
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', background: '#f8fafc', borderRadius: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#10b981', fontWeight: 600 }}>
                <CheckCircle size={16} /> Completed Jobs
              </div>
              <span style={{ fontWeight: 700 }}><CountUp end={statusCounts.completed || 0} duration={800} /></span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', background: '#f8fafc', borderRadius: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#3b82f6', fontWeight: 600 }}>
                <Clock size={16} /> Running / Training
              </div>
              <span style={{ fontWeight: 700 }}><CountUp end={statusCounts.running || statusCounts.training || 0} duration={800} /></span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', background: '#f8fafc', borderRadius: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#f59e0b', fontWeight: 600 }}>
                <Clock size={16} /> Pending in Queue
              </div>
              <span style={{ fontWeight: 700 }}><CountUp end={statusCounts.pending || 0} duration={800} /></span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', background: '#f8fafc', borderRadius: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#ef4444', fontWeight: 600 }}>
                <AlertTriangle size={16} /> Failed Training
              </div>
              <span style={{ fontWeight: 700 }}><CountUp end={statusCounts.failed || 0} duration={800} /></span>
            </div>

            {/* Average Duration Box */}
            <div style={{ border: '1.5px dashed var(--color-border)', borderRadius: '12px', padding: '16px', textAlign: 'center', marginTop: '8px' }}>
              <span style={{ fontSize: '12px', color: 'var(--color-text-muted)', fontWeight: 600, display: 'block', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Avg. Training Speed</span>
              <span style={{ fontSize: '22px', fontWeight: 700, color: 'var(--color-text-main)', display: 'block', margin: '4px 0' }}>
                {avgTrainingDuration > 0 ? <CountUp end={avgTrainingDuration} decimals={1} suffix=" mins" duration={1000} /> : 'N/A'}
              </span>
              <p style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>Computed across all completed pipeline executions.</p>
            </div>

          </div>
        </div>

      </section>

    </div>
  );
};

export default ReportsView;
