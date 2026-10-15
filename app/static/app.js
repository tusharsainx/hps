// Hospital Bulk Processing System - Frontend Client

let currentFile = null;
let currentBatchId = null;
let activeWebSocket = null;
let timerInterval = null;
let startTime = null;

// DOM Elements
const dropzone = document.getElementById('csv-dropzone');
const fileInput = document.getElementById('csv-file-input');
const fileBanner = document.getElementById('file-banner');
const fileNameDisplay = document.getElementById('file-name-display');
const fileSizeDisplay = document.getElementById('file-size-display');
const btnClearFile = document.getElementById('btn-clear-file');
const btnValidate = document.getElementById('btn-validate');
const btnProcess = document.getElementById('btn-process');
const validationBox = document.getElementById('validation-box');
const validationTitle = document.getElementById('validation-title');
const validationDetails = document.getElementById('validation-details');

const apiStatusBadge = document.getElementById('api-status-badge');
const apiStatusText = document.getElementById('api-status-text');
const wsIndicator = document.getElementById('ws-indicator');
const wsText = document.getElementById('ws-text');

const dispBatchId = document.getElementById('disp-batch-id');
const dispBatchStatus = document.getElementById('disp-batch-status');
const dispBatchTime = document.getElementById('disp-batch-time');
const progressBarFill = document.getElementById('progress-bar-fill');
const progressPctText = document.getElementById('progress-percentage-text');
const progressCountsText = document.getElementById('progress-counts-text');

const statTotal = document.getElementById('stat-total');
const statProcessed = document.getElementById('stat-processed');
const statFailed = document.getElementById('stat-failed');
const statActivated = document.getElementById('stat-activated');

const batchActions = document.getElementById('batch-actions');
const btnResumeBatch = document.getElementById('btn-resume-batch');
const btnDeleteBatch = document.getElementById('btn-delete-batch');

const hospitalsTbody = document.getElementById('hospitals-tbody');
const jsonViewer = document.getElementById('json-viewer');
const btnCopyJson = document.getElementById('btn-copy-json');

// Sample Generators
const SAMPLES = {
  valid5: `name,address,phone
St. Jude Children's Research Hospital,262 Danny Thomas Pl Memphis TN,901-595-3300
Mayo Clinic Hospital,200 1st St SW Rochester MN,507-284-2511
Cleveland Clinic Main Campus,9500 Euclid Ave Cleveland OH,216-444-2200
Johns Hopkins Hospital,1800 Orleans St Baltimore MD,410-955-5000
Massachusetts General Hospital,55 Fruit St Boston MA,617-726-2000`,

  valid20: `name,address,phone
St. Jude Children's Research Hospital,262 Danny Thomas Pl Memphis TN,901-595-3300
Mayo Clinic Hospital,200 1st St SW Rochester MN,507-284-2511
Cleveland Clinic Main Campus,9500 Euclid Ave Cleveland OH,216-444-2200
Johns Hopkins Hospital,1800 Orleans St Baltimore MD,410-955-5000
Massachusetts General Hospital,55 Fruit St Boston MA,617-726-2000
UCLA Medical Center,757 Westwood Plaza Los Angeles CA,310-267-8000
Cedars-Sinai Medical Center,8700 Beverly Blvd Los Angeles CA,310-423-3277
New York-Presbyterian Hospital,525 E 68th St New York NY,212-746-5454
Northwestern Memorial Hospital,251 E Huron St Chicago IL,312-926-2000
Stanford Health Care,300 Pasteur Dr Stanford CA,650-723-4000
Mount Sinai Hospital,1 Gustave L Levy Pl New York NY,212-241-6500
Barnes-Jewish Hospital,1 Barnes Jewish Hospital Pl St. Louis MO,314-747-3000
Houston Methodist Hospital,6565 Fannin St Houston TX,713-790-3311
Brigham and Women's Hospital,75 Francis St Boston MA,617-732-5500
Vanderbilt University Medical Center,1211 Medical Center Dr Nashville TN,615-322-5000
Duke University Hospital,2301 Erwin Rd Durham NC,919-684-8111
Penn Presbyterian Medical Center,51 N 39th St Philadelphia PA,215-662-8000
Rush University Medical Center,1620 W Harrison St Chicago IL,312-942-5000
UPMC Presbyterian Shadyside,200 Lothrop St Pittsburgh PA,412-647-2345
NYU Langone Hospitals,550 1st Ave New York NY,212-263-7300`,

  invalid25: `name,address,phone
${Array.from({ length: 25 }, (_, i) => `Hospital #${i + 1},${100 + i} Medical Center Way,555-01${String(i).padStart(2, '0')}`).join('\n')}`,

  invalidHeaders: `hospital_title,street_location,telephone
Metro Hospital,100 City Parkway,555-1234
City Clinic,200 Elm Street,555-5678`
};

