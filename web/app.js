/* SPDX-License-Identifier: GPL-3.0-only; Copyright (C) 2026 JM-KIMM and contributors. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const token = document.querySelector('meta[name="local-token"]').content;
  const blobs = [];
  let selectedFile = null, busy = false, completedJob = null;
  function status(message, error = false) {
    $('status').textContent = message; $('status').classList.toggle('error', error);
  }
  async function request(path, options = {}, json = true) {
    const response = await fetch(path, {...options, headers: {'X-Local-Token': token, ...options.headers}});
    if (!response.ok) {
      let message = '요청을 처리하지 못했습니다.';
      try { message = (await response.json()).error || message; } catch {}
      throw new Error(message);
    }
    return json ? response.json() : response.blob();
  }
  function blobLink(blob, element, filename) {
    const url = URL.createObjectURL(blob); blobs.push(url); element.href = url; element.download = filename;
  }
  async function renderResult(job) {
    const [preview, pdf, manifest] = await Promise.all(
      ['preview','pdf','manifest'].map(kind => request('/api/jobs/'+job.id+'/'+kind, {}, false)));
    blobs.splice(0).forEach(url => URL.revokeObjectURL(url));
    const url = URL.createObjectURL(preview); blobs.push(url); $('result-preview').src = url;
    blobLink(pdf, $('download-pdf'), job.name.replace(/\.pdf$/i, '')+'_워터마크.pdf');
    blobLink(manifest, $('download-manifest'), '워터마크_처리기록.json');
    const s = job.summary;
    $('result-stats').textContent = `${s.pages}쪽 · QR ${s.qr}개 · 박스 ${s.boxes || 0}개 교체`;
    $('result').hidden = false;
    let message = '완료했습니다. PDF를 내려받으세요.';
    if (s.math_watermark) message += ' 수학 전용 수식을 적용했습니다.';
    if (s.skipped) message += ` 고정 위치가 겹치는 ${s.skipped}개 QR은 생략했습니다. 처리 기록을 확인하세요.`;
    status(message);
  }
  async function fileBase64(file) {
    const bytes = new Uint8Array(await file.arrayBuffer()); let result = '';
    for (let start=0; start<bytes.length; start+=0x8000) result += String.fromCharCode(...bytes.subarray(start,start+0x8000));
    return btoa(result);
  }
  async function generate() {
    if (busy || !selectedFile) return;
    busy = true; $('pdf-file').disabled = true; $('dropzone').setAttribute('aria-disabled','true');
    $('retry').hidden = true; $('result').hidden = true; $('progress').hidden = false; $('progress').value = 2;
    status('파일을 준비하고 있습니다.');
    try {
      if (!completedJob) {
        let job = await request('/api/jobs', {method:'POST', headers:{'Content-Type':'application/json'},
          body:JSON.stringify({filename:selectedFile.name, file:await fileBase64(selectedFile), settings:{}})});
        const deadline = Date.now()+16*60*1000;
        while (job.state === 'working') {
          if (Date.now() > deadline) throw new Error('처리 시간이 초과됐습니다. 페이지 수를 줄여 다시 시도하세요.');
          status(job.total ? `${job.page} / ${job.total}쪽 · ${job.message}` : job.message);
          $('progress').value = job.total ? Math.max(5,job.page/job.total*95) : 5;
          await new Promise(resolve => setTimeout(resolve,900)); job = await request('/api/jobs/'+job.id);
        }
        if (job.state !== 'done') throw new Error(job.message || '생성하지 못했습니다.');
        completedJob = job;
      }
      await renderResult(completedJob); $('progress').value = 100;
    } catch (error) {
      status(error.message || '생성에 실패했습니다. 다시 시도하세요.', true); $('retry').hidden = false;
    } finally {
      busy = false; $('pdf-file').disabled = false; $('pdf-file').value = '';
      $('dropzone').setAttribute('aria-disabled','false'); $('progress').hidden = true;
    }
  }
  function choose(file) {
    if (!file || busy) return;
    if (!file.name.toLowerCase().endsWith('.pdf') || file.size > 25*1024*1024 || !file.size) {
      status('25MB 이하의 PDF 파일을 선택하세요.',true); $('pdf-file').value = ''; return;
    }
    selectedFile = file; completedJob = null; $('file-title').textContent = file.name;
    $('file-detail').textContent = `${(file.size/1024/1024).toFixed(1)}MB · 선택하면 자동 생성`; generate();
  }
  $('pdf-file').addEventListener('change', event => choose(event.target.files[0]));
  $('dropzone').addEventListener('keydown', event => {
    if (event.key === 'Enter' || event.key === ' ') {event.preventDefault(); if (!busy) $('pdf-file').click();}
  });
  ['dragenter','dragover'].forEach(type => $('dropzone').addEventListener(type,event => {
    event.preventDefault(); if (!busy) $('dropzone').classList.add('dragging');
  }));
  ['dragleave','drop'].forEach(type => $('dropzone').addEventListener(type,event => {
    event.preventDefault(); $('dropzone').classList.remove('dragging'); if (type === 'drop') choose(event.dataTransfer.files[0]);
  }));
  $('retry').addEventListener('click',generate);
  window.addEventListener('beforeunload', () => blobs.forEach(url => URL.revokeObjectURL(url)));
  if (location.protocol === 'file:') {
    status('웹실행.bat을 실행해 열린 브라우저에서 사용하세요.',true); $('pdf-file').disabled = true;
  }
})();
