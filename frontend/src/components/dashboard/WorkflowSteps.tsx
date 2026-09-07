import React from 'react';

export const WorkflowSteps: React.FC = () => {
  return (
    <div className="workflow-card">
      <div className="steps-container">
        {/* Step 1: Upload Image */}
        <div className="step-item">
          <div className="step-icon-wrapper">
            <div className="step-circle-icon">
              {/* Cloud with Up-Arrow Vector: #317827 */}
              <svg width="28" height="28" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path
                  d="M8.5 19.5 C5.5 19.5 4 17.5 4 15 C4 12.8 5.6 11 7.8 10.8 C8.4 7.5 11.2 5 14.5 5 C18.2 5 21.2 7.8 21.5 11.5 C23.5 11.8 25 13.5 25 15.5 C25 17.8 23.2 19.5 21 19.5"
                  stroke="#317827"
                  strokeWidth="2.2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M14.5 12 V22 M11 15.5 L14.5 12 L18 15.5"
                  stroke="#317827"
                  strokeWidth="2.2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>
            <div className="step-badge">1</div>
          </div>
          <h3 className="step-title">Upload Image</h3>
          <p className="step-desc">Capture/upload images from your device.</p>
        </div>

        {/* Dotted Arrow 1: #ADD192 */}
        <div className="step-connector">
          <svg width="56" height="14" viewBox="0 0 56 14" fill="none">
            <path
              d="M2 7 H48 M42 2 L49 7 L42 12"
              stroke="#add192"
              strokeWidth="2"
              strokeDasharray="4 4"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>

        {/* Step 2: Annotation */}
        <div className="step-item">
          <div className="step-icon-wrapper">
            <div className="step-circle-icon">
              {/* Pencil / Annotation Tool Vector: #317827 */}
              <svg width="28" height="28" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path
                  d="M19.5 5.5 L22.5 8.5 L9.5 21.5 H6.5 V18.5 L19.5 5.5 Z"
                  stroke="#317827"
                  strokeWidth="2.2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M16.5 8.5 L19.5 11.5"
                  stroke="#317827"
                  strokeWidth="2.2"
                  strokeLinecap="round"
                />
              </svg>
            </div>
            <div className="step-badge">2</div>
          </div>
          <h3 className="step-title">Annotation</h3>
          <p className="step-desc">Annotate objects in the image.</p>
        </div>

        {/* Dotted Arrow 2: #ADD192 */}
        <div className="step-connector">
          <svg width="56" height="14" viewBox="0 0 56 14" fill="none">
            <path
              d="M2 7 H48 M42 2 L49 7 L42 12"
              stroke="#add192"
              strokeWidth="2"
              strokeDasharray="4 4"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>

        {/* Step 3: Select Category */}
        <div className="step-item">
          <div className="step-icon-wrapper">
            <div className="step-circle-icon">
              {/* Category Tag Vector: #317827 */}
              <svg width="28" height="28" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path
                  d="M13.5 5 H7.5 C6.4 5 5.5 5.9 5.5 7 V13 C5.5 13.5 5.7 14.1 6.1 14.5 L15.5 23.9 C16.3 24.7 17.6 24.7 18.4 23.9 L23.9 18.4 C24.7 17.6 24.7 16.3 23.9 15.5 L14.5 6.1 C14.1 5.7 13.5 5.5 13.5 5 Z"
                  stroke="#317827"
                  strokeWidth="2.2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <circle cx="9.5" cy="9" r="1.5" fill="#317827" />
              </svg>
            </div>
            <div className="step-badge">3</div>
          </div>
          <h3 className="step-title">Select Category</h3>
          <p className="step-desc">Select the appropriate category.</p>
        </div>
      </div>
    </div>
  );
};