// Check Health on load
async function checkHealth() {
  try {
    const res = await fetch('/health');
    const data = await res.json();
    if (data.upstream_api_connected) {
      apiStatusBadge.querySelector('.status-dot').className = 'status-dot connected';
      apiStatusText.textContent = 'Upstream API Connected';
    } else {
      apiStatusText.textContent = 'Upstream API Unreachable';
    }
  } catch (err) {
    apiStatusText.textContent = 'Service Offline';
  }
}

// File Selection Handlers
function setFile(file) {
  currentFile = file;
  fileNameDisplay.textContent = file.name;
  fileSizeDisplay.textContent = `${(file.size / 1024).toFixed(1)} KB`;
  fileBanner.classList.remove('hidden');
  btnValidate.disabled = false;
  btnProcess.disabled = false;
  validationBox.classList.add('hidden');
}

function clearFile() {
  currentFile = null;
  fileInput.value = '';
  fileBanner.classList.add('hidden');
  btnValidate.disabled = true;
  btnProcess.disabled = true;
  validationBox.classList.add('hidden');
}

fileInput.addEventListener('change', (e) => {
  if (e.target.files && e.target.files[0]) {
    setFile(e.target.files[0]);
  }
});

btnClearFile.addEventListener('click', clearFile);

// Drag & Drop
['dragenter', 'dragover'].forEach(eventName => {
  dropzone.addEventListener(eventName, (e) => {
    e.preventDefault();
    dropzone.classList.add('dragover');
  });
});

['dragleave', 'drop'].forEach(eventName => {
  dropzone.addEventListener(eventName, (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
  });
});

dropzone.addEventListener('drop', (e) => {
  if (e.dataTransfer.files && e.dataTransfer.files[0]) {
    setFile(e.dataTransfer.files[0]);
  }
});

// Quick Sample Loaders
function loadSampleFile(content, filename) {
  const blob = new Blob([content], { type: 'text/csv' });
  const file = new File([blob], filename, { type: 'text/csv' });
  setFile(file);
}

document.getElementById('btn-load-valid-5').addEventListener('click', () => {
  loadSampleFile(SAMPLES.valid5, 'valid_hospitals_5.csv');
});

document.getElementById('btn-load-valid-20').addEventListener('click', () => {
  loadSampleFile(SAMPLES.valid20, 'valid_hospitals_20.csv');
});

document.getElementById('btn-load-invalid-25').addEventListener('click', () => {
  loadSampleFile(SAMPLES.invalid25, 'invalid_exceed_limit_25.csv');
});

document.getElementById('btn-load-invalid-headers').addEventListener('click', () => {
  loadSampleFile(SAMPLES.invalidHeaders, 'invalid_headers.csv');
});

