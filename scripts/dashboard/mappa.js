// La mappa della home: nodi (progetti, argomenti) con i task a raggiera, la prossima azione e il dettaglio nel pannello.
// Tutto in un IIFE: gli helper hanno il nome di quelli di dashboard.js (che carica dopo) e non devono scontrarsi.
(function () {
  const NS = 'http://www.w3.org/2000/svg';
  const STATI = ['da_fare', 'in_corso', 'fatto'];
  const NOME_STATO = { da_fare: 'da fare', in_corso: 'in corso', fatto: 'fatto' };
  const FILTRI = [['tutto', 'Tutto'], ['aperti', 'Aperti'], ['progetti', 'Progetti'], ['argomenti', 'Argomenti']];

  let dati = null;          // l'ultima risposta di /api/mappa
  let progetti = [];        // /api/stato, per «Dove sono» e l'ultimo commit
  let giorni = [];          // /api/oggi, voci con data
  let impronta = '';        // per non ridisegnare (e non interrompere un hover) se nulla è cambiato
  let filtro = 'tutto';
  let aperto = null;        // UN solo nodo aperto: nome del nodo sotto il puntatore o col fuoco
  let fissato = null;       // nome del nodo fissato con un clic
  let selezione = null;     // task scelto (clic su un satellite)
  let nodiSvg = new Map();  // nome -> gruppo SVG
  let pos = new Map();      // nome -> {x, y, r}
  let dimensione = '';
  let vista = { k: 1, x: 0, y: 0 };   // zoom e spostamento: si conservano a ogni ridisegno

  const $ = id => document.getElementById(id);
  function h(tag, classe, figli, attr) {
    const n = document.createElement(tag);
    if (classe) n.className = classe;
    (figli || []).forEach(f => f && n.appendChild(typeof f === 'string' ? document.createTextNode(f) : f));
    for (const k in attr || {}) n.setAttribute(k, attr[k]);
    return n;
  }
  function s(tag, attr, figli) {
    const n = document.createElementNS(NS, tag);
    for (const k in attr || {}) n.setAttribute(k, attr[k]);
    (figli || []).forEach(f => n.appendChild(typeof f === 'string' ? document.createTextNode(f) : f));
    return n;
  }
  function bottone(testo, classe, onclick) {
    const b = h('button', classe, [testo], { type: 'button' });
    b.addEventListener('click', onclick);
    return b;
  }
  const K_MIN = 0.6, K_MAX = 3;       // oltre questi limiti le etichette si toccano o i nodi escono dal riquadro
  const aperti = n => n.task.filter(t => t.stato !== 'fatto').length;
  const puoAggiungere = n => n.haCartella && n.tipo !== 'senza' && /^[A-Za-z][\p{L}\p{N}_-]*$/u.test(n.nome);   // il nome del nodo è il tag: deve essere un tag valido
  const haPiu = n => aperti(n) === 0 && puoAggiungere(n);   // nodo senza task da fare: un «+» per scriverne uno
  // Il «+» sta due volte: sul nodo, e sopra la zona dei satelliti quando il nodo è aperto (la zona copre il bordo del disco).
  function piu(n, p) {
    const A = s('g', { class: 'azione', transform: `translate(${(p.x + p.r * 0.78).toFixed(1)} ${(p.y - p.r * 0.78).toFixed(1)})`, tabindex: 0, role: 'button', 'aria-label': 'Aggiungi un task a ' + n.nome });
    A.append(s('title', {}, ['Aggiungi un task']), s('g', { class: 'azione-dentro' }, [s('circle', { r: 12 }), s('text', { dy: '0.35em' }, ['+'])]));
    A.addEventListener('click', e => { e.stopPropagation(); nuovoTask(n); });
    A.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); nuovoTask(n); } });
    return A;
  }
  const nodoPer = nome => dati && dati.nodi.find(n => n.nome === nome);
  function taglia(testo, max) {
    if (testo.length <= max) return testo;
    const t = testo.slice(0, max), i = t.lastIndexOf(' ');
    return (i > max / 2 ? t.slice(0, i) : t).replace(/[\s,;:.]+$/, '') + '…';
  }
  function giornoBreve(iso) {
    return new Date(iso + 'T12:00').toLocaleDateString('it-IT', { day: 'numeric', month: 'short' }).replace('.', '');
  }

  // ---- dati di prova (?prova=vuoto o ?prova=pieno): servono solo a verificare l'aspetto ----
  function prova(tipo) {
    if (tipo === 'vuoto') {
      return { nodi: ['alfa', 'beta', 'gamma'].map(nome => ({ nome, tipo: 'progetto', priorita: 'da definire', haCartella: true, task: [] })), prossima: null, conteggi: { da_fare: 0, in_corso: 0, in_ritardo: 0 } };
    }
    const nomi = ['Verificare il centralino con sessioni reali', 'Unire la PR della CI', 'Taratura del radar sui progetti attivi', 'Scrivere i test del parser', 'Inoltro email in configurazione', 'Aprire ai primi Club', 'Cron esterno per le notifiche', 'Pagare il dominio', 'Ridisegnare la pagina di accesso', 'Controllare i log del giovedì', 'Rispondere a chi ha scritto', 'Pubblicare le sei bozze', 'Conferma prima del voto', 'Android installa', 'Hardening del vault'];
    const stati = ['in_corso', 'da_fare', 'da_fare', 'da_fare', 'in_corso', 'da_fare', 'da_fare', 'da_fare', 'da_fare', 'da_fare', 'da_fare', 'da_fare', 'fatto', 'fatto', 'fatto'];
    const task = nomi.map((testo, i) => ({ data: '2026-11-' + String(10 + i).padStart(2, '0'), testo, vista: testo, stato: stati[i], ritardo: i === 3 }));
    return {
      nodi: [{ nome: 'Prova piena', tipo: 'progetto', priorita: 'alta', haCartella: true, task },
        { nome: 'linkedin', tipo: 'argomento', priorita: null, haCartella: true, task: [{ data: '2026-11-12', testo: 'Pubblicare 6 bozze', vista: 'Pubblicare 6 bozze', stato: 'da_fare', ritardo: false }] }],
      prossima: { nodo: 'Prova piena', ...task[0], motivo: 'in corso' }, conteggi: { da_fare: 11, in_corso: 2, in_ritardo: 1 },
    };
  }

  // ---- saluto ----
  // 32 caratteri al massimo, mai a metà parola (se non c'è uno spazio si tengono i 32), senza punteggiatura finale: il punto lo mette il saluto.
  const PAROLE_FUNZIONE = ['a', 'al', 'il', 'lo', 'la', 'le', 'i', 'gli', 'un', 'una', 'di', 'del', 'da', 'in', 'su', 'per', 'con', 'e', 'o', 'ma', 'che', 'nel', 'sul', 'dei', 'delle'];
  function brevePerSaluto(t) {
    if (t.length > 32) {
      const c = t.slice(0, 32);
      t = t[32] !== ' ' && c.includes(' ') ? c.slice(0, c.lastIndexOf(' ')) : c;
    }
    t = t.replace(/[\s,;:.…]+$/, '');
    const w = t.split(' ');
    while (w.length > 1 && PAROLE_FUNZIONE.includes(w[w.length - 1].toLowerCase())) w.pop();
    return w.join(' ').replace(/[\s,;:.…]+$/, '');
  }
  function saluto(ora) {
    const g = ora.getHours();
    const parola = g < 13 ? 'Buongiorno' : g < 18 ? 'Buon pomeriggio' : 'Buonasera';
    const p = dati && dati.prossima;
    const h1 = h('h1', 'saluto', [parola + '. ' + (p ? 'Prossimo: ' + brevePerSaluto(p.vista) + '.' : 'Niente di aperto.')]);
    const c = dati ? dati.conteggi : { da_fare: 0, in_corso: 0, in_ritardo: 0 };
    const punto = (cl, n, testo) => h('span', 'conteggio', [h('i', 'punto ' + cl), h('b', '', [String(n)]), ' ' + testo]);
    $('mappa-saluto').replaceChildren(h1, h('p', 'saluto-sub', [
      ora.toLocaleDateString('it-IT', { weekday: 'long', day: 'numeric', month: 'long' }),
      punto('st-da_fare', c.da_fare, 'da fare'), punto('st-in_corso', c.in_corso, 'in corso'), punto('ritardo', c.in_ritardo, 'in ritardo'),
    ]));
  }

  // ---- layout a forze, deterministico: stessi dati, stessa mappa (angolo aureo, niente numeri casuali) ----
  function layout(nodi, W, H) {
    const N = nodi.map((n, i) => {
      const a = i * 2.399, q = Math.min(W, H) * 0.4 * Math.sqrt((i + 0.5) / nodi.length);
      return { n, x: W / 2 + Math.cos(a) * q, y: H / 2 + Math.sin(a) * q, r: Math.min(60, 30 + 5 * aperti(n)) };
    });
    for (let passo = 0; passo < 300; passo++) {
      for (const a of N) {
        a.x += (W / 2 - a.x) * 0.004; a.y += (H / 2 - a.y) * 0.004;
        for (const b of N) {
          if (a === b) continue;
          const dx = a.x - b.x, dy = a.y - b.y, d = Math.hypot(dx, dy) || 1, min = a.r + b.r + 120;
          if (d < min) { const f = (min - d) / d * 0.25; a.x += dx * f; a.y += dy * f; }
        }
        a.x = Math.max(a.r + 40, Math.min(W - a.r - 40, a.x));
        a.y = Math.max(a.r + 70, Math.min(H - a.r - 56, a.y));
      }
    }
    return N;
  }
  function arco(cx, cy, r, a0, a1) {
    const p = a => `${(cx + r * Math.cos(a)).toFixed(2)} ${(cy + r * Math.sin(a)).toFixed(2)}`;
    return `M${p(a0)}A${r} ${r} 0 ${a1 - a0 > Math.PI ? 1 : 0} 1 ${p(a1)}`;
  }

  // ---- zoom e spostamento: una trasformazione sul gruppo del mondo; il testo non scala (vedi --k nel CSS) ----
  let trascinato = false;   // vero dopo un trascinamento: il clic che lo segue non deve deselezionare
  function applicaVista() {
    const m = $('mappa-mondo');
    if (!m) return;
    m.setAttribute('transform', `translate(${vista.x.toFixed(1)} ${vista.y.toFixed(1)}) scale(${vista.k.toFixed(3)})`);
    $('mappa-svg').style.setProperty('--k', vista.k.toFixed(3));
  }
  function limita() {       // lascia sempre almeno 80px di mappa in vista
    const svg = $('mappa-svg'), W = svg.clientWidth, H = svg.clientHeight, m = 80;
    vista.x = Math.max(m - W * vista.k, Math.min(W - m, vista.x));
    vista.y = Math.max(m - H * vista.k, Math.min(H - m, vista.y));
  }
  function zoomA(fattore, cx, cy) {   // cx, cy: punto fermo, in pixel dell'SVG
    const k = Math.max(K_MIN, Math.min(K_MAX, vista.k * fattore)), f = k / vista.k;
    vista = { k, x: cx - (cx - vista.x) * f, y: cy - (cy - vista.y) * f };
    limita(); applicaVista();
  }
  function sposta(dx, dy) { vista.x += dx; vista.y += dy; limita(); applicaVista(); }
  function adatta() { vista = { k: 1, x: 0, y: 0 }; applicaVista(); }
  function zoomCentro(fattore) { const svg = $('mappa-svg'); zoomA(fattore, svg.clientWidth / 2, svg.clientHeight / 2); }
  function portaInVista(nome) {       // un nodo che prende il fuoco fuori dal riquadro viene portato al centro
    const p = pos.get(nome), svg = $('mappa-svg');
    if (!p) return;
    const x = p.x * vista.k + vista.x, y = p.y * vista.k + vista.y, W = svg.clientWidth, H = svg.clientHeight;
    if (x < p.r || x > W - p.r || y < p.r || y > H - p.r) { vista.x += W / 2 - x; vista.y += H / 2 - y; limita(); applicaVista(); }
  }
  function gesti(svg) {
    const punti = new Map();           // dita o mouse attivi: id -> ultimo punto
    let spostato = 0, daSfondo = false;
    svg.addEventListener('wheel', e => {
      if (!e.ctrlKey && (e.deltaY < 0 ? vista.k >= K_MAX : vista.k <= K_MIN)) return;   // al limite la rotella fa scorrere la pagina
      e.preventDefault();
      const r = svg.getBoundingClientRect(), d = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY;
      zoomA(Math.exp(-d * (e.ctrlKey ? 0.01 : 0.0015)), e.clientX - r.left, e.clientY - r.top);   // ctrlKey: pizzico sul trackpad
    }, { passive: false });
    svg.addEventListener('pointerdown', e => {
      if (e.button > 0) return;
      const sfondo = !e.target.closest('.nodo, .sat, .azione');
      if (!punti.size) { trascinato = false; spostato = 0; daSfondo = sfondo; }
      if (!punti.size && !sfondo) return;   // un clic su un nodo resta un clic
      punti.set(e.pointerId, { x: e.clientX, y: e.clientY });
    });
    svg.addEventListener('pointermove', e => {
      const p = punti.get(e.pointerId);
      if (!p) return;
      const r = svg.getBoundingClientRect();
      if (punti.size === 1) {
        if (!daSfondo) return;
        const dx = e.clientX - p.x, dy = e.clientY - p.y;
        spostato += Math.abs(dx) + Math.abs(dy);
        p.x = e.clientX; p.y = e.clientY;
        if (spostato <= 4) return;        // sotto soglia è ancora un clic
        if (!trascinato) { trascinato = true; try { svg.setPointerCapture(e.pointerId); } catch (x) { /* puntatore già finito */ } }
        sposta(dx, dy);
      } else if (punti.size === 2) {      // pizzico: zoom sulla distanza, spostamento sul punto medio
        const a = [...punti.values()].find(q => q !== p), d0 = Math.hypot(p.x - a.x, p.y - a.y);
        const m0 = [(p.x + a.x) / 2 - r.left, (p.y + a.y) / 2 - r.top];
        p.x = e.clientX; p.y = e.clientY;
        const d1 = Math.hypot(p.x - a.x, p.y - a.y), m1 = [(p.x + a.x) / 2 - r.left, (p.y + a.y) / 2 - r.top];
        trascinato = true;
        sposta(m1[0] - m0[0], m1[1] - m0[1]);
        if (d0 > 0 && d1 > 0) zoomA(d1 / d0, m1[0], m1[1]);
      }
    });
    const fine = e => { punti.delete(e.pointerId); };
    svg.addEventListener('pointerup', fine);
    svg.addEventListener('pointercancel', fine);
    svg.addEventListener('lostpointercapture', fine);
    svg.addEventListener('keydown', e => {
      if (e.altKey || e.ctrlKey || e.metaKey) return;
      if (e.key === '+' || e.key === '=') zoomCentro(1.25);
      else if (e.key === '-' || e.key === '_') zoomCentro(0.8);
      else if (e.key === '0') adatta();
      else if (e.target === svg && e.key.startsWith('Arrow')) sposta(e.key === 'ArrowLeft' ? 60 : e.key === 'ArrowRight' ? -60 : 0, e.key === 'ArrowUp' ? 60 : e.key === 'ArrowDown' ? -60 : 0);   // sui nodi le frecce restano quelle di prima
      else return;
      e.preventDefault();
    });
  }

  // ---- filtri ----
  function visibili() {
    const f = dati.nodi.filter(n => filtro === 'progetti' ? n.tipo === 'progetto' : filtro === 'argomenti' ? n.tipo === 'argomento' : filtro === 'aperti' ? aperti(n) > 0 : true);
    return f;
  }

  // ---- disegno ----
  function disegna() {
    const svg = $('mappa-svg');
    if (!dati || !svg) return;
    const W = svg.clientWidth, H = svg.clientHeight;
    dimensione = W + 'x' + H;
    nodiSvg = new Map(); pos = new Map();
    const sfondo = s('rect', { class: 'mappa-sfondo', x: 0, y: 0, width: W, height: H });
    sfondo.addEventListener('pointerenter', () => { if (!fuocoNeiSatelliti()) apri(fissato); });
    sfondo.addEventListener('click', () => { if (!trascinato) deseleziona(); });
    svg.replaceChildren(sfondo);
    if (W < 2) return;                       // sotto i 760px l'SVG è nascosto: c'è la lista
    const mondo = s('g', { id: 'mappa-mondo' });   // tutto ciò che si zooma: nodi e satelliti
    svg.appendChild(mondo);
    const prossimo = dati.prossima && dati.prossima.nodo;
    for (const o of layout(visibili(), W, H)) {
      const { n, x, y, r } = o;
      pos.set(n.nome, { x, y, r });
      const G = s('g', { class: 'nodo' + (n.nome === prossimo ? ' prossimo' : ''), tabindex: 0, role: 'button', 'aria-label': n.nome + ', ' + aperti(n) + ' aperti' });
      G.append(s('circle', { class: 'alone', cx: x, cy: y, r: r + 9 }), s('circle', { class: 'disco', cx: x, cy: y, r }));
      const tot = n.task.length;
      if (tot) {
        let a0 = -Math.PI / 2;
        for (const st of ['fatto', 'in_corso', 'da_fare']) {
          const c = n.task.filter(t => t.stato === st).length;
          if (!c) continue;
          if (c === tot) { G.append(s('circle', { class: 'arco st-' + st, cx: x, cy: y, r: r - 5 })); break; }
          const a1 = a0 + c / tot * 2 * Math.PI;
          G.append(s('path', { class: 'arco st-' + st, d: arco(x, y, r - 5, a0 + 0.03, a1 - 0.03), 'stroke-linecap': 'round' }));
          a0 = a1;
        }
      }
      // scarti in em: il testo non scala con lo zoom, quindi la distanza dal disco deve seguire la sua grandezza
      G.append(s('text', { class: 'num', x, y, dy: '0.35em' }, [String(aperti(n))]),
        s('text', { class: 'nome', x, y: y + r, dy: '1.55em' }, [taglia(n.nome, 22)]),
        s('text', { class: 'tipo', x, y: y + r, dy: '3.2em' }, [n.tipo === 'senza' ? 'da etichettare' : n.tipo]));
      if (haPiu(n)) G.append(piu(n, pos.get(n.nome)));
      G.addEventListener('pointerenter', () => apri(n.nome));
      G.addEventListener('focus', () => { if (G.matches(':focus-visible')) portaInVista(n.nome); apri(n.nome); });   // solo dalla tastiera: al clic il nodo si sposterebbe sotto il puntatore
      G.addEventListener('click', () => scegli(n.nome));
      G.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); scegli(n.nome); }
        if (e.key === 'Enter' || e.key === 'ArrowRight') { e.preventDefault(); apri(n.nome); const primo = document.querySelector('#mappa-satelliti .sat[tabindex]'); if (primo) primo.focus(); }
      });
      nodiSvg.set(n.nome, G);
      mondo.appendChild(G);
    }
    mondo.appendChild(s('g', { id: 'mappa-satelliti' }));   // sempre ultimo: sta sopra tutti i nodi
    limita(); applicaVista();
    const da = aperto; aperto = null; apri(da, true);
  }

  // satelliti del nodo aperto: tutti gli aperti, gli ultimi 2 fatti (in ordine di file) e «+k fatti»
  function voci(n) {
    const v = n.task.filter(t => t.stato !== 'fatto').map(t => ({ t, stato: t.stato }));
    if (filtro === 'aperti') return v;
    const fatti = n.task.filter(t => t.stato === 'fatto');
    fatti.slice(-2).forEach(t => v.push({ t, stato: 'fatto' }));
    if (fatti.length > 2) v.push({ extra: fatti.length - 2, stato: 'fatto' });
    return v;
  }
  // Dove mettere i satelliti: a raggiera se c'è spazio per le etichette da entrambi i lati, altrimenti in colonna sul lato libero.
  function posizioni(m, p, W, H) {
    const out = [], libero = [p.x - p.r - 20, W - p.x - p.r - 20].map(v => v >= 200);   // [sinistra, destra]
    if (m <= 7 && libero[0] && libero[1]) {
      const R = p.r + 52;
      for (let i = 0; i < m; i++) { const a = -Math.PI / 2 + (i + 0.5) * 2 * Math.PI / m; out.push({ x: p.x + Math.cos(a) * R, y: p.y + Math.sin(a) * R, lato: Math.cos(a) >= 0 ? 1 : -1 }); }
    } else {                                  // colonne ad arco: le etichette non si toccano
      const lati = libero[0] === libero[1] ? [1, -1] : [libero[1] ? 1 : -1];
      const passo = Math.min(22, (H - 60) / Math.ceil(m / lati.length));
      const per = Math.ceil(m / lati.length);
      for (let i = 0; i < m; i++) {
        const lato = lati[Math.floor(i / per)], k = Math.min(per, m - Math.floor(i / per) * per), j = i % per;
        const dy = (j - (k - 1) / 2) * passo, Rs = Math.max(p.r + 70, (k - 1) * passo / 2 + 45);
        out.push({ x: p.x + lato * Math.sqrt(Math.max(Rs * Rs - dy * dy, 400)), y: p.y + dy, lato });
      }
    }
    const su = Math.min(...out.map(o => o.y)), giu = Math.max(...out.map(o => o.y));
    const sposta = su < 22 ? 22 - su : giu > H - 22 ? H - 22 - giu : 0;
    for (const o of out) { o.y += sposta; o.x = Math.max(16, Math.min(W - 16, o.x)); o.spazio = o.lato > 0 ? W - 8 - o.x - 13 : o.x - 8 - 13; }
    return out;
  }
  function disegnaSatelliti(nome) {
    const strato = $('mappa-satelliti'), n = nodoPer(nome), p = pos.get(nome);
    if (!strato) return;
    if (!n || !p) { strato.replaceChildren(); return; }
    const lista = voci(n), svg = $('mappa-svg');
    const posiz = posizioni(lista.length, p, svg.clientWidth, svg.clientHeight);
    const fili = [], sat = [], zona = s('g', { class: 'zona' });
    const R0 = p.r + 14;
    zona.append(s('path', { 'fill-rule': 'evenodd', d: `M${p.x - R0} ${p.y}a${R0} ${R0} 0 1 0 ${2 * R0} 0a${R0} ${R0} 0 1 0 ${-2 * R0} 0M${p.x - p.r + 1} ${p.y}a${p.r - 1} ${p.r - 1} 0 1 0 ${2 * p.r - 2} 0a${p.r - 1} ${p.r - 1} 0 1 0 ${-2 * p.r + 2} 0` }));
    lista.forEach((v, i) => {
      const q = posiz[i], d = Math.hypot(q.x - p.x, q.y - p.y) || 1;
      fili.push(s('line', { class: 'filo', x1: p.x + (q.x - p.x) / d * (p.r + 6), y1: p.y + (q.y - p.y) / d * (p.r + 6), x2: q.x, y2: q.y }));
      const testo = v.t ? v.t.vista : '+' + v.extra + ' fatti';
      const G = s('g', { class: 'sat st-' + v.stato + (v.t && v.t.ritardo ? ' ritardo' : ''), transform: `translate(${q.x.toFixed(1)} ${q.y.toFixed(1)})` });
      const dentro = s('g', { class: 'sat-dentro' });
      const etichetta = taglia(testo, Math.max(6, Math.min(26, Math.floor(q.spazio / 6.3)))), larg = 18 + etichetta.length * 6.3;
      zona.append(s('line', { x1: p.x + (q.x - p.x) / d * p.r, y1: p.y + (q.y - p.y) / d * p.r, x2: q.x, y2: q.y, 'stroke-width': 28 }), s('rect', { x: q.lato > 0 ? q.x - 12 : q.x - larg, y: q.y - 12, width: larg + 12, height: 24 }));
      dentro.append(s('circle', { class: 'sat-punto', r: v.t ? 7 : 5 }),
        s('text', { dx: (q.lato * 1.1) + 'em', dy: '0.33em', 'text-anchor': q.lato > 0 ? 'start' : 'end' }, [etichetta]));
      G.append(s('title', {}, [testo]), dentro);
      if (v.t) {
        G.setAttribute('tabindex', 0); G.setAttribute('role', 'button'); G.setAttribute('aria-label', testo + ', ' + NOME_STATO[v.stato]);
        G.addEventListener('click', e => { e.stopPropagation(); scegliTask(nome, v.t); });
        G.addEventListener('keydown', e => {
          const tutti = [...strato.querySelectorAll('.sat[tabindex]')], k = tutti.indexOf(G);
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); scegliTask(nome, v.t); }
          else if (e.key === 'ArrowLeft' || e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); nodiSvg.get(nome).focus(); }
          else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); const a = tutti[k + (e.key === 'ArrowDown' ? 1 : -1)]; if (a) a.focus(); }
        });
      }
      sat.push(G);
    });
    strato.replaceChildren(zona, ...fili, ...sat, ...(haPiu(n) ? [piu(n, p)] : []));   // la zona trasparente tiene aperto il nodo finché il puntatore va verso i satelliti
  }

  const fuocoNeiSatelliti = () => { const e = document.activeElement; return !!(e && e.closest && e.closest('#mappa-satelliti')); };

  // un solo nodo aperto: aprirne uno chiude il precedente; i satelliti si disegnano una volta sola
  function apri(nome, forza) {
    if (!forza && aperto === nome) return;
    if (aperto && nodiSvg.has(aperto)) nodiSvg.get(aperto).classList.remove('aperto');
    aperto = nodiSvg.has(nome) ? nome : null;
    $('mappa-svg').classList.toggle('focus', !!aperto);
    if (aperto) nodiSvg.get(aperto).classList.add('aperto');
    disegnaSatelliti(aperto);
  }
  function scegli(nome) { fissato = nome; selezione = null; apri(nome); pannello(); }
  // fissa il nodo, seleziona il task e porta il pannello su di lui: la lista dei task può essere più lunga del pannello
  function scegliTask(nome, t) {
    fissato = nome; selezione = t; apri(nome); pannello();
    const d = $('mappa-dettaglio'), el = d.querySelector('.task.scelto');
    if (el) d.scrollTop += el.getBoundingClientRect().top - d.getBoundingClientRect().top - (d.clientHeight - el.offsetHeight) / 2;
  }
  function deseleziona() { fissato = null; selezione = null; apri(null); pannello(); }

  // ---- lista equivalente (lettori di schermo; sotto i 760px prende il posto della mappa) ----
  function lista() {
    const ul = $('mappa-lista');
    if (!ul || !dati) return;
    ul.replaceChildren(...visibili().map(n => {
      const ts = filtro === 'aperti' ? n.task.filter(t => t.stato !== 'fatto') : n.task;
      return h('li', '', [
        h('h3', '', [n.nome, h('span', 'tipo-nodo', [n.tipo === 'senza' ? 'da etichettare' : n.tipo]), h('span', 'sub', [aperti(n) + ' aperti'])]),
        ts.length ? h('ul', '', ts.map(t => h('li', 'task-lista st-' + t.stato, [
          h('i', 'punto st-' + t.stato), bottone(t.vista, 'link' + (t.ritardo ? ' ritardo' : ''), () => { scegliTask(n.nome, t); $('mappa-dettaglio').scrollIntoView({ block: 'nearest' }); }),
          h('span', 'sub', [NOME_STATO[t.stato] + (t.data ? ' · ' + giornoBreve(t.data) : '')]),
        ]))) : null,
      ]);
    }));
  }

  // ---- pannello: prossima azione oppure dettaglio del nodo fissato ----
  function selettore(n, t) {
    return h('span', 'stati', STATI.map(st => {
      const b = bottone(NOME_STATO[st], 'stato st-' + st, () => cambia(n, t, st));
      b.setAttribute('aria-pressed', String(t.stato === st));
      return b;
    }));
  }
  function rigaTask(n, t) {
    const sel = selezione && selezione.testo === t.testo && selezione.data === t.data;
    const li = h('li', 'task' + (sel ? ' scelto' : ''), [
      h('span', 'task-testo' + (t.ritardo ? ' ritardo' : ''), [h('i', 'punto st-' + t.stato), t.vista, t.data ? h('span', 'sub', [' ' + (t.ritardo ? 'dal ' : '') + giornoBreve(t.data)]) : null]),
      h('span', 'riga-azioni', [selettore(n, t), n.haCartella && t.stato !== 'fatto' ? bottone(t.stato === 'in_corso' ? 'Riavvia' : 'Avvia', '', () => conferma(n, t)) : null]),
    ]);
    if (sel) li.setAttribute('aria-current', 'true');
    return li;
  }
  function dettaglioNodo(n) {
    const p = n.tipo === 'progetto' ? progetti.find(x => x.nome.toLowerCase() === n.nome.toLowerCase()) : null;
    const c = p && p.attivita && p.attivita.commit && p.attivita.commit[0];
    const da = n.task.find(t => t.stato === 'in_corso') || n.task.find(t => t.stato === 'da_fare');   // «Avvia» parte dal passo già in corso, poi dal primo da fare
    return [
      h('h2', '', [n.nome, h('span', 'sub', [n.tipo === 'senza' ? 'da etichettare' : n.tipo + (n.priorita ? ' · priorità ' + n.priorita : '')])]),
      p && p.doveSono ? h('p', 'dove-sono', [h('b', '', ['Dove sono ']), taglia(p.doveSono, 260)]) : null,
      c ? h('p', 'sub', ['Ultimo commit: ' + taglia(c.messaggio, 80) + (c.ramo ? ' (' + c.ramo + ')' : '')]) : null,
      n.task.length ? h('ul', 'task-elenco', n.task.map(t => rigaTask(n, t))) : h('p', 'vuoto', ['Nessun passo scritto in piano.md.']),
      h('div', 'riga-azioni', [
        da && n.haCartella ? bottone(da.stato === 'in_corso' ? 'Riavvia in Claude' : 'Avvia in Claude', 'primario', () => conferma(n, da)) : null,
        puoAggiungere(n) ? bottone('Aggiungi un task', '', () => nuovoTask(n)) : null,
        bottone('Torna alla prossima azione', '', deseleziona),
      ]),
    ];
  }
  function prossimaAzione() {
    const p = dati.prossima;
    if (!p) return [h('h2', '', ['Prossima azione']), h('p', 'vuoto', ['Niente di aperto.'])];
    const n = nodoPer(p.nodo);
    const t = n && n.task.find(x => x.testo === p.testo && x.data === p.data);
    return [
      h('h2', '', ['Prossima azione']),
      h('div', 'dove', [h('i', 'punto st-' + p.stato), p.nodo + ' · ' + p.motivo]),
      h('p', 'titolo-azione', [p.vista]),
      t ? h('div', 'riga-azioni', [
        n.haCartella ? bottone(t.stato === 'in_corso' ? 'Riavvia in Claude' : 'Avvia in Claude', 'primario', () => conferma(n, t)) : null,
        bottone('Fatto', '', () => cambia(n, t, 'fatto')),
      ]) : null,
    ];
  }
  function pannello() {
    if (!dati || !$('mappa-dettaglio')) return;
    const n = fissato && nodoPer(fissato);
    $('mappa-dettaglio').replaceChildren(...(n ? dettaglioNodo(n) : prossimaAzione()).filter(Boolean));
    // le righe in ritardo dei prossimi giorni
    const g = giorni.slice(0, 5);
    $('prossimi-giorni').replaceChildren(...(g.length ? [h('h2', '', ['Prossimi giorni']), h('ul', 'prossimi', g.map(v => h('li', '', [
      h('span', '', [v.testo]), h('span', 'quando' + (v.inRitardo ? ' ritardo' : ''), [v.inRitardo ? 'dal ' + giornoBreve(v.data) : giornoBreve(v.data)]),
    ])))] : []));
  }

  // ---- azioni ----
  let timerToast = null;
  function toast(testo) {
    let t = $('mappa-toast');
    if (!t) { t = h('div', 'toast', [], { id: 'mappa-toast', role: 'status' }); document.body.appendChild(t); }
    t.textContent = testo; t.hidden = false;
    clearTimeout(timerToast);
    timerToast = setTimeout(() => { t.hidden = true; }, 4500);
  }
  async function invia(percorso, corpo) {
    const r = await fetch(percorso, { method: 'POST', headers: { 'X-Azione': 'conferma', 'Content-Type': 'application/json' }, body: JSON.stringify(corpo) });
    let json = {};
    try { json = await r.json(); } catch (e) { /* risposta senza corpo */ }
    return { ok: r.ok, stato: r.status, json };
  }
  const ERRORI_409 = {
    doppia: 'Due voci uguali in piano.md: correggi in Obsidian.',
    cartella: 'Cartella non valida per questo task.',
    ripetuto: 'Già avviato: guarda il Terminale.',
    apertura: 'Non sono riuscito ad aprire il Terminale.',
  };
  function errore(r) {
    if (r.stato === 404) { toast('La voce è cambiata, ricarico.'); carica(); }
    else if (r.stato === 409) toast(ERRORI_409[r.json && r.json.errore] || ERRORI_409.doppia);
    else if (r.stato === 501) toast('Avvio disponibile solo su macOS.');
    else toast('Non è andata: errore ' + r.stato + '.');
  }
  const inProva = () => !!new URLSearchParams(location.search).get('prova');
  async function cambia(n, t, stato) {
    if (t.stato === stato) return;
    if (inProva()) return toast('Modalità prova: nessuna modifica.');
    try {
      const r = await invia('/api/mappa/stato', { data: t.data, testo: t.testo, stato });
      if (!r.ok) return errore(r);
      toast(stato === 'fatto' ? (n.tipo === 'senza' ? 'Fatto. Era senza nodo.' : 'Fatto.') : stato === 'in_corso' ? 'In corso.' : 'Da fare.');
      if (stato === 'fatto' && selezione === t) selezione = null;
      await carica();
    } catch (e) { toast('Non è andata: ' + e.message); }
  }
  function dialogo(id, etichetta) {
    let d = $(id);
    if (!d) { d = h('dialog', '', [], { id, 'aria-label': etichetta }); document.body.appendChild(d); }
    return d;
  }
  // aggiunge `- [ ] #<nome del nodo> testo` a piano.md; il server controlla di nuovo lunghezza, a capo e < >
  const TESTO_MASSIMO = 200;
  function nuovoTask(n) {
    if (inProva()) return toast('Modalità prova: nessuna modifica.');
    const d = dialogo('mappa-nuovo', 'Aggiungi un task');
    const campo = h('input', '', [], { type: 'text', maxlength: String(TESTO_MASSIMO), required: '', autocomplete: 'off', 'aria-label': 'Testo del task' });
    const aggiungi = bottone('Aggiungi', 'primario', () => {});
    aggiungi.type = 'submit';
    campo.addEventListener('input', () => campo.setCustomValidity(/[<>]/.test(campo.value) ? 'Niente < e >.' : ''));
    const form = h('form', '', [
      h('h2', '', ['Aggiungi un task']),
      h('p', 'sub', ['Nodo: ' + n.nome + '. Si scrive in docs/piano.md come #' + n.nome + '.']),
      campo,
      h('div', 'riga-azioni', [aggiungi, bottone('Annulla', '', () => d.close())]),
    ]);
    form.addEventListener('submit', async e => {
      e.preventDefault();
      const testo = campo.value.trim();
      if (!testo || !form.reportValidity()) return;
      aggiungi.disabled = true;
      try {
        const r = await invia('/api/mappa/nuovo', { tag: n.nome, testo });
        d.close();
        if (r.stato === 409) return toast('C\'è già un task uguale.');
        if (r.stato === 400) return toast('Testo non valido: niente a capo né < >, al massimo ' + TESTO_MASSIMO + ' caratteri.');
        if (!r.ok) return errore(r);
        toast('Aggiunto a ' + n.nome + '.');
        await carica();
        const nuovo = nodoPer(n.nome), grezzo = String(r.json.riga || '').slice(6);
        const t = nuovo && nuovo.task.find(x => x.data === null && x.testo === grezzo);
        if (t) scegliTask(n.nome, t);
      } catch (x) { d.close(); toast('Non è andata: ' + x.message); }
    });
    d.replaceChildren(form);
    d.showModal();
    campo.focus();
  }
  function conferma(n, t) {
    if (inProva()) return toast('Modalità prova: nessuna modifica.');
    const d = dialogo('mappa-avvia', 'Avvia in Claude');
    const avvia = bottone('Avvia', 'primario', async () => {
      avvia.disabled = true;
      try {
        const r = await invia('/api/mappa/avvia', { data: t.data, testo: t.testo });
        d.close();
        if (!r.ok) return errore(r);
        toast(r.json && r.json.avviso ? 'Terminale aperto, ma non ho potuto segnare «in corso».' : 'Claude avviato nel Terminale.');
        await carica();
      } catch (e) { d.close(); toast('Non è andata: ' + e.message); }
    });
    const annulla = bottone('Annulla', '', () => d.close());
    d.replaceChildren(h('form', '', [
      h('h2', '', ['Avvia in Claude']),
      h('p', 'sub', ['Si apre il Terminale con una sessione di Claude.']),
      h('p', 'sub', ['Nodo: ' + n.nome]),
      n.cartella ? h('p', 'sub', ['Cartella: ' + n.cartella]) : null,
      h('p', 'titolo-dialogo', [t.vista]),
      h('div', 'riga-azioni', [avvia, annulla]),
    ], { method: 'dialog' }));
    d.showModal();
  }

  // ---- struttura fissa (una volta) ----
  function struttura() {
    if ($('mappa-svg')) return;
    const filtri = h('div', 'scelta', FILTRI.map(([k, nome]) => {
      const b = bottone(nome, '', () => { filtro = k; for (const x of filtri.children) x.setAttribute('aria-pressed', String(x === b)); disegna(); lista(); });
      b.setAttribute('aria-pressed', String(k === filtro));
      return b;
    }), { role: 'group', 'aria-label': 'Filtro della mappa' });
    const svg = s('svg', { id: 'mappa-svg', role: 'group', tabindex: 0, 'aria-label': 'Mappa dei progetti e dei loro task: la stessa lista è sotto. Frecce per spostarla, più e meno per lo zoom, zero per la vista intera' });
    gesti(svg);
    const zoom = h('div', 'mappa-zoom', [
      bottone('+', '', () => zoomCentro(1.25)), bottone('−', '', () => zoomCentro(0.8)), bottone('Adatta', '', adatta),
    ], { role: 'group', 'aria-label': 'Zoom della mappa' });
    [['Ingrandisci', 0], ['Riduci', 1], ['Adatta alla vista', 2]].forEach(([nome, i]) => zoom.children[i].setAttribute('aria-label', nome));
    svg.addEventListener('pointerleave', () => { if (!fuocoNeiSatelliti()) apri(fissato); });
    const legenda = h('div', 'legenda', STATI.map(st => h('span', '', [h('i', 'punto st-' + st), NOME_STATO[st]])));
    $('mappa-area').replaceChildren(h('div', 'mappa-box', [
      h('div', 'mappa-testa', [h('h2', '', ['Mappa del lavoro']), filtri]), svg, legenda, zoom,
      h('ul', 'mappa-lista', [], { id: 'mappa-lista', 'aria-label': 'Nodi e task, in elenco' }),
    ]));
    new ResizeObserver(() => {
      const q = svg.clientWidth + 'x' + svg.clientHeight;
      if (dati && q !== dimensione) disegna();
    }).observe(svg);
  }

  async function prendi(percorso) {
    try { const r = await fetch(percorso, { cache: 'no-store' }); return r.ok ? await r.json() : null; } catch (e) { return null; }
  }
  async function carica() {
    struttura();
    const p = new URLSearchParams(location.search).get('prova');
    const m = p ? prova(p) : await prendi('/api/mappa');
    if (!m) { $('mappa-saluto').replaceChildren(h('h1', 'saluto', ['Non riesco a leggere la mappa.'])); return; }
    applica(m);
  }
  // /api/stato e /api/oggi le legge già dashboard.js (aggiorna) e le passa con imposta: la mappa non le chiede due volte
  function imposta(st, o) {
    progetti = st && st.progetti || [];
    giorni = o && o.conData || [];
    if (dati) applica(dati);
  }
  function applica(m) {
    const nuova = JSON.stringify([m, giorni]);
    dati = m;
    saluto(new Date());
    if (nuova === impronta) return;           // niente è cambiato: non interrompo hover e animazioni
    impronta = nuova;
    if (fissato && !nodoPer(fissato)) fissato = null;
    if (selezione && !(nodoPer(fissato) || { task: [] }).task.some(t => t.testo === selezione.testo && t.data === selezione.data)) selezione = null;
    disegna(); lista(); pannello();
  }

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && !document.querySelector('dialog[open]') && !$('mappa-vista').hidden && (fissato || aperto)) deseleziona();
  });
  // un clic fuori dal task evidenziato (e dai satelliti, dalla lista e dai dialog) toglie l'evidenziazione
  document.addEventListener('click', e => {
    const dopoTrascinamento = trascinato; trascinato = false;   // il clic che segue uno spostamento non conta
    if (dopoTrascinamento || !selezione || $('mappa-vista').hidden || e.target.closest('#mappa-dettaglio .task, #mappa-satelliti .sat, #mappa-lista, .mappa-zoom, dialog')) return;
    selezione = null; pannello();
  });
  document.addEventListener('visibilitychange', () => { if (!document.hidden && !$('mappa-vista').hidden) carica(); });

  window.Mappa = { carica, imposta };
})();
