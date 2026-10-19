// Номзод саҳифаси: битта экранда битта савол, саволлар харитаси, таймер ва автоматик сақлаш.
// Вақт серверда ҳисобланади; бу ердаги таймер фақат кўрсатиш учун.
(function () {
  const cfg = window.EXAM;
  const _ = text => (cfg.t && cfg.t[text]) || text;   // рус тилидаги таржима (бўлса)
  const cards = Array.from(document.querySelectorAll('.q-card'));
  const mapButtons = Array.from(document.querySelectorAll('#qmap button'));
  const statusEl = document.getElementById('save-status');
  const timerEl = document.getElementById('timer');
  const timerBox = document.getElementById('timer-box');
  const pending = new Map();   // questionId -> payload (ҳали юборилмаган)
  const editors = new Map();   // questionId -> TinyMCE
  let inFlight = false;
  let leaving = false;
  let current = 0;
  let endAt = Date.now() + cfg.secondsLeft * 1000;

  const store = {
    get(k, d) { try { return JSON.parse(sessionStorage.getItem(cfg.key + k)) ?? d; } catch (e) { return d; } },
    set(k, v) { try { sessionStorage.setItem(cfg.key + k, JSON.stringify(v)); } catch (e) {} },
  };
  const flags = new Set(store.get('flags', []));

  // ---------- Сақлаш ҳолати ----------
  const ICON_OK = '<svg class="ic" viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5"/></svg>';
  function setStatus(kind) {
    statusEl.classList.remove('ok', 'error');
    if (kind === 'saving') statusEl.innerHTML = _('Сақланмоқда…');
    if (kind === 'ok') { statusEl.innerHTML = ICON_OK + ' ' + _('Сақланди'); statusEl.classList.add('ok'); }
    if (kind === 'error') { statusEl.innerHTML = _('⚠ Сақланмади — қайта уринилмоқда'); statusEl.classList.add('error'); }
  }

  // ---------- Жавоб ҳолати ----------
  function isAnswered(card) {
    if (card.dataset.type === 'choice') return !!card.querySelector('input[type=radio]:checked');
    const ed = editors.get(card.dataset.question);
    const html = ed ? ed.getContent() : card.querySelector('textarea').value;
    return html.replace(/<[^>]*>/g, '').replace(/&nbsp;/g, '').trim().length > 0 || /<table/i.test(html);
  }

  function refreshMap() {
    let answered = 0;
    cards.forEach((card, i) => {
      const done = isAnswered(card);
      if (done) answered++;
      const b = mapButtons[i];
      b.classList.toggle('answered', done);
      b.classList.toggle('current', i === current);
      b.classList.toggle('flagged', flags.has(card.dataset.question));
      const fb = card.querySelector('[data-flag]');
      fb.classList.toggle('on', flags.has(card.dataset.question));
      fb.querySelector('span').textContent = flags.has(card.dataset.question) ? _('Белгиланган') : _('Кейин қайтиш учун белгилаш');
    });
    document.getElementById('progress-bar').style.width = (cards.length ? answered * 100 / cards.length : 0) + '%';
    document.getElementById('progress-lbl').textContent = _('Жавоб берилди:') + ' ' + answered + ' / ' + cards.length;
    return answered;
  }

  // ---------- Навигация ----------
  function show(i) {
    if (!cards.length || i < 0 || i >= cards.length) return;
    cards[current].classList.add('hidden');
    current = i;
    const card = cards[current];
    card.classList.remove('hidden');
    if (card.dataset.type === 'text') ensureEditor(card);
    store.set('current', current);
    refreshMap();
    window.scrollTo({top: 0, behavior: 'smooth'});
  }

  document.addEventListener('click', e => {
    if (e.target.closest('[data-next]')) show(current + 1);
    else if (e.target.closest('[data-prev]')) show(current - 1);
    else if (e.target.closest('[data-goto]')) show(parseInt(e.target.closest('[data-goto]').dataset.goto, 10));
    else if (e.target.closest('[data-flag]')) {
      const qid = cards[current].dataset.question;
      flags.has(qid) ? flags.delete(qid) : flags.add(qid);
      store.set('flags', Array.from(flags));
      refreshMap();
    } else if (e.target.closest('[data-finish]')) finish();
  });

  document.addEventListener('keydown', e => {
    if (e.target.closest('input[type=text], textarea, .tox, [contenteditable]') || document.querySelector('.modal-back')) return;
    if (e.key === 'ArrowRight') show(current + 1);
    if (e.key === 'ArrowLeft') show(current - 1);
  });

  const instr = document.getElementById('instr');
  if (instr) {
    if (store.get('instrHidden', false)) instr.classList.add('hidden');
    document.getElementById('instr-hide').addEventListener('click', () => { instr.classList.add('hidden'); store.set('instrHidden', true); });
  }

  // ---------- Сақлаш ----------
  function queue(questionId, payload) {
    pending.set(questionId, Object.assign({question: questionId}, payload));
    setStatus('saving');
    flushSoon();
    refreshMap();
  }

  let flushTimer = null;
  function flushSoon() { clearTimeout(flushTimer); flushTimer = setTimeout(flush, 400); }

  async function flush() {
    if (inFlight || pending.size === 0) return pending.size === 0;
    inFlight = true;
    let ok = true;
    for (const [qid, payload] of Array.from(pending.entries())) {
      try {
        const res = await fetch(cfg.saveUrl, {
          method: 'POST',
          headers: {'Content-Type': 'application/json', 'X-CSRFToken': cfg.csrf},
          body: JSON.stringify(payload),
          credentials: 'same-origin',
        });
        const data = await res.json().catch(() => ({}));
        if (res.ok && data.ok) {
          if (pending.get(qid) === payload) pending.delete(qid);
          if (typeof data.seconds_left === 'number') endAt = Date.now() + data.seconds_left * 1000;
        } else if (data.reload) {
          pending.clear();
          goTo(cfg.takeUrl);
          return false;
        } else ok = false;
      } catch (e) { ok = false; }
    }
    inFlight = false;
    if (!ok) { setStatus('error'); setTimeout(flush, 3000); }
    else if (pending.size === 0) setStatus('ok');
    else flushSoon();
    return ok && pending.size === 0;
  }

  async function flushAll(maxWaitMs) {
    const until = Date.now() + maxWaitMs;
    while ((pending.size > 0 || inFlight) && Date.now() < until) {
      if (!inFlight) await flush();
      await new Promise(r => setTimeout(r, 200));
    }
  }

  function goTo(url) { leaving = true; window.location.href = url; }

  document.querySelectorAll('.q-card[data-type="choice"] input[type=radio]').forEach(input => {
    input.addEventListener('change', () => queue(input.closest('.q-card').dataset.question, {option: input.value}));
  });

  function ensureEditor(card) {
    const qid = card.dataset.question;
    if (editors.has(qid)) return;
    editors.set(qid, null);
    initEditor('#ans' + qid, {
      setup(editor) {
        editors.set(qid, editor);
        let t = null;
        const save = () => { clearTimeout(t); t = setTimeout(() => queue(qid, {text: editor.getContent()}), 800); };
        editor.on('input change undo redo keyup', save);
        editor.on('paste drop', e => e.preventDefault());  // нусха кўчиришни тақиқлаш
      },
    }, 'candidate');
  }

  function collectEditors() {
    editors.forEach((ed, qid) => { if (ed) queue(qid, {text: ed.getContent()}); });
  }

  // ---------- Модал ----------
  function modal(title, html, okText, okClass) {
    return new Promise(resolve => {
      const back = document.createElement('div');
      back.className = 'modal-back';
      back.innerHTML = '<div class="modal" role="dialog"><h2></h2><div class="m-body"></div><div class="actions">' +
        (okText ? '<button type="button" class="btn secondary" data-a="0">' + _('Қайтиш') + '</button>' : '') +
        '<button type="button" class="btn ' + (okClass || '') + '" data-a="1">' + (okText || _('Тушунарли')) + '</button></div></div>';
      back.querySelector('h2').textContent = title;
      back.querySelector('.m-body').innerHTML = html;
      document.body.appendChild(back);
      back.querySelector('[data-a="1"]').focus();
      back.addEventListener('click', e => {
        const a = e.target.closest('[data-a]');
        if (a) { back.remove(); resolve(a.dataset.a === '1'); }
      });
    });
  }

  async function finish() {
    collectEditors();
    const answered = refreshMap();
    const left = cards.length - answered;
    const what = cfg.isLast ? _('Тестни якунлайсизми?') : _('Блокни якунлаб, кейингисига ўтасизми?');
    let html = '<p>' + (cfg.isLast
      ? _('Якунлагандан кейин жавобларни ўзгартириб бўлмайди.')
      : _('Кейинги блокка ўтгач, бу блокка қайтиб бўлмайди.')) + '</p>';
    html += '<p>' + _('Жавоб берилган саволлар:') + ' <b>' + answered + ' / ' + cards.length + '</b></p>';
    if (left > 0) html += '<div class="warn-box">⚠ ' + left + ' ' + _('та саволга жавоб берилмаган. Улар 0 балл билан баҳоланади.') + '</div>';
    if (flags.size) html += '<div class="warn-box">⚑ ' + flags.size + ' ' + _('та савол «кейин қайтиш учун» белгиланган.') + '</div>';
    if (!(await modal(what, html, cfg.isLast ? _('Ҳа, якунлаш') : _('Ҳа, кейинги блокка'), 'success'))) return;
    document.querySelectorAll('[data-finish]').forEach(b => b.disabled = true);
    setStatus('saving');
    await flushAll(10000);
    if (pending.size > 0) {
      document.querySelectorAll('[data-finish]').forEach(b => b.disabled = false);
      await modal(_('Жавоблар сақланмади'), '<p>' + _('Тармоқни текширинг ва қайтадан уриниб кўринг ёки назоратчини чақиринг.') + '</p>');
      return;
    }
    leaving = true;
    HTMLFormElement.prototype.submit.call(document.getElementById('next-form'));
  }

  // ---------- Таймер ----------
  function tick() {
    const left = Math.max(0, Math.round((endAt - Date.now()) / 1000));
    const h = Math.floor(left / 3600), m = Math.floor(left % 3600 / 60), s = left % 60;
    timerEl.textContent = (h ? h + ':' + String(m).padStart(2, '0') : String(m).padStart(2, '0')) + ':' + String(s).padStart(2, '0');
    timerBox.classList.toggle('low', left <= 60);
    if (left <= 0) {
      clearInterval(timerHandle);
      collectEditors();
      document.querySelectorAll('input, button').forEach(el => el.disabled = true);
      editors.forEach(ed => ed && ed.mode.set('readonly'));
      modal(_('Вақт тугади'), '<p>' + _('Жавобларингиз сақланмоқда. Бир оздан кейин кейинги қисм очилади.') + '</p>');
      flushAll(8000).then(() => goTo(cfg.takeUrl));
    }
  }
  const timerHandle = setInterval(tick, 1000);
  tick();

  window.addEventListener('beforeunload', e => {
    if (!leaving && pending.size > 0) { e.preventDefault(); e.returnValue = ''; }
  });

  show(Math.min(store.get('current', 0), cards.length - 1));
})();
