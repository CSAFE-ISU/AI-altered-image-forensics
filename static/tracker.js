  const state = {
    records:           [],
    currentId:         null,
    currentType:       null,
    currentRating:     null,
    copyPerformed:     false,
    pendingAiFile:     null,
    p0CopyPerformed:   false,
    p1RenamePerformed: false,
    expandedStudies:   new Set(),
    filters:           { type: '', model: '', blankOnly: '', analysis: '' },
  };

  function lockField(id)   { const el = document.getElementById(id); if (el.tagName === 'SELECT') { el.disabled = true; } else { el.readOnly = true; } el.classList.add('auto-field'); }
  function unlockField(id) { const el = document.getElementById(id); if (el.tagName === 'SELECT') { el.disabled = false; } else { el.readOnly = false; } el.classList.remove('auto-field'); }

  // ── Server I/O ────────────────────────────────────────────────────────────

  async function loadRecords() {
    try {
      const res = await fetch('/api/records');
      const body = await res.json();
      if (!res.ok) {
        showStatus('header-status', 'Could not load records: ' + (body.error || res.status), 'warning');
        return;
      }
      state.records = Array.isArray(body) ? body : [];
      state.records.forEach(r => delete r.metadata_diff);
      renderSidebar();
      updateInputImageLabels();
      if (state.records.length) showStatus('header-status', state.records.length + ' records loaded', 'success');
    } catch {
      showStatus('header-status', 'Could not load records — server unreachable', 'warning');
    }
  }

  async function persistRecord(rec) {
    if (!rec) return true;
    try {
      const resp = await fetch('/api/records/' + encodeURIComponent(rec.id), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(rec)
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        showPersistentStatus('header-status', 'Save failed — ' + (body.error || 'server error') + '. Do not reload until you try again.', 'warning');
        return false;
      }
      return true;
    } catch {
      showPersistentStatus('header-status', 'Save failed — server unreachable. Do not reload until resolved.', 'warning');
      return false;
    }
  }

  function persistCurrentRecord() {
    return persistRecord(state.records.find(r => r.id === state.currentId));
  }

  async function persistRecords() {
    try {
      const resp = await fetch('/api/records', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(state.records)
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        showPersistentStatus('header-status', 'Save failed — ' + (body.error || 'server error') + '. Do not reload until you try again.', 'warning');
        return false;
      }
      return true;
    } catch {
      showPersistentStatus('header-status', 'Save failed — server unreachable. Do not reload until resolved.', 'warning');
      return false;
    }
  }

  function exportAll() {
    if (!state.records.length) { showStatus('header-status', 'No records to export', 'warning'); return; }
    const blob = new Blob([JSON.stringify(state.records, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'ai_image_records_' + new Date().toISOString().slice(0,10) + '.json';
    a.click();
    showStatus('header-status', state.records.length + ' records exported', 'success');
  }

  // ── ID generation ─────────────────────────────────────────────────────────

  function nextCsafeId() {
    const nums = state.records
      .map(r => r.study_id || '')
      .filter(f => /^csafe-\d+$/.test(f))
      .map(f => parseInt(f.replace('csafe-', ''), 10));
    const max = nums.length ? Math.max(...nums) : 0;
    return 'csafe-' + String(max + 1).padStart(3, '0');
  }

  // ── Sidebar ───────────────────────────────────────────────────────────────

  function setFilter(key, value) {
    state.filters[key] = value;
    renderSidebar();
  }

  function hasBlankFields(r) {
    if (r.type === 'p0') return !r.original_filename || r.c2pa_viewer_found == null;
    if (r.type === 'p1') return !r.input_image || !r.mod_type || !r.mod_details || !r.mod_filename || r.c2pa_viewer_found == null;
    if (r.type === 'p2') return !r.input_image || !r.model || !r.ai_assigned_filename || !r.prompt || !r.object || !r.subjective_quality || !r.region_altered || !r.mask_used || r.c2pa_viewer_found == null;
    if (r.type === 'p3') return r.c2pa_viewer_found == null;
    return false;
  }

  function highlightBlankFields(type) {
    const form = document.getElementById('form-' + type);
    if (!form) return;
    form.querySelectorAll('.field-blank').forEach(el => el.classList.remove('field-blank'));

    const flag = id => {
      const el = document.getElementById(id);
      if (el && !el.value.trim()) el.classList.add('field-blank');
    };

    if (type === 'p0') {
      flag('p0_original_filename');
    }
    if (type === 'p1') {
      flag('p1_input_select');
      flag('p1_mod_type');
      flag('p1_mod_details');
      flag('p1_mod_filename');
    }
    if (type === 'p2') {
      flag('p2_input_select');
      const modelSel = document.getElementById('p2_model');
      const isOther = modelSel && modelSel.value === '__other__';
      if (modelSel && !modelSel.value) modelSel.classList.add('field-blank');
      if (isOther) {
        const custom = document.getElementById('p2_model_custom');
        if (custom && !custom.value.trim()) custom.classList.add('field-blank');
      }
      flag('p2_ai_filename');
      flag('p2_prompt');
      flag('p2_prompt_type');
      flag('p2_object');
      flag('p2_mask');
      const ratingGroup = document.getElementById('p2-rating-group');
      if (ratingGroup) ratingGroup.classList.toggle('field-blank', !state.currentRating);
      const regionWrap = document.getElementById('region-picker-wrap');
      if (regionWrap) regionWrap.classList.toggle('field-blank', !document.getElementById('p2_region').value);
    }
  }

  function applyFilters(records) {
    const { type, model, blankOnly, analysis } = state.filters;
    return records.filter(r => {
      if (type && r.type !== type) return false;
      if (model && (r.type !== 'p2' || (r.model || '').trim() !== model)) return false;
      if (blankOnly === 'yes' && !hasBlankFields(r)) return false;
      if (blankOnly === 'no'  &&  hasBlankFields(r)) return false;
      if (analysis === 'yes' && r.exif_anomalies === undefined) return false;
      if (analysis === 'no'  && r.exif_anomalies !== undefined) return false;
      return true;
    });
  }

  function renderSidebar() {
    // Refresh model dropdown options from all p2 records
    const modelSel = document.getElementById('filter-model');
    const savedModel = state.filters.model;
    const allModels = [...new Set(state.records.filter(r => r.type === 'p2').map(r => (r.model || '').trim()).filter(Boolean))].sort((a, b) => a.localeCompare(b));
    modelSel.innerHTML = '<option value="">All</option>';
    allModels.forEach(m => {
      const opt = document.createElement('option');
      opt.value = m; opt.textContent = m;
      if (m === savedModel) opt.selected = true;
      modelSel.appendChild(opt);
    });

    const visible = applyFilters(state.records);

    // Group visible records by study_id (exclude p3 — shown separately)
    const studyMap = {};
    const unsorted = [];
    const analyses = [];
    visible.forEach(r => {
      if (r.type === 'p3') { analyses.push(r); return; }
      const sid = r.study_id || '';
      if (sid) {
        if (!studyMap[sid]) studyMap[sid] = [];
        studyMap[sid].push(r);
      } else {
        unsorted.push(r);
      }
    });

    // Sort study IDs numerically (csafe-001, csafe-002, …)
    const studyIds = Object.keys(studyMap).sort((a, b) => {
      const n = s => parseInt(s.replace(/\D+/g, ''), 10) || 0;
      return n(a) - n(b);
    });

    const tree = document.getElementById('study-tree');
    tree.innerHTML = '';

    studyIds.forEach(sid => {
      tree.appendChild(buildStudyNode(sid, studyMap[sid]));
    });

    if (unsorted.length) {
      const node = document.createElement('div');
      node.className = 'study-node';
      const hdr = document.createElement('div');
      hdr.className = 'study-header';
      hdr.innerHTML = '<span class="study-toggle"></span>Unsorted';
      node.appendChild(hdr);
      const children = document.createElement('div');
      children.className = 'study-children';
      unsorted.forEach(r => children.appendChild(buildRecordItem(r)));
      node.appendChild(children);
      tree.appendChild(node);
    }

    // Analyses section (p3 records)
    const analysesSection = document.getElementById('analyses-section');
    const analysesTree    = document.getElementById('analyses-tree');
    if (analyses.length) {
      analysesSection.style.display = '';
      analysesTree.innerHTML = '';
      analyses.forEach(r => analysesTree.appendChild(buildRecordItem(r)));
    } else {
      analysesSection.style.display = 'none';
    }

    const total = state.records.length;
    const shown = visible.length;
    const isFiltered = total !== shown;
    document.getElementById('record-count').textContent =
      total ? (isFiltered ? `${shown} of ${total} records` : `${total} record${total !== 1 ? 's' : ''}`) : '';
  }

  function buildStudyNode(sid, recs) {
    const isExpanded = state.expandedStudies.has(sid);
    const hasActive = recs.some(r => r.id === state.currentId);

    const node = document.createElement('div');
    node.className = 'study-node';

    const header = document.createElement('div');
    header.className = 'study-header' + (hasActive ? ' has-active' : '');

    const toggle = document.createElement('span');
    toggle.className = 'study-toggle';
    toggle.textContent = isExpanded ? '▾' : '▸';
    header.appendChild(toggle);
    header.appendChild(document.createTextNode(sid));

    header.onclick = () => {
      if (state.expandedStudies.has(sid)) state.expandedStudies.delete(sid);
      else state.expandedStudies.add(sid);
      renderSidebar();
    };
    node.appendChild(header);

    const children = document.createElement('div');
    children.className = 'study-children';
    children.style.display = isExpanded ? 'block' : 'none';

    // Sort: p0 → p1 → p2, then alphabetically within each type
    const sorted = [...recs].sort((a, b) => {
      const order = { p0: 0, p1: 1, p2: 2 };
      const td = (order[a.type] ?? 3) - (order[b.type] ?? 3);
      if (td !== 0) return td;
      return getRecordName(a).localeCompare(getRecordName(b));
    });
    sorted.forEach(r => children.appendChild(buildRecordItem(r)));
    node.appendChild(children);
    return node;
  }

  function buildRecordItem(rec) {
    const item = document.createElement('div');
    item.className = 'record-item' + (rec.id === state.currentId ? ' active' : '');
    item.onclick = () => selectRecord(rec.id);

    const nameEl = document.createElement('div');
    nameEl.className = 'record-item-name';
    nameEl.textContent = getRecordName(rec);
    item.appendChild(nameEl);

    const meta = getRecordMeta(rec);
    if (meta) {
      const metaEl = document.createElement('div');
      metaEl.className = 'record-item-meta';
      metaEl.textContent = meta;
      item.appendChild(metaEl);
    }
    return item;
  }

  function getRecordName(rec) {
    if (rec.type === 'p0') return (rec.study_id || 'csafe-???') + '.jpg';
    if (rec.type === 'p1') return rec.mod_filename || 'Untitled modification';
    if (rec.type === 'p2') return rec.altered_filename || 'Untitled alteration';
    if (rec.type === 'p3') return rec.uploaded_filename || 'New analysis';
    return 'Untitled';
  }

  function getRecordMeta(rec) {
    if (rec.type === 'p0') return 'original';
    if (rec.type === 'p1') return (rec.mod_type || 'modification').toLowerCase();
    if (rec.type === 'p2') return (rec.model || 'alteration').toLowerCase();
    if (rec.type === 'p3') return 'analysis';
    return '';
  }

  // ── New / Select record ───────────────────────────────────────────────────

  async function newRecord(type) {
    const id = 'rec_' + Date.now();
    // p0 gets a new study ID immediately; p1/p2 derive theirs from the input image on save
    const study_id = type === 'p0' ? nextCsafeId() : '';
    const rec = { id, type, study_id };
    state.records.unshift(rec);
    state.currentId = id;
    state.currentType = type;
    if (study_id) state.expandedStudies.add(study_id);
    renderSidebar();
    showFormArea(true);
    await showFormFor(type, rec);
    if (type === 'p0') { document.getElementById('p0_study_id').value = study_id; updateFormTitle(); }
  }

  function newAnalysis() {
    const id = 'rec_' + Date.now();
    const rec = { id, type: 'p3' };
    state.records.push(rec);
    state.currentId = id;
    state.currentType = 'p3';
    renderSidebar();
    showFormArea(true);
    showFormFor('p3', rec);
    // Reset upload form
    document.getElementById('p3-file-input').value = '';
    document.getElementById('p3-file-info').style.display = 'none';
    document.getElementById('p3-empty').style.display = 'none';
    document.getElementById('an-p3-results').style.display = 'none';
    document.getElementById('p3-notes-card').style.display = 'none';
    document.getElementById('p3-form-actions').style.display = 'none';
    document.getElementById('p3-status').className = 'status-msg';
    document.getElementById('form-title').textContent = 'New analysis';
  }

  async function selectRecord(id) {
    state.currentId = id;
    const rec = state.records.find(r => r.id === id);
    state.currentType = rec.type;
    state.currentRating = rec.subjective_quality || null;
    // Expand the study containing this record so it's visible
    if (rec.study_id) state.expandedStudies.add(rec.study_id);
    renderSidebar();
    showFormArea(true);
    await showFormFor(rec.type, rec);
  }

  function showFormArea(show) {
    document.getElementById('form-area').style.display = show ? 'block' : 'none';
    document.getElementById('no-record-msg').style.display = show ? 'none' : 'flex';
  }

  async function showFormFor(type, rec) {
    ['p0','p1','p2','p3'].forEach(t => document.getElementById('form-' + t).style.display = t === type ? 'block' : 'none');
    const labels = { p0: 'Page 0 — Original image', p1: 'Page 1 — Modification', p2: 'Page 2 — AI alteration', p3: 'Page 3 — Analysis' };
    document.getElementById('form-subtitle').textContent = labels[type] || '';
    if (type === 'p0') await fillP0(rec);
    if (type === 'p1') fillP1(rec);
    if (type === 'p2') fillP2(rec);
    if (type === 'p3') fillP3(rec);
  }

  // ── Fill forms ────────────────────────────────────────────────────────────

  async function fillP0(rec) {
    setVal('p0_study_id', rec.study_id);
    lockField('p0_study_id');
    setVal('p0_original_filename', rec.original_filename);
    setVal('p0_filesize', rec.filesize);
    setVal('p0_dims', rec.dims);
    setVal('p0_notes', rec.notes);
    updateFormTitle();
    refreshP0Preview();
    state.p0CopyPerformed = false;
    document.getElementById('btn-browse-original').disabled = false;
    await updateP0ComputedRename();
    fillAnalysisSection('p0', rec);
    highlightBlankFields('p0');
  }

  function fillP1(rec) {
    setVal('p1_input_select', rec.input_image || '');
    setVal('p1_mod_type', rec.mod_type);
    setVal('p1_mod_details', rec.mod_details);
    setVal('p1_mod_filesize', rec.mod_filesize);
    setVal('p1_mod_dims', rec.mod_dims);
    setVal('p1_mod_filename', rec.mod_filename);
    setVal('p1_current_filename', '');
    setVal('p1_notes', rec.notes);
    const btn = document.getElementById('p1-rename-btn');
    if (rec.mod_filename) {
      state.p1RenamePerformed = true;
      if (btn) btn.disabled = true;
      lockField('p1_mod_filename');
      lockField('p1_mod_type');
    } else {
      state.p1RenamePerformed = false;
      if (btn) btn.disabled = true;
      unlockField('p1_mod_filename');
      unlockField('p1_mod_type');
    }
    updateFormTitle();
    refreshP1Preview();
    fillAnalysisSection('p1', rec);
    highlightBlankFields('p1');
  }

  async function fillP2(rec) {
    setVal('p2_input_select', rec.input_image || '');
    setModelSelectValue(rec.model);
    setVal('p2_version', rec.model_version);
    setVal('p2_prompt', rec.prompt);
    setVal('p2_prompt_type', rec.prompt_strategy);
    setVal('p2_object', rec.object);
    setRegionPicker(rec.region_altered);
    setVal('p2_mask', rec.mask_used);
    setVal('p2_altered_filename', rec.altered_filename);
    setVal('p2_format', rec.output_format);
    setVal('p2_out_dims', rec.output_dimensions);
    setVal('p2_datetime', rec.datetime_generated);
    setVal('p2_notes', rec.notes);
    const wmYes = !!rec.visible_watermark;
    document.getElementById('p2_watermark_yes').checked = wmYes;
    document.getElementById('p2_watermark_no').checked = !wmYes;
    document.getElementById('p2_watermark_desc_wrap').style.display = wmYes ? '' : 'none';
    setVal('p2_watermark_desc', rec.watermark_description);

    state.currentRating = rec.subjective_quality || null;
    document.querySelectorAll('.rating-btn').forEach((b, i) => b.classList.toggle('selected', state.currentRating && i < state.currentRating));

    state.pendingAiFile = null;
    setVal('p2_ai_filename', rec.ai_assigned_filename || '');

    if (rec.altered_filename) {
      state.copyPerformed = true;
      lockField('p2_altered_filename');
      document.getElementById('btn-browse-p2-ai').disabled = true;
    } else {
      state.copyPerformed = false;
      clearCopyRenameStatus();
      document.getElementById('btn-browse-p2-ai').disabled = false;
    }

    updateFormTitle();
    refreshP2Preview();

    fillAnalysisSection('p2', rec);
    highlightBlankFields('p2');
  }

  // ── Analysis helpers ──────────────────────────────────────────────────────

  function parseC2paViewerJson(prefix) {
    const jsonStr = getVal('an-' + prefix + '-viewer-json').trim();
    if (!jsonStr) return;
    let data;
    try { data = JSON.parse(jsonStr); } catch { return; }

    // Locate the active manifest entry
    let manifest = data;
    if (data.manifests) {
      const key = data.active_manifest || Object.keys(data.manifests)[0];
      manifest = data.manifests[key] || manifest;
    }

    const sig = manifest.signature_info || {};

    // Signed by
    const signedBy = sig.issuer || manifest.issuer || data.issuer || '';
    if (signedBy) setVal('an-' + prefix + '-viewer-signed-by', signedBy);

    // Issued — ISO timestamp → YYYY-MM-DD for <input type="date">
    const rawTime = sig.time || sig.date || manifest.time || '';
    if (rawTime) setVal('an-' + prefix + '-viewer-issued', rawTime.substring(0, 10));

    // Algorithm
    const alg = sig.alg || sig.algorithm || manifest.alg || '';
    if (alg) setVal('an-' + prefix + '-viewer-algorithm', alg);

    // Software — prefer claim_generator_info array, fall back to claim_generator string
    const cgInfo = manifest.claim_generator_info;
    let software = '';
    if (Array.isArray(cgInfo) && cgInfo.length) {
      const entry = cgInfo[0];
      software = [entry.name, entry.version].filter(Boolean).join(' ');
    }
    if (!software) software = manifest.claim_generator || data.claim_generator || '';
    if (software) setVal('an-' + prefix + '-viewer-software', software.trim());
  }

  function toggleViewerDetails(prefix) {
    const yes = document.getElementById('an-' + prefix + '-viewer-found-yes');
    const no  = document.getElementById('an-' + prefix + '-viewer-found-no');
    const wrap = document.getElementById('an-' + prefix + '-viewer-details');
    if (wrap) wrap.style.display = yes?.checked ? '' : 'none';
    const foundField = document.getElementById('an-' + prefix + '-viewer-found-field');
    if (foundField) foundField.classList.toggle('field-blank', !yes?.checked && !no?.checked);
  }

  function fillViewerSection(prefix, rec) {
    const found = rec.c2pa_viewer_found;
    const yes = document.getElementById('an-' + prefix + '-viewer-found-yes');
    const no  = document.getElementById('an-' + prefix + '-viewer-found-no');
    if (yes) yes.checked = found === true;
    if (no)  no.checked  = found === false;
    const foundField = document.getElementById('an-' + prefix + '-viewer-found-field');
    if (foundField) foundField.classList.toggle('field-blank', found !== true && found !== false);
    const wrap = document.getElementById('an-' + prefix + '-viewer-details');
    if (wrap) wrap.style.display = found ? '' : 'none';
    setVal('an-' + prefix + '-viewer-signed-by',   rec.c2pa_viewer_signed_by   || '');
    setVal('an-' + prefix + '-viewer-issued',       rec.c2pa_viewer_issued      || '');
    setVal('an-' + prefix + '-viewer-algorithm',    rec.c2pa_viewer_algorithm   || '');
    setVal('an-' + prefix + '-viewer-cert-status',  rec.c2pa_viewer_cert_status || '');
    setVal('an-' + prefix + '-viewer-software',     rec.c2pa_viewer_software    || '');
    setVal('an-' + prefix + '-viewer-json',         rec.c2pa_viewer_json        || '');
    setVal('an-' + prefix + '-viewer-notes',        rec.c2pa_viewer_notes       || '');
  }

  function getViewerFields(prefix) {
    const yes = document.getElementById('an-' + prefix + '-viewer-found-yes');
    const no  = document.getElementById('an-' + prefix + '-viewer-found-no');
    const found = yes?.checked ? true : no?.checked ? false : null;
    return {
      c2pa_viewer_found:       found,
      c2pa_viewer_signed_by:   getVal('an-' + prefix + '-viewer-signed-by'),
      c2pa_viewer_issued:      getVal('an-' + prefix + '-viewer-issued'),
      c2pa_viewer_algorithm:   getVal('an-' + prefix + '-viewer-algorithm'),
      c2pa_viewer_cert_status: getVal('an-' + prefix + '-viewer-cert-status'),
      c2pa_viewer_software:    getVal('an-' + prefix + '-viewer-software'),
      c2pa_viewer_json:        getVal('an-' + prefix + '-viewer-json'),
      c2pa_viewer_notes:       getVal('an-' + prefix + '-viewer-notes'),
    };
  }

  function _buildC2paTable(tableEl, detailsEl, c2paDetails) {
    if (!detailsEl || !tableEl) return;
    if (!c2paDetails) { detailsEl.style.display = 'none'; return; }
    const d = c2paDetails;
    const rows = [];
    if (d.claim_generator)             rows.push(['Claim generator', d.claim_generator, null]);
    if (d.software_agent)              rows.push(['Software agent', d.software_agent, null]);
    if (d.c2pa_version)                rows.push(['C2PA version', d.c2pa_version, null]);
    if (d.actions?.length)             rows.push(['Actions', d.actions.join(', '), null]);
    if (d.digital_source_type)         rows.push(['Digital source type', d.digital_source_type, null]);
    if (d.manifest_id)                 rows.push(['Manifest ID', d.manifest_id, null]);
    if (d.validation_failures?.length) {
      rows.push(['Validation failures',
        d.validation_failure_explanations?.join('; ') || d.validation_failures.join('; '),
        'c2pa-warn']);
    } else if (rows.length) {
      rows.push(['Validation', 'All checks passed', 'c2pa-ok']);
    }
    tableEl.textContent = '';
    rows.forEach(([label, value, cls]) => {
      const tr = document.createElement('tr');
      const tdL = document.createElement('td'); tdL.textContent = label;
      const tdV = document.createElement('td'); tdV.textContent = value;
      if (cls) tdV.className = cls;
      tr.append(tdL, tdV);
      tableEl.appendChild(tr);
    });
    detailsEl.style.display = '';
  }

  function _buildIfd0Table(tableEl, detailsEl, ifd0Tags) {
    if (!detailsEl || !tableEl) return;
    if (!ifd0Tags || !Object.keys(ifd0Tags).length) { detailsEl.style.display = 'none'; return; }
    tableEl.textContent = '';
    Object.entries(ifd0Tags).forEach(([key, value]) => {
      const tr = document.createElement('tr');
      const tdL = document.createElement('td'); tdL.textContent = key.startsWith('IFD0:') ? key.slice(5) : key;
      const tdV = document.createElement('td'); tdV.textContent = value;
      tr.append(tdL, tdV);
      tableEl.appendChild(tr);
    });
    detailsEl.style.display = '';
  }

  function _buildIndicatorTable(tableEl, detailsEl, rows) {
    if (!detailsEl || !tableEl) return;
    if (!rows || !rows.length) { detailsEl.style.display = 'none'; return; }
    tableEl.textContent = '';
    rows.forEach(([label, value, cls]) => {
      const tr = document.createElement('tr');
      const tdL = document.createElement('td'); tdL.textContent = label;
      const tdV = document.createElement('td'); tdV.textContent = value;
      if (cls) tdV.className = cls;
      tr.append(tdL, tdV);
      tableEl.appendChild(tr);
    });
    detailsEl.style.display = '';
  }

  function _fillIndicatorsSection(prefix, rec) {
    const ind = rec.indicators;
    setVal('an-' + prefix + '-indicators-summary', ind?.summary || '');

    // Camera EXIF
    const camRows = ind?.camera_exif ? [
      ...Object.entries(ind.camera_exif.present).map(([k, v]) => [k, v, null]),
      ...(ind.camera_exif.absent.length ? [['Absent', ind.camera_exif.absent.join(', '), 'c2pa-warn']] : []),
    ] : null;
    _buildIndicatorTable(
      document.getElementById('an-' + prefix + '-camera-exif-table'),
      document.getElementById('an-' + prefix + '-camera-exif-details'),
      camRows
    );

    // Photoshop/Adobe
    const psRows = ind?.photoshop_adobe
      ? Object.entries(ind.photoshop_adobe).map(([k, v]) => [k.replace(/^(Photoshop|Adobe):/, ''), v, null])
      : null;
    _buildIndicatorTable(
      document.getElementById('an-' + prefix + '-photoshop-table'),
      document.getElementById('an-' + prefix + '-photoshop-details'),
      psRows
    );

    // ICC meas/view
    const iccRows = ind?.icc_meas_view
      ? Object.entries(ind.icc_meas_view).map(([k, v]) => [k.replace(/^ICC-(meas|view):/, ''), v, null])
      : null;
    _buildIndicatorTable(
      document.getElementById('an-' + prefix + '-icc-table'),
      document.getElementById('an-' + prefix + '-icc-details'),
      iccRows
    );

    // Grok signatures
    const grokRows = ind?.grok_signatures ? [
      ...(ind.grok_signatures.artist      ? [['Artist (UUID)',  ind.grok_signatures.artist,       'c2pa-warn']] : []),
      ...(ind.grok_signatures.user_comment ? [['UserComment',   ind.grok_signatures.user_comment,  'c2pa-warn']] : []),
    ] : null;
    _buildIndicatorTable(
      document.getElementById('an-' + prefix + '-grok-table'),
      document.getElementById('an-' + prefix + '-grok-details'),
      grokRows
    );

    // C2PA auto-detected
    const c2pa = ind?.c2pa;
    const c2paRows = c2pa ? (() => {
      const rows = [['Status', c2pa.status || '', null]];
      if (c2pa.claim_generator)         rows.push(['Claim generator', c2pa.claim_generator, null]);
      if (c2pa.software_agent)          rows.push(['Software agent', c2pa.software_agent, null]);
      if (c2pa.c2pa_version)            rows.push(['C2PA version', c2pa.c2pa_version, null]);
      if (c2pa.actions?.length)         rows.push(['Actions', c2pa.actions.join(', '), null]);
      if (c2pa.digital_source_type)     rows.push(['Digital source type', c2pa.digital_source_type, null]);
      if (c2pa.manifest_id)             rows.push(['Manifest ID', c2pa.manifest_id, null]);
      if (c2pa.validation_failures?.length) {
        rows.push(['Validation', c2pa.validation_failure_explanations?.join('; ') || c2pa.validation_failures.join('; '), 'c2pa-warn']);
      } else if (rows.length > 1) {
        rows.push(['Validation', 'All checks passed', 'c2pa-ok']);
      }
      return rows;
    })() : null;
    _buildIndicatorTable(
      document.getElementById('an-' + prefix + '-c2pa-table'),
      document.getElementById('an-' + prefix + '-c2pa-details'),
      c2paRows
    );
  }

  function _renderElaPreview(previewId, imgId, b64) {
    const preview = document.getElementById(previewId);
    const img     = document.getElementById(imgId);
    if (!preview || !img) return;
    if (b64) {
      img.src = 'data:image/png;base64,' + b64;
      preview.style.display = '';
    } else {
      preview.style.display = 'none';
    }
  }

  function fillAnalysisSection(prefix, rec) {
    const hasViewerData = rec.c2pa_viewer_found !== null && rec.c2pa_viewer_found !== undefined || !!rec.c2pa_viewer_notes;
    const hasData = rec.indicators || rec.exif_anomalies || rec.c2pa_status || (rec.artifacts && rec.artifacts.length) || rec.artifact_notes || hasViewerData;
    const section  = document.getElementById('an-' + prefix + '-section');
    const empty    = document.getElementById('an-' + prefix + '-empty');
    const results  = document.getElementById('an-' + prefix + '-results');
    if (!section) return;
    const analyzeBtn = document.getElementById('btn-analyze-' + prefix);
    if (!hasData) {
      if (empty) empty.style.display = '';
      if (results) results.style.display = 'none';
      if (analyzeBtn) analyzeBtn.style.display = '';
      section.open = false;
      _fillIndicatorsSection(prefix, rec);
      fillViewerSection(prefix, rec);
      return;
    }
    if (empty) empty.style.display = 'none';
    if (results) results.style.display = '';
    if (analyzeBtn) analyzeBtn.style.display = 'none';
    section.open = true;

    _fillIndicatorsSection(prefix, rec);
    setVal('an-' + prefix + '-artifact-notes', rec.artifact_notes);

    // Artifact tags
    const listEl = document.getElementById('an-' + prefix + '-artifact-list');
    if (listEl) {
      listEl.innerHTML = '';
      (rec.artifacts || []).forEach(a => {
        const tag = document.createElement('span');
        tag.className = 'artifact-tag';
        tag.textContent = a;
        listEl.appendChild(tag);
      });
    }

    fillViewerSection(prefix, rec);
    _renderElaPreview('an-' + prefix + '-ela-preview', 'an-' + prefix + '-ela-img', rec.ela_image_b64);
  }

  function fillP3(rec) {
    document.getElementById('form-title').textContent = rec.uploaded_filename || 'Analysis';
    if (rec.uploaded_filename) {
      setVal('p3-filename-display', rec.uploaded_filename);
      setVal('p3-filesize-display', rec.filesize || '');
      setVal('p3-dims-display', rec.dims || '');
      setVal('p3-linked-display', rec.linked_record || 'Standalone');
      document.getElementById('p3-file-info').style.display = '';
      document.getElementById('an-p3-results').style.display = '';
      document.getElementById('p3-notes-card').style.display = '';
      document.getElementById('p3-form-actions').style.display = '';
      document.getElementById('p3-empty').style.display = 'none';

      _fillIndicatorsSection('p3', rec);
      setVal('an-p3-artifact-notes', rec.artifact_notes);
      setVal('p3-analysis-notes', rec.analysis_notes);

      const listEl = document.getElementById('an-p3-artifact-list');
      if (listEl) {
        listEl.innerHTML = '';
        (rec.artifacts || []).forEach(a => {
          const tag = document.createElement('span');
          tag.className = 'artifact-tag';
          tag.textContent = a;
          listEl.appendChild(tag);
        });
      }

      fillViewerSection('p3', rec);
      _renderElaPreview('an-p3-ela-preview', 'an-p3-ela-img', rec.ela_image_b64);
    } else {
      document.getElementById('p3-file-info').style.display = 'none';
      document.getElementById('an-p3-results').style.display = 'none';
      document.getElementById('p3-notes-card').style.display = 'none';
      document.getElementById('p3-form-actions').style.display = 'none';
      document.getElementById('p3-empty').style.display = 'none';
    }
  }

  async function uploadAndAnalyze() {
    const fileInput = document.getElementById('p3-file-input');
    if (!fileInput.files.length) {
      showStatus('p3-status', 'Select a file first', 'warning');
      return;
    }
    const file = fileInput.files[0];
    const btn = document.getElementById('p3-upload-btn');
    btn.disabled = true;
    showStatus('p3-status', 'Uploading…', '');

    try {
      const formData = new FormData();
      formData.append('file', file);
      const resp = await fetch('/api/upload_and_analyze', { method: 'POST', body: formData });
      const result = await resp.json();
      if (!resp.ok) {
        showStatus('p3-status', result.error || 'Upload failed', 'warning');
        return;
      }

      // Try to match filename against existing records
      const fn = result.filename;
      const matched = state.records.find(r =>
        r.original_filename === fn || r.renamed_filename === fn ||
        r.mod_filename === fn || r.altered_filename === fn ||
        r.ai_assigned_filename === fn || r.uploaded_filename === fn
      );

      if (matched) {
        // Attach analysis to existing record and navigate to it
        Object.assign(matched, {
          exif_anomalies:  result.exif_anomalies,
          c2pa_status:     result.c2pa_status,
          c2pa_details:    result.c2pa_details,
          artifacts:       result.artifacts,
          artifact_notes:  result.artifact_notes,
          ela_image_b64:   result.ela_image_b64,
          ela_max_diff:    result.ela_max_diff,
          ela_mean_diff:   result.ela_mean_diff,
          ela_std_diff:    result.ela_std_diff,
          ela_source:      result.ela_source,
          block_noise_std: result.block_noise_std,
          noise_skewness:  result.noise_skewness,
          noise_kurtosis:  result.noise_kurtosis,
        });
        // Remove the blank p3 placeholder we created in newAnalysis()
        const placeholderId = state.currentId;
        state.records = state.records.filter(r => r.id !== placeholderId);
        await fetch('/api/records/' + encodeURIComponent(placeholderId), { method: 'DELETE' });
        await persistRecord(matched);
        selectRecord(matched.id);
        showStatus('header-status', 'Analysis linked to ' + getRecordName(matched), 'success');
      } else {
        // Save as standalone p3 record
        const rec = state.records.find(r => r.id === state.currentId);
        Object.assign(rec, {
          uploaded_filename: result.filename,
          filesize:          result.filesize,
          dims:              result.dims,
          uploaded_at:       new Date().toISOString(),
          exif_anomalies:    result.exif_anomalies,
          c2pa_status:       result.c2pa_status,
          c2pa_details:      result.c2pa_details,
          artifacts:         result.artifacts,
          artifact_notes:    result.artifact_notes,
          ela_image_b64:     result.ela_image_b64,
          ela_max_diff:      result.ela_max_diff,
          ela_mean_diff:     result.ela_mean_diff,
          ela_std_diff:      result.ela_std_diff,
          ela_source:        result.ela_source,
          block_noise_std:   result.block_noise_std,
          noise_skewness:    result.noise_skewness,
          noise_kurtosis:    result.noise_kurtosis,
          analysis_notes:    '',
          linked_record:     ''
        });
        renderSidebar();
        fillP3(rec);
        await persistCurrentRecord();
        showStatus('p3-status', 'Analysis complete', 'success');
      }
    } catch (err) {
      showStatus('p3-status', 'Error: ' + err.message, 'warning');
    } finally {
      btn.disabled = false;
    }
  }

  // ── Analyze ───────────────────────────────────────────────────────────────

  async function runAnalysis(type) {
    const rec = state.records.find(r => r.id === state.currentId);
    if (!rec) return;

    const filenameMap = { p0: rec.renamed_filename, p1: rec.mod_filename, p2: rec.altered_filename };
    const filename = filenameMap[type];
    const statusId = 'status-analyze-' + type;

    if (!filename) {
      showStatus(statusId, 'Save the record first to generate a filename', 'warning');
      return;
    }

    const btn = document.getElementById('btn-analyze-' + type);
    btn.disabled = true;
    showPersistentStatus(statusId, 'Analyzing…', '');

    try {
      const resp = await fetch('/api/analyze_file', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename })
      });
      const result = await resp.json();
      if (!resp.ok) {
        showStatus(statusId, result.error || 'Analysis failed', 'warning');
        return;
      }
      Object.assign(rec, {
        exif_anomalies:  result.exif_anomalies,
        ifd0_tags:       result.ifd0_tags,
        indicators:      result.indicators,
        c2pa_status:     result.c2pa_status,
        c2pa_details:    result.c2pa_details,
        artifacts:       result.artifacts,
        artifact_notes:  result.artifact_notes,
        ela_image_b64:   result.ela_image_b64,
        ela_max_diff:    result.ela_max_diff,
        ela_mean_diff:   result.ela_mean_diff,
        ela_std_diff:    result.ela_std_diff,
        ela_source:      result.ela_source,
        block_noise_std: result.block_noise_std,
        noise_skewness:  result.noise_skewness,
        noise_kurtosis:  result.noise_kurtosis,
      });
      fillAnalysisSection(type, rec);
      document.getElementById('an-' + type + '-results')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      const saved = await persistCurrentRecord();
      if (saved !== false) {
        showStatus(statusId, 'Analysis complete', 'success');
        document.getElementById('btn-analyze-' + type).style.display = 'none';
      }
    } catch (err) {
      showStatus(statusId, 'Error: ' + err.message, 'warning');
    } finally {
      btn.disabled = false;
    }
  }

  // ── Input change handlers ─────────────────────────────────────────────────

  function p1InputChanged() {
    const rec = state.records.find(r => r.id === state.currentId);
    if (rec) rec.input_image = document.getElementById('p1_input_select').value;
    suggestModFilename();
    refreshP1Preview();
  }

  function suggestModFilename() {
    if (state.p1RenamePerformed) return;
    const input = document.getElementById('p1_input_select').value;
    const modType = document.getElementById('p1_mod_type').value.toLowerCase();
    const btn = document.getElementById('p1-rename-btn');
    if (!input || !modType) { if (btn) btn.disabled = true; return; }
    const dotIdx = input.lastIndexOf('.');
    const base = dotIdx > -1 ? input.slice(0, dotIdx) : input;
    const ext = dotIdx > -1 ? input.slice(dotIdx) : '.jpg';
    const suffixes = { cropped: '-cropped', resized: '-small', recompressed: '-recomp', rotated: '-rot', other: '-mod' };
    const suffix = suffixes[modType] || '-mod';
    document.getElementById('p1_mod_filename').value = base + suffix + ext;
    if (btn) btn.disabled = false;
    updateFormTitle();
    refreshP1Preview();
  }

  function p2InputChanged() {
    const val = document.getElementById('p2_input_select').value;
    if (!val) return;
    const rec = state.records.find(r => r.id === state.currentId);
    if (rec) rec.input_image = val;
    updateFormTitle();
    refreshP2Preview();
    updateComputedRename();
    maybeAutoSaveAndRename();
  }

  // ── Save ──────────────────────────────────────────────────────────────────

  async function saveRecord() {
    const rec = state.records.find(r => r.id === state.currentId);
    if (!rec) return;

    if (rec.type === 'p0') {
      Object.assign(rec, {
        study_id: getVal('p0_study_id'),
        original_filename: getVal('p0_original_filename'),
        renamed_filename: getVal('p0_renamed_filename'),
        filesize: getVal('p0_filesize'),
        dims: getVal('p0_dims'),
        notes: getVal('p0_notes'),
        ...getViewerFields('p0')
      });
      showStatus('status-p0', 'Saved', 'success');
    }

    if (rec.type === 'p1') {
      const inputVal = document.getElementById('p1_input_select').value;
      Object.assign(rec, {
        input_image: inputVal,
        study_id: deriveStudyId(inputVal),
        mod_type: getVal('p1_mod_type'),
        mod_details: getVal('p1_mod_details'),
        mod_filesize: getVal('p1_mod_filesize'),
        mod_dims: getVal('p1_mod_dims'),
        mod_filename: getVal('p1_mod_filename'),
        notes: getVal('p1_notes'),
        ...getViewerFields('p1')
      });
      showStatus('status-p1', 'Saved', 'success');
    }

    if (rec.type === 'p2') {
      const inputVal = document.getElementById('p2_input_select').value;
      Object.assign(rec, {
        input_image: inputVal,
        study_id: deriveStudyId(inputVal),
        model: document.getElementById('p2_model').value === '__other__' ? getVal('p2_model_custom') : getVal('p2_model'),
        model_version: getVal('p2_version'),
        prompt: getVal('p2_prompt'),
        prompt_strategy: getVal('p2_prompt_type'),
        object: getVal('p2_object'),
        region_altered: getVal('p2_region'),
        mask_used: getVal('p2_mask'),
        ai_assigned_filename: getVal('p2_ai_filename'),
        altered_filename: getVal('p2_altered_filename'),
        output_format: getVal('p2_format'),
        output_dimensions: getVal('p2_out_dims'),
        datetime_generated: getVal('p2_datetime'),
        subjective_quality: state.currentRating,
        visible_watermark: document.getElementById('p2_watermark_yes').checked,
        watermark_description: getVal('p2_watermark_desc'),
        notes: getVal('p2_notes'),
        ...getViewerFields('p2')
      });
      showStatus('status-p2a', 'Saved', 'success');
    }

    if (rec.type === 'p3') {
      Object.assign(rec, { analysis_notes: getVal('p3-analysis-notes'), ...getViewerFields('p3') });
      showStatus('status-p3', 'Saved', 'success');
    }

    renderSidebar();
    await persistCurrentRecord();
  }

  function deriveStudyId(filename) {
    if (!filename) return '';
    const match = filename.match(/^(csafe-\d+)/i);
    return match ? match[1] : '';
  }

  // ── Delete / Clear ────────────────────────────────────────────────────────

  async function deleteRecord() {
    if (!state.currentId || !confirm('Delete this record? This cannot be undone.')) return;
    const idToDelete = state.currentId;
    state.records = state.records.filter(r => r.id !== idToDelete);
    state.currentId = null; state.currentType = null;
    renderSidebar(); showFormArea(false);
    try {
      await fetch('/api/records/' + encodeURIComponent(idToDelete), { method: 'DELETE' });
    } catch { /* silently ignore — record is already removed from local state */ }
  }

  function clearCurrentForm() {
    if (!confirm('Clear all fields? Unsaved changes will be lost.')) return;
    const rec = state.records.find(r => r.id === state.currentId);
    if (!rec) return;
    const { id, type, study_id } = rec;
    state.records = state.records.map(r => r.id === id ? { id, type, study_id } : r);
    showFormFor(type, { id, type, study_id });
  }

  // ── Rating ────────────────────────────────────────────────────────────────

  function setRating(val) {
    state.currentRating = val;
    document.querySelectorAll('.rating-btn').forEach((b, i) => b.classList.toggle('selected', i < val));
    highlightBlankFields('p2');
  }

  // ── Artifacts ─────────────────────────────────────────────────────────────

  function toggleArtifact(label) {
    setTimeout(() => label.classList.toggle('checked', label.querySelector('input').checked), 0);
  }

  // ── Image previews ────────────────────────────────────────────────────────

  function setImgSlot(imgId, captionSpanId, missId, filename) {
    const img = document.getElementById(imgId);
    const cap = document.getElementById(captionSpanId);
    const miss = document.getElementById(missId);
    if (!filename) {
      img.style.display = 'none';
      miss.style.display = 'none';
      cap.textContent = '';
      return;
    }
    cap.textContent = ' — ' + filename;
    img.style.display = 'block';
    miss.style.display = 'none';
    img.src = '/images/' + encodeURIComponent(filename);
    img.onload = () => { img.style.display = 'block'; miss.style.display = 'none'; };
    img.onerror = () => { img.style.display = 'none'; miss.style.display = 'block'; };
  }

  function refreshP0Preview() {
    const fn = getVal('p0_original_filename');
    const card = document.getElementById('prev-p0');
    card.style.display = fn ? 'block' : 'none';
    setImgSlot('img-p0', 'cap-p0', 'miss-p0', fn);
  }

  function refreshP1Preview() {
    const inputFn = document.getElementById('p1_input_select').value;
    const outputFn = getVal('p1_mod_filename');
    const card = document.getElementById('prev-p1');
    card.style.display = (inputFn || outputFn) ? 'block' : 'none';
    setImgSlot('img-p1-input',  'cap-p1-input',  'miss-p1-input',  inputFn);
    setImgSlot('img-p1-output', 'cap-p1-output', 'miss-p1-output', outputFn);
  }

  function refreshP2Preview() {
    const inputFn = document.getElementById('p2_input_select').value;
    const outputFn = getVal('p2_altered_filename');
    const card = document.getElementById('prev-p2');
    card.style.display = (inputFn || outputFn) ? 'block' : 'none';
    setImgSlot('img-p2-input',  'cap-p2-input',  'miss-p2-input',  inputFn);
    setImgSlot('img-p2-output', 'cap-p2-output', 'miss-p2-output', outputFn);
    updateRegionPickerImage(outputFn);
  }

  function selectRegion(cell) {
    cell.classList.toggle('selected');
    const selected = [...document.querySelectorAll('.region-cell.selected')]
      .map(c => c.dataset.region);
    document.getElementById('p2_region').value = selected.join(',');
    highlightBlankFields('p2');
    autoSave();
  }

  function setRegionPicker(value) {
    const values = (value || '').split(',').map(s => s.trim()).filter(Boolean);
    document.querySelectorAll('.region-cell').forEach(c =>
      c.classList.toggle('selected', values.includes(c.dataset.region))
    );
    document.getElementById('p2_region').value = value || '';
  }

  function updateRegionPickerImage(filename) {
    const img = document.getElementById('region-picker-img');
    const placeholder = document.getElementById('region-picker-placeholder');
    if (!img || !placeholder) return;
    if (filename) {
      img.src = '/images/' + encodeURIComponent(filename);
      img.style.display = 'block';
      placeholder.style.display = 'none';
      img.onerror = () => {
        img.style.display = 'none';
        placeholder.style.display = 'flex';
        placeholder.textContent = 'Image not found';
      };
    } else {
      img.style.display = 'none';
      img.src = '';
      placeholder.style.display = 'flex';
      placeholder.textContent = 'Select altered image above to enable region picker';
    }
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  function getVal(id) { return document.getElementById(id)?.value?.trim() || ''; }
  function setVal(id, val) { const el = document.getElementById(id); if (el) el.value = val || ''; }

  function updateFormTitle() {
    let title = 'Untitled record';
    if (state.currentType === 'p0') title = document.getElementById('p0_study_id')?.value || 'Untitled original';
    if (state.currentType === 'p1') title = document.getElementById('p1_mod_filename')?.value || 'Untitled modification';
    if (state.currentType === 'p2') title = document.getElementById('p2_altered_filename')?.value || 'Untitled alteration';
    if (state.currentType === 'p3') { const rec = state.records.find(r => r.id === state.currentId); title = rec?.uploaded_filename || 'New analysis'; }
    document.getElementById('form-title').textContent = title;
  }

  function autoSave() { persistCurrentRecord(); }

  function showStatus(id, msg, type) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = msg; el.className = 'status-msg ' + type;
    setTimeout(() => { el.className = 'status-msg'; }, 3000);
  }

  function handleModelSelect(sel) {
    const custom = document.getElementById('p2_model_custom');
    custom.style.display = sel.value === '__other__' ? 'block' : 'none';
    if (sel.value !== '__other__') custom.value = '';
    // If the file was already uploaded (pendingAiFile cleared), the destination folder
    // was model-specific — must re-browse. If still pending, keep the file reference.
    if (!state.pendingAiFile) {
      setVal('p2_ai_filename', '');
    }
    setVal('p2_altered_filename', '');
    state.copyPerformed = false;
    updateComputedRename();
    maybeAutoSaveAndRename();
  }

  // ── Dynamic model + file lists ────────────────────────────────────────────

  async function loadInputImages() {
    try {
      const res = await fetch('/api/input_images');
      const { original = [], modified = [] } = await res.json();
      ['p1_input_select', 'p2_input_select'].forEach(id => {
        const sel = document.getElementById(id);
        sel.innerHTML = '<option value="">— select —</option>';
        if (original.length) {
          const grp = document.createElement('optgroup');
          grp.label = 'Original images';
          original.forEach(f => {
            const opt = document.createElement('option');
            opt.value = f; opt.textContent = f;
            grp.appendChild(opt);
          });
          sel.appendChild(grp);
        }
        if (modified.length) {
          const grp = document.createElement('optgroup');
          grp.label = 'Modified images';
          modified.forEach(f => {
            const opt = document.createElement('option');
            opt.value = f; opt.textContent = f;
            grp.appendChild(opt);
          });
          sel.appendChild(grp);
        }
      });
    } catch { /* keep existing options */ }
  }

  function updateInputImageLabels() {
    const map = {};
    state.records.forEach(r => {
      if (r.type === 'p0' && r.renamed_filename && r.original_filename) {
        map[r.renamed_filename] = r.original_filename;
      }
    });
    ['p1_input_select', 'p2_input_select'].forEach(id => {
      const sel = document.getElementById(id);
      for (const opt of sel.options) {
        if (!opt.value) continue;
        const orig = map[opt.value];
        opt.textContent = orig ? `${opt.value} (${orig})` : opt.value;
      }
    });
  }

  async function loadModels() {
    try {
      const res = await fetch('/api/models');
      const models = await res.json();
      const sel = document.getElementById('p2_model');
      const otherOpt = sel.querySelector('option[value="__other__"]');
      sel.innerHTML = '';
      const blank = document.createElement('option');
      blank.value = ''; blank.textContent = '— select —';
      sel.appendChild(blank);
      models.forEach(m => {
        const opt = document.createElement('option');
        opt.value = m; opt.textContent = m;
        sel.appendChild(opt);
      });
      sel.appendChild(otherOpt);
    } catch { /* keep existing options */ }
  }

  function setModelSelectValue(model) {
    const sel = document.getElementById('p2_model');
    const custom = document.getElementById('p2_model_custom');
    if (!model) {
      sel.value = ''; custom.style.display = 'none'; custom.value = ''; return;
    }
    const modelLower = model.toLowerCase();
    // Exact match first, then case-insensitive
    for (const opt of sel.options) {
      if (opt.value === model) { sel.value = model; custom.style.display = 'none'; custom.value = ''; return; }
    }
    for (const opt of sel.options) {
      if (opt.value !== '__other__' && opt.value.toLowerCase() === modelLower) {
        sel.value = opt.value; custom.style.display = 'none'; custom.value = ''; return;
      }
    }
    // Fall back to custom
    sel.value = '__other__'; custom.style.display = 'block'; custom.value = model;
  }

  // ── Copy and Rename ───────────────────────────────────────────────────────

  function getP2Model() {
    const sel = document.getElementById('p2_model');
    if (sel.value === '__other__') return document.getElementById('p2_model_custom').value.trim();
    return sel.value;
  }

  function clearCopyRenameStatus() {
    const el = document.getElementById('status-copy-rename');
    if (el) el.className = 'status-msg';
  }

  function showPersistentStatus(id, msg, type) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = msg;
    el.className = 'status-msg ' + type;
  }

  async function updateComputedRename() {
    if (state.copyPerformed) return;
    const inputImage = document.getElementById('p2_input_select').value;
    const aiFilename = getVal('p2_ai_filename');
    const model = getP2Model();
    if (!inputImage || !aiFilename || !model) return;

    try {
      const res = await fetch(
        '/api/compute_renamed?input_image=' + encodeURIComponent(inputImage) +
        '&ai_filename=' + encodeURIComponent(aiFilename) +
        '&model=' + encodeURIComponent(model)
      );
      const data = await res.json();
      if (data.filename) {
        setVal('p2_altered_filename', data.filename);
        updateFormTitle();
        refreshP2Preview();
      }
    } catch {
      // silently ignore — fields stay as-is
    }
  }

  async function maybeAutoSaveAndRename() {
    if (state.copyPerformed) return;
    const inputImage = document.getElementById('p2_input_select').value;
    const model = getP2Model();
    if (!inputImage || !model || !getVal('p2_ai_filename')) return;

    showPersistentStatus('status-copy-rename', 'Saving…', 'warning');
    try {
      if (state.pendingAiFile) {
        const uploadData = await uploadFile(state.pendingAiFile, '/api/upload_downloaded', { model });
        if (!uploadData.ok) {
          showPersistentStatus('status-copy-rename', uploadData.error || 'Upload failed', 'warning');
          return;
        }
        state.pendingAiFile = null;
        // Server may sanitize the filename (e.g. remove spaces); use the returned name
        setVal('p2_ai_filename', uploadData.filename);
        await populateImageInfo();
      }

      // Re-read after potential update from upload above
      const aiFilename = getVal('p2_ai_filename');
      const res = await fetch('/api/copy_rename_image', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ input_image: inputImage, ai_filename: aiFilename, model })
      });
      const data = await res.json();
      if (data.warning) {
        showStatus('status-copy-rename', data.warning, 'warning');
        if (data.filename) {
          setVal('p2_altered_filename', data.filename);
          updateFormTitle();
          refreshP2Preview();
          state.copyPerformed = true;
          lockField('p2_altered_filename');
          document.getElementById('btn-browse-p2-ai').disabled = true;
        }
      } else if (data.ok) {
        setVal('p2_altered_filename', data.filename);
        updateFormTitle();
        refreshP2Preview();
        showStatus('status-copy-rename', 'Saved → ' + data.filename, 'success');
        state.copyPerformed = true;
        lockField('p2_altered_filename');
        document.getElementById('btn-browse-p2-ai').disabled = true;
      } else {
        showPersistentStatus('status-copy-rename', data.error || 'Copy failed', 'warning');
      }
    } catch {
      showPersistentStatus('status-copy-rename', 'Copy failed — server unreachable', 'warning');
    }
  }

  async function populateP0ImageInfo() {
    const filename = getVal('p0_original_filename');
    if (!filename) return;
    try {
      const res = await fetch('/api/original_image_info?filename=' + encodeURIComponent(filename));
      const data = await res.json();
      if (data.filesize) setVal('p0_filesize', data.filesize);
      if (data.dimensions) setVal('p0_dims', data.dimensions);
    } catch { /* silently ignore */ }
  }

  async function populateP1ImageInfo() {
    const filename = getVal('p1_mod_filename');
    if (!filename) return;
    try {
      const res = await fetch('/api/original_image_info?filename=' + encodeURIComponent(filename));
      const data = await res.json();
      if (data.filesize) setVal('p1_mod_filesize', data.filesize);
      if (data.dimensions) setVal('p1_mod_dims', data.dimensions);
    } catch { /* silently ignore */ }
  }

  async function populateImageInfo() {
    const model = getP2Model();
    const filename = getVal('p2_ai_filename');
    if (!model || !filename) return;
    try {
      const res = await fetch(
        '/api/image_info?model=' + encodeURIComponent(model) +
        '&filename=' + encodeURIComponent(filename)
      );
      const data = await res.json();
      if (data.format) setVal('p2_format', data.format);
      if (data.dimensions) setVal('p2_out_dims', data.dimensions);
    } catch { /* silently ignore */ }
  }


  async function uploadFile(file, endpoint, extraFields) {
    const form = new FormData();
    form.append('file', file);
    if (extraFields) for (const [k, v] of Object.entries(extraFields)) form.append(k, v);
    const res = await fetch(endpoint, { method: 'POST', body: form });
    return await res.json();
  }

  async function onOriginalFilePicked(input) {
    if (!input.files.length) return;
    const file = input.files[0];
    input.value = '';
    const dup = state.records.find(r => r.type === 'p0' && r.original_filename === file.name);
    if (dup) {
      showPersistentStatus('status-copy-rename-original',
        `This original image already exists in the database (study ID: ${dup.study_id}).`, 'warning');
      return;
    }
    showPersistentStatus('status-copy-rename-original', 'Copying…', 'warning');
    try {
      const uploadData = await uploadFile(file, '/api/upload_original');
      if (!uploadData.ok) {
        showPersistentStatus('status-copy-rename-original', uploadData.error || 'Upload failed', 'warning');
        return;
      }
      setVal('p0_original_filename', uploadData.filename);
      highlightBlankFields('p0');
      refreshP0Preview();
      populateP0ImageInfo();

      const studyId = getVal('p0_study_id');
      const res = await fetch('/api/copy_rename_original', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ original_filename: uploadData.filename, study_id: studyId }),
      });
      const copyData = await res.json();
      if (copyData.ok || copyData.warning) {
        setVal('p0_renamed_filename', copyData.filename);
        const msg = copyData.warning || ('Copied → ' + copyData.filename);
        showPersistentStatus('status-copy-rename-original', msg, copyData.warning ? 'warning' : 'success');
        document.getElementById('btn-browse-original').disabled = true;
        state.p0CopyPerformed = true;
      } else {
        showPersistentStatus('status-copy-rename-original', copyData.error || 'Copy failed', 'warning');
      }
    } catch {
      showPersistentStatus('status-copy-rename-original', 'Copy failed — server unreachable', 'warning');
    }
  }

  async function onP1ModFilePicked(input) {
    if (!input.files.length) return;
    const file = input.files[0];
    input.value = '';
    const destFilename = getVal('p1_mod_filename');
    if (!destFilename) {
      showStatus('status-p1-rename', 'Set the modification type first to generate a filename', 'warning');
      return;
    }
    showPersistentStatus('status-p1-rename', 'Copying…', 'warning');
    try {
      const data = await uploadFile(file, '/api/upload_modified', { dest_filename: destFilename });
      if (data.warning) {
        showPersistentStatus('status-p1-rename', data.warning, 'warning');
      } else if (data.ok) {
        state.p1RenamePerformed = true;
        document.getElementById('p1-rename-btn').disabled = true;
        setVal('p1_current_filename', file.name);
        lockField('p1_mod_filename');
        lockField('p1_mod_type');
        highlightBlankFields('p1');
        showPersistentStatus('status-p1-rename', 'Copied → ' + data.filename, 'success');
        refreshP1Preview();
        await populateP1ImageInfo();
      } else {
        showPersistentStatus('status-p1-rename', data.error || 'Copy failed', 'warning');
      }
    } catch {
      showPersistentStatus('status-p1-rename', 'Copy failed — server unreachable', 'warning');
    }
  }

  async function onAiFilePicked(input) {
    if (!input.files.length) return;
    const file = input.files[0];
    input.value = '';
    // Store the file and update display; upload happens in maybeAutoSaveAndRename
    state.pendingAiFile = file;
    state.copyPerformed = false;
    setVal('p2_ai_filename', file.name);
    setVal('p2_altered_filename', '');
    document.getElementById('btn-browse-p2-ai').disabled = false;
    highlightBlankFields('p2');
    await updateComputedRename();
    await maybeAutoSaveAndRename();
  }

  // ── Original image copy / rename ─────────────────────────────────────────

  async function updateP0ComputedRename() {
    const originalFilename = getVal('p0_original_filename');
    const studyId = getVal('p0_study_id');
    const renamedEl = document.getElementById('p0_renamed_filename');
    const statusEl = document.getElementById('status-copy-rename-original');

    if (!originalFilename || !studyId) {
      renamedEl.value = '';
      statusEl.innerHTML = '';
      return;
    }

    try {
      const res = await fetch('/api/compute_original_renamed?' +
        new URLSearchParams({ original_filename: originalFilename, study_id: studyId }));
      const data = await res.json();
      if (data.filename) {
        renamedEl.value = data.filename;
        if (data.already_exists) {
          state.p0CopyPerformed = true;
          document.getElementById('btn-browse-original').disabled = true;
        } else {
          state.p0CopyPerformed = false;
          document.getElementById('btn-browse-original').disabled = false;
          statusEl.textContent = '';
          statusEl.className = 'status-msg';
        }
      }
    } catch { /* silently ignore */ }
  }

  // ── Dashboard ─────────────────────────────────────────────────────────────

  function buildDashGroup(title, open = true) {
    const details = document.createElement('details');
    details.className = 'dash-group';
    if (open) details.open = true;
    const summary = document.createElement('summary');
    summary.textContent = title;
    details.appendChild(summary);
    const body = document.createElement('div');
    body.className = 'dash-group-body';
    details.appendChild(body);
    return { details, body };
  }

  function buildMetadataIndicatorsSection(p0, p1, p2) {
    const section = document.createElement('div');
    const titleEl = document.createElement('div');
    titleEl.className = 'dash-section-title';
    titleEl.textContent = 'Metadata Tags by Image Type';
    section.appendChild(titleEl);
    const subEl1 = document.createElement('p');
    subEl1.className = 'dash-section-subtitle';
    subEl1.textContent = 'Percentage of total images of the specified type that have the indicator in their metadata.';
    section.appendChild(subEl1);

    const INDICATORS = [
      ['Camera EXIF',                      r => r.indicators?.camera_exif && Object.keys(r.indicators.camera_exif.present || {}).length > 0],
      ['Photoshop / Adobe markers',       r => r.indicators?.photoshop_adobe != null],
      ['ICC measurement / viewing cond.', r => r.indicators?.icc_meas_view != null],
      ['Grok signature',                  r => r.indicators?.grok_signatures != null],
      ['C2PA manifest',                   r => r.indicators?.c2pa != null],
    ];

    const types = [
      { label: 'Original', records: p0 },
      { label: 'Modified', records: p1 },
      { label: 'Altered',  records: p2 },
    ];

    const anyAnalyzed = [...p0, ...p1, ...p2].some(r => r.indicators);
    if (!anyAnalyzed) {
      const empty = document.createElement('p');
      empty.style.cssText = 'font-size:12px; color:var(--text-muted); margin:0;';
      empty.textContent = 'No analyzed records yet.';
      section.appendChild(empty);
      return section;
    }

    types.forEach(({ label, records }) => {
      const analyzed = records.filter(r => r.indicators);
      if (!analyzed.length) return;
      const group = document.createElement('div');
      group.className = 'dash-indicator-group';
      const lbl = document.createElement('div');
      lbl.className = 'dash-indicator-label';
      lbl.textContent = label;
      group.appendChild(lbl);
      const chart = document.createElement('div');
      chart.className = 'dash-bar-chart';
      INDICATORS.forEach(([name, fn]) => {
        const matching = analyzed.filter(fn);
        const count = matching.length;
        const pct = Math.round(count / analyzed.length * 100);
        const row = document.createElement('div');
        row.className = 'dash-bar-row';
        if (count > 0) {
          row.style.cursor = 'pointer';
          row.title = 'Click to view in gallery';
          const ids = new Set(matching.map(r => r.id));
          row.addEventListener('click', () => {
            closeDashboard();
            openGallery(ids, `${name} — ${label}`);
          });
        }
        const labelEl = document.createElement('span');
        labelEl.className = 'dash-bar-label';
        labelEl.textContent = name;
        labelEl.style.width = '220px';
        const track = document.createElement('div');
        track.className = 'dash-bar-track';
        const fill = document.createElement('div');
        fill.className = 'dash-bar-fill';
        fill.style.width = pct + '%';
        track.appendChild(fill);
        const cEl = document.createElement('span');
        cEl.className = 'dash-bar-count-wide';
        cEl.textContent = `${pct}%`;
        row.append(labelEl, track, cEl);
        chart.appendChild(row);
      });
      group.appendChild(chart);
      section.appendChild(group);
    });

    return section;
  }

  function buildModelIndicatorTable(p0, p1, p2) {
    const section = document.createElement('div');
    const titleEl = document.createElement('div');
    titleEl.className = 'dash-section-title';
    titleEl.textContent = 'Indicator Presence by Model';
    section.appendChild(titleEl);
    const subEl = document.createElement('p');
    subEl.className = 'dash-section-subtitle';
    subEl.textContent = 'Marked if any image in that group has the indicator present.';
    section.appendChild(subEl);

    const INDICATORS = [
      ['Camera EXIF',         r => r.indicators?.camera_exif && Object.keys(r.indicators.camera_exif.present || {}).length > 0],
      ['Photoshop / Adobe',   r => r.indicators?.photoshop_adobe != null],
      ['ICC meas./viewing',   r => r.indicators?.icc_meas_view != null],
      ['Grok signature',      r => r.indicators?.grok_signatures != null],
      ['C2PA manifest',       r => r.indicators?.c2pa != null],
      ['Visible watermark',   r => !!r.visible_watermark],
    ];

    const models = [...new Set(p2.map(r => (r.model || 'Unknown').trim() || 'Unknown'))].sort((a, b) => a.localeCompare(b));

    const table = document.createElement('table');
    table.className = 'dash-table';

    const thead = table.createTHead();
    const hrow = thead.insertRow();
    const modelTh = document.createElement('th');
    modelTh.textContent = 'Group';
    hrow.appendChild(modelTh);
    INDICATORS.forEach(([label]) => {
      const th = document.createElement('th');
      th.textContent = label;
      th.style.textAlign = 'center';
      hrow.appendChild(th);
    });

    const tbody = table.createTBody();

    const addRow = (label, records) => {
      const tr = tbody.insertRow();
      tr.insertCell().textContent = label;
      INDICATORS.forEach(([, fn]) => {
        const td = tr.insertCell();
        td.style.textAlign = 'center';
        if (records.some(fn)) td.textContent = 'x';
      });
    };

    addRow('Originals', p0);
    addRow('Modified', p1);
    models.forEach(model => addRow(model, p2.filter(r => (r.model || 'Unknown').trim() === model)));

    section.appendChild(table);
    return section;
  }

  // ── KDE density plot ──────────────────────────────────────────────────────

  function buildDensityPlot(title, unit, datasets) {
    // datasets: [{ label, color, values: number[] }, ...]
    const section = document.createElement('div');
    const titleEl = document.createElement('div');
    titleEl.className = 'dash-section-title';
    titleEl.textContent = title;
    section.appendChild(titleEl);

    const allValues = datasets.flatMap(d => d.values);
    if (!allValues.length) {
      const empty = document.createElement('p');
      empty.style.cssText = 'font-size:12px; color:var(--text-muted); margin:0;';
      empty.textContent = 'No data yet.';
      section.appendChild(empty);
      return section;
    }

    const NS = 'http://www.w3.org/2000/svg';
    const ML = 44, MR = 20, MT = 20, MB = 36;
    const plotW = 480, plotH = 140;
    const totalW = ML + plotW + MR;
    const totalH = MT + plotH + MB;

    // Compute KDE for each dataset
    function silverman(vals) {
      const n = vals.length;
      if (n < 2) return 1;
      const mean = vals.reduce((s, v) => s + v, 0) / n;
      const std  = Math.sqrt(vals.reduce((s, v) => s + (v - mean) ** 2, 0) / (n - 1));
      return Math.max(1.06 * std * Math.pow(n, -0.2), 0.1);
    }

    const xMin = Math.min(...allValues);
    const xMax = Math.max(...allValues);
    const xPad = (xMax - xMin) * 0.1 || 1;
    const xLo = xMin - xPad, xHi = xMax + xPad;
    const STEPS = 200;
    const xs = Array.from({ length: STEPS + 1 }, (_, i) => xLo + (xHi - xLo) * i / STEPS);

    const curves = datasets.map(({ label, color, values }) => {
      if (!values.length) return { label, color, ys: xs.map(() => 0) };
      const h = silverman(values);
      const ys = xs.map(x =>
        values.reduce((sum, xi) => {
          const u = (x - xi) / h;
          return sum + Math.exp(-0.5 * u * u) / Math.sqrt(2 * Math.PI);
        }, 0) / (values.length * h)
      );
      return { label, color, ys };
    });

    const yMax = Math.max(...curves.flatMap(c => c.ys), 1e-9);
    const xScale = x => ML + (x - xLo) / (xHi - xLo) * plotW;
    const yScale = y => MT + plotH - y / yMax * plotH;

    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', `0 0 ${totalW} ${totalH}`);
    svg.setAttribute('width', '100%');
    svg.style.maxWidth = totalW + 'px';
    svg.style.display = 'block';

    // Grid lines
    [0, 0.25, 0.5, 0.75, 1].forEach(t => {
      const y = MT + plotH * (1 - t);
      const line = document.createElementNS(NS, 'line');
      line.setAttribute('x1', ML); line.setAttribute('x2', ML + plotW);
      line.setAttribute('y1', y);  line.setAttribute('y2', y);
      line.setAttribute('stroke', 'var(--border)'); line.setAttribute('stroke-width', '0.5');
      svg.appendChild(line);
    });

    // X-axis ticks
    const nTicks = 6;
    for (let i = 0; i <= nTicks; i++) {
      const xv = xLo + (xHi - xLo) * i / nTicks;
      const px = xScale(xv);
      const tick = document.createElementNS(NS, 'line');
      tick.setAttribute('x1', px); tick.setAttribute('x2', px);
      tick.setAttribute('y1', MT + plotH); tick.setAttribute('y2', MT + plotH + 4);
      tick.setAttribute('stroke', 'var(--text-faint)'); tick.setAttribute('stroke-width', '1');
      svg.appendChild(tick);
      const label = document.createElementNS(NS, 'text');
      label.setAttribute('x', px); label.setAttribute('y', MT + plotH + 14);
      label.setAttribute('text-anchor', 'middle');
      label.setAttribute('font-size', '9'); label.setAttribute('fill', 'var(--text-muted)');
      label.setAttribute('font-family', 'var(--mono)');
      label.textContent = Math.round(xv * 10) / 10;
      svg.appendChild(label);
    }

    // X-axis label (unit)
    const xAxisLabel = document.createElementNS(NS, 'text');
    xAxisLabel.setAttribute('x', ML + plotW / 2);
    xAxisLabel.setAttribute('y', totalH - 2);
    xAxisLabel.setAttribute('text-anchor', 'middle');
    xAxisLabel.setAttribute('font-size', '9'); xAxisLabel.setAttribute('fill', 'var(--text-faint)');
    xAxisLabel.setAttribute('font-family', 'var(--mono)');
    xAxisLabel.textContent = unit;
    svg.appendChild(xAxisLabel);

    // KDE curves (filled)
    curves.forEach(({ color, ys }) => {
      const pts = xs.map((x, i) => `${xScale(x).toFixed(1)},${yScale(ys[i]).toFixed(1)}`).join(' ');
      const baseline = `${xScale(xs[xs.length - 1]).toFixed(1)},${(MT + plotH).toFixed(1)} ${xScale(xs[0]).toFixed(1)},${(MT + plotH).toFixed(1)}`;
      const fill = document.createElementNS(NS, 'polygon');
      fill.setAttribute('points', pts + ' ' + baseline);
      fill.setAttribute('fill', color); fill.setAttribute('fill-opacity', '0.15');
      svg.appendChild(fill);
      const path = document.createElementNS(NS, 'polyline');
      path.setAttribute('points', pts);
      path.setAttribute('fill', 'none'); path.setAttribute('stroke', color);
      path.setAttribute('stroke-width', '1.5'); path.setAttribute('stroke-linejoin', 'round');
      svg.appendChild(path);
    });

    // Axes
    const axisColor = 'var(--text-faint)';
    [[ML, MT, ML, MT + plotH], [ML, MT + plotH, ML + plotW, MT + plotH]].forEach(([x1, y1, x2, y2]) => {
      const ax = document.createElementNS(NS, 'line');
      ax.setAttribute('x1', x1); ax.setAttribute('y1', y1);
      ax.setAttribute('x2', x2); ax.setAttribute('y2', y2);
      ax.setAttribute('stroke', axisColor); ax.setAttribute('stroke-width', '1');
      svg.appendChild(ax);
    });

    section.appendChild(svg);

    // Legend
    const legend = document.createElement('div');
    legend.style.cssText = 'display:flex; gap:1.5rem; margin-top:0.5rem;';
    datasets.forEach(({ label, color }) => {
      const item = document.createElement('div');
      item.style.cssText = 'display:flex; align-items:center; gap:6px; font-family:var(--mono); font-size:11px; color:var(--text-muted);';
      const swatch = document.createElement('span');
      swatch.style.cssText = `display:inline-block; width:18px; height:3px; background:${color}; border-radius:2px; flex-shrink:0;`;
      item.appendChild(swatch);
      item.appendChild(document.createTextNode(label));
      legend.appendChild(item);
    });
    section.appendChild(legend);
    return section;
  }

  function buildFeatureDistributionsSection(p0, p2) {
    const RF_FEATURES = [
      { field: 'ela_mean_diff',   label: 'ELA Mean Diff',   unit: 'mean pixel diff' },
      { field: 'ela_std_diff',    label: 'ELA Std Diff',    unit: 'std pixel diff'  },
      { field: 'ela_max_diff',    label: 'ELA Max Diff',    unit: 'max pixel diff'  },
      { field: 'block_noise_std', label: 'Block Noise Std', unit: 'block noise std' },
      { field: 'noise_skewness',  label: 'Noise Skewness',  unit: 'skewness'        },
      { field: 'noise_kurtosis',  label: 'Noise Kurtosis',  unit: 'kurtosis'        },
    ];
    const MODEL_COLORS = ['#e05c5c','#f5a623','#4eb84e','#9b59b6','#1abc9c','#e67e22','#3498db'];
    const ORIG_COLOR   = '#4e9af1';
    const ALT_COLOR    = '#e05c5c';

    const models = [...new Set(p2.map(r => (r.model || '').trim()).filter(Boolean))].sort();
    const modelCounts = {};
    p2.forEach(r => { const m = (r.model || '').trim(); if (m) modelCounts[m] = (modelCounts[m] || 0) + 1; });

    const wrapper = document.createElement('div');
    wrapper.style.cssText = 'display:flex; flex-direction:column; gap:1.5rem;';

    // ── Mode toggle ──
    const toggleRow = document.createElement('div');
    toggleRow.style.cssText = 'display:flex; gap:0.5rem; align-items:center;';
    const btnCombined = document.createElement('button');
    btnCombined.className = 'btn';
    btnCombined.textContent = 'Combined';
    const btnByModel = document.createElement('button');
    btnByModel.className = 'btn';
    btnByModel.textContent = 'By Model';
    toggleRow.appendChild(btnCombined);
    toggleRow.appendChild(btnByModel);
    wrapper.appendChild(toggleRow);

    // ── Model checkboxes (Combined mode only) ──
    const checkboxArea = document.createElement('div');
    checkboxArea.style.cssText = 'display:flex; flex-wrap:wrap; gap:0.5rem 1.5rem;';
    const checkboxes = {};
    models.forEach(m => {
      const lbl = document.createElement('label');
      lbl.style.cssText = 'display:flex; align-items:center; gap:6px; font-family:var(--mono); font-size:0.82rem; color:var(--text); cursor:pointer; user-select:none;';
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = true;
      cb.style.cssText = 'cursor:pointer; accent-color:var(--accent);';
      cb.addEventListener('change', rebuildPlots);
      checkboxes[m] = cb;
      const span = document.createElement('span');
      span.style.color = 'var(--text-muted)';
      span.textContent = `${m} (${modelCounts[m] || 0})`;
      lbl.appendChild(cb);
      lbl.appendChild(span);
      checkboxArea.appendChild(lbl);
    });
    wrapper.appendChild(checkboxArea);

    // ── Plots container ──
    const plotsContainer = document.createElement('div');
    plotsContainer.style.cssText = 'display:flex; flex-direction:column; gap:2rem;';
    wrapper.appendChild(plotsContainer);

    let currentMode = 'combined';

    function rebuildPlots() {
      plotsContainer.innerHTML = '';
      RF_FEATURES.forEach(({ field, label, unit }) => {
        let datasets;
        if (currentMode === 'combined') {
          const selected = new Set(models.filter(m => checkboxes[m].checked));
          const altRecs  = p2.filter(r => selected.has((r.model || '').trim()));
          datasets = [
            { label: 'Original', color: ORIG_COLOR, values: p0.map(r => r[field]).filter(v => v != null && typeof v === 'number') },
            { label: 'Altered',  color: ALT_COLOR,  values: altRecs.map(r => r[field]).filter(v => v != null && typeof v === 'number') },
          ];
        } else {
          datasets = [
            { label: 'Original', color: ORIG_COLOR, values: p0.map(r => r[field]).filter(v => v != null && typeof v === 'number') },
            ...models.map((m, i) => ({
              label:  m,
              color:  MODEL_COLORS[i % MODEL_COLORS.length],
              values: p2.filter(r => (r.model || '').trim() === m).map(r => r[field]).filter(v => v != null && typeof v === 'number'),
            })),
          ];
        }
        plotsContainer.appendChild(buildDensityPlot(label, unit, datasets));
      });
    }

    function setMode(mode) {
      currentMode = mode;
      checkboxArea.style.display = mode === 'combined' ? 'flex' : 'none';
      btnCombined.classList.toggle('active', mode === 'combined');
      btnByModel.classList.toggle('active', mode === 'bymodel');
      rebuildPlots();
    }

    btnCombined.addEventListener('click', () => setMode('combined'));
    btnByModel.addEventListener('click', () => setMode('bymodel'));

    setMode('combined');
    return wrapper;
  }

  function buildRFControls(container, p2) {
    const models = [...new Set(p2.map(r => (r.model || '').trim()).filter(Boolean))].sort();
    const modelCounts = {};
    p2.forEach(r => {
      const m = (r.model || '').trim();
      if (m) modelCounts[m] = (modelCounts[m] || 0) + 1;
    });

    // ── Model checkboxes ──
    const ctrlSub = document.createElement('p');
    ctrlSub.className = 'dash-section-subtitle';
    ctrlSub.textContent = 'Select which AI models to include as the "AI-altered" class. All originals are always included.';
    container.appendChild(ctrlSub);

    const checkboxArea = document.createElement('div');
    checkboxArea.style.cssText = 'display:flex; flex-wrap:wrap; gap:0.5rem 1.5rem; margin-bottom:1rem;';

    const checkboxes = {};
    models.forEach(model => {
      const label = document.createElement('label');
      label.style.cssText = 'display:flex; align-items:center; gap:6px; font-family:var(--mono); font-size:0.82rem; color:var(--text); cursor:pointer; user-select:none;';
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = true;
      cb.style.cssText = 'cursor:pointer; accent-color:var(--accent);';
      checkboxes[model] = cb;
      const count = document.createElement('span');
      count.style.cssText = 'color:var(--text-muted);';
      count.textContent = `${model} (${modelCounts[model] ?? 0})`;
      label.appendChild(cb);
      label.appendChild(count);
      checkboxArea.appendChild(label);
    });
    container.appendChild(checkboxArea);

    // ── Train button ──
    const btn = document.createElement('button');
    btn.className = 'btn';
    btn.textContent = 'Train Random Forest';
    btn.style.cssText = 'margin-bottom:1.5rem;';
    container.appendChild(btn);

    // ── Results area ──
    const resultsArea = document.createElement('div');
    container.appendChild(resultsArea);

    btn.addEventListener('click', async () => {
      const selectedModels = models.filter(m => checkboxes[m].checked);
      if (!selectedModels.length) {
        resultsArea.innerHTML = '';
        const warn = document.createElement('p');
        warn.className = 'dash-section-subtitle';
        warn.textContent = 'Select at least one model to train.';
        resultsArea.appendChild(warn);
        return;
      }

      btn.disabled = true;
      btn.textContent = 'Training…';
      resultsArea.innerHTML = '';

      try {
        const resp = await fetch('/api/random_forest', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ models: selectedModels }),
        });
        const data = await resp.json();
        if (!resp.ok) {
          const err = document.createElement('p');
          err.className = 'dash-section-subtitle';
          err.textContent = 'Error: ' + (data.error || 'unknown');
          resultsArea.appendChild(err);
        } else {
          resultsArea.appendChild(buildRandomForestSection(data));
        }
      } catch (e) {
        const err = document.createElement('p');
        err.className = 'dash-section-subtitle';
        err.textContent = 'Failed to load: ' + e.message;
        resultsArea.appendChild(err);
      } finally {
        btn.disabled = false;
        btn.textContent = 'Train Random Forest';
      }
    });
  }

  function buildRandomForestSection(data) {
    const wrapper = document.createElement('div');
    wrapper.style.cssText = 'display:flex; flex-direction:column; gap:2rem;';

    // ── Description ──
    const desc = document.createElement('p');
    desc.className = 'dash-section-subtitle';
    const modelNote = data.selected_models
      ? `Models: ${data.selected_models.join(', ')}.`
      : 'All models included.';
    desc.textContent =
      `5-fold stratified cross-validation on ${data.n_total} images ` +
      `(${data.n_original} original, ${data.n_altered} AI-altered). ` +
      `${modelNote} Features: ELA mean/std/max, block noise std, noise skewness/kurtosis, ELA source.`;
    wrapper.appendChild(desc);

    // ── Accuracy card ──
    const accCard = document.createElement('div');
    accCard.style.cssText = 'display:flex; align-items:baseline; gap:0.5rem;';
    const accVal = document.createElement('span');
    accVal.style.cssText = 'font-size:2rem; font-weight:700; font-family:var(--mono); color:var(--accent);';
    accVal.textContent = (data.mean_accuracy * 100).toFixed(1) + '%';
    const accLabel = document.createElement('span');
    accLabel.style.cssText = 'font-size:0.85rem; color:var(--text-muted); font-family:var(--mono);';
    accLabel.textContent = `± ${(data.std_accuracy * 100).toFixed(1)}%  mean 5-fold CV accuracy`;
    accCard.appendChild(accVal);
    accCard.appendChild(accLabel);
    wrapper.appendChild(accCard);

    // Per-fold breakdown
    const foldRow = document.createElement('div');
    foldRow.style.cssText = 'display:flex; gap:0.75rem; flex-wrap:wrap;';
    data.fold_accuracies.forEach((a, i) => {
      const chip = document.createElement('span');
      chip.style.cssText = 'font-family:var(--mono); font-size:0.8rem; color:var(--text-muted); background:var(--bg-alt); padding:2px 8px; border-radius:4px;';
      chip.textContent = `Fold ${i + 1}: ${(a * 100).toFixed(1)}%`;
      foldRow.appendChild(chip);
    });
    wrapper.appendChild(foldRow);

    // ── Confusion matrix ──
    const cmTitle = document.createElement('div');
    cmTitle.className = 'dash-section-title';
    cmTitle.textContent = 'Confusion Matrix';
    wrapper.appendChild(cmTitle);

    const cmSub = document.createElement('p');
    cmSub.className = 'dash-section-subtitle';
    cmSub.textContent = 'Rows = true label, columns = predicted label. Aggregated across all 5 folds.';
    wrapper.appendChild(cmSub);

    const cm = data.confusion_matrix;
    const maxCell = Math.max(...cm.flat());
    const grid = document.createElement('div');
    grid.style.cssText = 'display:grid; grid-template-columns:140px repeat(2,110px); grid-template-rows:repeat(3,auto); gap:4px; width:fit-content;';

    const cellStyle = (val, isHeader) => {
      if (isHeader) return 'display:flex; align-items:center; justify-content:center; padding:6px 10px; font-family:var(--mono); font-size:0.78rem; color:var(--text-muted); font-weight:600;';
      const alpha = 0.15 + 0.7 * (val / maxCell);
      return `display:flex; align-items:center; justify-content:center; padding:12px 8px; font-family:var(--mono); font-size:1.1rem; font-weight:700; border-radius:6px; background:rgba(78,154,241,${alpha.toFixed(2)}); color:var(--text);`;
    };

    [['', 'Pred: Original', 'Pred: AI-altered'],
     ['True: Original',  cm[0][0], cm[0][1]],
     ['True: AI-altered', cm[1][0], cm[1][1]]].forEach((row, ri) => {
      row.forEach((cell, ci) => {
        const el = document.createElement('div');
        const isHeader = ri === 0 || ci === 0;
        el.style.cssText = cellStyle(cell, isHeader);
        el.textContent = cell;
        grid.appendChild(el);
      });
    });
    wrapper.appendChild(grid);

    // ── FPR / FNR ──
    const tn = cm[0][0], fp = cm[0][1], fn = cm[1][0], tp = cm[1][1];
    const fpr = fp / (fp + tn);
    const fnr = fn / (fn + tp);

    const rateRow = document.createElement('div');
    rateRow.style.cssText = 'display:flex; gap:2rem; margin-top:0.75rem;';
    [
      { label: 'False Positive Rate', value: fpr, note: 'originals misclassified as AI-altered' },
      { label: 'False Negative Rate', value: fnr, note: 'AI-altered images misclassified as original' },
    ].forEach(({ label, value, note }) => {
      const block = document.createElement('div');
      const lbl = document.createElement('div');
      lbl.style.cssText = 'font-family:var(--mono); font-size:0.72rem; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.05em; margin-bottom:2px;';
      lbl.textContent = label;
      const val = document.createElement('div');
      val.style.cssText = 'font-family:var(--mono); font-size:1.4rem; font-weight:700; color:var(--text);';
      val.textContent = (value * 100).toFixed(1) + '%';
      const sub = document.createElement('div');
      sub.style.cssText = 'font-family:var(--mono); font-size:0.72rem; color:var(--text-muted);';
      sub.textContent = `${label === 'False Positive Rate' ? fp : fn} of ${label === 'False Positive Rate' ? (fp + tn) : (fn + tp)} — ${note}`;
      block.appendChild(lbl);
      block.appendChild(val);
      block.appendChild(sub);
      rateRow.appendChild(block);
    });
    wrapper.appendChild(rateRow);

    // ── Feature importances ──
    const fiTitle = document.createElement('div');
    fiTitle.className = 'dash-section-title';
    fiTitle.textContent = 'Feature Importances';
    wrapper.appendChild(fiTitle);

    const fiSub = document.createElement('p');
    fiSub.className = 'dash-section-subtitle';
    fiSub.textContent = 'Mean decrease in impurity, trained on the full dataset. All features contribute nearly equally.';
    wrapper.appendChild(fiSub);

    const maxImp = data.feature_importances[0].importance;
    const fiChart = document.createElement('div');
    fiChart.style.cssText = 'display:flex; flex-direction:column; gap:6px; max-width:520px;';
    data.feature_importances.forEach(({ label, importance }) => {
      const row = document.createElement('div');
      row.style.cssText = 'display:flex; align-items:center; gap:10px;';
      const lbl = document.createElement('span');
      lbl.style.cssText = 'font-family:var(--mono); font-size:0.78rem; color:var(--text-muted); width:160px; text-align:right; flex-shrink:0;';
      lbl.textContent = label;
      const barWrap = document.createElement('div');
      barWrap.style.cssText = 'flex:1; background:var(--bg-alt); border-radius:3px; height:16px; position:relative;';
      const bar = document.createElement('div');
      bar.style.cssText = `width:${(importance / maxImp * 100).toFixed(1)}%; height:100%; background:#4e9af1; border-radius:3px;`;
      const val = document.createElement('span');
      val.style.cssText = 'font-family:var(--mono); font-size:0.75rem; color:var(--text-muted); margin-left:6px; flex-shrink:0;';
      val.textContent = (importance * 100).toFixed(1) + '%';
      barWrap.appendChild(bar);
      row.appendChild(lbl);
      row.appendChild(barWrap);
      row.appendChild(val);
      fiChart.appendChild(row);
    });
    wrapper.appendChild(fiChart);

    return wrapper;
  }

  function buildPixelArtifactsSection(p0, p1, p2) {
    const COLORS = { Original: '#4e9af1', Modified: '#f5a623', Altered: '#e05c5c' };

    function dataset(label, records, field) {
      return { label, color: COLORS[label], values: records.map(r => r[field]).filter(v => v != null && typeof v === 'number') };
    }

    function subtitle(text) {
      const s = document.createElement('p');
      s.className = 'dash-section-subtitle';
      s.textContent = text;
      return s;
    }

    function plotWithSubtitle(title, unit, field, note) {
      const container = document.createElement('div');
      container.appendChild(subtitle(note));
      container.appendChild(buildDensityPlot(title, unit, [
        dataset('Original', p0, field),
        dataset('Modified', p1, field),
        dataset('Altered',  p2, field),
      ]));
      return container;
    }

    const wrapper = document.createElement('div');
    wrapper.style.cssText = 'display:flex; flex-direction:column; gap:2rem;';
    wrapper.appendChild(plotWithSubtitle(
      'ELA Mean Pixel Diff', 'mean pixel diff', 'ela_mean_diff',
      'Mean per-pixel error after re-saving at JPEG quality 75. PNG-source images show higher values due to first-time JPEG compression.'
    ));
    wrapper.appendChild(plotWithSubtitle(
      'ELA Std Pixel Diff', 'std pixel diff', 'ela_std_diff',
      'Standard deviation of per-pixel error at quality 75 — measures spatial uniformity of compression artifacts.'
    ));
    wrapper.appendChild(plotWithSubtitle(
      'Noise Skewness', 'skewness', 'noise_skewness',
      'Skewness of the block noise distribution. Real camera noise is approximately symmetric (≈ 0); AI images may deviate.'
    ));
    return wrapper;
  }

  function openDashboard() {
    const content = document.getElementById('dashboard-content');
    content.innerHTML = '';

    const p0 = state.records.filter(r => r.type === 'p0');
    const p1 = state.records.filter(r => r.type === 'p1');
    const p2 = state.records.filter(r => r.type === 'p2');

    // ── Summary group ──
    const { details: sumDetails, body: sumBody } = buildDashGroup('Summary');
    content.appendChild(sumDetails);

    const cards = document.createElement('div');
    cards.className = 'dash-cards';
    [[p0.length, 'Originals'], [p1.length, 'Modifications'], [p2.length, 'Alterations']].forEach(([num, label]) => {
      const card = document.createElement('div');
      card.className = 'dash-card';
      const n = document.createElement('div'); n.className = 'dash-card-num'; n.textContent = num;
      const l = document.createElement('div'); l.className = 'dash-card-label'; l.textContent = label;
      card.appendChild(n); card.appendChild(l); cards.appendChild(card);
    });
    sumBody.appendChild(cards);

    if (p2.length) {
      const modelCounts = {}, modelIds = {};
      p2.forEach(r => {
        const m = (r.model || 'Unknown').trim() || 'Unknown';
        modelCounts[m] = (modelCounts[m] || 0) + 1;
        (modelIds[m] = modelIds[m] || []).push(r.id);
      });
      sumBody.appendChild(buildBarChart('Alterations by model', modelCounts, false, modelIds));
    }

    if (p2.length) {
      const qualityCounts = {}, qualityIds = {};
      p2.forEach(r => {
        const q = r.subjective_quality ? '★' + r.subjective_quality : 'Not rated';
        qualityCounts[q] = (qualityCounts[q] || 0) + 1;
        (qualityIds[q] = qualityIds[q] || []).push(r.id);
      });
      const ordered = {}, orderedIds = {};
      ['★5','★4','★3','★2','★1'].forEach(k => {
        if (qualityCounts[k]) { ordered[k] = qualityCounts[k]; orderedIds[k] = qualityIds[k]; }
      });
      if (qualityCounts['Not rated']) { ordered['Not rated'] = qualityCounts['Not rated']; orderedIds['Not rated'] = qualityIds['Not rated']; }
      sumBody.appendChild(buildBarChart('Subjective quality (alterations)', ordered, true, orderedIds));
    }

    if (p2.length) sumBody.appendChild(buildScatterPlot('Subjective quality (Alterations) by Model', p2));

    // ── AI Indicators group ──
    const { details: aiDetails, body: aiBody } = buildDashGroup('AI Indicators');
    content.appendChild(aiDetails);

    aiBody.appendChild(buildModelIndicatorTable(p0, p1, p2));

    // Models with visible watermarks
    if (p2.length) {
      const watermarked = p2.filter(r => r.visible_watermark);
      const allModels = [...new Set(p2.map(r => (r.model || 'Unknown').trim() || 'Unknown'))].sort((a, b) => a.localeCompare(b));
      const wmModels = new Set(watermarked.map(r => (r.model || 'Unknown').trim() || 'Unknown'));
      const noWmModels = allModels.filter(m => !wmModels.has(m));

      const wmSection = document.createElement('div');
      const wmTitle = document.createElement('div');
      wmTitle.className = 'dash-section-title';
      wmTitle.textContent = 'Models with Visible Watermarks';
      wmSection.appendChild(wmTitle);

      const wmSummary = document.createElement('p');
      wmSummary.style.cssText = 'font-size:12px; color:var(--text-muted); margin:0 0 1rem;';
      wmSummary.textContent = `${wmModels.size} out of ${allModels.length} models have visible watermarks`;
      wmSection.appendChild(wmSummary);

      if (watermarked.length) {
        const table = document.createElement('table');
        table.className = 'dash-table';
        const thead = table.createTHead();
        const hrow = thead.insertRow();
        ['Model', 'Watermark description'].forEach(h => {
          const th = document.createElement('th'); th.textContent = h; hrow.appendChild(th);
        });
        const tbody = table.createTBody();
        const seen = new Set();
        [...watermarked].sort((a, b) => (a.model || '').localeCompare(b.model || '')).forEach(r => {
          const key = (r.model || '') + '|' + (r.watermark_description || '');
          if (seen.has(key)) return;
          seen.add(key);
          const tr = tbody.insertRow();
          tr.insertCell().textContent = r.model || '—';
          tr.insertCell().textContent = r.watermark_description || '—';
        });
        wmSection.appendChild(table);
      }

      if (noWmModels.length) {
        const noWmTitle = document.createElement('p');
        noWmTitle.style.cssText = 'font-size:12px; color:var(--text-muted); margin:1rem 0 0.4rem;';
        noWmTitle.textContent = 'Models without visible watermarks:';
        wmSection.appendChild(noWmTitle);
        const noWmList = document.createElement('p');
        noWmList.style.cssText = 'font-family:var(--mono); font-size:12px; color:var(--text); margin:0;';
        noWmList.textContent = noWmModels.join(', ');
        wmSection.appendChild(noWmList);
      }

      aiBody.appendChild(wmSection);
    }

    // Metadata indicators
    aiBody.appendChild(buildMetadataIndicatorsSection(p0, p1, p2));

    // ── Visual / pixel-level artifacts group ──
    const { details: pixDetails, body: pixBody } = buildDashGroup('Visual / pixel-level artifacts');
    content.appendChild(pixDetails);
    pixBody.appendChild(buildPixelArtifactsSection(p0, p1, p2));

    // ── Feature distributions group ──
    const { details: fdDetails, body: fdBody } = buildDashGroup('Feature Distributions', false);
    content.appendChild(fdDetails);
    fdBody.appendChild(buildFeatureDistributionsSection(p0, p2));

    // ── Random Forest group ──
    const { details: rfDetails, body: rfBody } = buildDashGroup('Random Forest Classifier', false);
    content.appendChild(rfDetails);
    buildRFControls(rfBody, p2);

    document.getElementById('dashboard-overlay').style.display = 'flex';
  }

  function buildBarChart(title, counts, preserveOrder = false, labelToIds = null, maxVal = null, formatValue = null) {
    const section = document.createElement('div');
    const titleEl = document.createElement('div');
    titleEl.className = 'dash-section-title';
    titleEl.textContent = title;
    section.appendChild(titleEl);

    const chart = document.createElement('div');
    chart.className = 'dash-bar-chart';
    const maxVal_ = maxVal !== null ? maxVal : Math.max(...Object.values(counts), 1);
    const sorted = preserveOrder
      ? Object.entries(counts)
      : Object.entries(counts).sort((a, b) => b[1] - a[1]);
    sorted.forEach(([label, count]) => {
      const row = document.createElement('div');
      row.className = 'dash-bar-row';
      if (labelToIds) {
        row.style.cursor = 'pointer';
        row.title = 'Click to view in gallery';
        row.addEventListener('click', () => {
          const ids = new Set(labelToIds[label] || []);
          closeDashboard();
          openGallery(ids, label);
        });
      }
      const lEl = document.createElement('span');
      lEl.className = 'dash-bar-label';
      lEl.textContent = label;
      const track = document.createElement('div');
      track.className = 'dash-bar-track';
      const fill = document.createElement('div');
      fill.className = 'dash-bar-fill';
      fill.style.width = Math.round(count / maxVal_ * 100) + '%';
      track.appendChild(fill);
      const cEl = document.createElement('span');
      cEl.className = 'dash-bar-count';
      cEl.textContent = formatValue ? formatValue(count) : count;
      row.appendChild(lEl);
      row.appendChild(track);
      row.appendChild(cEl);
      chart.appendChild(row);
    });
    section.appendChild(chart);
    return section;
  }

  function buildScatterPlot(title, records) {
    const section = document.createElement('div');
    const titleEl = document.createElement('div');
    titleEl.className = 'dash-section-title';
    titleEl.textContent = title;
    section.appendChild(titleEl);

    const rated = records.filter(r => r.subjective_quality);
    if (!rated.length) return section;

    // Group by model, sort models by avg quality descending
    const modelData = {};
    rated.forEach(r => {
      const m = (r.model || 'Unknown').trim() || 'Unknown';
      (modelData[m] = modelData[m] || []).push(r);
    });
    const avgQ = arr => arr.reduce((s, r) => s + Number(r.subjective_quality), 0) / arr.length;
    const models = Object.keys(modelData).sort((a, b) => a.localeCompare(b));

    const NS = 'http://www.w3.org/2000/svg';
    const ML = 130, MR = 30, MT = 16, MB = 36;
    const rowH = 48;
    const plotW = 460;
    const totalW = ML + plotW + MR;
    const totalH = MT + models.length * rowH + MB;
    const xScale = q => ML + (q - 1) / 4 * plotW;

    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', `0 0 ${totalW} ${totalH}`);
    svg.setAttribute('width', '100%');
    svg.style.maxWidth = totalW + 'px';
    svg.style.display = 'block';

    // Alternating row backgrounds
    models.forEach((m, i) => {
      if (i % 2 === 0) {
        const rect = document.createElementNS(NS, 'rect');
        rect.setAttribute('x', ML); rect.setAttribute('y', MT + i * rowH);
        rect.setAttribute('width', plotW); rect.setAttribute('height', rowH);
        rect.setAttribute('fill', 'var(--surface)');
        svg.appendChild(rect);
      }
    });

    // Vertical grid lines + X axis labels
    for (let q = 1; q <= 5; q++) {
      const x = xScale(q);
      const line = document.createElementNS(NS, 'line');
      line.setAttribute('x1', x); line.setAttribute('x2', x);
      line.setAttribute('y1', MT); line.setAttribute('y2', MT + models.length * rowH);
      line.setAttribute('stroke', 'var(--border)'); line.setAttribute('stroke-width', '1');
      svg.appendChild(line);

      const lbl = document.createElementNS(NS, 'text');
      lbl.setAttribute('x', x); lbl.setAttribute('y', totalH - 8);
      lbl.setAttribute('text-anchor', 'middle');
      lbl.setAttribute('font-size', '11'); lbl.setAttribute('fill', 'var(--text-muted)');
      lbl.setAttribute('font-family', 'var(--mono)');
      lbl.textContent = '★' + q;
      svg.appendChild(lbl);
    }

    // Model labels (Y axis)
    models.forEach((m, i) => {
      const lbl = document.createElementNS(NS, 'text');
      lbl.setAttribute('x', ML - 10);
      lbl.setAttribute('y', MT + i * rowH + rowH / 2 + 4);
      lbl.setAttribute('text-anchor', 'end');
      lbl.setAttribute('font-size', '11'); lbl.setAttribute('fill', 'var(--text)');
      lbl.setAttribute('font-family', 'var(--mono)');
      lbl.textContent = m;
      svg.appendChild(lbl);
    });

    // Data points with Y jitter
    rated.forEach(r => {
      const m = (r.model || 'Unknown').trim() || 'Unknown';
      const q = Number(r.subjective_quality);
      const i = models.indexOf(m);
      if (i === -1) return;

      const cx = xScale(q);
      const cy = MT + i * rowH + rowH / 2 + (Math.random() - 0.5) * rowH * 0.25;

      const circle = document.createElementNS(NS, 'circle');
      circle.setAttribute('cx', cx); circle.setAttribute('cy', cy);
      circle.setAttribute('r', '5');
      circle.setAttribute('fill', 'var(--accent)');
      circle.setAttribute('opacity', '0.65');
      circle.style.cursor = 'pointer';

      const tip = document.createElementNS(NS, 'title');
      tip.textContent = getRecordName(r);
      circle.appendChild(tip);

      circle.addEventListener('click', () => {
        closeDashboard();
        openLightbox('/images/' + encodeURIComponent(getRecordName(r)), getRecordName(r), getRecordMeta(r));
      });

      svg.appendChild(circle);
    });

    section.appendChild(svg);
    return section;
  }

  function closeDashboard() {
    document.getElementById('dashboard-overlay').style.display = 'none';
  }

  // ── Gallery ───────────────────────────────────────────────────────────────

  function buildGalleryCard(rec) {
    const filename = getRecordName(rec);
    const meta = getRecordMeta(rec);
    const src = '/images/' + encodeURIComponent(filename);

    const card = document.createElement('div');
    card.className = 'gallery-card';
    card.onclick = () => openLightbox(src, filename, meta);

    const wrap = document.createElement('div');
    wrap.className = 'gallery-thumb-wrap';

    const img = document.createElement('img');
    img.className = 'gallery-thumb';
    img.alt = filename;
    img.src = src;
    img.onerror = () => {
      img.remove();
      const miss = document.createElement('div');
      miss.className = 'gallery-no-img';
      miss.textContent = 'Image not found';
      wrap.appendChild(miss);
      card.onclick = null;
      card.style.cursor = 'default';
    };
    wrap.appendChild(img);

    const label = document.createElement('div');
    label.className = 'gallery-label';
    label.textContent = filename;

    const metaEl = document.createElement('div');
    metaEl.className = 'gallery-card-meta';
    metaEl.textContent = meta;

    card.appendChild(wrap);
    card.appendChild(label);
    card.appendChild(metaEl);
    return card;
  }

  function buildGalleryRow(label, recs) {
    if (!recs.length) return null;
    const row = document.createElement('div');
    row.className = 'gallery-row';
    const lbl = document.createElement('div');
    lbl.className = 'gallery-row-label';
    lbl.textContent = label;
    row.appendChild(lbl);
    const grid = document.createElement('div');
    grid.className = 'gallery-grid';
    const sorted = [...recs].sort((a, b) => getRecordName(a).localeCompare(getRecordName(b)));
    sorted.forEach(rec => grid.appendChild(buildGalleryCard(rec)));
    row.appendChild(grid);
    return row;
  }

  function openGallery(filterIds = null, filterLabel = '') {
    const content = document.getElementById('gallery-content');
    content.innerHTML = '';

    const titleEl = document.getElementById('gallery-bar-title');
    const showAllBtn = document.getElementById('gallery-show-all-btn');
    if (filterIds) {
      titleEl.textContent = filterLabel ? `Study Gallery — ${filterLabel}` : 'Study Gallery (filtered)';
      showAllBtn.style.display = '';
    } else {
      titleEl.textContent = 'Study Gallery';
      showAllBtn.style.display = 'none';
    }

    const studyMap = {};
    state.records.forEach(r => {
      if (filterIds && !filterIds.has(r.id)) return;
      const sid = r.study_id || '';
      if (!sid) return;
      if (!studyMap[sid]) studyMap[sid] = { p0: [], p1: [], p2: [] };
      (studyMap[sid][r.type] = studyMap[sid][r.type] || []).push(r);
    });

    const studyIds = Object.keys(studyMap).sort((a, b) => {
      const n = s => parseInt(s.replace(/\D+/g, ''), 10) || 0;
      return n(a) - n(b);
    });

    studyIds.forEach(sid => {
      const section = document.createElement('div');
      section.className = 'gallery-study';

      const title = document.createElement('div');
      title.className = 'gallery-study-title';
      title.textContent = sid;
      section.appendChild(title);

      const { p0 = [], p1 = [], p2 = [] } = studyMap[sid];
      [
        buildGalleryRow('Original', p0),
        buildGalleryRow('Modifications', p1),
        buildGalleryRow('Alterations', p2),
      ].forEach(row => { if (row) section.appendChild(row); });

      content.appendChild(section);
    });

    document.getElementById('gallery-overlay').style.display = 'flex';
  }

  function closeGallery() {
    document.getElementById('gallery-overlay').style.display = 'none';
  }

  function openLightbox(src, filename, meta) {
    document.getElementById('lightbox-img').src = src;
    document.getElementById('lightbox-caption').textContent = filename + (meta ? ' — ' + meta : '');
    document.getElementById('lightbox').style.display = 'flex';
  }

  function closeLightbox() {
    document.getElementById('lightbox').style.display = 'none';
    document.getElementById('lightbox-img').src = '';
  }

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') { closeLightbox(); closeGallery(); closeDashboard(); }
  });

  document.getElementById('form-area').addEventListener('input',  () => { if (state.currentType) highlightBlankFields(state.currentType); });
  document.getElementById('form-area').addEventListener('change', () => { if (state.currentType) highlightBlankFields(state.currentType); });

  // ── Boot ──────────────────────────────────────────────────────────────────
  loadModels();
  loadInputImages();
  loadRecords();
