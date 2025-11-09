const tabs = document.querySelectorAll('.tab');
const chatView = document.getElementById('view_chat');
const dashView = document.getElementById('view_dash');
const dashEls = () => document.querySelectorAll('.dash-only');
function setTab(which){
  tabs.forEach(x => x.classList.toggle('active', x.dataset.tab===which));
  chatView.classList.toggle('active', which === 'chat');
  dashView.classList.toggle('active', which === 'dash');
  dashEls().forEach(el => el.classList.toggle('hide', which !== 'dash'));
}
tabs.forEach(t => t.addEventListener('click', () => setTab(t.dataset.tab)));
setTab('chat');

// Toasts & errors
const toasts = document.getElementById('toasts');
function toast(msg, ms=2200){ const el=document.createElement('div'); el.className='toast'; el.textContent=msg; toasts.appendChild(el); setTimeout(()=>el.remove(),ms); }
function showError(msg){ const box=document.getElementById('errorBox'); if(!msg){ box.classList.add('hide'); box.textContent=''; return;} box.classList.remove('hide'); box.textContent=msg; }

// Metrics & receipts (dashboard only)
function updateMetrics(m){
  const g = (x)=> (typeof x==='number' && isFinite(x)) ? x : 0;
  const ids = ['m_prompt','m_gen','m_tools','m_receipts','m_latency'];
  if (!ids.every(id=>document.getElementById(id))) return;
  document.getElementById('m_prompt').textContent   = g(m?.tokens_in);
  document.getElementById('m_gen').textContent      = g(m?.tokens_out);
  document.getElementById('m_tools').textContent    = g(m?.tool_calls);
  document.getElementById('m_receipts').textContent = g(m?.receipts);
  document.getElementById('m_latency').textContent  = g(m?.gen_time_ms);
}
function renderReceipts(list){
  const box=document.getElementById('receipts_list'); if(!box){ return; }
  box.innerHTML='';
  if(!Array.isArray(list)||!list.length){ box.innerHTML='<div class="muted">No receipts.</div>'; return; }
  list.forEach(r=>{
    const row=document.createElement('div'); row.className='receipt';
    const left=document.createElement('div'); left.innerHTML=`<span class="kbd">${r.tool||'tool'}</span>`;
    const mid=document.createElement('div'); mid.style.flex='1'; mid.textContent=r.summary||'';
    row.appendChild(left); row.appendChild(mid);
    if(r.uri){ const a=document.createElement('a'); a.href=r.uri; a.target='_blank'; a.rel='noopener'; a.textContent='open'; row.appendChild(a); }
    box.appendChild(row);
  });
}

