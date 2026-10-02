// ═══════════════════════════════════════════════════════════════════════════════
// RoleMatcherAi — Main Script
// ═══════════════════════════════════════════════════════════════════════════════

const API_BASE = '/api';

async function apiFetch(url, options = {}) {
    const headers = { ...(options.headers || {}) };
    const apiKey = localStorage.getItem('aiApiKey');
    if (apiKey) headers['X-API-Key'] = apiKey;
    const model = localStorage.getItem('aiModel');
    if (model) headers['X-Model'] = model;
    const res = await fetch(url, { ...options, headers });
    if (!res.ok) {
        let msg = `Request failed (${res.status})`;
        try {
            const body = await res.json();
            msg = body.detail || body.error || msg;
        } catch (_) { /* non-JSON error */ }
        throw new Error(msg);
    }
    return res;
}

let resumeData = null;
let jobsData = [];
let careerPlan = null;

let clHistory = [];

let tailoredResume = null;

function esc(value) {
    return String(value == null ? '' : value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// ── Utility ─────────────────────────────────────────────────────────────────
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `<i class="fas fa-${type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : 'info-circle'}"></i> ${message}`;
    container.appendChild(toast);
    setTimeout(() => { toast.style.animation = 'toastIn 0.3s ease reverse forwards'; setTimeout(() => toast.remove(), 300); }, 3500);
}

function showLoading(text = 'Loading...') {
    let overlay = document.querySelector('.loading-overlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.className = 'loading-overlay';
        overlay.innerHTML = '<div class="loader"><div class="loader-spinner"></div><p></p></div>';
        document.body.appendChild(overlay);
    }
    overlay.querySelector('p').textContent = text;
    overlay.style.display = 'flex';
}

function hideLoading() {
    const overlay = document.querySelector('.loading-overlay');
    if (overlay) overlay.style.display = 'none';
}

// ── Navigation ──────────────────────────────────────────────────────────────
function navigateTo(section) {
    const overlay = document.getElementById('api-key-overlay');
    if (section === 'settings') {
        if (overlay) overlay.classList.add('hidden');
    } else if (!isApiKeyConfigured()) {
        showToast('Please set your API key and model in Settings first', 'error');
        if (overlay) overlay.classList.remove('hidden');
        section = 'settings';
    }
    const target = document.getElementById(`section-${section}`);
    if (!target) return;
    document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
    document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
    target.classList.add('active');
    const navLink = document.querySelector(`.nav-link[data-section="${section}"]`);
    if (navLink) navLink.classList.add('active');
    window.scrollTo({ top: 0, behavior: 'smooth' });
    const navCenter = document.querySelector('.nav-center');
    if (navCenter) navCenter.classList.remove('open');
    const hamburger = document.getElementById('hamburger-btn');
    if (hamburger) hamburger.classList.remove('active');
}

// ── Settings ────────────────────────────────────────────────────────────────
function isApiKeyConfigured() {
    return !!(localStorage.getItem('aiApiKey') && localStorage.getItem('aiModel'));
}

function checkApiKeyRequired() {
    const overlay = document.getElementById('api-key-overlay');
    if (!overlay) return;
    if (isApiKeyConfigured()) {
        overlay.classList.add('hidden');
    } else {
        overlay.classList.remove('hidden');
    }
}
function getSelectedModel() {
    const select = document.getElementById('settings-model');
    if (select.value === '__custom__') {
        return document.getElementById('settings-custom-model').value.trim() || '';
    }
    return select.value;
}

function syncCustomModelInput() {
    const select = document.getElementById('settings-model');
    const isCustom = select.value === '__custom__';
    document.getElementById('settings-custom-model-group').classList.toggle('hidden', !isCustom);
    if (isCustom) document.getElementById('settings-custom-model').focus();
}

function initSettings() {
    // Model save
    document.getElementById('settings-save-model').addEventListener('click', () => {
        const provider = document.getElementById('settings-provider').value;
        const model = getSelectedModel();
        const apiKey = document.getElementById('settings-api-key').value;
        if (!model) return showToast('Please enter a model name', 'error');
        localStorage.setItem('aiProvider', provider);
        localStorage.setItem('aiModel', model);
        if (apiKey) localStorage.setItem('aiApiKey', apiKey);
        showToast('Model settings saved', 'success');
        checkApiKeyRequired();
    });

    // Load saved model
    const savedProvider = localStorage.getItem('aiProvider');
    if (savedProvider) document.getElementById('settings-provider').value = savedProvider;
    const savedApiKey = localStorage.getItem('aiApiKey');
    if (savedApiKey) document.getElementById('settings-api-key').value = savedApiKey;
    const savedModel = localStorage.getItem('aiModel');
    const modelSelect = document.getElementById('settings-model');
    if (savedModel) {
        const isKnown = Array.from(modelSelect.options).some(o => o.value === savedModel);
        if (isKnown) {
            modelSelect.value = savedModel;
        } else {
            modelSelect.value = '__custom__';
            document.getElementById('settings-custom-model').value = savedModel;
            document.getElementById('settings-custom-model-group').classList.remove('hidden');
        }
    }

    // Provider change updates models
    document.getElementById('settings-provider').addEventListener('change', (e) => {
        const models = {
            gemini: [['gemini/gemini-2.5-flash', 'Gemini 2.5 Flash'], ['gemini/gemini-2.5-flash-lite', 'Gemini 2.5 Flash Lite']],
            openai: [['openai/gpt-4o-mini', 'GPT-4o Mini'], ['openai/gpt-4o', 'GPT-4o']],
            groq: [['groq/llama-3.3-70b-versatile', 'Llama 3.3 70B']],
            deepseek: [['deepseek/deepseek-chat', 'DeepSeek V3']],
            qwen: [['qwen/qwen-turbo', 'Qwen Turbo']],
        };
        const modelSelect = document.getElementById('settings-model');
        modelSelect.innerHTML = (models[e.target.value] || []).map(([v, l]) => `<option value="${v}">${l}</option>`).join('') + '<option value="__custom__">Custom (type exact model name)</option>';
        document.getElementById('settings-custom-model-group').classList.add('hidden');
    });

    // Custom model toggle
    document.getElementById('settings-model').addEventListener('change', syncCustomModelInput);
}

// ── Navigation Links ────────────────────────────────────────────────────────
function initNavigation() {
    document.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', () => navigateTo(link.dataset.section));
    });

    const hamburger = document.getElementById('hamburger-btn');
    hamburger.addEventListener('click', () => {
        hamburger.classList.toggle('active');
        document.querySelector('.nav-center').classList.toggle('open');
    });
}

// ── Resume ──────────────────────────────────────────────────────────────────
function initResume() {
    const zone = document.getElementById('upload-zone');
    const input = document.getElementById('resume-file-input');
    const btn = document.getElementById('upload-btn');

    btn.addEventListener('click', (e) => { e.stopPropagation(); input.click(); });
    zone.addEventListener('click', () => input.click());

    zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('drag-over'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
    zone.addEventListener('drop', (e) => {
        e.preventDefault();
        zone.classList.remove('drag-over');
        if (e.dataTransfer.files.length) uploadResume(e.dataTransfer.files[0]);
    });

    input.addEventListener('change', (e) => {
        if (e.target.files.length) uploadResume(e.target.files[0]);
    });

    document.getElementById('delete-resume-btn').addEventListener('click', deleteResume);
}

async function uploadResume(file) {
    if (file.type !== 'application/pdf') {
        showToast('Please upload a PDF file', 'error');
        return;
    }
    showLoading('Uploading resume...');
    try {
        const formData = new FormData();
        formData.append('file', file);
        const data = await apiFetch(`${API_BASE}/resumes`, {
            method: 'POST',
            body: formData,
        }).then(r => r.json());
        hideLoading();
        resumeData = data;
        document.getElementById('upload-zone').classList.add('hidden');
        document.getElementById('resume-card').classList.remove('hidden');
        document.getElementById('resume-tips').classList.add('hidden');
        document.getElementById('resume-next-steps').classList.remove('hidden');
        document.getElementById('resume-filename').textContent = file.name;
        document.getElementById('resume-words').textContent = data.word_count || '—';
        document.getElementById('resume-sections').textContent = data.sections_found || '—';
        if (data.ats_score) {
            const atsEl = document.getElementById('resume-ats-score');
            if (atsEl) atsEl.textContent = `${data.ats_score}%`;
        }
        const profileEl = document.getElementById('resume-profile');
        if (data.summary) {
            profileEl.textContent = data.summary;
        } else {
            profileEl.innerHTML = `<div class="resume-profile-empty"><i class="fas fa-sparkles"></i><p>Resume parsed successfully. Use the actions above to get matched jobs, ATS scores, or practice interviews.</p></div>`;
        }
        showToast('Resume uploaded successfully', 'success');
        updateDashboardProgress();
    } catch (err) {
        hideLoading();
        showToast('Upload failed: ' + err.message, 'error');
    }
}

function deleteResume() {
    resumeData = null;
    document.getElementById('upload-zone').classList.remove('hidden');
    document.getElementById('resume-card').classList.add('hidden');
    document.getElementById('resume-tips').classList.remove('hidden');
    document.getElementById('resume-next-steps').classList.add('hidden');
    document.getElementById('resume-profile').innerHTML = `<div class="resume-profile-empty"><i class="fas fa-sparkles"></i><p>Upload complete. Your resume has been parsed and is ready for analysis.</p><span>Use the actions below to get matched jobs, ATS scores, or practice interviews.</span></div>`;
    showToast('Resume removed', 'info');
}

// ── Jobs ────────────────────────────────────────────────────────────────────
let jobsMode = 'manual';

function initJobs() {
    document.getElementById('search-jobs-btn').addEventListener('click', () => {
        if (jobsMode === 'resume') searchResumeJobs();
        else searchJobs();
    });
    document.getElementById('jobs-mode-manual').addEventListener('click', () => setJobsMode('manual'));
    document.getElementById('jobs-mode-resume').addEventListener('click', () => setJobsMode('resume'));
}

function setJobsMode(mode) {
    jobsMode = mode;
    document.querySelectorAll('#section-jobs .cl-mode-btn').forEach(b => b.classList.toggle('active', b.dataset.mode === mode));
    document.getElementById('jobs-manual-form').classList.toggle('hidden', mode !== 'manual');
    document.getElementById('jobs-resume-hint').classList.toggle('hidden', mode !== 'resume');
    if (mode === 'resume') {
        const status = document.getElementById('jobs-resume-status');
        if (resumeData?.resume_id) {
            status.textContent = 'Your resume is ready to use.';
            status.style.color = 'var(--accent-primary)';
        } else {
            status.textContent = 'Upload a resume first, or use Manual Search mode.';
            status.style.color = '#ef4444';
        }
    }
}

async function searchJobs() {
    const keywords = document.getElementById('job-keywords').value;
    const location = document.getElementById('job-location').value.trim() || 'All Countries';
    if (!keywords.trim()) return showToast('Enter a job title or keywords', 'error');
    showLoading('Searching jobs...');
    try {
        const data = await apiFetch(`${API_BASE}/jobs/search`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target_role: keywords.trim(), location }),
        }).then(r => r.json());
        hideLoading();
        jobsData = (data.jobs || []).slice(0, 15);
        renderJobs();
        if (jobsData.length === 0) {
            const locText = location.toLowerCase() === 'all countries' ? '' : ` in ${location}`;
            showToast(`No jobs found for this role${locText}. Try a different location or broaden your search.`, 'info');
        } else {
            const locText = location.toLowerCase() === 'all countries' ? '' : ` in ${location}`;
            showToast(`Found ${jobsData.length} jobs${locText}`, 'success');
        }
    } catch (err) {
        hideLoading();
        showToast(err.message || 'Search failed', 'error');
    }
}

