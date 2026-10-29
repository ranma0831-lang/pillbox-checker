// 약 복용 확인 휴대폰 화면. 판정은 PC 프로그램이 하고 여기서는 받은 값만 그린다.
const K = new URLSearchParams(location.search).get('k') || '';
const $ = id => document.getElementById(id);
const toM = s => { const [h, m] = s.split(':').map(Number); return h * 60 + m; };
const fm = m => String(Math.floor(m / 60)).padStart(2, '0') + ':' + String(Math.round(m % 60)).padStart(2, '0');
const WD = ['일', '월', '화', '수', '목', '금', '토'];
const dLabel = iso => { const d = new Date(iso + 'T00:00'); return `${d.getMonth() + 1}월 ${d.getDate()}일 (${WD[d.getDay()]})`; };
const EV = { lid_open: '뚜껑 열림', lid_close: '뚜껑 닫힘', press: '본인 확인 (버튼)', early_press: '인정 전 누름 · 판정에 쓰지 않음', ack: '가족 확인',
  connect: '상자 연결됨', disconnect: '상자 연결 끊김', setting: '복용 시각 변경', unconfirmed: '보드 적용 미확인' };
const STATUS = { done: ['✓', at => `오늘 ${at} 확인됨`], late: ['!', at => `오늘 ${at} 늦게 확인됨`], before: ['–', () => '아직 인정 시간 전'],
  window: ['–', () => '곧 드실 시간'], due: ['…', () => '지금 드실 시간'], caution: ['!', () => '아직 확인 안 됨'],
  warning: ['✕', () => '확인 안 됨 · 1시간 지남'], unknown: ['?', () => '상태를 알 수 없음'] };
const DAYWORD = { done: '제시간 확인', late: '늦게 확인', missed: '놓침', none: '기록 없음' };

let S = null, H = [], sel = null, paused = false, alertsOn = false, soundTimer = null, lastLive = '', timer = null;

async function api(path, body) {
  const sep = path.includes('?') ? '&' : '?';
  const r = await fetch(`${path}${sep}k=${encodeURIComponent(K)}`, body === undefined ? {} :
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) { const e = new Error(data.error || `오류 ${r.status}`); e.status = r.status; throw e; }
  return data;
}

async function poll() {
  try {
    const [s, h] = await Promise.all([api('/api/state'), api('/api/history?days=35')]);
    S = s; H = h;
    if (!sel || !H.some(d => d.date === sel)) sel = S.date;
    render();
  } catch (e) {
    offline(e.status === 403 ? '접속 주소를 다시 확인해 주세요' : 'PC 프로그램에 연결할 수 없어요');
  }
}

function offline(text) {
  $('conn').className = 'conn off';
  $('conn').querySelector('.sp').innerHTML = `<b>${text}</b>`;
  say(text);
  stopSound();
}

function say(text) { if (text !== lastLive) { lastLive = text; $('live').textContent = text; } }