/* ---------- Lightweight Markdown renderer for final text ---------- */
function mdToHtml(md){
  if(!md) return '';
  // escape first
  let s = md.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

  // headings "## Title"
  s = s.replace(/^##\s*(.+)$/gm, '<h4>$1</h4>');
  // bold **text**
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

  // lines -> paragraphs/lists
  const lines = s.split(/\r?\n/);
  const out = [];
  let inList = false;
  for(const line of lines){
    const m = line.match(/^\s*[\*\-]\s+(.*)$/);
    if(m){
      if(!inList){ out.push('<ul>'); inList = true; }
      out.push(`<li>${m[1]}</li>`);
      continue;
    }
    if(inList){ out.push('</ul>'); inList = false; }
    if(line.trim()===''){ out.push(''); }
    else { out.push(`<p>${line}</p>`); }
  }
  if(inList) out.push('</ul>');
  return out.join('\n');
}
function renderFinal(html){
  const finalChat = document.getElementById('final');
  const finalDash = document.getElementById('final_dash');
  if(finalChat) finalChat.innerHTML = html || '...';
  if(finalDash) finalDash.innerHTML = html || '...';
}

/* ---------- Multi-image attach (max 2), auto-clear after run ---------- */
const LIMIT = 2;
const fileInput   = document.getElementById('fileInput');
const attachBtn   = document.getElementById('attachBtn');
const thumbsBox   = document.getElementById('thumbs');
const imageUrisEl = document.getElementById('image_uris');
const fileName    = document.getElementById('fileName');

let localThumbs = [];      // [{url, name}]
let uploadedUris = [];     // ['file://...', 'gs://...']

function syncHidden(){ imageUrisEl.value = JSON.stringify(uploadedUris); }
function clearAttachments(){
  localThumbs.forEach(t=>URL.revokeObjectURL(t.url));
  localThumbs = []; uploadedUris = [];
  syncHidden(); thumbsBox.innerHTML=''; fileName.textContent='';
}
function renderThumbs(){
  thumbsBox.innerHTML='';
  localThumbs.forEach((t,idx)=>{
    const wrap=document.createElement('div'); wrap.style.position='relative';
    const img=document.createElement('img'); img.src=t.url; img.alt=t.name; img.className='thumb';
    img.style.width='40px'; img.style.height='40px'; img.style.borderRadius='6px'; img.style.objectFit='cover';
    const x=document.createElement('button');
    x.textContent='×'; x.className='btn bad'; x.style.position='absolute'; x.style.top='-8px'; x.style.right='-8px'; x.style.padding='0 6px';
    x.addEventListener('click', ()=>{
      URL.revokeObjectURL(t.url);
      localThumbs.splice(idx,1);
      uploadedUris.splice(idx,1);
      syncHidden(); renderThumbs();
    });
    wrap.appendChild(img); wrap.appendChild(x); thumbsBox.appendChild(wrap);
  });
  fileName.textContent = localThumbs.length ? localThumbs.map(t=>t.name).join(', ') : '';
}

// open file dialog
attachBtn.addEventListener('click',()=>fileInput.click());

// handle selection + upload (sequential)
fileInput.addEventListener('change', async ()=>{
  if(!fileInput.files?.length) return;
  const chosen = Array.from(fileInput.files);
  for(const f of chosen){
    if(localThumbs.length >= LIMIT){ toast(`Max ${LIMIT} images`); break; }
    if(!f.type.startsWith('image/')){ toast('Only images allowed'); continue; }
    if(f.size>6*1024*1024){ toast('Image too large (>6MB)'); continue; }

    const url=URL.createObjectURL(f);
    localThumbs.push({url, name:f.name}); renderThumbs();

    const fd=new FormData(); fd.append('image', f);
    try{
      const res=await fetch('/upload',{method:'POST', body:fd, headers:{'Accept':'application/json'}, cache:'no-store'});
      const ct=res.headers.get('content-type')||''; const raw=await res.text();
      const data = ct.includes('application/json') ? JSON.parse(raw) : (()=>{throw new Error('Upload: non-JSON response');})();
      if(!data.ok) throw new Error(data.error||'upload failed');
      uploadedUris.push(data.uri); syncHidden(); toast('Image attached');
    }catch(e){
      toast('Upload failed'); showError(String(e.message||e));
      const ix = localThumbs.findIndex(t=>t.url===url);
      if(ix>=0){ URL.revokeObjectURL(localThumbs[ix].url); localThumbs.splice(ix,1); }
      renderThumbs(); syncHidden();
    }
  }
  fileInput.value='';
});

// Run handling (+ retry on transient responses)
const runBtn=document.getElementById('runBtn');
const cancelBtn=document.getElementById('cancelBtn');
const overlay=document.getElementById('overlay');
const govlog=document.getElementById('govlog');
const planPre=document.getElementById('plan');
const receiptsPre=document.getElementById('receipts_pre');
const finalChat=document.getElementById('final');
const finalDash=document.getElementById('final_dash');
const queryBox=document.getElementById('query');
let controller=null;

function setBusy(b){ runBtn.disabled=b; attachBtn.disabled=b; cancelBtn.disabled=!b; overlay.classList.toggle('show', b); }
cancelBtn.addEventListener('click',()=>{ if(controller) controller.abort(); setBusy(false); toast('Request canceled'); });

async function fetchJSONOnce(fd, signal){
  const res = await fetch('/run_plan', {
    method:'POST',
    body: fd,
    headers:{'X-Requested-With':'fetch','Accept':'application/json'},
    cache:'no-store', signal
  });
  const ct = res.headers.get('content-type') || '';
  const raw = await res.text();
  if (!ct.includes('application/json')) {
    const head = raw.trim().slice(0, 30).toUpperCase();
    if (head.startsWith('<!DOCTYPE') || head.startsWith('<HTML')) throw new Error('Server returned HTML instead of JSON');
    try { return JSON.parse(raw); } catch { throw new Error('Malformed non-JSON response'); }
  }
  return JSON.parse(raw);
}

runBtn.addEventListener('click', async ()=>{
  const q=queryBox.value.trim(); if(!q){ showError('Query is required'); return; }
  showError(''); setBusy(true); controller=new AbortController();

  const buildFD = ()=>{
    const fd=new FormData();
    fd.append('query', q);
    fd.append('image_uris', imageUrisEl.value || '[]');
    return fd;
  };
  let retried = false;

  try{
    let data;
    try { data = await fetchJSONOnce(buildFD(), controller.signal); }
    catch (e) {
      const msg = String(e.message||'');
      if (!retried && (msg.includes('NetworkError') || msg.includes('Failed to fetch') || msg.includes('HTML') || msg.includes('Malformed'))) {
        retried = true; toast('Transient glitch. Retrying…');
        data = await fetchJSONOnce(buildFD(), controller.signal);
      } else { throw e; }
    }

    if(!data?.ok) throw new Error(data?.error || 'Run failed');

    if (planPre)      planPre.textContent = data.plan || '[]';
    if (receiptsPre)  receiptsPre.textContent = JSON.stringify(data.receipts||[], null, 2);
    if (govlog)       govlog.textContent = JSON.stringify(data.governor_log||[], null, 2);

    // FINAL: render as simple Markdown
    renderFinal(mdToHtml(data.final_output || ''));

    renderReceipts(data.receipts||[]);
    updateMetrics(data.metrics||{});
    showError(data.error||''); toast('Done');

    clearAttachments();
  }catch(e){
    if(e.name!=='AbortError') showError(String(e.message||e));
  }finally{
    setBusy(false); controller=null;
  }
});

// Initial hydrate
(function(){
  try{
    const seed=document.getElementById('seed');
    const metrics=JSON.parse(seed.dataset.metrics || '{}');
    const receipts=JSON.parse(seed.dataset.receipts || '[]');
    const err=(seed.dataset.error||'').trim();
    const initialFinal = seed.dataset.final || '';

    renderReceipts(receipts);
    updateMetrics(metrics||{});
    if (initialFinal) renderFinal(mdToHtml(initialFinal));
    if (err) showError(err);
  }catch{}
})();