async function searchResumeJobs() {
    if (!resumeData?.resume_id) return showToast('Upload a resume first', 'error');
    const location = document.getElementById('job-location').value.trim() || 'All Countries';
    showLoading('Matching jobs to your resume...');
    try {
        const data = await apiFetch(`${API_BASE}/jobs/search`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ resume_id: resumeData.resume_id, location }),
        }).then(r => r.json());
        hideLoading();
        jobsData = (data.jobs || []).slice(0, 15);
        renderJobs();
        if (jobsData.length === 0) {
            const locText = location.toLowerCase() === 'all countries' ? '' : ` in ${location}`;
            showToast(`No matching jobs found for your profile${locText}. Try a different location or broaden your search.`, 'info');
        } else {
            const locText = location.toLowerCase() === 'all countries' ? '' : ` in ${location}`;
            showToast(`Found ${jobsData.length} matched jobs${locText}`, 'success');
        }
    } catch (err) {
        hideLoading();
        showToast(err.message || 'Matching failed', 'error');
    }
}

function quickJobSearch(term) {
    if (jobsMode !== 'manual') setJobsMode('manual');
    document.getElementById('job-keywords').value = term;
    searchJobs();
}

function renderJobs() {
    const list = document.getElementById('jobs-list');
    const empty = document.getElementById('jobs-empty');
    if (!jobsData.length) {
        list.innerHTML = '';
        empty.classList.remove('hidden');
        return;
    }
    empty.classList.add('hidden');
    list.innerHTML = jobsData.map((job, i) => {
        const match = job.match || {};
        const score = match.overall_score;
        // Score can be 0-1 (from pipeline) or 0-100 (from ATS) — normalize to 0-100
        const scorePct = score != null ? (score > 1 ? Math.round(score) : Math.round(score * 100)) : null;
        const missing = (match.missing_skills || []).slice(0, 4);
        const source = job.source || '';
        const desc = job.description || '';
        const showMeta = (job.location || job.employment_type || job.remote || job.salary_max);
        return `
        <div class="job-card glass-card">
            <div class="job-card-head">
                <div class="job-icon"><i class="fas fa-briefcase"></i></div>
                <div class="job-body">
                    <div class="job-title-row">
                        <div class="job-title">${job.title || 'Untitled'}</div>
                        ${source ? `<span class="job-source">${source}</span>` : ''}
                    </div>
                    <div class="job-company"><i class="fas fa-building"></i> ${job.company || 'Unknown'}</div>
                </div>
                ${scorePct != null ? `
                <div class="job-score-badge ${scorePct >= 60 ? 'high' : scorePct >= 30 ? 'mid' : 'low'}">
                    <div class="job-score-num">${scorePct}%</div>
                    <div class="job-score-label">match</div>
                </div>` : ''}
            </div>
            ${showMeta ? `
            <div class="job-meta">
                ${job.location ? `<span class="job-meta-pill"><i class="fas fa-map-marker-alt"></i> ${job.location}</span>` : ''}
                ${job.employment_type ? `<span class="job-meta-pill"><i class="fas fa-clock"></i> ${job.employment_type}</span>` : ''}
                ${job.remote ? '<span class="job-meta-pill"><i class="fas fa-globe"></i> Remote</span>' : ''}
                ${job.salary_max ? `<span class="job-meta-pill"><i class="fas fa-dollar-sign"></i> ${job.salary_min ? '$' + job.salary_min + ' - ' : ''}$${job.salary_max}</span>` : ''}
            </div>` : ''}
            ${scorePct != null && scorePct >= 0 ? `
            <div class="job-match-bar">
                <div class="job-match-track"><div class="job-match-fill ${scorePct >= 60 ? 'high' : scorePct >= 30 ? 'mid' : 'low'}" style="width:${scorePct}%"></div></div>
                <span class="job-match-label ${scorePct >= 60 ? 'high' : scorePct >= 30 ? 'mid' : 'low'}">${scorePct}% match</span>
            </div>` : ''}
            ${missing.length ? `
            <div class="job-missing">
                <span class="job-missing-label">Missing skills:</span>
                ${missing.map(s => `<span class="job-missing-chip">${s}</span>`).join('')}
            </div>` : ''}
            ${desc ? `<div class="job-desc">${desc.slice(0, 200)}${desc.length > 200 ? '...' : ''}</div>` : ''}
            <div class="job-actions">
                ${resumeData?.resume_id ? `<button class="btn btn-primary btn-sm" onclick="analyzeJob(${i})"><i class="fas fa-clipboard-check"></i> ATS</button>` : `<button class="btn btn-primary btn-sm" onclick="showToast('Upload a resume first to run ATS analysis', 'info')" title="Upload a resume first"><i class="fas fa-clipboard-check"></i> ATS</button>`}
                ${resumeData?.resume_id ? `<button class="btn btn-tailor btn-sm" onclick="tailorResume(${i})"><i class="fas fa-wand-magic-sparkles"></i> AI Resume Builder</button>` : `<button class="btn btn-tailor btn-sm" onclick="showToast('Upload a resume first to build your AI resume', 'info')" title="Upload a resume first"><i class="fas fa-wand-magic-sparkles"></i> AI Resume Builder</button>`}
                <a class="btn btn-primary btn-sm job-apply-link" href="${job.source_url || `https://www.google.com/search?q=${encodeURIComponent((job.title || '') + ' ' + (job.company || '') + ' job apply')}`}" target="_blank" rel="noopener"><i class="fas fa-external-link-alt"></i> Apply Now</a>
            </div>
        </div>
    `;
    }).join('');
}

async function analyzeJob(index) {
    const job = jobsData[index];
    if (!job) return;
    showLoading('Analyzing job match...');
    try {
        const jobId = job.id || job.match?.job_id || job.job_id;
        if (!jobId) { hideLoading(); return showToast('Job ID not found', 'error'); }
        const res = await apiFetch(`${API_BASE}/jobs/${jobId}/analyze`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ resume_id: resumeData?.resume_id || null }),
        });
        const data = await res.json();
        hideLoading();
        if (!res.ok) return showToast(data.error || 'Analysis failed', 'error');
        showToast('ATS analysis complete', 'success');
        const report = data.report || {};
        const existing = jobsData[index];
        existing.match = {
            ...(existing.match || {}),
            overall_score: report.overall_score != null ? report.overall_score / 100 : existing.match?.overall_score,
            missing_skills: report.missing_skills || existing.match?.missing_skills || [],
        };
        renderJobs();
        renderAtsModal(job, report);
    } catch (err) {
        hideLoading();
        showToast('Analysis failed', 'error');
    }
}

function renderAtsModal(job, report) {
    const modal = document.getElementById('ats-modal');
    const body = document.getElementById('ats-modal-body');
    const scores = [
        ['Overall Match', report.overall_score],
        ['Keywords', report.keyword_score],
        ['Skills', report.skill_score],
        ['Experience', report.experience_score],
        ['Semantic', report.semantic_score],
        ['Education', report.education_score],
    ].filter(([, v]) => v != null);
    // ATS scores are already 0-100, just round them
    const pct = v => Math.round(v || 0);

    let html = `
        <div class="ats-job-info">
            <div class="ats-job-title">${job.title || 'Untitled'}</div>
            <div class="ats-job-company">${job.company || 'Unknown'}</div>
        </div>
        <div class="ats-score-grid">`;
    scores.forEach(([label, val]) => {
        const p = pct(val);
        const cls = p >= 60 ? 'high' : p >= 30 ? 'mid' : 'low';
        html += `
        <div class="ats-score-item">
            <div class="ats-score-label">${label}</div>
            <div class="ats-score-ring ${cls}"><span>${p}%</span></div>
            <div class="ats-score-bar"><div class="ats-score-fill ${cls}" style="width:${p}%"></div></div>
        </div>`;
    });
    html += `</div>`;

    if (report.missing_keywords && report.missing_keywords.length) {
        html += `<div class="ats-section"><h4>Missing Keywords</h4><div class="ats-chips">${report.missing_keywords.slice(0, 15).map(k => `<span class="ats-chip">${k}</span>`).join('')}</div></div>`;
    }
    if (report.missing_skills && report.missing_skills.length) {
        html += `<div class="ats-section"><h4>Missing Skills</h4><div class="ats-chips">${report.missing_skills.slice(0, 15).map(k => `<span class="ats-chip">${k}</span>`).join('')}</div></div>`;
    }
    if (report.recommendations && report.recommendations.length) {
        html += `<div class="ats-section"><h4>Recommendations</h4><div class="ats-recs-markdown">${report.recommendations.map(r => window.marked ? marked.parse(r) : `<p>${r}</p>`).join('')}</div></div>`;
    }

    body.innerHTML = html;
    modal.classList.add('show');
}

function closeAtsModal() {
    document.getElementById('ats-modal').classList.remove('show');
}

// ── AI Resume Builder (job-specific resume optimiser) ────────────────────────

async function tailorResume(index) {
    const job = jobsData[index];
    if (!job) return;
    if (!resumeData?.resume_id) return showToast('Upload a resume first to build your AI resume', 'info');

    showLoading('Building your AI resume for this job...');
    try {
        const jobId = job.id || job.match?.job_id || job.job_id;
        const res = await apiFetch(`${API_BASE}/resume-optimizer/tailor`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                resume_id: resumeData.resume_id,
                job_id: jobId || null,
                job_title: job.title || '',
                company_name: job.company || '',
                job_description: job.description || '',
            }),
        });
        const data = await res.json();
        hideLoading();
        if (!res.ok) return showToast(data.detail || data.error || 'Could not build your resume', 'error');
        tailoredResume = data;
        renderTailorModal(data);
        showToast('AI resume built for this job', 'success');
    } catch (err) {
        hideLoading();
        showToast(err.message || 'Could not build your AI resume', 'error');
    }
}

function _humanDate(value) {
    const s = String(value || '').trim();
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
    if (m) {
        const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        const mi = parseInt(m[2], 10) - 1;
        return mi >= 0 && mi < 12 ? `${months[mi]} ${m[1]}` : m[1];
    }
    return s;
}

function _expRange(exp) {
    const start = _humanDate(exp.start_date);
    const now = exp.is_current || !exp.end_date;
    if (start && now) return `${start} – Present`;
    if (start && exp.end_date) return `${start} – ${_humanDate(exp.end_date)}`;
    return start || _humanDate(exp.end_date) || '';
}

function renderTailorModal(data) {
    const modal = document.getElementById('tailor-modal');
    const body = document.getElementById('tailor-modal-body');
    const o = data.optimized || {};
    const contact = o.contact || {};
    const contactBits = [contact.email, contact.phone, contact.linkedin, contact.github].filter(Boolean);
    const changes = o.changes || [];
    const matched = o.matched_keywords || [];
    const stripped = data.stripped || [];
    const experience = o.experience || [];
    const projects = o.projects || [];
    const education = o.education || [];
    const certs = o.certifications || [];

    let html = `
        <div class="ats-job-info">
            <div class="ats-job-title">${esc(o.target_role || data.job_title || 'AI Resume Builder')}</div>
            <div class="ats-job-company">${esc(data.company_name || '')}</div>
        </div>`;

    if (changes.length) {
        html += `<div class="ats-section"><h4><i class="fas fa-wand-magic-sparkles" style="color:var(--accent-primary)"></i> What changed</h4>
            <ul class="ats-recs">${changes.map(c => `<li>${esc(c)}</li>`).join('')}</ul></div>`;
    }

    if (matched.length) {
        html += `<div class="ats-section"><h4>Matched keywords (${matched.length})</h4>
            <div class="ats-chips">${matched.slice(0, 24).map(k => `<span class="ats-chip">${esc(k)}</span>`).join('')}</div></div>`;
    }

    if (stripped.length) {
        html += `<div class="ats-section"><h4><i class="fas fa-shield-halved" style="color:var(--accent-primary)"></i> Guardrails applied</h4>
            <ul class="ats-recs tailor-guard">${stripped.map(s => `<li>${esc(s)}</li>`).join('')}</ul></div>`;
    }

    html += `<div class="tailor-preview">`;
    if (contact.name) html += `<div class="tailor-preview-name">${esc(contact.name)}</div>`;
    if (contactBits.length) html += `<div class="tailor-preview-contact">${contactBits.map(esc).join(' &nbsp;•&nbsp; ')}</div>`;

    if (o.summary) {
        html += `<div class="tailor-preview-block"><h5>Professional Summary</h5><p>${esc(o.summary)}</p></div>`;
    }
    if ((o.skills || []).length) {
        html += `<div class="tailor-preview-block"><h5>Skills</h5><p>${o.skills.map(esc).join(' &nbsp;•&nbsp; ')}</p></div>`;
    }
    if (experience.length) {
        html += `<div class="tailor-preview-block"><h5>Professional Experience</h5>` + experience.map(e => `
            <div class="tailor-preview-exp">
                <div class="tailor-preview-exp-head">
                    <strong>${esc(e.title)}</strong>
                    <span>${esc(e.company)}</span>
                    <em>${esc(_expRange(e))}</em>
                </div>
                ${(e.location ? `<div class="tailor-preview-exp-loc">${esc(e.location)}</div>` : '')}
                <ul>${(e.bullets || []).map(b => `<li>${esc(b)}</li>`).join('')}</ul>
            </div>`).join('') + `</div>`;
    }
    if (projects.length) {
        html += `<div class="tailor-preview-block"><h5>Projects</h5>` + projects.map(p => `
            <div class="tailor-preview-exp">
                <div class="tailor-preview-exp-head">
                    <strong>${esc(p.name)}</strong>
                    ${(p.technologies || []).length ? `<em>${esc((p.technologies || []).join(', '))}</em>` : ''}
                </div>
                ${p.description ? `<p>${esc(p.description)}</p>` : ''}
                ${(p.bullets || []).length ? `<ul>${p.bullets.map(b => `<li>${esc(b)}</li>`).join('')}</ul>` : ''}
            </div>`).join('') + `</div>`;
    }
    if (education.length) {
        html += `<div class="tailor-preview-block"><h5>Education</h5>` + education.map(e => `
            <div class="tailor-preview-exp">
                <div class="tailor-preview-exp-head">
                    <strong>${esc([e.degree, e.field].filter(Boolean).join(' — ') || e.institution)}</strong>
                    <span>${esc(e.institution)}</span>
                    <em>${esc(_expRange(e))}</em>
                </div>
                ${e.gpa ? `<div class="tailor-preview-exp-loc">GPA: ${esc(e.gpa)}</div>` : ''}
            </div>`).join('') + `</div>`;
    }
    if (certs.length) {
        html += `<div class="tailor-preview-block"><h5>Certifications</h5><ul>${
            certs.map(c => `<li>${esc(c.name)}${[c.issuer, c.date_obtained].filter(Boolean).length ? ` — ${esc([c.issuer, c.date_obtained].filter(Boolean).join(', '))}` : ''}</li>`).join('')
        }</ul></div>`;
    }

    html += `</div>`;

    body.innerHTML = html;
    modal.classList.add('show');
    const dl = document.getElementById('tailor-download-btn');
    if (dl) dl.style.display = 'inline-flex';
}

function closeTailorModal() {
    document.getElementById('tailor-modal').classList.remove('show');
}

async function downloadTailoredResume() {
    if (!tailoredResume?.optimized_id) return showToast('Build your AI resume first', 'info');
    showToast('Preparing DOCX...', 'info');
    try {
        const headers = {};
        const apiKey = localStorage.getItem('aiApiKey');
        if (apiKey) headers['X-API-Key'] = apiKey;
        const model = localStorage.getItem('aiModel');
        if (model) headers['X-Model'] = model;

        const res = await fetch(`${API_BASE}/resume-optimizer/${tailoredResume.optimized_id}/download`, { headers });
        if (!res.ok) {
            let msg = 'Download failed';
            try { msg = (await res.json()).detail || msg; } catch (_) { }
            throw new Error(msg);
        }
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = tailoredResume.filename || 'tailored-resume.docx';
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 5000);
        showToast('DOCX downloaded', 'success');
    } catch (err) {
        showToast(err.message || 'Download failed', 'error');
    }
}

// ── PDF export for the AI Resume Builder ────────────────────────────────────

function _pdfSafe(value) {
    return String(value == null ? '' : value)
        .replace(/[\u2018\u2019\u2032]/g, "'")
        .replace(/[\u201C\u201D]/g, '"')
        .replace(/[\u2013\u2014\u2212]/g, '-')
        .replace(/[\u2022\u25AA\u2023\u25CF]/g, '-')
        .replace(/\u2026/g, '...')
        .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, ' ')
        .replace(/[^\u0020-\u00FF]/g, '?');
}

function downloadTailoredPdf() {
    if (!tailoredResume?.optimized_id) return showToast('Build your AI resume first', 'info');
    if (!window.jspdf || !window.jspdf.jsPDF) {
        return showToast('PDF library is not loaded. Please refresh the page.', 'error');
    }

    try {
        showToast('Generating PDF...', 'info');
        const o = tailoredResume.optimized || {};
        const contact = (o.contact && typeof o.contact === 'object') ? o.contact : {};
        const { jsPDF } = window.jspdf;
        const pdf = new jsPDF('p', 'mm', 'a4');

        const pageW = 210, margin = 16, contentW = pageW - margin * 2, bottom = 297 - 18;
        const ACCENT = [46, 158, 110];
        const HEAD = [17, 24, 39];
        const BODY = [55, 65, 81];
        const MUTED = [107, 114, 128];
        const RULE = [209, 213, 219];
        const safe = _pdfSafe;
        let y = margin;

        const obj = (v) => (v && typeof v === 'object') ? v : {};
        const str = (v) => (v == null ? '' : String(v)).trim();
        const arr = (v) => Array.isArray(v) ? v : (v ? [v] : []);

        const ink = (c) => pdf.setTextColor(c[0], c[1], c[2]);
        const need = (h) => { if (y + h > bottom) { pdf.addPage(); y = margin; } };
        const rule = (after) => {
            pdf.setDrawColor(RULE[0], RULE[1], RULE[2]);
            pdf.setLineWidth(0.3);
            pdf.line(margin, y, pageW - margin, y);
            y += after;
        };

        const sectionTitle = (title) => {
            if (!str(title)) return;
            need(18);
            pdf.setFont('helvetica', 'bold');
            pdf.setFontSize(11);
            ink(ACCENT);
            pdf.text(safe(str(title)).toUpperCase(), margin, y);
            y += 4.8;
            rule(5.5);
            pdf.setFont('helvetica', 'normal');
        };

        const para = (text, size = 10, color = BODY, gap = 2.5, indent = 0) => {
            if (!str(text)) return;
            pdf.setFont('helvetica', 'normal');
            pdf.setFontSize(size);
            ink(color);
            const lines = pdf.splitTextToSize(safe(str(text)), contentW - indent);
            const lh = size * 0.46 + 0.6;
            need(lines.length * lh + gap);
            pdf.text(lines, margin + indent, y);
            y += lines.length * lh + gap;
        };

        const bulletLine = (text, indent = 0) => {
            if (!str(text)) return;
            pdf.setFont('helvetica', 'normal');
            pdf.setFontSize(10);
            const lines = pdf.splitTextToSize(safe(str(text)), contentW - indent - 5);
            const lh = 4.7;
            need(lines.length * lh + 1.6);
            ink(ACCENT);
            pdf.text('\u2022', margin + indent, y);
            ink(BODY);
            pdf.text(lines, margin + indent + 5, y);
            y += lines.length * lh + 1.6;
        };

        // ── Header ────────────────────────────────────────────────────────
        const name = str(contact.name);
        const headline = str(o.headline || o.target_role);
        const contactBits = [contact.email, contact.phone, contact.linkedin,
            contact.github, contact.website].map(str).filter(Boolean).join('   \u2022   ');

        if (name) {
            pdf.setFont('helvetica', 'bold');
            pdf.setFontSize(19);
            ink(HEAD);
            pdf.text(safe(name), margin, y + 7);
            y += 10;
        }
        if (headline) {
            pdf.setFont('helvetica', 'bold');
            pdf.setFontSize(11.5);
            ink(ACCENT);
            const hl = pdf.splitTextToSize(safe(headline), contentW);
            pdf.text(hl, margin, y + 3);
            y += 3 + hl.length * 4.6;
        }
        if (contactBits) {
            pdf.setFont('helvetica', 'normal');
            pdf.setFontSize(9);
            ink(MUTED);
            const cl = pdf.splitTextToSize(safe(contactBits), contentW);
            pdf.text(cl, margin, y + 4);
            y += 4 + cl.length * 4;
        }
        y += 3;
        rule(7);

        // ── Summary ───────────────────────────────────────────────────────
        if (str(o.summary)) {
            sectionTitle('Professional Summary');
            para(o.summary, 10, BODY, 2);
        }

        // ── Skills ────────────────────────────────────────────────────────
        const skills = arr(o.skills).map(str).filter(Boolean);
        if (skills.length) {
            sectionTitle('Skills');
            para(skills.join('   \u2022   '), 10, BODY, 2);
        }

        // ── Experience ────────────────────────────────────────────────────
        const experience = arr(o.experience).map(obj).filter((e) => str(e.title) || str(e.company));
        if (experience.length) {
            sectionTitle('Professional Experience');
            for (const e of experience) {
                const left = safe([str(e.title), str(e.company)].filter(Boolean).join('  \u2014  '));
                const dates = safe(_expRange(e));
                const headLines = pdf.splitTextToSize(left, dates ? contentW - 46 : contentW);
                need(headLines.length * 4.6 + 6);
                pdf.setFont('helvetica', 'bold');
                pdf.setFontSize(10.5);
                ink(HEAD);
                pdf.text(headLines, margin, y);
                if (dates) {
                    pdf.setFont('helvetica', 'italic');
                    pdf.setFontSize(9);
                    ink(MUTED);
                    pdf.text(dates, pageW - margin, y, { align: 'right' });
                }
                y += headLines.length * 4.6 + 1;
                pdf.setFont('helvetica', 'normal');

                if (str(e.location)) {
                    pdf.setFontSize(9);
                    ink(MUTED);
                    pdf.text(safe(str(e.location)), margin, y);
                    y += 4;
                }
                arr(e.bullets).forEach((b) => bulletLine(b));
                y += 3;
            }
        }

        // ── Projects ──────────────────────────────────────────────────────
        const projects = arr(o.projects).map(obj).filter((p) => str(p.name));
        if (projects.length) {
            sectionTitle('Projects');
            for (const p of projects) {
                const techs = arr(p.technologies).map(str).filter(Boolean).join(', ');
                const title = safe(str(p.name) + (techs ? '  \u2014  ' + techs : ''));
                need(10);
                pdf.setFont('helvetica', 'bold');
                pdf.setFontSize(10.5);
                ink(HEAD);
                pdf.text(title, margin, y);
                y += 5;
                pdf.setFont('helvetica', 'normal');
                para(p.description, 9.5, BODY, 1.5);
                arr(p.bullets).forEach((b) => bulletLine(b));
                y += 3;
            }
        }

        // ── Education ─────────────────────────────────────────────────────
        const education = arr(o.education).map(obj).filter((d) => str(d.institution) || str(d.degree));
        if (education.length) {
            sectionTitle('Education');
            for (const d of education) {
                const left = safe([str(d.degree), str(d.field), str(d.institution)]
                    .filter(Boolean).join('  \u2014  '));
                const right = safe(str(d.gpa) ? `GPA: ${str(d.gpa)}` : '');
                const lines = pdf.splitTextToSize(left, right ? contentW - 40 : contentW);
                need(lines.length * 4.6 + 4);
                pdf.setFont('helvetica', 'bold');
                pdf.setFontSize(10.5);
                ink(HEAD);
                pdf.text(lines, margin, y);
                if (right) {
                    pdf.setFont('helvetica', 'italic');
                    pdf.setFontSize(9);
                    ink(MUTED);
                    pdf.text(right, pageW - margin, y, { align: 'right' });
                }
                y += lines.length * 4.6 + 4;
                pdf.setFont('helvetica', 'normal');
            }
        }

        // ── Certifications ────────────────────────────────────────────────
        const certs = arr(o.certifications).map(obj).filter((c) => str(c.name));
        if (certs.length) {
            sectionTitle('Certifications');
            for (const c of certs) {
                const bits = [str(c.issuer), str(c.date_obtained)].filter(Boolean).join(', ');
                bulletLine(str(c.name) + (bits ? '  \u2014  ' + bits : ''));
            }
        }

        // ── Footer ────────────────────────────────────────────────────────
        need(16);
        y += 8;
        const target = str(o.target_role || tailoredResume.job_title);
        const company = str(o.target_company || tailoredResume.company_name);
        let tail = target ? `for the ${target} role` : '';
        if (company) tail += ` at ${company}`;
        pdf.setFont('helvetica', 'italic');
        pdf.setFontSize(8);
        ink(MUTED);
        pdf.text(safe(tail ? `Resume optimized ${tail}` : 'Optimized resume'),
            pageW / 2, y, { align: 'center' });

        const base = str(tailoredResume.filename).replace(/\.(docx?|pdf)$/i, '') || 'Optimized-Resume';
        const filename = `${base}.pdf`;
        pdf.setProperties({ title: base, subject: 'Optimized resume', creator: 'RoleMatcherAi' });

        try {
            pdf.save(filename);
        } catch (_saveErr) {
            // saveAs can be blocked — fall back to a plain anchor + blob
            const blob = pdf.output('blob');
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            a.remove();
            setTimeout(() => URL.revokeObjectURL(url), 5000);
        }
        showToast('PDF downloaded', 'success');
    } catch (err) {
        showToast(err.message || 'PDF generation failed', 'error');
    }
}

// ── Career Plan ─────────────────────────────────────────────────────────────

function initCareer() {
    document.getElementById('generate-plan-btn').addEventListener('click', generateCareerPlan);
    document.getElementById('export-plan-btn').addEventListener('click', exportPlan);
}

async function generateCareerPlan() {
    const targetField = document.getElementById('career-target-field').value.trim();
    if (!targetField) return showToast('Describe your target career field', 'error');
    const payload = { target_role: targetField };
    showLoading('Generating career plan...');
    try {
        const data = await apiFetch(`${API_BASE}/career/plan`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        }).then(r => r.json());
        hideLoading();
        careerPlan = data;
        const result = document.getElementById('career-plan-result');
        result.classList.remove('hidden');
        result.innerHTML = renderCareerPlan(data);
        const legend = document.getElementById('career-roadmap-legend');
        if (legend) legend.classList.remove('hidden');
        document.getElementById('export-plan-btn').style.display = 'inline-flex';
        showToast('Career plan generated', 'success');
        updateDashboardProgress();
    } catch (err) {
        hideLoading();
        showToast(err.message || 'Generation failed', 'error');
    }
}

function renderCareerPlan(data) {
    const plan = data.plan || {};
    const target = data.target_role || '';
    const skillGaps = plan.skill_gaps || data.skill_gaps || [];
    const roadmapSteps = plan.roadmap_steps || [];
    const portfolioProjects = plan.portfolio_projects || [];
    const appStrategy = plan.application_strategy || {};

    let html = '';

    // ── Header card ──
    html += `<div class="cp-header glass-card">
        <div class="cp-header-top">
            <div class="cp-header-icon"><i class="fas fa-route"></i></div>
            <div>
                <h3 class="cp-header-title">Expertise Roadmap</h3>
                <p class="cp-header-sub">${target ? `Your path to mastering <strong>${target}</strong>` : 'Your personalized learning path'}</p>
            </div>
        </div>
    </div>`;

    // ── Skill Gaps ──
    if (skillGaps.length) {
        const priorityColor = (p) => p <= 1 ? '#ef4444' : p <= 2 ? '#f59e0b' : p <= 3 ? '#3ecf8e' : '#737373';
        const priorityBg = (p) => p <= 1 ? 'rgba(239,68,68,0.1)' : p <= 2 ? 'rgba(245,158,11,0.1)' : p <= 3 ? 'rgba(62,207,142,0.1)' : 'rgba(115,115,115,0.1)';
        const demandIcon = (d) => d === 'high' ? 'fa-arrow-up' : d === 'medium' ? 'fa-minus' : 'fa-arrow-down';

        html += `<div class="cp-section glass-card">
            <h4 class="cp-section-title"><i class="fas fa-crosshairs" style="color:var(--accent-primary)"></i> Skill Gaps <span class="cp-count">${skillGaps.length}</span></h4>
            <div class="cp-gaps-grid">
                ${skillGaps.slice(0, 10).map(g => {
                    const gObj = typeof g === 'string' ? { skill: g, priority: 5, market_demand: 'low' } : g;
                    const p = gObj.priority || 5;
                    const d = gObj.market_demand || 'low';
                    return `<div class="cp-gap-item">
                        <div class="cp-gap-priority" style="background:${priorityBg(p)};color:${priorityColor(p)}">P${p}</div>
                        <div class="cp-gap-body">
                            <div class="cp-gap-skill">${gObj.skill || 'Skill'}</div>
                            <div class="cp-gap-demand"><i class="fas ${demandIcon(d)}"></i> ${d} demand</div>
                        </div>
                    </div>`;
                }).join('')}
            </div>
        </div>`;
    }

    // ── Step-by-Step Roadmap ──
    if (roadmapSteps.length) {
        html += `<div class="cp-section glass-card">
            <h4 class="cp-section-title"><i class="fas fa-map-signs" style="color:var(--accent-primary)"></i> Step-by-Step Roadmap</h4>
            <div class="cp-steps-list">
                ${roadmapSteps.map((step, i) => {
                    const stepNum = step.step || (i + 1);
                    const title = step.title || `Step ${stepNum}`;
                    const duration = step.duration || '';
                    const topics = step.topics || [];
                    const resources = step.resources || [];
                    const practice = step.practice || '';

                    return `<div class="cp-step-card">
                        <div class="cp-step-header">
                            <div class="cp-step-num">${stepNum}</div>
                            <div class="cp-step-title">${title}</div>
                            ${duration ? `<div class="cp-step-duration"><i class="fas fa-clock"></i> ${duration}</div>` : ''}
                        </div>
                        <div class="cp-step-body">
                            ${topics.length ? `
                            <div class="cp-step-topics">
                                <div class="cp-step-label"><i class="fas fa-list-check"></i> What to learn</div>
                                <ul>
                                    ${topics.map(t => `<li>${t}</li>`).join('')}
                                </ul>
                            </div>` : ''}
                            ${resources.length ? `
                            <div class="cp-step-resources">
                                <div class="cp-step-label"><i class="fas fa-book"></i> Resources</div>
                                <div class="cp-step-chips">
                                    ${resources.map(r => `<span class="cp-step-chip">${r}</span>`).join('')}
                                </div>
                            </div>` : ''}
                            ${practice ? `
                            <div class="cp-step-practice">
                                <div class="cp-step-label"><i class="fas fa-code"></i> Practice</div>
                                <div class="cp-step-practice-text">${practice}</div>
                            </div>` : ''}
                        </div>
                    </div>`;
                }).join('')}
            </div>
        </div>`;
    }

    // ── Portfolio Projects ──
    if (portfolioProjects.length) {
        const diffColor = (d) => d === 'beginner' ? '#3ecf8e' : d === 'intermediate' ? '#f59e0b' : '#ef4444';
        html += `<div class="cp-section glass-card">
            <h4 class="cp-section-title"><i class="fas fa-diagram-project" style="color:var(--accent-primary)"></i> Portfolio Projects</h4>
            <div class="cp-projects-grid">
                ${portfolioProjects.map(p => {
                    const skills = p.skills_practiced || [];
                    const techs = p.technologies || [];
                    return `<div class="cp-project-card">
                        <div class="cp-project-header">
                            <div class="cp-project-name">${p.name || 'Project'}</div>
                            <div class="cp-project-diff" style="color:${diffColor(p.difficulty)}">${(p.difficulty || '').charAt(0).toUpperCase() + (p.difficulty || '').slice(1)}</div>
                        </div>
                        <div class="cp-project-desc">${p.description || ''}</div>
                        <div class="cp-project-meta">
                            ${p.estimated_time ? `<span class="cp-project-meta-pill"><i class="fas fa-clock"></i> ${p.estimated_time}</span>` : ''}
                            ${techs.map(t => `<span class="cp-project-tech-chip">${t}</span>`).join('')}
                        </div>
                        ${skills.length ? `<div class="cp-project-skills"><div class="cp-step-label"><i class="fas fa-graduation-cap"></i> Skills practiced</div><div class="cp-step-chips">${skills.map(s => `<span class="cp-step-chip">${s}</span>`).join('')}</div></div>` : ''}
                    </div>`;
                }).join('')}
            </div>
        </div>`;
    }

    // ── Application Strategy ──
    if (appStrategy.resume_tips || appStrategy.portfolio_tips || appStrategy.networking || appStrategy.job_search) {
        const sections = [
            { key: 'resume_tips', icon: 'fa-file-alt', title: 'Resume Tips', items: appStrategy.resume_tips },
            { key: 'portfolio_tips', icon: 'fa-briefcase', title: 'Portfolio Tips', items: appStrategy.portfolio_tips },
            { key: 'networking', icon: 'fa-users', title: 'Networking', items: appStrategy.networking },
            { key: 'job_search', icon: 'fa-search', title: 'Job Search', items: appStrategy.job_search },
        ].filter(s => s.items && s.items.length);

        if (sections.length) {
            html += `<div class="cp-section glass-card">
                <h4 class="cp-section-title"><i class="fas fa-rocket" style="color:var(--accent-primary)"></i> How to Apply</h4>
                <div class="cp-strategy-grid">
                    ${sections.map(s => `
                    <div class="cp-strategy-card">
                        <div class="cp-strategy-title"><i class="fas ${s.icon}"></i> ${s.title}</div>
                        <ul class="cp-strategy-list">
                            ${s.items.map(item => `<li>${item}</li>`).join('')}
                        </ul>
                    </div>`).join('')}
                </div>
            </div>`;
        }
    }

    return html;
}

function exportPlan() {
    if (!careerPlan) return;
    showToast('Generating PDF...', 'info');
    try {
        const plan = careerPlan.plan || {};
        const target = careerPlan.target_role || 'Career Plan';
        const { jsPDF } = window.jspdf;
        const pdf = new jsPDF('p', 'mm', 'a4');
        const pageW = 210;
        const margin = 16;
        const contentW = pageW - margin * 2;
        let y = 0;

        const BRAND = '#6366f1';
        const HEAD = '#111827';
        const BODY = '#374151';
        const MUTED = '#6b7280';

        function resetY(needed) {
            if (y + needed > 281) { pdf.addPage(); y = 16; }
        }
        function wrap(text, width, size) {
            return pdf.splitTextToSize(String(text || ''), width, { fontSize: size });
        }
        function sectionIcon() {
            pdf.setFillColor(BRAND);
            pdf.circle(margin + 2, y - 1.1, 2, 'F');
        }
        function drawHeader() {
            pdf.setFillColor(BRAND);
            pdf.rect(0, 0, pageW, 28, 'F');
            pdf.setTextColor(255, 255, 255);
            pdf.setFont('helvetica', 'bold');
            pdf.setFontSize(20);
            pdf.text('RoleMatcherAi', margin, 12);
            pdf.setFontSize(11);
            pdf.setFont('helvetica', 'normal');
            pdf.text('Personalized Career Roadmap', margin, 19);
            pdf.setFont('helvetica', 'bold');
            pdf.setFontSize(13);
            pdf.text(target.length > 60 ? wrap(target, contentW, 13)[0] : target, pageW - margin, 15, { align: 'right' });
        }

        function addSection(title) {
            resetY(16);
            sectionIcon();
            pdf.setTextColor(HEAD);
            pdf.setFont('helvetica', 'bold');
            pdf.setFontSize(13);
            const lines = wrap(title, contentW - 8, 13);
            pdf.text(lines, margin + 7, y);
            y += lines.length * 5.2;
            pdf.setDrawColor(229, 231, 235);
            pdf.setLineWidth(0.3);
            pdf.line(margin + 7, y - 1.2, pageW - margin, y - 1.2);
            y += 4;
            pdf.setFont('helvetica', 'normal');
        }

        function addBody(text, size = 10) {
            pdf.setFont('helvetica', 'normal');
            pdf.setFontSize(size);
            pdf.setTextColor(BODY);
            const lines = wrap(text, contentW, size);
            resetY(lines.length * (size * 0.4) + 2);
            pdf.text(lines, margin, y);
            y += lines.length * (size * 0.45) + 1;
        }

        function addListItem(text, bullet = '•') {
            pdf.setFont('helvetica', 'normal');
            pdf.setFontSize(10);
            pdf.setTextColor(BODY);
            const lines = wrap(text, contentW - 6, 10);
            resetY(lines.length * 4.5 + 2);
            pdf.text(bullet, margin, y);
            pdf.text(lines, margin + 6, y);
            y += lines.length * 4.5 + 0.6;
        }

        function addSubTitle(text) {
            resetY(11);
            pdf.setFont('helvetica', 'bold');
            pdf.setFontSize(11);
            pdf.setTextColor(BRAND);
            pdf.text(wrap(text, contentW, 11), margin, y);
            y += 5.6;
        }

        drawHeader();
        y = 38;

        pdf.setFont('helvetica', 'normal');
        pdf.setFontSize(10.5);
        pdf.setTextColor(MUTED);
        pdf.text(wrap(`Roadmap for ${target}`, contentW, 10.5), margin, y);
        y += 6;
        pdf.setTextColor(MUTED);
        pdf.text(wrap(`Generated by RoleMatcherAi on ${new Date().toLocaleDateString()}`, contentW, 10.5), margin, y);
        y += 14;

        // ── Summary ──
        if (plan.summary || plan.focus_areas || plan.estimated_timeline) {
            addSection('Summary');
            if (plan.summary) addBody(plan.summary);
            if (plan.estimated_timeline) {
                pdf.setFont('helvetica', 'bold');
                pdf.setFontSize(10);
                pdf.setTextColor(HEAD);
                pdf.text('Estimated timeline: ', margin, y);
                pdf.setFont('helvetica', 'normal');
                pdf.setTextColor(BODY);
                const tl = wrap(plan.estimated_timeline, contentW - 45, 10);
                pdf.text(tl, margin + 45, y);
                y += Math.max(tl.length, 1) * 4.5;
            }
            if (plan.focus_areas && plan.focus_areas.length) {
                resetY(8);
                pdf.setFont('helvetica', 'bold');
                pdf.setFontSize(10);
                pdf.setTextColor(HEAD);
                pdf.text('Focus areas:', margin, y);
                y += 5;
                plan.focus_areas.forEach(f => addListItem(f));
            }
            y += 4;
        }

        // ── Skill Gaps ──
        const skillGaps = plan.skill_gaps || careerPlan.skill_gaps || [];
        if (skillGaps.length) {
            addSection(`Skill Gaps (${skillGaps.length})`);
            skillGaps.slice(0, 12).forEach(g => {
                const name = typeof g === 'string' ? g : (g.skill || 'Skill');
                const priority = typeof g === 'string' ? '' : (g.priority ? ` — Priority ${g.priority}` : '');
                const demand = typeof g === 'string' ? '' : (g.market_demand ? ` (${g.market_demand} demand)` : '');
                addListItem(name + priority + demand);
            });
            y += 4;
        }

        // ── Roadmap Steps ──
        const roadmapSteps = plan.roadmap_steps || [];
        if (roadmapSteps.length) {
            addSection(`Step-by-Step Roadmap (${roadmapSteps.length} steps)`);
            roadmapSteps.forEach((step, i) => {
                const title = step.title || `Step ${step.step || i + 1}`;
                const duration = step.duration ? `  [${step.duration}]` : '';
                addSubTitle(`Step ${step.step || i + 1}: ${title}${duration}`);
                if (step.topics && step.topics.length) {
                    addBody('What to learn:', 10);
                    step.topics.forEach(t => addListItem(t, '•'));
                }
                if (step.resources && step.resources.length) {
                    addBody('Resources:', 10);
                    step.resources.forEach(r => addListItem(r, '◦'));
                }
                if (step.practice) {
                    addBody('Practice: ' + step.practice, 10);
                }
                y += 2;
            });
            y += 4;
        }

        // ── Portfolio Projects ──
        const portfolioProjects = plan.portfolio_projects || [];
        if (portfolioProjects.length) {
            addSection(`Portfolio Projects (${portfolioProjects.length})`);
            portfolioProjects.forEach(p => {
                addSubTitle(p.name || 'Project');
                if (p.description) addBody(p.description, 10);
                if (p.estimated_time) {
                    pdf.setFont('helvetica', 'bold');
                    pdf.setFontSize(9.5);
                    pdf.setTextColor(MUTED);
                    pdf.text('Estimated time: ' + p.estimated_time, margin, y);
                    y += 4.5;
                    pdf.setFont('helvetica', 'normal');
                }
                if (p.technologies && p.technologies.length) {
                    addBody('Technologies: ' + p.technologies.join(', '), 9.5);
                }
                if (p.skills_practiced && p.skills_practiced.length) {
                    addBody('Skills practiced: ' + p.skills_practiced.join(', '), 9.5);
                }
                y += 2;
            });
            y += 4;
        }

        // ── Application Strategy ──
        const app = plan.application_strategy || {};
        const sections = [
            ['Resume Tips', app.resume_tips],
            ['Portfolio Tips', app.portfolio_tips],
            ['Networking', app.networking],
            ['Job Search', app.job_search],
        ].filter(([, items]) => items && items.length);
        if (sections.length) {
            addSection('How to Apply');
            sections.forEach(([title, items]) => {
                addSubTitle(title);
                items.forEach(i => addListItem(i));
                y += 2;
            });
        }

        if (careerPlan.recommendations && careerPlan.recommendations.length) {
            addSection('Recommendations');
            careerPlan.recommendations.forEach(r => addListItem(r));
        }

        pdf.save(`career-plan-${target.replace(/[^a-z0-9]+/gi, '-').toLowerCase().slice(0, 40) || 'export'}.pdf`);
        showToast('PDF exported successfully', 'success');
    } catch (err) {
        console.error('PDF export failed:', err);
        showToast('PDF export failed', 'error');
        const raw = careerPlan.plan || careerPlan.content || careerPlan;
        const text = typeof raw === 'string' ? raw : JSON.stringify(raw, null, 2);
        const blob = new Blob([text], { type: 'text/plain' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'career-plan.txt';
        a.click();
    }
}

// ── Interview ───────────────────────────────────────────────────────────────
let interviewSession = null;
let currentQuestionIndex = 0;

function initInterview() {
    document.getElementById('start-interview-btn').addEventListener('click', startInterview);
    document.querySelectorAll('#interview-type-selector .cl-tone-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#interview-type-selector .cl-tone-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        });
    });
}

async function startInterview() {
    const role = document.getElementById('interview-job-role').value.trim();
    const jobDesc = document.getElementById('interview-job-desc').value.trim();
    const type = document.querySelector('#interview-type-selector .cl-tone-btn.active')?.dataset.type || 'mixed';
    if (!role) return showToast('Enter a job role to prepare for', 'error');

    showLoading('Preparing 15 interview questions...');
    try {
        const data = await apiFetch(`${API_BASE}/interviews`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                job_role: role,
                job_description: jobDesc,
                interview_type: type,
                resume_id: resumeData?.resume_id || null,
            }),
        }).then(r => r.json());
        hideLoading();
        interviewSession = data;
        currentQuestionIndex = 0;
        document.getElementById('interview-setup-card').classList.add('hidden');
        const container = document.getElementById('interview-questions');
        container.classList.remove('hidden');
        renderInterviewQuestion(0);
        showToast(`${data.total_questions} questions ready`, 'success');
    } catch (err) {
        hideLoading();
        showToast(err.message || 'Failed to start interview', 'error');
    }
}

function renderInterviewQuestion(index) {
    const container = document.getElementById('interview-questions');
    const q = interviewSession.questions[index];
    if (!q) return;
    currentQuestionIndex = index;
    const total = interviewSession.total_questions || interviewSession.questions.length;
    const progress = Math.round((index / total) * 100);
    container.innerHTML = `
        <div class="interview-progress">
            <div class="interview-progress-track"><div class="interview-progress-fill" style="width:${progress}%"></div></div>
            <span class="interview-progress-label">Question ${index + 1} of ${total}</span>
        </div>
        <div class="interview-question glass-card" id="interview-current-q">
            <div class="interview-q-meta">
                <span class="interview-q-cat">${q.category || 'technical'}</span>
                <span class="interview-q-diff">${q.difficulty || 'medium'}</span>
            </div>
            <h3>Question ${index + 1}</h3>
            <div class="interview-q-text">${q.question || q}</div>
            <textarea class="interview-textarea" id="interview-answer" placeholder="Type your answer... (be specific, use examples, and structure your response)"></textarea>
            <button class="btn btn-primary btn-sm" id="interview-submit-btn" onclick="submitInterviewAnswer()">
                <i class="fas fa-check"></i> Submit Answer
            </button>
            <div class="interview-feedback hidden" id="interview-feedback"></div>
        </div>
    `;
    container.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function submitInterviewAnswer() {
    const answer = document.getElementById('interview-answer').value;
    if (!answer.trim()) return showToast('Type an answer first', 'error');
    const submitBtn = document.getElementById('interview-submit-btn');
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Evaluating...';
    try {
        const data = await apiFetch(`${API_BASE}/interviews/${interviewSession.session_id}/answer`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question_index: currentQuestionIndex, answer: answer.trim() }),
        }).then(r => r.json());
        renderInterviewFeedback(data);
    } catch (err) {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<i class="fas fa-check"></i> Submit Answer';
        showToast(err.message || 'Feedback failed', 'error');
    }
}

function renderInterviewFeedback(data) {
    const container = document.getElementById('interview-current-q');
    const feedbackDiv = document.getElementById('interview-feedback');
    feedbackDiv.classList.remove('hidden');
    const score = data.score ?? 0;
    const scoreColor = score >= 7 ? 'var(--accent-primary)' : score >= 4 ? '#eab308' : '#ef4444';
    const strengths = data.strengths || [];
    const improvements = data.improvements || [];
    const modelAnswer = data.model_answer || '';

    let html = `
        <div class="interview-score" style="border-color:${scoreColor}">
            <span class="interview-score-value" style="color:${scoreColor}">${score}/10</span>
            <span class="interview-score-label">Score</span>
        </div>
        <div class="interview-fb-section">
            <h4>Feedback</h4>
            <p>${data.feedback || 'Good answer!'}</p>
        </div>
    `;
    if (strengths.length) {
        html += `<div class="interview-fb-section"><h4>Strengths</h4><ul>${strengths.map(s => `<li>${s}</li>`).join('')}</ul></div>`;
    }
    if (improvements.length) {
        html += `<div class="interview-fb-section"><h4>Areas to Improve</h4><ul>${improvements.map(s => `<li>${s}</li>`).join('')}</ul></div>`;
    }
    if (modelAnswer) {
        html += `<div class="interview-fb-section"><h4>Model Answer</h4><div class="interview-model-answer">${window.marked ? marked.parse(modelAnswer) : modelAnswer}</div></div>`;
    }

    const total = interviewSession.total_questions || interviewSession.questions.length;
    const isLast = currentQuestionIndex >= total - 1;

    html += `<div class="interview-actions" style="display:flex;gap:12px;justify-content:center;margin-top:20px;flex-wrap:wrap">`;
    if (isLast) {
        html += `<button class="btn btn-primary" id="interview-finish-btn" onclick="finishInterview()"><i class="fas fa-flag-checkered"></i> Finish & See Results</button>`;
    } else {
        html += `<button class="btn btn-primary" onclick="renderInterviewQuestion(currentQuestionIndex + 1)"><i class="fas fa-arrow-right"></i> Next Question</button>`;
    }
    html += `</div>`;

    feedbackDiv.innerHTML = html;
    container.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function finishInterview() {
    showLoading('Calculating your score...');
    try {
        const data = await apiFetch(`${API_BASE}/interviews/${interviewSession.session_id}`, {
            method: 'GET',
        }).then(r => r.json());
        hideLoading();
        if (data.completed) markInterviewCompleted();
        renderInterviewResults(data);
    } catch (err) {
        hideLoading();
        showToast(err.message || 'Failed to load results', 'error');
    }
}

function renderInterviewResults(data) {
    const container = document.getElementById('interview-questions');
    const scores = (data.scores || []).filter(s => s !== null);
    const total = data.total_questions || scores.length || 0;
    const overall = data.overall_score ?? 0;
    const correct = scores.filter(s => s >= 7).length;
    const needsWork = scores.filter(s => s >= 4 && s < 7).length;
    const retry = scores.filter(s => s < 4).length;

    const pct = Math.round((correct / (scores.length || 1)) * 100);
    const grade = overall >= 8 ? 'Excellent' : overall >= 6 ? 'Good' : overall >= 4 ? 'Fair' : 'Needs Improvement';
    const gradeColor = overall >= 7 ? 'var(--accent-primary)' : overall >= 4 ? '#eab308' : '#ef4444';

    container.innerHTML = `
        <div class="interview-results glass-card">
            <h3><i class="fas fa-trophy" style="color:var(--accent-primary)"></i> Interview Complete!</h3>
            <div class="interview-results-score">
                <div class="interview-results-big" style="color:${gradeColor}">${overall}/10</div>
                <div class="interview-results-grade">${grade}</div>
                <div class="interview-results-bar-track"><div class="interview-results-bar-fill" style="width:${pct}%"></div></div>
            </div>
            <div class="interview-results-stats">
                <div class="interview-result-stat">
                    <div class="interview-result-num" style="color:var(--accent-primary)">${correct}</div>
                    <div class="interview-result-label">Strong</div>
                </div>
                <div class="interview-result-stat">
                    <div class="interview-result-num" style="color:#eab308">${needsWork}</div>
                    <div class="interview-result-label">Good</div>
                </div>
                <div class="interview-result-stat">
                    <div class="interview-result-num" style="color:#ef4444">${retry}</div>
                    <div class="interview-result-label">Needs Work</div>
                </div>
                <div class="interview-result-stat">
                    <div class="interview-result-num">${total}</div>
                    <div class="interview-result-label">Total</div>
                </div>
            </div>
            <div class="interview-results-actions" style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap;margin-top:20px">
                <button class="btn btn-primary" onclick="retryWeakQuestions()"><i class="fas fa-redo"></i> Retry Weak Questions</button>
                <button class="btn btn-ghost" onclick="resetInterview()"><i class="fas fa-rotate-left"></i> New Interview</button>
            </div>
        </div>
    `;
    container.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function retryWeakQuestions() {
    const container = document.getElementById('interview-questions');
    const scores = interviewSession.scores || [];
    const weakIndices = scores.map((s, i) => s !== null && s < 7 ? i : null).filter(i => i !== null);
    if (!weakIndices.length) {
        showToast('No weak questions to retry. Great job!', 'success');
        return;
    }
    const q = interviewSession.questions[weakIndices[0]];
    currentQuestionIndex = weakIndices[0];
    const total = interviewSession.questions.length;
    container.innerHTML = `
        <div class="interview-progress">
            <div class="interview-progress-track"><div class="interview-progress-fill" style="width:${Math.round((currentQuestionIndex / total) * 100)}%"></div></div>
            <span class="interview-progress-label">Retrying Question ${currentQuestionIndex + 1} of ${total}</span>
        </div>
        <div class="interview-question glass-card" id="interview-current-q">
            <div class="interview-q-meta">
                <span class="interview-q-cat">${q.category}</span>
                <span class="interview-q-diff">${q.difficulty}</span>
            </div>
            <h3>Retry Question ${currentQuestionIndex + 1}</h3>
            <div class="interview-q-text">${q.question}</div>
            <textarea class="interview-textarea" id="interview-answer" placeholder="Try again with a more detailed answer..."></textarea>
            <button class="btn btn-primary btn-sm" id="interview-submit-btn" onclick="submitInterviewAnswer()">
                <i class="fas fa-check"></i> Submit Answer
            </button>
            <div class="interview-feedback hidden" id="interview-feedback"></div>
        </div>
    `;
    container.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function resetInterview() {
    interviewSession = null;
    interviewCompleted = false;
    currentQuestionIndex = 0;
    document.getElementById('interview-questions').classList.add('hidden');
    document.getElementById('interview-setup-card').classList.remove('hidden');
    document.getElementById('interview-job-desc').value = '';
    document.getElementById('interview-job-role').value = '';
    updateDashboardProgress();
}

// ── Cover Letter ────────────────────────────────────────────────────────────
let clMode = 'form';

function initCoverLetter() {
    const toneBtns = document.querySelectorAll('#section-cover-letter .cl-tone-btn');
    toneBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            toneBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        });
    });

    document.getElementById('cl-generate-btn').addEventListener('click', generateCoverLetter);
    document.getElementById('cl-copy-btn').addEventListener('click', copyCoverLetter);
    document.getElementById('cl-mode-form').addEventListener('click', () => setClMode('form'));
    document.getElementById('cl-mode-resume').addEventListener('click', () => setClMode('resume'));
}

function setClMode(mode) {
    clMode = mode;
    document.querySelectorAll('#section-cover-letter .cl-mode-btn').forEach(b => b.classList.toggle('active', b.dataset.mode === mode));
    document.getElementById('cl-form-fields').classList.toggle('hidden', mode !== 'form');
    document.getElementById('cl-resume-hint').classList.toggle('hidden', mode !== 'resume');
    if (mode === 'resume') {
        const status = document.getElementById('cl-resume-status');
        if (resumeData?.resume_id) {
            status.textContent = 'Your resume is ready to use.';
            status.style.color = 'var(--accent-primary)';
        } else {
            status.textContent = 'Upload a resume first, or use Fill Details mode.';
            status.style.color = '#ef4444';
        }
    }
}

async function generateCoverLetter() {
    const company = document.getElementById('cl-company').value.trim();
    const role = document.getElementById('cl-role').value.trim();
    const jobDesc = document.getElementById('cl-job-desc').value.trim();
    const tone = document.querySelector('#section-cover-letter .cl-tone-btn.active')?.dataset.tone || 'professional';

    const payload = { tone };
    if (clMode === 'resume') {
        if (!resumeData?.resume_id) return showToast('Upload a resume first, or switch to Fill Details', 'error');
        payload.resume_id = resumeData.resume_id;
        if (company) payload.company_name = company;
        if (role) payload.job_title = role;
    } else {
        if (!company || !role) return showToast('Fill in company and role', 'error');
        payload.company_name = company;
        payload.job_title = role;
    }
    if (jobDesc) payload.job_description = jobDesc;

    showLoading('Generating cover letter...');
    try {
        const data = await apiFetch(`${API_BASE}/cover-letters`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        }).then(r => r.json());
        hideLoading();
        const content = data.content || data.cover_letter || data.text || '';
        document.getElementById('cl-result').classList.remove('hidden');
        document.getElementById('cl-result-content').textContent = content;
        const companyDisp = data.company_name || company || '';
        const roleDisp = data.job_title || role || '';
        document.getElementById('cl-result-meta').textContent = `${companyDisp}${companyDisp && roleDisp ? ' — ' : ''}${roleDisp}${tone ? ' — ' + tone : ''}`;
        clHistory.unshift({ company: companyDisp, role: roleDisp, tone, content, date: new Date() });
        renderCLHistory();
        showToast('Cover letter generated', 'success');
    } catch (err) {
        hideLoading();
        showToast('Generation failed', 'error');
    }
}

function copyCoverLetter() {
    const text = document.getElementById('cl-result-content').textContent;
    navigator.clipboard.writeText(text).then(() => showToast('Copied to clipboard', 'success'));
}

function renderCLHistory() {
    const list = document.getElementById('cl-history-list');
    list.innerHTML = clHistory.map((item, i) => `
        <div class="cl-history-card glass-card" onclick="showCLHistory(${i})">
            <div class="cl-history-icon"><i class="fas fa-pen-fancy"></i></div>
            <div class="cl-history-body">
                <div class="cl-history-name">${item.company} — ${item.role}</div>
                <div class="cl-history-detail">${item.tone} • ${item.date.toLocaleDateString()}</div>
            </div>
            <i class="fas fa-chevron-right cl-history-arrow"></i>
        </div>
    `).join('');
}

function showCLHistory(index) {
    const item = clHistory[index];
    if (!item) return;
    document.getElementById('cl-result').classList.remove('hidden');
    document.getElementById('cl-result-content').textContent = item.content;
    document.getElementById('cl-result-meta').textContent = `${item.company} — ${item.role} — ${item.tone}`;
}

// ── Reviews ────────────────────────────────────────────────────────────────
function initReviews() {
    const submitBtn = document.getElementById('review-submit-btn');
    if (submitBtn) {
        submitBtn.addEventListener('click', submitReview);
    }
    loadReviews();
    loadHomeTestimonials();
}

async function submitReview() {
    const name = document.getElementById('review-name').value.trim();
    const email = document.getElementById('review-email').value.trim();
    const profession = document.getElementById('review-profession').value.trim();
    const review = document.getElementById('review-text').value.trim();

    if (!name) return showToast('Please enter your name', 'error');
    if (!email || !email.includes('@')) return showToast('Please enter a valid email', 'error');
    if (!review) return showToast('Please write your review', 'error');

    const btn = document.getElementById('review-submit-btn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Submitting...';
    try {
        await apiFetch(`${API_BASE}/reviews`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, email, review, profession }),
        });
        document.getElementById('review-name').value = '';
        document.getElementById('review-email').value = '';
        document.getElementById('review-profession').value = '';
        document.getElementById('review-text').value = '';
        showToast('Thank you for your review!', 'success');
        await Promise.all([loadReviews(), loadHomeTestimonials()]);
    } catch (err) {
        showToast(err.message || 'Failed to submit review', 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-paper-plane"></i> Submit Review';
    }
}

function reviewAvatar(name) {
    const parts = (name || 'U').trim().split(/\s+/);
    return (parts[0][0] + (parts[1] ? parts[1][0] : '')).toUpperCase();
}

const _avatarColors = ['#3ecf8e', '#1aad6d', '#00c573', '#22c55e', '#17a566', '#15b070'];
function avatarColor(name) {
    let hash = 0;
    for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
    return _avatarColors[hash % _avatarColors.length];
}

function formatReviewDate(iso) {
    try {
        const d = new Date(iso);
        return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
    } catch (e) {
        return '';
    }
}

async function loadReviews() {
    try {
        const data = await apiFetch(`${API_BASE}/reviews`).then(r => r.json());
        const list = document.getElementById('reviews-list');
        const reviews = data.reviews || [];
        if (!reviews.length) {
            list.innerHTML = `<div class="reviews-empty glass-card"><i class="fas fa-star"></i> No reviews yet — be the first to leave one!</div>`;
            return;
        }
        list.innerHTML = reviews.map(r => `
            <div class="review-card glass-card">
                <div class="review-card-head">
                    <div class="review-avatar" style="background:${avatarColor(r.name || 'U')}">${reviewAvatar(r.name)}</div>
                    <div>
                        <div class="review-name">${r.name || 'Anonymous'}${r.profession ? `<span class="review-profession"><i class="fas fa-briefcase"></i> ${r.profession}</span>` : ''}</div>
                        <div class="review-date">${formatReviewDate(r.created_at)}</div>
                    </div>
                    <div class="review-stars"><i class="fas fa-star"></i><i class="fas fa-star"></i><i class="fas fa-star"></i><i class="fas fa-star"></i><i class="fas fa-star"></i></div>
                </div>
                <p class="review-text">${r.review || ''}</p>
            </div>
        `).join('');
    } catch (err) {
        document.getElementById('reviews-list').innerHTML = `<div class="reviews-empty glass-card"><i class="fas fa-exclamation-circle"></i> Could not load reviews.</div>`;
    }
}

async function loadHomeTestimonials() {
    const container = document.getElementById('home-testimonials');
    if (!container) return;
    try {
        const data = await apiFetch(`${API_BASE}/reviews`).then(r => r.json());
        const reviews = data.reviews || [];
        if (!reviews.length) return; // keep the default static testimonials
        const shuffled = [...reviews].sort(() => 0.5 - Math.random()).slice(0, 3);
        container.innerHTML = shuffled.map(r => `
            <div class="cf-testimonial glass-card">
                <div class="cf-testi-quote"><i class="fas fa-quote-left"></i></div>
                <p class="cf-testi-text">${r.review || ''}</p>
                <div class="cf-testi-author">
                    <div class="cf-testi-avatar" style="background:${avatarColor(r.name || 'U')}">${reviewAvatar(r.name)}</div>
                    <div>
                        <div class="cf-testi-name">${r.name || 'Anonymous'}</div>
                        <div class="cf-testi-role">${r.profession || r.email || ''}</div>
                    </div>
                </div>
            </div>
        `).join('');
    } catch (err) {
        // keep the default static testimonials on error
    }
}

// ── Chat ────────────────────────────────────────────────────────────────────
function initChat() {
    const fab = document.getElementById('chat-fab');
    const widget = document.getElementById('chat-widget');
    const closeBtn = document.getElementById('chat-widget-close');
    const input = document.getElementById('chat-input');
    const sendBtn = document.getElementById('send-chat-btn');

    fab.addEventListener('click', () => {
        fab.classList.toggle('active');
        widget.classList.toggle('open');
    });

    closeBtn.addEventListener('click', () => {
        fab.classList.remove('active');
        widget.classList.remove('open');
    });

    sendBtn.addEventListener('click', sendMessage);
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
    });

    input.addEventListener('input', () => {
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 80) + 'px';
    });
}

async function sendMessage() {
    const input = document.getElementById('chat-input');
    const msg = input.value.trim();
    if (!msg) return;

    const messagesDiv = document.getElementById('chat-messages');
    const welcome = messagesDiv.querySelector('.chat-welcome');
    if (welcome) welcome.remove();

    messagesDiv.innerHTML += `
        <div class="chat-msg user">
            <div class="chat-msg-avatar human"><i class="fas fa-user"></i></div>
            <div class="chat-msg-bubble">${msg}</div>
        </div>
    `;

    input.value = '';
    input.style.height = 'auto';

    const meta = document.getElementById('chat-meta');
    meta.innerHTML = '<div class="typing-indicator"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div>';

    try {
        const data = await apiFetch(`${API_BASE}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: msg }),
        }).then(r => r.json());
        meta.innerHTML = '';
        const reply = data.reply || data.response || data.message || 'I could not process that request.';
        messagesDiv.innerHTML += `
            <div class="chat-msg assistant">
                <div class="chat-msg-avatar ai"><i class="fas fa-robot"></i></div>
                <div class="chat-msg-bubble">${reply}</div>
            </div>
        `;
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
    } catch (err) {
        meta.innerHTML = '';
        messagesDiv.innerHTML += `
            <div class="chat-msg assistant">
                <div class="chat-msg-avatar ai"><i class="fas fa-robot"></i></div>
                <div class="chat-msg-bubble" style="color:#ef4444">Error: ${err.message || 'Connection failed. Please try again.'}</div>
            </div>
        `;
    }
}