function render() {
  const s = S;
  $('demo').hidden = !s.demo;
  const c = $('conn');
  c.className = 'conn' + (s.board.connected ? '' : ' off');
  const age = s.board.last_rx_age_s;
  c.querySelector('.sp').innerHTML = s.board.connected
    ? `상자 연결됨 · ${paused ? '갱신 멈춤' : `${age ?? 0}초 전 수신`}`
    : `<b>상자 연결 끊김</b>${s.board.reason === 'busy' ? ' · 다른 프로그램이 포트를 쓰고 있어요' : ''}${age != null ? ` · ${Math.round(age / 60)}분 전 마지막 수신` : ''}`;

  // 알림 띠
  const lids = s.lid_events.length;
  let bn = '';
  if (s.alert === 'unknown') bn = `<div class="banner unknown"><b>⚠ 상자 상태를 알 수 없어요</b><p>PC 프로그램이나 USB 연결을 확인해 주세요. 마지막으로 받은 기록까지만 보여 줍니다.</p></div>`;
  else if (s.alert === 'caution' || s.alert === 'warning') {
    const w = s.alert === 'warning';
    bn = `<div class="banner ${s.alert}" ${w && !s.acked_at ? 'role="alert"' : ''}><b>${w ? '✕ 1시간이 지났는데 아직 확인되지 않았어요' : '! 아직 확인되지 않았어요'}</b>
      <p>복용 시각 ${s.dose_time} · 뚜껑 열림 ${lids}회, 버튼 확인 없음${s.acked_at ? ` · 가족 확인 ${s.acked_at}` : ''}</p>
      ${s.acked_at ? '' : `<div class="row"><button class="btn primary" id="ack" type="button">확인했어요</button>${alertsOn ? '<button class="btn" id="mute" type="button">소리 끄기</button>' : ''}</div>`}</div>`;
  }
  $('banner').innerHTML = bn;
  if ($('ack')) $('ack').onclick = async () => { try { S = await api('/api/ack', {}); stopSound(); render(); $('h-today').focus(); } catch (e) { say(e.message); } };
  if ($('mute')) $('mute').onclick = () => { setAlerts(false); render(); };

  // 상태 카드
  const [ic, text] = STATUS[s.status] || STATUS.unknown;
  const big = text(s.at);
  $('status').className = 'status s-' + s.status;
  $('status').innerHTML = `<span class="ic" aria-hidden="true">${ic}</span><span class="big">${big}</span><span class="sub">${dLabel(s.date)} · 지금 ${s.now}</span>`;
  $('meta').innerHTML = `<div>복용 시각<b>${s.dose_time}</b></div><div>인정 시작<b>${fm(toM(s.dose_time) - 120)}</b></div><div>뚜껑 열림<b>${lids}회</b></div>`;
  say(`오늘 상태: ${big}`);
  document.title = (s.alert === 'warning' && !s.acked_at ? '(!) ' : '') + '약 복용 확인';
  if (document.activeElement !== $('dose')) $('dose').value = s.dose_time;

  if (s.alert === 'warning' && !s.acked_at && alertsOn) { if (!soundTimer) startSound(); } else stopSound();
  renderTimeline(); renderCal(); renderTrend(); renderLog();
}

const dayOf = iso => iso === S.date ? { date: S.date, status: S.status, at: S.at, events: S.events } : H.find(d => d.date === iso);

function renderTimeline() {
  const d = dayOf(sel), isT = sel === S.date, dose = toM(S.dose_time), A = 240, B = 1440;
  const X = m => 20 + (Math.min(B, Math.max(A, m)) - A) / (B - A) * 320;
  let s = `<svg viewBox="0 0 360 130" role="img" aria-label="${dLabel(sel)} 타임라인. 자세한 내용은 아래 기록 표에 있습니다.">`;
  s += `<text x="20" y="14" font-size="12" style="fill:var(--fg);font-weight:500">${dLabel(sel)}${isT ? ' · 오늘' : ''}</text>`;
  s += `<rect x="${X(dose - 120)}" y="30" width="${X(dose) - X(dose - 120)}" height="56" style="fill:var(--zone-win)"/><rect x="${X(dose)}" y="30" width="${X(dose + 30) - X(dose)}" height="56" style="fill:var(--zone-grace)"/>`;
  s += `<line x1="20" y1="72" x2="340" y2="72" style="stroke:var(--line)" stroke-width="2"/>`;
  for (let h = 4; h <= 24; h += 2) { const x = X(h * 60); s += `<line x1="${x}" y1="86" x2="${x}" y2="${h % 4 ? 90 : 93}" style="stroke:var(--muted)"/>`; if (h % 4 === 0) s += `<text x="${x}" y="106" font-size="11" text-anchor="middle">${String(h).padStart(2, '0')}</text>`; }
  s += `<line x1="${X(dose)}" y1="24" x2="${X(dose)}" y2="88" style="stroke:var(--accent)" stroke-width="2"/><text x="${X(dose) + 3}" y="26" font-size="10" style="fill:var(--accent)">복용 ${S.dose_time}</text>`;
  if (isT) { const x = X(toM(S.now)); s += `<line x1="${x}" y1="30" x2="${x}" y2="88" style="stroke:var(--fg)" stroke-dasharray="3 3"/><text x="${x}" y="122" font-size="10" text-anchor="middle" style="fill:var(--fg)">지금</text>`; }
  for (const e of d.events) {
    const x = X(toM(e.t));
    if (e.e === 'lid_open') s += `<path d="M${x} 44l-6 10h12z" style="fill:var(--muted)"><title>뚜껑 열림 ${e.t}</title></path>`;
    else if (e.e === 'early_press') s += `<circle cx="${x}" cy="72" r="7" style="fill:var(--surface);stroke:var(--muted)" stroke-width="2"><title>인정 전 누름 ${e.t}</title></circle>`;
    else if (e.e === 'ack') s += `<path d="M${x} 84l6 6-6 6-6-6z" style="fill:var(--accent)"><title>가족 확인 ${e.t}</title></path>`;
  }
  if (d.at) { const x = X(toM(d.at)); s += `<g><circle cx="${x}" cy="72" r="9" style="fill:var(--ok)"/><path d="M${x - 4} 72l3 3 5-6" fill="none" style="stroke:var(--surface)" stroke-width="2"/><title>본인 확인 ${d.at}</title></g>`; }
  if (d.status === 'none') s += `<text x="180" y="62" font-size="12" text-anchor="middle" style="fill:var(--fg)">이날은 PC가 꺼져 기록이 없습니다</text>`;
  $('tl').innerHTML = s + '</svg>';
}

