(() => {
  'use strict';
  const $=id=>document.getElementById(id), token=document.querySelector('meta[name="local-token"]').content;
  let last=0,rows=[],running=false,polling=false,signature='';
  async function request(path,options={},blob=false){
    const r=await fetch(path,{...options,headers:{'X-Local-Token':token,'Content-Type':'application/json',...options.headers}});
    if(!r.ok){let message='요청을 처리하지 못했습니다.';try{message=(await r.json()).error||message;}catch{}throw new Error(message);}
    return blob?r.blob():r.json();
  }
  function renderRows(){
    const body=$('events');body.replaceChildren();
    if(!rows.length){const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=7;td.textContent='접속 기록이 없습니다.';tr.append(td);body.append(tr);return;}
    for(const r of rows){const tr=document.createElement('tr');for(const v of [r.timestamp_kst.replace('T',' ').replace('+09:00',''),r.issuance_ref||'공유·미배정',r.ip,r.title,`${r.page} / ${r.question}`,r.status===200?'기록됨':'중지된 링크',r.user_agent]){const td=document.createElement('td');td.textContent=String(v);td.title=String(v);tr.append(td);}body.append(tr);}
  }
  async function update(){
    if(polling)return;polling=true;
    try{
      const d=await request('/api/dashboard?after='+last);running=d.collector.running;
      if(d.last_id<last){last=0;rows=[];}
      rows=[...d.events,...rows].filter((r,i,a)=>a.findIndex(v=>v.id===r.id)===i).sort((a,b)=>b.id-a.id).slice(0,200);
      last=d.last_id;renderRows();$('total').textContent=d.total;$('visitors').textContent=d.observed_ips;$('campaigns').textContent=d.campaigns.length;
      $('server').textContent=(running?'접수 중 · ':'중지 · ')+d.collector.base_url;$('toggle').textContent=running?'서버 중지':'서버 시작';
      $('updated').textContent='1초 갱신 · '+new Date().toLocaleTimeString('ko-KR');
      const next=JSON.stringify(d.campaigns);
      if(next!==signature){signature=next;$('issued').replaceChildren();for(const c of d.campaigns){const div=document.createElement('div'),span=document.createElement('span'),button=document.createElement('button');div.className='issuance';span.textContent=`${c.issuance_ref||'공유·미배정'} · ${c.title} · QR ${c.issued}개`;button.textContent=c.active?'링크 중지':'링크 재개';button.addEventListener('click',async()=>{try{await request('/api/campaign/active',{method:'POST',body:JSON.stringify({campaign_id:c.id,active:!c.active})});signature='';await update();}catch(e){$('updated').textContent=e.message;}});div.append(span,button);$('issued').append(div);}}
    }catch(e){$('updated').textContent=e.message;}finally{polling=false;}
  }
  $('toggle').addEventListener('click',async()=>{try{await request('/api/collector/'+(running?'stop':'start'),{method:'POST',body:'{}'});await update();}catch(e){$('updated').textContent=e.message;}});
  for(const [id,name] of [['events-csv','events.csv'],['visitors-csv','visitors.csv']])$(id).addEventListener('click',async()=>{try{const blob=await request('/api/archive/'+name,{},true),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);}catch(e){$('updated').textContent=e.message;}});
  update();setInterval(update,1000);
})();