// ── FAQ ─────────────────────────────────────────────────────────────────────
function initFAQ() {
    document.querySelectorAll('.cf-faq-question').forEach(btn => {
        btn.addEventListener('click', () => {
            const item = btn.closest('.cf-faq-item');
            item.classList.toggle('open');
        });
    });
}

// ── Dashboard Progress ──────────────────────────────────────────────────────
let interviewCompleted = false;

function markInterviewCompleted() {
    interviewCompleted = true;
    updateDashboardProgress();
}

function updateDashboardProgress() {
    const steps = [
        { key: 'resume', done: !!resumeData },
        { key: 'jobs', done: jobsData.length > 0 },
        { key: 'career', done: !!careerPlan },
        { key: 'interview', done: interviewCompleted },
    ];
    const doneCount = steps.filter(s => s.done).length;
    const pct = Math.round((doneCount / steps.length) * 100);
    document.getElementById('dash-progress-pct').textContent = `${pct}%`;
    document.getElementById('dash-progress-fill').style.width = `${pct}%`;
    document.querySelectorAll('.cf-journey-step').forEach(el => {
        const step = steps.find(s => s.key === el.dataset.jstep);
        el.classList.toggle('done', !!(step && step.done));
    });
}

// ── Page Loader ─────────────────────────────────────────────────────────────
function initLoader() {
    const loader = document.getElementById('page-loader');
    setTimeout(() => loader.classList.add('hidden'), 1400);
}

// ── Init ────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initLoader();
    initNavigation();
    initSettings();
    checkApiKeyRequired();
    initResume();
    initJobs();
    initCareer();
    initInterview();
    initCoverLetter();
    initChat();
    initReviews();
    initFAQ();

    // Settings toggle icon
    const settingsToggle = document.getElementById('settings-toggle');
    if (settingsToggle) {
        settingsToggle.addEventListener('click', () => navigateTo('settings'));
    }
});
