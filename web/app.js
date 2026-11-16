/* SPDX-License-Identifier: GPL-3.0-only; Copyright (C) 2026 JM-KIMM and contributors. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const token = document.querySelector('meta[name="local-token"]').content;
  let selectedFile = null, collectorRunning = false, busy = false;
  const blobs = [];
  // The server still takes intensity 1/2/3; the screen offers one default (2) and two optional switches.
  const descriptions = {
    1: '문제 주변에 QR만 넣습니다. 원래 페이지 크기를 유지합니다.',
    2: '상단·우측은 문구 A, 하단·좌측은 문구 B를 반복합니다.',
    3: '기본 구성에 더해 구분선 후보를 QR 무늬로 바꿉니다. 결과 확인이 필요합니다.'
  };
  const labels = {1: 'QR만', 2: '기본', 3: '기본 + 구분선'};
  function resetPreview() {
    $('result-preview').hidden=true;$('paper-demo').hidden=false;
    $('result-stats').hidden=true;$('result-actions').hidden=true;
    $('preview-title').textContent='이렇게 배치돼요';
    $('preview-note').textContent='배치 예시입니다. 생성 후 실제 첫 페이지를 확인할 수 있어요.';
    blobs.splice(0).forEach(url=>URL.revokeObjectURL(url));
  }
  function status(message, error = false) { $('status').textContent = message; $('status').classList.toggle('error', error); }
  async function request(path, options = {}, json = true) {
    const response = await fetch(path, {...options, headers: {'X-Local-Token': token, ...options.headers}});
    if (!response.ok) { let message = '요청을 처리하지 못했습니다.'; try { message = (await response.json()).error || message; } catch {} throw new Error(message); }
    return json ? response.json() : response.blob();
  }
  function localDate(value) { return new Date(value.getTime() + 9*3600000).toISOString().slice(0,16); }
  $('starts-at').value = localDate(new Date());
  $('ends-at').value = localDate(new Date(Date.now()+7*86400000));
  function level() { return $('qr-only').checked ? 1 : $('line-patterns').checked ? 3 : 2; }
  function updateLevel() { if(busy)return;resetPreview();const value = level(); $('level-description').textContent = descriptions[value]; $('preview-tag').textContent = labels[value]; $('paper-demo').className = 'paper level-'+value; }
  // The two switches exclude each other: line patterns need the border layout.
  $('qr-only').addEventListener('change', () => { if ($('qr-only').checked) $('line-patterns').checked = false; updateLevel(); });
  $('line-patterns').addEventListener('change', () => { if ($('line-patterns').checked) $('qr-only').checked = false; updateLevel(); });
  updateLevel();
  function choose(file) {
    if (!file || busy) return;
    if (!file.name.toLowerCase().endsWith('.pdf') || file.size > 25*1024*1024) { status('25MB 이하의 PDF 파일을 선택하세요.', true); return; }
    resetPreview();selectedFile = file; $('file-title').textContent = file.name; $('file-detail').textContent = (file.size/1024/1024).toFixed(1)+'MB · 다른 파일을 선택하려면 클릭'; status('');
  }
  $('pdf-file').addEventListener('change', event => choose(event.target.files[0]));
  $('dropzone').addEventListener('keydown', event => { if (event.key==='Enter' || event.key===' ') { event.preventDefault(); $('pdf-file').click(); } });
  ['dragenter','dragover'].forEach(type => $('dropzone').addEventListener(type, event => { event.preventDefault(); $('dropzone').classList.add('dragging'); }));
  ['dragleave','drop'].forEach(type => $('dropzone').addEventListener(type, event => { event.preventDefault(); $('dropzone').classList.remove('dragging'); if (type==='drop') choose(event.dataTransfer.files[0]); }));
  $('tracking').addEventListener('change', () => { $('tracking-options').hidden = !$('tracking').checked; if ($('tracking').checked) updateCollector(); });
  $('generate-form').addEventListener('change',event=>{if(!busy && event.target.id!=='pdf-file')resetPreview();});
  async function updateCollector() { try { const info=await request('/api/collector'); collectorRunning=info.running; $('collector-status').textContent=info.running?'접수 서버 실행 중':'접수 서버 중지'; $('collector-toggle').textContent=info.running?'기록 중지':'기록 시작'; } catch (error) { status(error.message,true); } }
  $('collector-toggle').addEventListener('click', async () => { try { await request('/api/collector/'+(collectorRunning?'stop':'start'),{method:'POST',body:'{}'}); await updateCollector(); } catch(error) { status(error.message,true); } });
  function blobLink(blob, element, filename) { const url=URL.createObjectURL(blob); blobs.push(url); element.href=url; element.download=filename; }
  $('csv-download').addEventListener('click', async () => { try { const blob=await request('/api/scans.csv',{},false); const link=document.createElement('a'); blobLink(blob,link,'QR_접속기록.csv'); link.click(); } catch(error) { status(error.message,true); } });
  function settings() { return {intensity:level(),font_size:Number($('font-size').value),opacity:Number($('opacity').value),size_jitter:Number($('size-jitter').value),width_jitter:Number($('width-jitter').value),qr_placement:$('qr-placement').value,qr_size:Number($('qr-size').value),font_mode:'source',tracking:$('tracking').checked,base_url:$('base-url').value,starts_at:$('starts-at').value,ends_at:$('ends-at').value,retention_days:Number($('retention-days').value),max_events:Number($('max-events').value)}; }
  async function fileBase64(file) { const bytes = new Uint8Array(await file.arrayBuffer()); let result=''; for(let start=0;start<bytes.length;start+=0x8000) result+=String.fromCharCode(...bytes.subarray(start,start+0x8000)); return btoa(result); }
  const delay = ms => new Promise(resolve => setTimeout(resolve,ms));
  async function renderResult(job) {
    const [preview,pdf,manifest] = await Promise.all([request('/api/jobs/'+job.id+'/preview',{},false),request('/api/jobs/'+job.id+'/pdf',{},false),request('/api/jobs/'+job.id+'/manifest',{},false)]);
    const url=URL.createObjectURL(preview);blobs.push(url);$('result-preview').src=url;$('result-preview').hidden=false;$('paper-demo').hidden=true;
    $('preview-title').textContent='생성된 시험지';$('preview-tag').textContent=labels[job.summary.intensity]||'기본';$('preview-note').textContent='실제 PDF의 첫 페이지입니다. 내려받은 파일에서 전체 페이지를 확인하세요.';
    const summary=job.summary;
    $('result-stats').replaceChildren();
    for(const [value,label] of [[summary.pages,'쪽'],[summary.qr,'개 QR'],...(summary.intensity===3?[[summary.lines,'개 선 변경']]:[])]) { const span=document.createElement('span');span.className='stat';const b=document.createElement('b');b.textContent=value;span.append(b,' '+label);$('result-stats').append(span); }
    $('result-stats').hidden=false;blobLink(pdf,$('download-pdf'),job.name.replace(/\.pdf$/i,'')+'_워터마크.pdf');blobLink(manifest,$('download-manifest'),'워터마크_설정.json');$('result-actions').hidden=false;
    let message='완료! PDF를 내려받으세요.';
    if(summary.math_watermark) message+=' 수학 전용 수식 워터마크를 적용했습니다.';
    if(summary.captions_skipped) message+=' 본문과 겹치지 않는 공간이 없는 '+summary.captions_skipped+'개 QR의 안내 문구는 생략했습니다.';
    if(summary.skipped) message+=' 공간이 부족한 '+summary.skipped+'개 문제의 QR은 생략했습니다.';
    if(summary.intensity===3 && !summary.lines) message+=' 변경 가능한 구분선이 없어 선은 유지했습니다.';
    if(summary.tracking && !collectorRunning) message+=' IP 기록을 받으려면 접수 서버를 시작하세요.';
    status(message);
  }
  $('generate-form').addEventListener('submit',async event => {
    event.preventDefault();if(busy)return;if(!selectedFile){status('먼저 PDF 파일을 선택하세요.',true);$('pdf-file').focus();return;}
    const chosen=settings();
    if(chosen.tracking && (!chosen.starts_at || !chosen.ends_at || chosen.starts_at>=chosen.ends_at)){status('QR 접근 시작·종료 시간을 확인하세요.',true);return;}
    resetPreview();busy=true;document.querySelectorAll('#generate-form input,#generate-form select').forEach(input=>input.disabled=true);$('generate').disabled=true;$('generate').textContent='시험지를 준비하고 있어요…';$('progress').hidden=false;$('progress-fill').style.width='4%';$('result-actions').hidden=true;status('파일을 준비하고 있습니다.');
    try {
      let job=await request('/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:selectedFile.name,file:await fileBase64(selectedFile),settings:chosen})});
      while(job.state==='working') { status(job.total?job.page+' / '+job.total+'쪽 · '+job.message:job.message);$('progress-fill').style.width=(job.total?Math.max(5,job.page/job.total*95):5)+'%';await delay(900);job=await request('/api/jobs/'+job.id); }
      if(job.state==='error')throw new Error(job.message);$('progress-fill').style.width='100%';await renderResult(job);
    } catch(error) { status(error.message||'생성에 실패했습니다. 다시 시도하세요.',true); }
    finally { busy=false;document.querySelectorAll('#generate-form input,#generate-form select').forEach(input=>input.disabled=false);$('generate').disabled=false;$('generate').innerHTML='워터마크 PDF 만들기 <span aria-hidden="true">↗</span>'; }
  });
  window.addEventListener('beforeunload',()=>blobs.forEach(url=>URL.revokeObjectURL(url)));
  if(location.protocol==='file:'){status('웹실행.bat을 실행하면 이 화면이 브라우저에서 열립니다.',true);$('generate').disabled=true;}
})();