function renderCal() {
  const t = new Date(S.date + 'T00:00'), y = t.getFullYear(), m = t.getMonth();
  $('h-cal').textContent = `${y}년 ${m + 1}월`;
  const first = (new Date(y, m, 1).getDay() + 6) % 7, days = new Date(y, m + 1, 0).getDate();
  const SY = { done: '✓', late: '!', missed: '✕', none: '·' };
  let h = ['월', '화', '수', '목', '금', '토', '일'].map(w => `<span class="wd" aria-hidden="true">${w}</span>`).join('') + '<span></span>'.repeat(first);
  for (let n = 1; n <= days; n++) {
    const iso = `${y}-${String(m + 1).padStart(2, '0')}-${String(n).padStart(2, '0')}`, d = dayOf(iso);
    if (!d) { h += `<span class="day empty" aria-hidden="true"><span class="n">${n}</span></span>`; continue; }
    const today = iso === S.date, fin = d.status in SY, lids = d.events.filter(e => e.e === 'lid_open').length;
    const word = DAYWORD[d.status] || '진행 중';
    h += `<button type="button" class="day ${fin ? d.status : ''}${today ? ' today' : ''}" data-d="${iso}" aria-pressed="${iso === sel}" tabindex="${iso === sel ? 0 : -1}"
      aria-label="${dLabel(iso)}, ${word}${d.at ? ' ' + d.at : ''}, 뚜껑 열림 ${lids}회"><span class="n">${n}</span><span class="sy" aria-hidden="true">${fin ? SY[d.status] : '…'}</span><span class="tm" aria-hidden="true">${d.at || (lids ? '▲' + lids : '')}</span></button>`;
  }
  $('cal').innerHTML = h;
}
function pick(iso) { if (!dayOf(iso)) return; sel = iso; render(); $('cal').querySelector(`[data-d="${sel}"]`)?.focus(); }
$('cal').addEventListener('click', e => { const b = e.target.closest('button.day'); if (b) pick(b.dataset.d); });
$('cal').addEventListener('keydown', e => {
  const k = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[e.key]; if (!k || !sel) return;
  e.preventDefault(); const d = new Date(sel + 'T00:00'); d.setDate(d.getDate() + k);
  pick(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`);
});

function renderTrend() {
  const ds = H.slice(-14), dose = toM(S.dose_time), A = 300, B = 660;
  const Y = m => 150 - (Math.min(B, Math.max(A, m)) - A) / (B - A) * 120, X = i => 44 + i * 21.5;
  let s = `<svg viewBox="0 0 360 185" role="img" aria-label="최근 14일 확인 시각. 날짜별 값은 달력과 기록 표에도 있습니다.">`;
  s += `<rect x="34" y="${Y(dose + 30)}" width="316" height="${Y(dose - 120) - Y(dose + 30)}" style="fill:var(--zone-win)"/>`;
  for (let h = 5; h <= 11; h++) { const y = Y(h * 60); s += `<line x1="34" y1="${y}" x2="350" y2="${y}" style="stroke:var(--line)"/>`; if (h % 2) s += `<text x="30" y="${y + 4}" font-size="10" text-anchor="end">${String(h).padStart(2, '0')}:00</text>`; }
  s += `<line x1="34" y1="${Y(dose)}" x2="350" y2="${Y(dose)}" style="stroke:var(--accent)" stroke-width="1.5" stroke-dasharray="5 3"/>`;
  ds.forEach((d, i) => {
    const x = X(i), n = +d.date.slice(8);
    if (i % 2 === 1 || i === ds.length - 1) s += `<text x="${x}" y="176" font-size="10" text-anchor="middle">${n}</text>`;
    if (d.at) s += `<circle cx="${x}" cy="${Y(toM(d.at))}" r="5" style="fill:${d.status === 'late' ? 'var(--warn)' : 'var(--ok)'}"><title>${dLabel(d.date)} ${d.at}</title></circle>`;
    else if (d.status === 'missed') s += `<text x="${x}" y="${Y(B) + 12}" font-size="14" text-anchor="middle" style="fill:var(--bad);font-weight:700">✕<title>${dLabel(d.date)} 놓침</title></text>`;
    else if (d.status === 'none') s += `<text x="${x}" y="${Y(B) + 12}" font-size="14" text-anchor="middle">·<title>${dLabel(d.date)} 기록 없음</title></text>`;
  });
  $('trend').innerHTML = s + '</svg>';
  const wk = H.slice(-7).filter(d => d.date !== S.date || d.at), ok = wk.filter(d => d.at);
  const avg = ok.length ? ok.reduce((a, d) => a + toM(d.at), 0) / ok.length : null;
  $('sum').innerHTML = `<div>최근 7일 확인<b>${ok.length}/${wk.length}일</b></div><div>평균 확인<b>${avg == null ? '—' : fm(avg)}</b></div><div>복용 시각 대비<b>${avg == null ? '—' : (avg - dose >= 0 ? '+' : '−') + Math.abs(Math.round(avg - dose)) + '분'}</b></div>`;
}

function renderLog() {
  const d = dayOf(sel);
  $('log-cap').textContent = dLabel(sel) + ' 기록';
  $('log').innerHTML = d.events.length ? d.events.map(e => `<tr><td>${e.t}</td><td>${EV[e.e] || e.e}</td></tr>`).join('')
    : `<tr><td>—</td><td>${d.status === 'none' ? 'PC가 꺼져 기록 없음' : '아직 기록 없음'}</td></tr>`;
}

// 설정
$('set-form').addEventListener('submit', async e => {
  e.preventDefault();
  const v = $('dose').value, err = $('dose-err');
  if (!/^\d{2}:\d{2}$/.test(v)) { err.textContent = '복용 시각을 시:분 형식으로 입력해 주세요 (예: 08:00).'; $('dose').setAttribute('aria-invalid', 'true'); return; }
  try { S = await api('/api/settings', { dose_time: v }); err.textContent = ''; $('dose').removeAttribute('aria-invalid'); say(`복용 시각을 ${v}로 저장했습니다`); poll(); }
  catch (x) { err.textContent = x.message; $('dose').setAttribute('aria-invalid', 'true'); }
});

// 알림 소리: 사용자가 버튼을 누른 뒤에만 (브라우저 정책)
let actx = null;
function beep() { try { actx = actx || new AudioContext(); const o = actx.createOscillator(), g = actx.createGain(); o.frequency.value = 880; g.gain.value = .15; o.connect(g).connect(actx.destination); o.start(); o.stop(actx.currentTime + .35); } catch (e) { } }
function startSound() { beep(); try { navigator.vibrate?.([300, 150, 300]); } catch (e) { } soundTimer = setInterval(beep, 4000); }
function stopSound() { clearInterval(soundTimer); soundTimer = null; }
function setAlerts(on) {
  alertsOn = on; $('alerts').setAttribute('aria-pressed', on); $('alerts').textContent = on ? '알림 소리 켜짐' : '알림 소리 켜기';
  if (on) { try { actx = actx || new AudioContext(); actx.resume(); } catch (e) { } } else stopSound();
}
$('alerts').onclick = () => { setAlerts(!alertsOn); if (S) render(); };
$('pause').onclick = () => {
  paused = !paused; $('pause').setAttribute('aria-pressed', paused); $('pause').textContent = paused ? '자동 갱신 다시 시작' : '자동 갱신 멈춤';
  clearInterval(timer); if (!paused) { poll(); timer = setInterval(poll, 2000); } else if (S) render();
};

poll();
timer = setInterval(poll, 2000);