// Pre-validate CSV
btnValidate.addEventListener('click', async () => {
  if (!currentFile) return;

  btnValidate.disabled = true;
  btnValidate.querySelector('.btn-text').textContent = 'Validating...';

  const formData = new FormData();
  formData.append('file', currentFile);

  try {
    const res = await fetch('/hospitals/bulk/validate', {
      method: 'POST',
      body: formData,
    });
    const data = await res.json();

    validationBox.classList.remove('hidden');
    validationBox.className = data.valid ? 'validation-box valid' : 'validation-box invalid';
    validationTitle.textContent = data.valid ? '✓ CSV Validation Passed' : '✗ CSV Validation Errors Detected';

    if (data.valid) {
      validationDetails.innerHTML = `<p>${data.message}</p><p class="text-secondary">Rows detected: <strong>${data.total_rows}</strong></p>`;
    } else {
      const errList = data.errors.map(err => `<li>${err.row ? `Row ${err.row}: ` : ''}${err.message}</li>`).join('');
      validationDetails.innerHTML = `<ul style="padding-left: 18px; margin-top: 6px;">${errList}</ul>`;
    }
  } catch (err) {
    validationBox.classList.remove('hidden');
    validationBox.className = 'validation-box invalid';
    validationTitle.textContent = 'Validation Request Failed';
    validationDetails.textContent = err.message;
  } finally {
    btnValidate.disabled = false;
    btnValidate.querySelector('.btn-text').textContent = 'Pre-Validate CSV';
  }
});

// Timer utility
function startTimer() {
  if (timerInterval) clearInterval(timerInterval);
  startTime = Date.now();
  timerInterval = setInterval(() => {
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(2);
    dispBatchTime.textContent = `${elapsed}s`;
  }, 100);
}

function stopTimer(finalSeconds) {
  if (timerInterval) clearInterval(timerInterval);
  if (finalSeconds !== undefined) {
    dispBatchTime.textContent = `${Number(finalSeconds).toFixed(2)}s`;
  }
}

// Status Polling Engine
let pollInterval = null;

function pollBatch(batchId) {
  if (pollInterval) clearInterval(pollInterval);
  wsIndicator.querySelector('.ws-dot').className = 'ws-dot connected';
  wsText.textContent = 'Polling Status';

  pollInterval = setInterval(async () => {
    try {
      const res = await fetch(`/hospitals/bulk/${batchId}`);
      if (!res.ok) return;
      const data = await res.json();
      updateBatchUI(data);
      if (['activated', 'completed', 'partially_failed', 'failed'].includes(data.status)) {
        clearInterval(pollInterval);
        wsIndicator.querySelector('.ws-dot').className = 'ws-dot';
        wsText.textContent = 'Batch Finalized';
      }
    } catch (e) {
      console.error('Polling error:', e);
    }
  }, 500);
}

// Update UI elements based on batch progress
function updateBatchUI(batch) {
  currentBatchId = batch.batch_id;
  dispBatchId.textContent = batch.batch_id;
  dispBatchStatus.textContent = batch.status;

  // Set status pill styling
  if (batch.status === 'activated') {
    dispBatchStatus.className = 'meta-value badge status-created-and-activated';
  } else if (batch.status === 'partially_failed' || batch.status === 'failed') {
    dispBatchStatus.className = 'meta-value badge status-failed';
  } else {
    dispBatchStatus.className = 'meta-value badge status-pending';
  }

  // Progress Bar
  const pct = batch.progress_percentage || 0;
  progressBarFill.style.width = `${pct}%`;
  progressPctText.textContent = `${pct.toFixed(0)}%`;

  const doneCount = (batch.processed_hospitals || 0) + (batch.failed_hospitals || 0);
  progressCountsText.textContent = `${doneCount} / ${batch.total_hospitals || 0} Processed`;

  // Mini Stats
  statTotal.textContent = batch.total_hospitals || 0;
  statProcessed.textContent = batch.processed_hospitals || 0;
  statFailed.textContent = batch.failed_hospitals || 0;
  statActivated.textContent = batch.batch_activated ? 'Yes ✓' : 'No';

  // Resume / Rollback buttons visibility
  if (batch.failed_hospitals > 0 && !batch.batch_activated) {
    batchActions.classList.remove('hidden');
  } else {
    batchActions.classList.add('hidden');
  }

  // Update Hospital Table
  if (batch.hospitals && batch.hospitals.length > 0) {
    renderHospitalsTable(batch.hospitals);
  }

  // If completed / activated, stop timer
  if (batch.status === 'activated' || batch.status === 'completed' || batch.status === 'partially_failed' || batch.status === 'failed') {
    if (batch.processing_time_seconds) {
      stopTimer(batch.processing_time_seconds);
    }
  }
}

// Render Table Rows
function renderHospitalsTable(items) {
  hospitalsTbody.innerHTML = '';
  items.forEach(h => {
    const tr = document.createElement('tr');
    
    let statusBadgeClass = 'status-pending';
    if (h.status === 'created_and_activated') statusBadgeClass = 'status-created-and-activated';
    else if (h.status === 'created') statusBadgeClass = 'status-created';
    else if (h.status === 'failed') statusBadgeClass = 'status-failed';

    tr.innerHTML = `
      <td class="mono">${h.row}</td>
      <td class="mono">${h.hospital_id !== null ? h.hospital_id : '<span class="text-muted">—</span>'}</td>
      <td style="font-weight: 500;">${h.name}</td>
      <td>${h.address || '—'}</td>
      <td>${h.phone || '<span class="text-muted">—</span>'}</td>
      <td>
        <span class="row-status-badge ${statusBadgeClass}">${h.status}</span>
        ${h.error ? `<div style="font-size: 0.72rem; color: #f87171; margin-top: 2px;">${h.error}</div>` : ''}
      </td>
    `;
    hospitalsTbody.appendChild(tr);
  });
}

// Execute Bulk Upload
btnProcess.addEventListener('click', async () => {
  if (!currentFile) return;

  btnProcess.disabled = true;
  btnProcess.querySelector('.btn-text').textContent = 'Processing Batch...';
  validationBox.classList.add('hidden');

  startTimer();
  hospitalsTbody.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 24px;">Submitting batch to processing engine...</td></tr>';

  const formData = new FormData();
  formData.append('file', currentFile);

  try {
    // Standard synchronous call awaiting complete response
    const res = await fetch('/hospitals/bulk', {
      method: 'POST',
      body: formData,
    });

    const data = await res.json();

    if (!res.ok) {
      stopTimer();
      validationBox.classList.remove('hidden');
      validationBox.className = 'validation-box invalid';
      validationTitle.textContent = `Upload Error (${res.status})`;
      validationDetails.textContent = data.message || data.detail?.message || JSON.stringify(data);
      jsonViewer.textContent = JSON.stringify(data, null, 2);
      return;
    }

    // Success response
    updateBatchUI(data);
    stopTimer(data.processing_time_seconds);
    jsonViewer.textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    stopTimer();
    validationBox.classList.remove('hidden');
    validationBox.className = 'validation-box invalid';
    validationTitle.textContent = 'Request Exception';
    validationDetails.textContent = err.message;
  } finally {
    btnProcess.disabled = false;
    btnProcess.querySelector('.btn-text').textContent = 'Execute Bulk Upload';
  }
});

// Resume Batch Action
btnResumeBatch.addEventListener('click', async () => {
  if (!currentBatchId) return;

  btnResumeBatch.disabled = true;
  btnResumeBatch.textContent = 'Resuming...';
  startTimer();

  try {
    const res = await fetch(`/hospitals/bulk/${currentBatchId}/resume`, {
      method: 'POST',
    });
    const data = await res.json();
    updateBatchUI(data);
    stopTimer(data.processing_time_seconds);
    jsonViewer.textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    alert(`Resume failed: ${err.message}`);
  } finally {
    btnResumeBatch.disabled = false;
    btnResumeBatch.textContent = '↺ Resume Failed Batch';
  }
});

// Delete/Rollback Batch Action
btnDeleteBatch.addEventListener('click', async () => {
  if (!currentBatchId) return;
  if (!confirm(`Are you sure you want to rollback/delete batch ${currentBatchId} from upstream?`)) return;

  try {
    const res = await fetch(`/hospitals/bulk/${currentBatchId}`, {
      method: 'DELETE',
    });
    const data = await res.json();
    alert(`Rollback successful: ${JSON.stringify(data)}`);
    dispBatchStatus.textContent = 'deleted';
  } catch (err) {
    alert(`Delete failed: ${err.message}`);
  }
});

// Copy JSON
btnCopyJson.addEventListener('click', () => {
  navigator.clipboard.writeText(jsonViewer.textContent);
  btnCopyJson.textContent = 'Copied!';
  setTimeout(() => { btnCopyJson.textContent = 'Copy JSON'; }, 1500);
});

// Initialize on page load
checkHealth();
