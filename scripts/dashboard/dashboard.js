const $ = id => document.getElementById(id);
$('data-oggi').textContent = new Date().toLocaleDateString('it-IT', { weekday: 'long', day: 'numeric', month: 'long' });

function el(tag, classe, figli) {
  const nodo = document.createElement(tag);
  if (classe) nodo.className = classe;
  (figli || []).forEach(f => nodo.appendChild(typeof f === 'string' ? document.createTextNode(f) : f));
  return nodo;
}

// Una novità del radar: il titolo, come link se c'è un indirizzo http(s) (il server scarta ogni altro schema).
function titoloNovita(n) {
  if (!n.link || !/^https?:\/\//.test(n.link)) return n.titolo;
  const a = el('a', '', [n.titolo]);
  a.href = n.link; a.target = '_blank'; a.rel = 'noopener noreferrer';
  return a;
}

function vuoto(messaggio) {
  return el('p', 'vuoto', [messaggio]);
}

// launchctl parla inglese: running / not running (un job a calendario tra due giri è «a riposo»)
const STATI_JOB = { running: 'attivo', 'not running': 'a riposo', 'non caricato': 'non caricato' };
function pillolaJob(stato) {
  const classe = stato === 'running' ? 'ok' : stato === 'non caricato' ? 'attesa' : '';
  return el('span', 'pillola ' + classe, [STATI_JOB[stato] || stato]);
}

let aperte = false;  // la lista delle scartate resta aperta dopo un voto

async function vota(titolo, giudizio) {
  try {
    const r = await fetch('/api/radar/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Azione': 'conferma' },
      body: JSON.stringify({ titolo, giudizio }),
    });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    aggiorna();
  } catch (e) {
    $('fresco').className = 'fresco errore';
    $('fresco').textContent = 'voto non salvato: ' + e.message;
  }
}

function votoScartata(c, testo, giudizio) {
  const b = el('button', 'voto', [testo]);
  b.type = 'button';
  b.setAttribute('aria-pressed', String(c.giudizio === giudizio));
  b.onclick = () => vota(c.titolo, giudizio);
  return b;
}

// Dal feed alla lettura: quante novità sono arrivate e quante sono sopravvissute a ogni stadio.
function imbutoRadar(righe) {
  const max = Math.max(1, ...righe.map(r => r[1]));
  return el('div', 'imbuto', righe.map(([nome, n, nota]) => {
    const riempi = el('span', 'riempi', []);
    riempi.style.width = (n ? Math.max(1.5, n / max * 100) : 0) + '%';
    return el('div', 'riga-imbuto', [el('span', '', [nome, nota ? el('small', '', [nota]) : '']), el('div', 'barra', [riempi]), el('b', '', [String(n)])]);
  }));
}

function renderRadar(radar, inbox, prossimo) {
  const nodo = $('radar');
  if (!radar) { nodo.replaceChildren(vuoto('Nessun report ancora. Il radar scrive la prima scheda quando gira (lunedì alle 07:30): per provarlo adesso raccogli le novità con scripts/feed.py e lancia «Radar» dalla pagina Avvii.')); return; }
  const file = (inbox || []).find(f => f.file.startsWith(radar.data));
  const ricevute = file ? file.voci : null;
  const daLeggere = radar.daLeggere.length, scartate = radar.scartate.length;
  const prossimoTesto = prossimo ? new Date(prossimo.replace(' ', 'T')).toLocaleString('it-IT', { weekday: 'long', day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' }) : '–';
  const imbuto = el('section', '', [
    el('h2', '', ['Dal feed alla lettura', el('span', 'sub', ['Report del ' + giorno(radar.data)])]),
    imbutoRadar([
      ['Novità ricevute', ricevute === null ? daLeggere + scartate : ricevute, ricevute === null ? 'numero non disponibile' : ''],
      ['Dopo lo stadio 1', daLeggere + scartate, 'somiglianza con i progetti, soglia 0,5'],
      ['Dopo lo stadio 2', daLeggere, 'giudizio del modello locale'],
    ]),
    el('p', 'sub', ['Prossimo radar: ' + prossimoTesto + '. ' + (daLeggere ? '' : 'In questo giro nessuna novità da leggere.')]),
  ]);
  const lettura = daLeggere ? el('section', '', [el('h2', '', ['Da leggere']), el('ul', '', radar.daLeggere.map(n => el('li', '', [titoloNovita(n)])))]) : '';
  const tabellaScartate = scartate ? el('div', '', [el('table', 'scartate', [
    el('thead', '', [el('tr', '', [el('th', '', ['Novità']), el('th', '', ['Progetto']), el('th', 'num', ['Score']), el('th', '', ['Il filtro ha sbagliato?'])])]),
    el('tbody', '', radar.scartate.map(c => el('tr', '', [
      el('td', '', [el('details', '', [el('summary', '', [c.titolo]), el('p', 'sub', [c.motivo || 'Nessun motivo registrato.'])])]),
      el('td', '', [c.progetto]),
      el('td', 'num', [c.score === null ? '–' : String(c.score).replace('.', ',')]),
      el('td', '', [votoScartata(c, 'Falso scarto', 'falso-scarto'), ' ', votoScartata(c, 'Scarto giusto', 'scarto-giusto')]),
    ]))),
  ])]) : vuoto('Nessuna novità scartata dallo stadio 2.');
  const sezScartate = el('section', '', [
    el('h2', '', ['Scartate dallo stadio 2', el('span', 'sub', [radar.falsiScarti + ' falsi scarti su ' + radar.valutate + ' valutate'])]),
    tabellaScartate,
  ]);
  nodo.replaceChildren(imbuto, lettura, sezScartate);
}

function renderSistema(s) {
  const modelli = s.ollama === null
    ? 'Ollama non risponde'
    : (s.ollama.length ? s.ollama.join(', ') : 'nessun modello in memoria');
  const log = s.logAvvio.length
    ? el('ul', 'sub', s.logAvvio.map(r => el('li', 'mono', [r])))
    : vuoto('Log di avvio vuoto.');
  $('sistema').replaceChildren(
    el('div', 'elenco-stat', [
      el('div', '', [el('span', '', ['Modelli Ollama caricati']), el('b', '', [modelli])]),
      el('div', '', [el('span', '', ['Prossima inbox da n8n']), el('b', '', [s.prossimoRadar])]),
    ]),
    el('details', '', [el('summary', '', ['Ultime righe del log di avvio']), log]),
  );
}

function elenco(titolo, voci, classe) {
  return voci.length ? el('div', classe || '', [el('h4', '', [titolo]), el('ul', '', voci.map(v => el('li', '', typeof v === 'string' ? [v] : v)))]) : '';
}

function renderJobVault(s) {
  const v = s.vault;
  const job = Object.entries(s.job).map(([nome, stato]) =>
    el('tr', '', [el('td', '', [nome]), el('td', 'num', [pillolaJob(stato)])])
  );
  const commit = v.ultimiCommit.map(c => {
    const [hash, ...resto] = c.split(' ');
    return el('li', '', [el('span', 'mono', [hash]), ' ' + resto.join(' ')]);
  });
  const nonUniti = v.branchNonUniti.length
    ? 'Non ancora uniti al main: ' + v.branchNonUniti.join(', ')
    : 'Tutti i branch sono uniti al main.';
  $('jobvault').replaceChildren(
    el('table', '', [
      el('thead', '', [el('tr', '', [el('th', '', ['Job']), el('th', 'num', ['Stato'])])]),
      el('tbody', '', job),
    ]),
    el('p', 'sub', ['Branch ' + v.branch + ' · ' + (v.nonCommittate ? v.nonCommittate + ' file non committati' : 'nessuna modifica in sospeso')]),
    el('ul', '', commit),
    el('p', 'sub', [nonUniti]),
  );
}

function aggiornaKpi(s) {
  $('kpi-radar').textContent = s.radar ? s.radar.daLeggere.length : '–';
}

const FONTI_SPUNTABILI = ['piano', 'scadenze'];

function voceSpuntabile(v, nodoTesto) {
  const casella = el('input', '', []);
  casella.type = 'checkbox';
  casella.checked = !!v.fatto;
  casella.setAttribute('aria-label', 'Fatto: ' + v.testo);
  casella.addEventListener('change', () => spunta(v, casella));
  return el('label', 'voce', [casella, nodoTesto]);
}

async function spunta(v, casella) {
  const fatto = casella.checked;
  casella.disabled = true;
  casella.closest('li').classList.toggle('fatto', fatto);
  try {
    const r = await fetch('/api/spunte', {
      method: 'POST',
      headers: { 'X-Azione': 'conferma', 'Content-Type': 'application/json' },
      body: JSON.stringify({ fonte: v.fonte, data: v.data || null, testo: v.testo, fatto }),
    });
    if (!r.ok) throw new Error(r.status === 404 ? 'la voce è cambiata nel file' : r.status === 409 ? 'nel file ci sono due voci uguali' : 'HTTP ' + r.status);
    setTimeout(() => CARICA[vista](), 700);
  } catch (e) {
    casella.checked = !fatto;
    casella.disabled = false;
    casella.closest('li').classList.toggle('fatto', !fatto);
    $('fresco').className = 'fresco errore';
    $('fresco').textContent = 'spunta non salvata: ' + e.message;
  }
}

function testoVoce(c) {
  return el('span', 'testo', [
    c.data ? el('span', 'mono quando', [c.data]) : '',
    c.inRitardo ? el('span', 'pillola attesa', ['in ritardo']) : '',
    el('span', '', [c.testo]),
  ]);
}

function renderOggi(o) {
  const nodo = $('oggi');
  if (!o.senzaData.length) { nodo.replaceChildren(); return; }
  nodo.replaceChildren(el('details', '', [
    el('summary', '', ['Senza data (' + o.senzaData.length + ')']),
    el('ul', 'piano-voci', o.senzaData.map(v => el('li', '', [
      FONTI_SPUNTABILI.includes(v.fonte)
        ? voceSpuntabile({ ...v, fatto: false }, el('span', 'testo', [el('span', '', [v.testo])]))
        : el('span', 'voce', [el('span', 'testo', [el('span', 'mono quando', [v.fonte.replace('progetto:', '')]), el('span', '', [v.testo])])]),
    ]))),
  ]));
}

const NOMI_FONTE = { calendario: 'calendario', piano: 'piano', scadenze: 'scadenza', rinnovo: 'rinnovo', post: 'post' };
let ripetiAspetta = null;

function intestazioneGiorno(iso) {
  const d = new Date(iso + 'T12:00'), oggi = new Date(); oggi.setHours(12, 0, 0, 0);
  const diff = Math.round((d - oggi) / 86400000);
  return diff === 0 ? 'Oggi' : diff === 1 ? 'Domani' : d.toLocaleDateString('it-IT', { weekday: 'long', day: 'numeric', month: 'long' });
}

function rigaAspetta(v) {
  const contenuto = el('span', 'testo', [
    el('span', 'ora', [v.ora ? v.ora + (v.fine ? '–' + v.fine : '') : v.fonte === 'calendario' ? 'tutto il giorno' : 'senza ora']),
    el('span', '', [v.titolo + (v.inCorso ? ' (in corso)' : '')]),
    ...(v.dettaglio ? [el('span', 'sub', [v.dettaglio])] : []),
    el('span', 'pillola' + (v.inRitardo ? ' negativa' : v.lavoro ? ' avviso' : ''), [v.inRitardo ? 'in ritardo dal ' + giorno(v.originale) : v.lavoro ? 'lavoro' : NOMI_FONTE[v.fonte] || v.fonte]),
  ]);
  return el('li', 'riga-aspetta', [FONTI_SPUNTABILI.includes(v.fonte) ? voceSpuntabile({ fonte: v.fonte, data: v.data, testo: v.testo, fatto: false }, contenuto) : el('span', 'voce senza-casella', [contenuto])]);
}

function renderAspetta(a) {
  const gruppi = [];
  for (const v of a.voci) {
    const chiave = v.arretrato ? 'arretrati' : v.inRitardo ? 'ritardo' : v.giorno;
    let g = gruppi.find(x => x.chiave === chiave);
    if (!g) { g = { chiave, titolo: v.inRitardo ? 'In ritardo' : intestazioneGiorno(v.giorno), voci: [] }; gruppi.push(g); }
    g.voci.push(v);
  }
  // I post scaduti da più di due giorni stanno chiusi in grigio con il conteggio: il rosso resta per ciò che serve oggi.
  $('aspetta').replaceChildren(...(gruppi.length
    ? gruppi.flatMap(g => g.chiave === 'arretrati'
      ? [el('details', 'arretrati', [el('summary', '', ['Post arretrati (' + g.voci.length + ')']), el('ul', 'piano-voci', g.voci.map(rigaAspetta))])]
      : [el('h3', 'giorno-aspetta' + (g.chiave === 'ritardo' ? ' ritardo' : ''), [g.titolo]), el('ul', 'piano-voci', g.voci.map(rigaAspetta))])
    : [vuoto('Niente in programma nei prossimi 7 giorni.')]));
  const c = a.calendario;
  $('aspetta-calendario').textContent = c.stato === 'caricamento' ? 'Sto leggendo il calendario: le prime volte ci mette un minuto o più.'
    : c.stato === 'errore' ? 'Il calendario non risponde (' + c.errore.slice(0, 120) + '): sotto vedi solo scadenze e post.'
    : c.assente ? 'Nessun calendario collegato: sotto vedi solo scadenze e post. Come collegarne uno: README, «Calendario».'
    : 'Appuntamenti letti dal calendario alle ' + new Date(c.aggiornato).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' }) + '. Quali calendari mostrare: docs/calendari.md.'
      + (c.avvisi && c.avvisi.length ? ' Attenzione: ' + c.avvisi.join('; ').slice(0, 200) : '');
  if (c.stato === 'caricamento' && !ripetiAspetta) ripetiAspetta = setTimeout(() => { ripetiAspetta = null; if (vista === 'agenda') aggiorna(); }, 10000);
  const n = a.novita;
  $('aspetta-novita').replaceChildren(n.daLeggere.length
    ? el('ul', 'piano-voci', n.daLeggere.map(x => el('li', 'riga-aspetta', [el('span', 'voce senza-casella', [el('span', 'testo', [titoloNovita(x)])])])))
    : vuoto('Nessuna novità rilevante nell\'ultimo giro' + (n.data ? ' (' + giorno(n.data) + ')' : '') + '.'));
}

const ETICHETTE = { morning: 'morning', 'chiudi-giornata': 'chiusura della giornata', radar: 'radar', pulizia: 'pulizia del venerdì', bozze: 'la preparazione delle bozze' };

function renderEsecuzioni(e) {
  const righe = Object.keys(ETICHETTE).map(nome => el('li', '', [
    ...(e[nome].inCorso ? [el('span', 'pillola attesa', ['in corso']), ' '] : []),
    ETICHETTE[nome],
    el('details', '', [
      el('summary', '', ['Ultime righe del log']),
      el('ul', 'mono', e[nome].ultimeRighe.map(r => el('li', '', [r]))),
    ]),
  ]));
  $('esecuzioni').replaceChildren(
    el('ul', 'piano-voci', righe),
    el('details', '', [el('summary', '', ['Ultimi commit del vault']), el('ul', 'mono', e.commit.map(c => el('li', '', [c])))]),
  );
}

async function aggiornaEsecuzioni() {
  renderEsecuzioni(await (await fetch('/api/esecuzioni', { cache: 'no-store' })).json());
}

async function avviaAzione(nome) {
  if (!confirm('Avviare ' + ETICHETTE[nome] + ' adesso? Lo script scrive nel vault.')) return;
  const r = await fetch('/api/azioni/' + nome, { method: 'POST', headers: { 'X-Azione': 'conferma' } });
  if (!r.ok) alert(r.status === 409 ? 'È già in corso.' : 'Azione non riuscita (HTTP ' + r.status + ').');
  aggiornaEsecuzioni();
  if (vista === 'avvii') aggiornaAvvii();
}

document.querySelectorAll('[data-azione]').forEach(b => b.addEventListener('click', () => avviaAzione(b.dataset.azione)));

const RETI_BOZZE = { linkedin: { nome: 'LinkedIn', apri: 'https://www.linkedin.com/feed/' }, instagram: { nome: 'Instagram', apri: 'https://www.instagram.com/' } };

function schedaBozza(rete, b) {
  const stato = el('span', '', []);
  const copia = el('button', 'primario', ['Copia testo e apri ' + RETI_BOZZE[rete].nome]);
  copia.type = 'button';
  copia.addEventListener('click', () => {
    // Prima la finestra, poi la copia: il browser concede l'apertura solo dentro il clic.
    window.open(RETI_BOZZE[rete].apri, '_blank', 'noopener');
    navigator.clipboard.writeText(b.testo).then(
      () => { stato.textContent = 'Testo copiato. Incollalo e allega l\'immagine.'; },
      () => { stato.textContent = 'Copia non riuscita: seleziona il testo qui sotto e copialo a mano.'; },
    );
  });
  const azioni = [copia];
  const figli = [];
  const segna = (testo, nuovo) => {
    const bt = el('button', '', [testo]); bt.type = 'button';
    bt.addEventListener('click', () => cambiaStatoBozza(rete, b, nuovo));
    return bt;
  };
  if (b.stato === 'pubblicata') azioni.push(el('span', 'pillola ok', ['pubblicata il ' + giorno(b.data)]), segna('Rimetti in coda', 'da pubblicare'));
  else azioni.push(segna('Segna come pubblicata', 'pubblicata'), segna('Scarta', 'scartata'));
  if (b.immagine) {
    const url = '/api/bozze/immagine/' + rete + '/' + b.immagine;
    const img = el('img', 'anteprima', []);
    img.src = url; img.alt = 'Immagine della bozza ' + b.titolo; img.loading = 'lazy';
    figli.push(img);
    const scarica = el('a', 'bottone', ['Scarica immagine']);
    scarica.href = url; scarica.download = b.immagine;
    azioni.push(scarica);
  }
  figli.push(el('h3', '', [b.titolo]), el('p', 'mono', [b.nome]),
    el('details', '', [el('summary', '', ['Testo']), el('p', 'testo-bozza', [b.testo])]),
    el('div', 'riga-azioni', azioni), el('p', 'sub', [stato]));
  return el('article', 'bozza', figli);
}

let bozzePerRete = {}, vistaBozze = 'da pubblicare';
async function cambiaStatoBozza(rete, b, stato) {
  try {
    const r = await fetch('/api/bozze/stato', { method: 'POST', headers: { 'X-Azione': 'conferma', 'Content-Type': 'application/json' },
      body: JSON.stringify({ rete, nome: b.nome, stato }) });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    b.stato = stato; b.data = new Date().toISOString().slice(0, 10);
    avviso('«' + b.titolo + '»: ' + stato + '.', false);
    renderBozze(bozzePerRete);
  } catch (e) { avviso('Stato non cambiato: ' + e.message, true); }
}

function renderBozze(per_rete) {
  bozzePerRete = per_rete;
  const quante = v => Object.values(per_rete).reduce((n, l) => n + l.filter(b => b.stato === v).length, 0);
  const scelta = el('div', 'scelta', [['da pubblicare', 'Da pubblicare'], ['pubblicata', 'Già pubblicate']].map(([v, nome]) => {
    const bt = el('button', '', [nome + ' (' + quante(v) + ')']); bt.type = 'button'; bt.setAttribute('aria-pressed', String(vistaBozze === v));
    bt.addEventListener('click', () => { vistaBozze = v; renderBozze(per_rete); });
    return bt;
  }));
  $('bozze').replaceChildren(scelta, ...Object.keys(RETI_BOZZE).map(rete => {
    const lista = per_rete[rete].filter(b => b.stato === vistaBozze);
    if (vistaBozze === 'pubblicata') lista.sort((a, b) => (b.data || '').localeCompare(a.data || ''));
    return el('div', 'rete', [
      el('h2', '', [RETI_BOZZE[rete].nome]),
      ...(lista.length ? [el('div', 'bozze-griglia', lista.map(b => schedaBozza(rete, b)))] : [vuoto(vistaBozze === 'pubblicata' ? 'Ancora niente di pubblicato qui.' : 'Nessuna bozza in coda.')]),
    ]);
  }));
}

async function aggiorna() {
  try {
    const r = await fetch('/api/stato', { cache: 'no-store' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const s = await r.json();
    aggiornaKpi(s);
    renderRadar(s.radar, s.inbox, s.prossimoRadar);
    renderSistema(s);
    renderJobVault(s);
    const oggi = await (await fetch('/api/oggi', { cache: 'no-store' })).json();
    renderOggi(oggi);
    window.Mappa && window.Mappa.imposta(s, oggi);   // la mappa riusa queste due letture: non le rifà
    renderAspetta(await (await fetch('/api/aspetta', { cache: 'no-store' })).json());
    aggiornaEsecuzioni();
    const ra = await fetch('/api/attesa', { cache: 'no-store' });
    if (!ra.ok) throw new Error('attesa: HTTP ' + ra.status);
    renderAttesa(await ra.json());
    $('fresco').className = 'fresco';
    $('fresco').textContent = 'aggiornato alle ' + new Date(s.generato).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
  } catch (e) {
    $('fresco').className = 'fresco errore';
    $('fresco').textContent = 'errore nel caricamento: ' + e.message;
  }
}

function formatoMb(mb) {
  return mb === null ? '–' : Math.round(mb).toLocaleString('it-IT');
}

function renderModelliProcessi(p) {
  const modelli = p.modelli === null
    ? vuoto('Ollama non risponde: installalo e avvialo (l\'app Ollama, oppure ollama serve).')
    : (p.modelli.length
      ? el('table', '', [
        el('thead', '', [el('tr', '', [el('th', '', ['Modello']), el('th', 'num', ['Memoria GB']), el('th', 'num', ['Su GPU'])])]),
        el('tbody', '', p.modelli.map(m => el('tr', '', [
          el('td', '', [m.nome]), el('td', 'num', [m.gb.toLocaleString('it-IT')]), el('td', 'num', [m.gpuPct === null ? '–' : m.gpuPct + ' %']),
        ]))),
      ])
      : vuoto('Nessun modello in memoria: Ollama lo carica alla prima chiamata.'));
  const processi = p.processiOllama.length
    ? el('table', '', [
      el('thead', '', [el('tr', '', [el('th', '', ['Processo']), el('th', 'num', ['PID']), el('th', 'num', ['RAM MB']), el('th', 'num', ['CPU %'])])]),
      el('tbody', '', p.processiOllama.map(x => el('tr', '', [
        el('td', 'mono', [x.comando]), el('td', 'num', [String(x.pid)]), el('td', 'num', [x.rssMb.toLocaleString('it-IT')]), el('td', 'num', [x.cpu.toFixed(1).replace('.', ',')]),
      ]))),
    ])
    : vuoto('Nessun processo Ollama in esecuzione.');
  $('p-modelli-tab').replaceChildren(modelli, el('p', 'sub', ['Processi Ollama']), processi);
}

// Le schede dei modelli scaricati, con i collegamenti per cercarne altri.
function renderInstallati(p) {
  $('p-disco').textContent = p.discoLiberoGb !== undefined ? p.discoLiberoGb.toLocaleString('it-IT') + ' GB liberi sul disco' : '';
  if (p.installati === null) { $('p-installati').replaceChildren(vuoto('Ollama non risponde: installalo e avvialo (l\'app Ollama, oppure ollama serve), poi scarica un modello con ollama pull.')); }
  else if (!p.installati.length) { $('p-installati').replaceChildren(vuoto('Nessun modello scaricato in Ollama.')); }
  else {
    $('p-installati').replaceChildren(el('ul', 'schede-modelli', p.installati.map(m => el('li', '', [
      el('div', 'testata', [el('b', '', [m.nome]), el('span', 'cifra', [m.gb.toLocaleString('it-IT') + ' GB'])]),
      el('div', 'etichette', [
        ...[m.parametri && m.parametri + ' parametri', m.quantizzazione, m.famiglia].filter(Boolean).map(t => el('span', 'etichetta', [t])),
        ...(m.inMemoria ? [el('span', 'pillola positiva', ['in memoria'])] : []),
        ...(m.usatoDa ? [el('span', 'pillola approvare', [m.usatoDa])] : []),
      ]),
      el('div', 'sub', ['Scaricato il ' + (m.scaricato ? giorno(m.scaricato) : '–')]),
    ]))));
  }
  if ($('p-scarica').childElementCount) return;
  const link = (testo, url) => { const a = el('a', 'bottone', [testo]); a.href = url; a.target = '_blank'; a.rel = 'noopener noreferrer'; return a; };
  const nome = el('input', '', []); nome.placeholder = 'nome del modello, per esempio qwen3:4b'; nome.setAttribute('aria-label', 'Nome del modello da scaricare');
  const copia = el('button', '', ['Copia il comando']); copia.type = 'button';
  copia.addEventListener('click', () => {
    if (!/^[\w.:\/-]+$/.test(nome.value.trim())) { avviso('Scrivi il nome di un modello, per esempio qwen3:4b.', true); return; }
    navigator.clipboard.writeText('ollama pull ' + nome.value.trim()).then(() => avviso('Copiato: incollalo nel terminale per scaricare il modello.', false), () => avviso('Copia non riuscita.', true));
  });
  $('p-scarica').replaceChildren(link('Libreria di Ollama', 'https://ollama.com/library'), link('Hugging Face (GGUF)', 'https://huggingface.co/models?library=gguf&sort=trending'), nome, copia);
}

function renderChiamate(c) {
  const op = Object.entries(c.perOperazione);
  $('p-operazioni').replaceChildren(
    op.length
      ? el('table', '', [
        el('thead', '', [el('tr', '', [el('th', '', ['Operazione']), el('th', 'num', ['Chiamate']), el('th', 'num', ['Durata media s']), el('th', 'num', ['Token/s'])])]),
        el('tbody', '', op.map(([nome, g]) => el('tr', '', [
          el('td', '', [nome]), el('td', 'num', [String(g.chiamate)]),
          el('td', 'num', [g.durataMedia.toFixed(2).replace('.', ',')]),
          el('td', 'num', [g.tokenAlSecondoMedia === null ? '–' : g.tokenAlSecondoMedia.toFixed(1).replace('.', ',')]),
        ]))),
      ])
      : vuoto('Nessuna chiamata registrata.')
  );
  // Velocità dei giudizi, una barra per chiamata dalla più vecchia alla più recente: si vede se la velocità cala.
  const giudizi = c.ultime.filter(r => r.operazione === 'giudizio' && r.token_al_secondo).reverse();
  if (!giudizi.length) { $('p-ultime').replaceChildren(vuoto('Nessuna chiamata ancora.')); return; }
  const max = Math.max(...giudizi.map(r => r.token_al_secondo));
  const passo = [1, 2, 5, 10, 20, 50].find(v => v * 4 >= max) || 50, alto = Math.ceil(max / passo) * passo;
  const W = 900, H = 200, sx = 44, bx = 12, by = 160, larg = (W - sx - bx) / giudizi.length;
  const svg = sv('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'Token al secondo di ogni giudizio, dal più vecchio al più recente' });
  for (let v = 0; v <= alto; v += passo) {
    const y = by - (v / alto) * (by - 12);
    svg.append(sv('line', { x1: sx, x2: W - bx, y1: y, y2: y, class: 'griglia' }));
    const t = sv('text', { x: sx - 8, y: y + 4, 'text-anchor': 'end', class: 'asse-testo' }); t.textContent = String(v); svg.append(t);
  }
  giudizi.forEach((r, i) => {
    const h = (r.token_al_secondo / alto) * (by - 12), x = sx + i * larg + larg * 0.2, w = larg * 0.6;
    const rect = sv('rect', { x, y: by - h, width: w, height: h, rx: 3, class: 'colonna' });
    const tip = sv('title'); tip.textContent = r.ts.replace('T', ' ') + ': ' + String(r.token_al_secondo).replace('.', ',') + ' token/s, ' + String(r.durata_s).replace('.', ',') + ' s, ' + r.token_out + ' token in uscita';
    rect.append(tip); svg.append(rect);
    const t = sv('text', { x: x + w / 2, y: by + 18, 'text-anchor': 'middle', class: 'asse-testo' }); t.textContent = r.ts.slice(5, 10).split('-').reverse().join('/') + ' ' + r.ts.slice(11, 16); svg.append(t);
  });
  $('p-ultime').replaceChildren(svg, el('p', 'sub', ['Token al secondo di ogni giudizio del radar, dalla chiamata più vecchia alla più recente.']));
}

const tra = iso => {
  const min = Math.round((new Date(iso) - Date.now()) / 60000);
  if (min <= 0) return 'ora';
  const g = Math.floor(min / 1440), h = Math.floor((min % 1440) / 60), m = min % 60;
  return ('tra ' + (g ? g + ' g ' : '') + (h ? h + ' h ' : '') + (g ? '' : m + ' min')).trim();
};
const aggiornaAspetta = async () => renderAspetta(await (await fetch('/api/aspetta', { cache: 'no-store' })).json());
async function postAssistente(azione, corpo) {
  const x = await fetch('/api/assistente/' + azione, { method: 'POST', headers: { 'X-Azione': 'conferma', 'Content-Type': 'application/json' }, body: JSON.stringify(corpo) });
  const d = await x.json().catch(() => ({}));
  if (!x.ok) throw new Error(d.errore || 'HTTP ' + x.status);
  return d;
}

function schedaAppuntamento(d) {
  const p = d.proposta, campo = (nome, tipo, valore, extra) => {
    const i = el('input', '', []); i.type = tipo; i.value = valore; i.setAttribute('aria-label', nome); Object.assign(i, extra || {});
    return el('label', 'campo', [el('span', 'sub', [nome]), i]);
  };
  const titolo = campo('Titolo', 'text', p.titolo, { maxLength: 120 }), data = campo('Giorno', 'date', p.data), ora = campo('Ora', 'time', p.ora),
    durata = campo('Durata (minuti)', 'number', String(p.durata_min), { min: 5, max: 480, step: 5 });
  const scelti = d.calendari.map(nome => { const c = el('input', '', []); c.type = 'checkbox'; c.checked = true; c.value = nome; return c; });
  const nota = el('p', 'sub', []), esito = el('p', 'sub', []);
  const val = l => l.querySelector('input').value;
  const aggiorna = () => {
    nota.textContent = !val(ora) ? 'Manca l\'ora: scrivila prima di aggiungere.' : '';
    aggiungi.disabled = !val(titolo).trim() || !val(data) || !val(ora) || !scelti.some(c => c.checked);
  };
  const aggiungi = el('button', 'primario', ['Aggiungi al calendario']); aggiungi.type = 'button';
  const annulla = el('button', '', ['Non aggiungere']); annulla.type = 'button';
  annulla.addEventListener('click', () => $('appuntamento-scheda').replaceChildren());
  aggiungi.addEventListener('click', async () => {
    aggiungi.disabled = true; esito.textContent = 'Scrivo nel Calendario…';
    try {
      const r = await postAssistente('applica', { titolo: val(titolo), data: val(data), ora: val(ora), durata_min: Number(val(durata)), calendari: scelti.filter(c => c.checked).map(c => c.value) });
      esito.textContent = 'Aggiunto in: ' + r.creati.map(c => c.calendario).join(', ') + '. Google può metterci un minuto a mostrarlo sul telefono.';
      const togli = el('button', '', ['Togli di nuovo']); togli.type = 'button';
      togli.addEventListener('click', async () => {
        togli.disabled = true;
        try { for (const c of r.creati) await postAssistente('annulla', { uid: c.uid }); esito.textContent = 'Tolto.'; togli.remove(); }
        catch (e) { esito.textContent = 'Non l\'ho tolto: ' + e.message; togli.disabled = false; }
      });
      esito.after(togli); aggiungi.remove(); annulla.remove();
      aggiornaAspetta();
    } catch (e) { esito.textContent = 'Non aggiunto: ' + e.message; aggiungi.disabled = false; }
  });
  [titolo, data, ora, durata].forEach(l => l.querySelector('input').addEventListener('input', aggiorna)); scelti.forEach(c => c.addEventListener('change', aggiorna));
  aggiorna();
  return el('div', 'scheda-appuntamento', [
    el('p', '', ['Controlla prima di aggiungere. Il modello ha letto la frase, i giorni li ha calcolati il codice.']),
    el('div', 'riga-azioni', [titolo, data, ora, durata]),
    el('div', 'riga-azioni', [el('span', 'sub', ['Scrivi in']), ...d.calendari.map((n, i) => el('label', '', [scelti[i], ' ' + n]))]),
    ...(d.conflitti.length ? [el('p', 'sub avviso-testo', ['Si sovrappone a: ' + d.conflitti.join(', ') + '.'])] : []),
    nota, el('div', 'riga-azioni', [aggiungi, annulla]), esito]);
}
$('appuntamento-form').addEventListener('submit', async e => {
  e.preventDefault();
  const frase = $('appuntamento-frase').value.trim();
  if (frase.length < 2) return;
  $('appuntamento-scheda').replaceChildren(el('p', 'sub', ['Sto leggendo la frase…']));
  try { $('appuntamento-scheda').replaceChildren(schedaAppuntamento(await postAssistente('proponi', { frase }))); }
  catch (e) { $('appuntamento-scheda').replaceChildren(el('p', 'sub', ['Non ho capito: ' + e.message])); }
});

const DOMANDE_ASSISTENTE = ['Cosa devo fare oggi?', 'Cosa scade questa settimana?', 'Dove trovo un\'ora libera domani?'];
async function chiediAssistente(domanda) {
  const r = $('assistente-risposta'), n = $('assistente-nota'), b = $('assistente-form').querySelector('button');
  r.textContent = 'Sto pensando…'; n.textContent = ''; b.disabled = true;
  try {
    const x = await fetch('/api/assistente/chiedi', { method: 'POST', headers: { 'X-Azione': 'conferma', 'Content-Type': 'application/json' }, body: JSON.stringify({ domanda }) });
    if (!x.ok) throw new Error('HTTP ' + x.status);
    const d = await x.json();
    r.textContent = d.risposta;
    n.textContent = d.pronto ? 'Risposta di ' + etichettaModello() + ' in ' + d.secondi + ' s, dai dati del Calendario letti ' + quando(d.calendario.aggiornato) + '. Può sbagliare: controlla le date.' : '';
  } catch (e) { r.textContent = 'Non ho potuto chiedere: ' + e.message; } finally { b.disabled = false; }
}
$('assistente-form').addEventListener('submit', e => { e.preventDefault(); const q = $('assistente-domanda').value.trim(); if (q.length >= 2) chiediAssistente(q); });
$('assistente-chip').replaceChildren(...DOMANDE_ASSISTENTE.map(q => { const c = el('button', '', [q]); c.type = 'button'; c.addEventListener('click', () => { $('assistente-domanda').value = q; chiediAssistente(q); }); return c; }));
const GIORNI = ['dom', 'lun', 'mar', 'mer', 'gio', 'ven', 'sab'];

function barraUso(etichetta, parte, classe, valore) {
  const riempi = el('span', 'riempi', []);
  riempi.style.width = Math.min(100, parte * 100) + '%';
  const barra = el('div', 'barra ' + classe, [riempi]);
  barra.setAttribute('role', 'img'); barra.setAttribute('aria-label', etichetta + ': ' + valore);
  return el('div', 'riga-barra', [el('span', 'etichetta-barra', [etichetta]), barra, el('span', 'valore', [valore])]);
}

function finestraClaude(f) {
  if (f.inattiva) return el('article', 'finestra', [
    el('header', '', [el('h2', '', ['Finestra di 5 ore']), el('span', 'pillola', ['non aperta'])]),
    el('p', 'sub', ['Nessuna finestra di 5 ore aperta: parte al prossimo messaggio a Claude e da lì conta 5 ore. Claude Code non la segnala finché non c\'è.'])]);
  const usato = f.percentuale / 100;
  let ritmo, classe;
  if (f.scaduto) { ritmo = 'La finestra si è rinnovata ' + quando(f.rinnovo) + ': la percentuale letta era di prima (' + f.percentuale + '%).'; classe = 'avviso'; }
  else if (usato > f.trascorso + 0.1) { ritmo = 'Stai consumando più in fretta del tempo che passa: ' + f.percentuale + '% usato contro ' + Math.round(f.trascorso * 100) + '% del tempo.'; classe = 'avviso'; }
  else { ritmo = 'Il consumo è in linea con il tempo trascorso: ' + f.percentuale + '% usato contro ' + Math.round(f.trascorso * 100) + '% del tempo.'; classe = 'ok'; }
  const corpo = [
    el('header', '', [el('h2', '', [f.nome === '5 ore' ? 'Finestra di 5 ore' : 'Finestra settimanale']), el('span', 'pillola ' + classe, [f.scaduto ? 'dato vecchio' : (classe === 'ok' ? 'nel ritmo' : 'sopra il ritmo')])]),
    el('p', 'grande' + (f.scaduto ? ' vecchio' : ''), [f.percentuale + '%', el('small', '', [f.scaduto ? 'usato prima del rinnovo' : 'usato'])]),
    barraUso('Usato', usato, f.scaduto ? 'vecchio' : '', f.percentuale + '%'),
    barraUso('Tempo trascorso', f.trascorso, 'tempo', Math.round(f.trascorso * 100) + '%'),
  ];
  if (f.nome === 'Settimana') {
    const inizio = new Date(f.inizio);
    corpo.push(el('div', 'giorni', Array.from({ length: 7 }, (_, i) => el('span', '', [GIORNI[(inizio.getDay() + i) % 7]]))));
  } else {
    corpo.push(el('div', 'estremi', [el('span', '', [new Date(f.inizio).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' })]), el('span', '', [new Date(f.rinnovo).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' })])]));
  }
  corpo.push(el('p', 'sub', [(f.scaduto ? '' : 'Si rinnova ' + tra(f.rinnovo) + ', ' + quando(f.rinnovo) + '. ') + ritmo]));
  return el('article', 'finestra', corpo);
}

function renderClaude(c) {
  if (!c.finestre.length) { $('p-claude').replaceChildren(vuoto('Nessun dato: Claude Code non ha ancora salvato le percentuali d\'uso. Servono la barra di stato scripts/statusline-uso.py (vedi il README, «Quando una pagina è vuota») e una risposta in una sessione.')); return; }
  $('p-claude').replaceChildren(...c.finestre.map(finestraClaude));
  $('p-claude-nota').textContent = 'Letto da Claude Code il ' + quando(c.aggiornato) + '. Non salva un limite giornaliero: restano la finestra di 5 ore e quella settimanale. Si aggiorna solo quando lo chiede lui: per il dato fresco usa /usage nella sessione.';
}

// Token per giorno: una serie, una tinta, 4 linee di griglia leggere, asse con valori tondi.
function renderConsumo(c) {
  const giorni = c.giorni, max = Math.max(1, ...giorni.map(g => g.token));
  const passo = [1, 2, 2.5, 5, 10].map(m => m * 10 ** Math.floor(Math.log10(max / 4))).find(v => v >= max / 4) || max;
  const alto = Math.ceil(max / passo) * passo, W = 900, H = 240, sx = 56, bx = 28, by = 190;
  const asse = Array.from({ length: alto / passo + 1 }, (_, i) => i * passo);
  const larg = (W - sx - bx) / giorni.length;
  const svg = sv('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'Token elaborati da Claude Code in ciascuno degli ultimi ' + giorni.length + ' giorni' });
  for (const v of asse) {
    const y = by - (v / alto) * (by - 14);
    svg.append(sv('line', { x1: sx, x2: W - bx, y1: y, y2: y, class: 'griglia' }));
    const t = sv('text', { x: sx - 8, y: y + 4, 'text-anchor': 'end', class: 'asse-testo' }); t.textContent = new Intl.NumberFormat('it-IT', { notation: 'compact' }).format(v); svg.append(t);
  }
  giorni.forEach((g, i) => {
    const h = (g.token / alto) * (by - 14), x = sx + i * larg + larg * 0.16, w = larg * 0.68;
    const r = sv('rect', { x, y: by - h, width: w, height: Math.max(h, g.token ? 2 : 0), rx: 3, class: 'colonna' });
    const tip = sv('title'); tip.textContent = new Date(g.data + 'T12:00').toLocaleDateString('it-IT', { weekday: 'long', day: 'numeric', month: 'long' }) + ': ' + new Intl.NumberFormat('it-IT').format(g.token) + ' token, ' + g.messaggi + ' risposte';
    r.append(tip); svg.append(r);
    if (i % 2 === giorni.length % 2 || giorni.length <= 8) {
      const t = sv('text', { x: x + w / 2, y: by + 20, 'text-anchor': 'middle', class: 'asse-testo' }); t.textContent = new Date(g.data + 'T12:00').toLocaleDateString('it-IT', { day: 'numeric', month: 'short' }); svg.append(t);
    }
  });
  $('p-consumo').replaceChildren(svg, el('p', 'sub', ['Input, output e scrittura in cache di Claude Code su questo Mac, letti dalle sessioni locali. Non coincide con il limite del piano: mostra quanto lavoro ha fatto ogni giorno.']));
}

async function aggiornaPrestazioni() {
  try {
    const r = await fetch('/api/prestazioni', { cache: 'no-store' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const p = await r.json();
    $('p-modelli').textContent = p.modelli === null ? '–' : p.modelli.length;
    $('p-swap').textContent = formatoMb(p.memoria.swapUsatoMb);
    $('p-chiamate').textContent = p.chiamate.totale;
    const giudizio = p.chiamate.perOperazione.giudizio;
    $('p-velocita').textContent = giudizio && giudizio.tokenAlSecondoMedia !== null ? giudizio.tokenAlSecondoMedia.toFixed(1).replace('.', ',') : '–';
    renderClaude(p.claude);
    renderConsumo(p.consumo);
    renderInstallati(p);
    renderModelliProcessi(p);
    renderChiamate(p.chiamate);
    $('fresco').className = 'fresco';
    $('fresco').textContent = 'prestazioni aggiornate alle ' + new Date(p.generato).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
  } catch (e) {
    $('fresco').className = 'fresco errore';
    $('fresco').textContent = 'errore nel caricamento: ' + e.message;
  }
}

function nomi(lista, vuotoTesto) {
  return lista.length ? el('div', 'elenco-nomi', lista.map(n => el('span', '', [n]))) : el('p', 'sub', [vuotoTesto]);
}

function tabella(testata, righe, classiCol) {
  return el('div', '', [el('table', '', [
    el('thead', '', [el('tr', '', testata.map((t, i) => el('th', (classiCol || [])[i] || '', [t])))]),
    el('tbody', '', righe.map(r => el('tr', '', r.map((c, i) => el('td', (classiCol || [])[i] || '', [c]))))),
  ])]);
}

const STATO_SKILL = { uguale: 'aggiornata', nuova: 'versione nuova', modificata: 'modificata in locale', rimossa: 'non più nel repo' };

async function chiamaConfig(percorso, corpo) {
  const r = await fetch(percorso, { method: 'POST', headers: { 'X-Azione': 'conferma', 'Content-Type': 'application/json' }, body: JSON.stringify(corpo) });
  const dati = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(dati.errore || 'HTTP ' + r.status);
  return dati;
}

function avviso(testo, errore) {
  $('fresco').className = 'fresco' + (errore ? ' errore' : '');
  $('fresco').textContent = testo;
}

// Un pulsante che esegue 'fai', si blocca mentre lavora e riporta l'esito in basso a sinistra.
function pulsante(testo, classe, fai) {
  const b = el('button', classe, [testo]);
  b.type = 'button';
  b.addEventListener('click', async () => {
    b.disabled = true;
    try { avviso(await fai(), false); await aggiornaConfigurazione(false); }
    catch (e) { avviso(e.message, true); b.disabled = false; }
  });
  return b;
}

const attendi = ms => new Promise(r => setTimeout(r, ms));

function pulsanteControlla() {
  return pulsante('Controlla ora', '', async () => {
    avviso('controllo delle skill in corso…', false);
    await chiamaConfig('/api/azioni/controllo-skill', {nome: 'controllo-skill'}).catch(e => { if (!/già in corso|409/.test(e.message)) throw e; });
    for (let i = 0; i < 60; i++) {
      await attendi(3000);
      const e = await (await fetch('/api/esecuzioni', { cache: 'no-store' })).json();
      if (!e['controllo-skill'].inCorso) return 'Controllo delle skill finito.';
    }
    throw new Error('il controllo non è ancora finito: riapri la scheda tra poco');
  });
}

function pulsanteInterruttore(tipo, nome, attivo) {
  return pulsante(attivo ? 'Disattiva' : 'Attiva', '', async () => {
    await chiamaConfig('/api/configurazione/interruttore', { tipo, nome, attivo: !attivo });
    return nome + (attivo ? ' disattivata' : ' attivata') + ': vale dalla prossima sessione di Claude.';
  });
}

function pulsanteAggiorna(x) {
  if (!x.azione.startsWith('aggiornare')) return el('p', 'segnalazione', ['Per aggiornarla serve il tuo «installa lo stesso» in chat.']);
  const b = pulsante('Aggiorna', 'primario', async () => {
    if (!confirm('Aggiornare ' + x.nome + ' da ' + x.installata + ' a ' + x.disponibile + '?\nRiscarico il repo, rifaccio la scansione e, se è ancora senza segnalazioni gravi, sostituisco la cartella. Il backup della vecchia resta in ~/.agents/skills-backup.')) throw new Error('aggiornamento annullato');
    const d = await chiamaConfig('/api/configurazione/aggiorna', { nome: x.nome, atteso: x.disponibile });
    return x.nome + ' aggiornata a ' + d.versione + '. Backup in ' + d.backup + '. Vale dalla prossima sessione.';
  });
  return b;
}

// Lo stesso aggiornamento del pulsante singolo, una skill alla volta; alla prima che non riesce si ferma.
function pulsanteAggiornaTutte(lista, saltate) {
  return pulsante('Aggiorna tutte (' + lista.length + ')', 'primario', async () => {
    const righe = lista.map(x => '• ' + x.nome + ': ' + x.installata + ' → ' + x.disponibile).join('\n');
    if (!confirm('Aggiornare ' + lista.length + ' skill?\n' + righe + '\n\nPer ognuna riscarico il repo, rifaccio la scansione e, se è ancora senza segnalazioni gravi, sostituisco la cartella. Mi fermo alla prima che non riesce. Il backup delle vecchie resta in ~/.agents/skills-backup.'
      + (saltate ? '\n' + saltate + ' non si possono aggiornare da qui (serve il tuo «installa lo stesso» in chat).' : ''))) throw new Error('aggiornamento annullato');
    const fatte = [];
    for (const x of lista) {
      avviso('Aggiorno ' + x.nome + ' (' + (fatte.length + 1) + ' di ' + lista.length + ')…', false);
      try {
        await chiamaConfig('/api/configurazione/aggiorna', { nome: x.nome, atteso: x.disponibile });
        fatte.push(x.nome);
      } catch (e) {
        await aggiornaConfigurazione(false);
        const rimaste = lista.slice(fatte.length + 1).map(y => y.nome);
        throw new Error((fatte.length ? 'Aggiornate: ' + fatte.join(', ') + '. ' : 'Nessuna aggiornata. ') + 'Mi fermo su ' + x.nome + ': ' + e.message
          + (rimaste.length ? '. Non provate: ' + rimaste.join(', ') + '.' : ''));
      }
    }
    return fatte.length + ' skill aggiornate (' + fatte.join(', ') + '). Backup in ~/.agents/skills-backup. Vale dalla prossima sessione.';
  });
}

function renderAggiornamenti(c) {
  if (!c) return [el('h3', 'riga-titolo', ['Aggiornamenti delle skill', pulsanteControlla()]), vuoto('Nessun controllo ancora: parte il venerdì alle 18:00, oppure premi «Controlla ora».')];
  const fonti = c.fonti.map(f => f.url.replace('https://github.com/', '').replace('.git', '') + ' ' + f.commit + ' del ' + f.data).join(' · ');
  const nuove = c.skill.filter(x => x.stato === 'nuova');
  const altre = (stato, titolo) => {
    const l = c.skill.filter(x => x.stato === stato);
    return l.length ? el('details', '', [el('summary', '', [titolo + ' (' + l.length + ')']), nomi(l.map(x => x.nome), '')]) : '';
  };
  const lock = c.skill.filter(x => x.stato === 'uguale' && !x.lockAllineato);
  const aggiornabili = nuove.filter(x => x.azione.startsWith('aggiornare'));
  return [
    el('h3', 'riga-titolo', ['Aggiornamenti delle skill', pulsanteControlla()]),
    el('p', 'sub', ['Controllo del ' + c.generato.slice(0, 10) + ', repo letti: ' + fonti + '. Il controllo non installa nulla: per ogni aggiornamento serve il tuo ok.']),
    aggiornabili.length > 1 ? el('p', '', [pulsanteAggiornaTutte(aggiornabili, nuove.length - aggiornabili.length)]) : '',
    nuove.length
      ? tabella(['Skill', 'Installata → disponibile', 'Scansione', 'Azione suggerita'], nuove.map(x => {
          const sc = x.scansione;
          const esito = !sc || sc.errore ? 'non riuscita' : sc.severita + ', punteggio ' + sc.score + ', ' + sc.raccomandazione;
          const seg = sc && sc.segnalazioni ? sc.segnalazioni.map(g => el('p', 'segnalazione', [g.severita + ' · ' + g.file + ':' + g.riga + ' · ' + g.testo])) : [];
          return [x.nome, x.installata + ' → ' + x.disponibile, el('div', '', [esito, ...seg]), el('div', '', [el('span', 'pillola ' + (x.azione.startsWith('aggiornare') ? 'ok' : 'attesa'), [x.azione]), pulsanteAggiorna(x)])];
        }))
      : vuoto('Nessuna versione nuova disponibile.'),
    altre('modificata', 'Modificate in locale, repo invariato'),
    altre('rimossa', 'Non più nel repo di origine'),
    lock.length ? el('details', '', [el('summary', '', ['Aggiornate a mano, con lock obsoleto (' + lock.length + ')']), nomi(lock.map(x => x.nome), '')]) : '',
    ...c.errori.map(e => el('p', 'sub', ['Errore: ' + e])),
  ];
}

function renderGlobale(g) {
  const attive = g.skill.filter(x => x.attiva);
  const spente = g.skill.filter(x => !x.attiva);
  const plugin = tabella(['Plugin', 'Versione', 'Stato', 'Skill', 'Hook', 'MCP', ''], g.plugin.map(x => [
    x.nome, x.versione || '–', el('span', 'pillola ' + (x.attivo ? 'ok' : ''), [x.attivo ? 'attivo' : 'disattivato']),
    String(x.skill.length), x.hook.join(', ') || '–', x.mcp.join(', ') || '–',
    pulsanteInterruttore('plugin', x.nome + '@' + x.mercato, x.attivo),
  ]));
  const riga = x => [
    x.nome + (x.versione ? ' ' + x.versione : ''),
    x.tracciata ? x.origine : x.origine + (x.lockObsoleto ? ' (lock obsoleto)' : ''),
    x.aggiornata || '–',
    x.controllo ? STATO_SKILL[x.controllo.stato] : (x.tracciata ? 'non controllata' : 'non tracciata'),
    pulsanteInterruttore('skill', x.nome, x.attiva),
  ];
  return {
    plugin: [plugin],
    skill: [
      el('p', 'sub', ['Skill attive: ' + attive.length + ' su ' + g.skill.length + '. Le altre sono disattivate in settings.json.']),
      tabella(['Skill', 'Origine', 'Aggiornata il', 'Controllo', ''], attive.map(riga)),
      el('details', '', [el('summary', '', ['Disattivate in settings.json (' + spente.length + ')']), tabella(['Skill', 'Origine', 'Aggiornata il', 'Controllo', ''], spente.map(riga))]),
    ],
    sincronizzati: [
      el('p', 'sub', ['Plugin: ' + (g.sincronizzati.plugin.map(x => x.nome + ' ' + (x.versione || '')).join(', ') || 'nessuno') + '. Non hanno una versione locale da aggiornare.']),
      nomi(g.sincronizzati.skill, 'Nessuna skill sincronizzata.'),
      el('p', 'sub', ['MCP dei plugin sincronizzati: ' + (g.sincronizzati.plugin.flatMap(x => x.mcp).filter((v, i, a) => a.indexOf(v) === i).join(', ') || 'nessuno')]),
      el('p', 'sub', ['MCP in ~/.claude.json: ' + (g.mcp.join(', ') || 'nessuno') + '. Hook in settings.json: ' + (g.hook.join(', ') || 'nessuno') + '. Gli hook dei plugin sono nella tabella dei plugin.']),
    ],
  };
}

function renderProgettoConf(p) {
  const riga = (nome, lista) => [el('dt', '', [nome]), el('dd', '', [lista.length ? lista.join(', ') : '–'])];
  return el('div', 'conf-progetto', [
    el('h3', '', [p.nome]),
    p.esiste ? '' : el('p', 'sub', ['Cartella non trovata.']),
    el('dl', '', [
      ...riga('Skill', p.skill), ...riga('Comandi', p.comandi), ...riga('Agenti', p.agenti),
      ...riga('Plugin', p.plugin.map(([n, v]) => n + (v ? '' : ' (disattivato)'))),
      ...riga('Hook', p.hook), ...riga('MCP', p.mcp),
    ]),
  ]);
}

let schedaConf = null;

// Progetti: strumenti per progetto, a barre, e la tabella con i nomi dietro un dettaglio.
function pannelloProgettiConf(progetti) {
  const totale = p => p.skill.length + p.comandi.length + p.agenti.length;
  const max = Math.max(1, ...progetti.map(totale));
  const barre = el('div', 'imbuto', [...progetti].sort((a, b) => totale(b) - totale(a)).map(p => {
    const riempi = el('span', 'riempi', []);
    riempi.style.width = (totale(p) ? Math.max(1.5, totale(p) / max * 100) : 0) + '%';
    return el('div', 'riga-imbuto', [el('span', '', [p.nome, el('small', '', [p.skill.length + ' skill · ' + p.comandi.length + ' comandi · ' + p.agenti.length + ' agenti'])]), el('div', 'barra', [riempi]), el('b', '', [String(totale(p))])]);
  }));
  const elenco = (nomi) => nomi.length ? el('details', '', [el('summary', '', [String(nomi.length)]), el('p', 'sub', [nomi.join(', ')])]) : el('span', 'sub', ['–']);
  const tab = tabella(['Progetto', 'Skill', 'Comandi', 'Agenti', 'Plugin', 'Hook', 'MCP'], progetti.map(p => [
    p.nome + (p.esiste ? '' : ' (cartella non trovata)'), elenco(p.skill), elenco(p.comandi), elenco(p.agenti),
    elenco(p.plugin.map(([n, v]) => n + (v ? '' : ' (disattivato)'))), elenco(p.hook), elenco(p.mcp),
  ]));
  return [el('p', 'sub', ['Skill, comandi e agenti definiti dentro ogni progetto. Solo i nomi: niente variabili né chiavi.']), barre, tab];
}

function renderConfigurazione(d) {
  const g = renderGlobale(d.globale);
  const attive = d.globale.skill.filter(x => x.attiva).length;
  const plugin = d.globale.plugin, pluginAttivi = plugin.filter(x => x.attivo).length;
  const controllo = renderAggiornamenti(d.controllo);
  const daFare = ((d.controllo && d.controllo.skill) || []).filter(x => /^(aggiornare|chiedere)/.test(x.azione || '')).length;
  const pannelli = {
    aggiornamenti: ['Aggiornamenti', controllo],
    plugin: ['Plugin', g.plugin],
    skill: ['Skill', g.skill],
    sincronizzati: ['Sincronizzati', g.sincronizzati],
    progetti: ['Progetti', pannelloProgettiConf(d.progetti)],
  };
  if (!pannelli[schedaConf]) schedaConf = daFare ? 'aggiornamenti' : 'plugin';
  const kpi = el('ul', 'riepilogo', [
    el('li', '', [el('b', daFare ? 'dato' : '', [String(daFare)]), el('span', '', ['aggiornamenti delle skill da valutare'])]),
    el('li', '', [el('b', '', [pluginAttivi + ' su ' + plugin.length]), el('span', '', ['plugin attivi'])]),
    el('li', '', [el('b', '', [attive + ' su ' + d.globale.skill.length]), el('span', '', ['skill attive'])]),
    el('li', '', [el('b', '', [String(d.progetti.length)]), el('span', '', ['progetti con strumenti propri'])]),
  ]);
  const scelta = el('div', 'scelta', Object.entries(pannelli).map(([chiave, [nome]]) => {
    const b = el('button', '', [nome]); b.type = 'button'; b.setAttribute('aria-pressed', String(chiave === schedaConf));
    b.addEventListener('click', () => { schedaConf = chiave; renderConfigurazione(d); });
    return b;
  }));
  $('conf-contenuto').replaceChildren(kpi, scelta, el('section', 'conf-sez', pannelli[schedaConf][1]));
}

async function aggiornaConfigurazione(avvisa = true) {
  try {
    const r = await fetch('/api/configurazione', { cache: 'no-store' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    renderConfigurazione(await r.json());
    if (!avvisa) return;
    $('fresco').className = 'fresco';
    $('fresco').textContent = 'configurazione letta alle ' + new Date().toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
  } catch (e) {
    $('fresco').className = 'fresco errore';
    $('fresco').textContent = 'errore nel caricamento: ' + e.message;
  }
}

const STATI_AVVIO = { ok: 'partito', 'in-corso': 'in corso', 'in-attesa': 'non ancora', 'in-ritardo': 'partito in ritardo', mancato: 'non partito', mai: 'mai partito', fallito: 'fallito', saltato: 'saltato' };
const CLASSE_AVVIO = { ok: 'positiva', 'in-ritardo': 'avviso', mancato: 'negativa', mai: 'negativa', fallito: 'negativa' };
const NOMI_AVVIO = { morning: 'Morning, ore 8:00', chiusura: 'Chiusura, ore 18:30', radar: 'Radar, lunedì', pulizia: 'Pulizia, venerdì', bozze: 'Bozze, lunedì' };
const quando = iso => iso ? new Date(iso).toLocaleString('it-IT', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '–';

function renderAvvii(d) {
  $('avvii-mac').textContent = d.macAcceso ? 'Il Mac è acceso dal ' + quando(d.macAcceso) + '.' : '';
  $('avvii-contenuto').replaceChildren(...d.job.map(j => {
    const bottone = j.azione ? el('button', '', ['Avvia ora']) : null;
    if (bottone) { bottone.type = 'button'; bottone.addEventListener('click', () => avviaAzione(j.azione)); }
    return el('div', 'avvio', [
      el('div', '', [
        el('div', 'nome', [NOMI_AVVIO[j.nome] || j.nome, el('span', 'pillola ' + (CLASSE_AVVIO[j.stato] || ''), [STATI_AVVIO[j.stato]])]),
        el('p', 'sub', [j.motivo + '. Previsto ' + quando(j.previsto) + ', ultimo log ' + quando(j.ultimoLog) + ', prossimo ' + quando(j.prossimo) + '.']),
        j.ultimaRiga ? el('div', 'mono', [j.ultimaRiga]) : '',
      ]),
      bottone || '',
    ]);
  }));
}

// «Aspetta te»: ciò che chiede una decisione adesso. Ogni riga porta alla pagina dove decidere.
function renderAttesa(a) {
  $('oggi-fatto').textContent = a.fatto;
  $('oggi-fatto').style.color = a.conteggi.job ? 'var(--negative)' : 'var(--muted)';
  $('kpi-bozze').textContent = a.conteggi.bozze;
  $('kpi-skill').textContent = a.conteggi.skill ?? '–';
  $('aspetta-te-lista').replaceChildren(a.voci.length
    ? el('ul', 'piano-voci', a.voci.map(v => {
      const b = el('button', '', ['Apri']);
      b.type = 'button';
      b.addEventListener('click', () => mostra(v.link));
      return el('li', 'attesa-voce', [el('span', '', [v.testo]), b]);
    }))
    : vuoto('Niente aspetta te.'));
}

async function aggiornaAvvii() {
  try {
    const r = await fetch('/api/avvii', { cache: 'no-store' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    renderAvvii(await r.json());
    avviso('avvii letti alle ' + new Date().toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' }), false);
  } catch (e) { avviso('errore nel caricamento: ' + e.message, true); }
}

let progettoServizi = null;

const numero = v => parseFloat(String(v).replace(',', '.'));
const NF = new Intl.NumberFormat('it-IT', { maximumFractionDigits: 2 });
const cifra = (v, unita) => NF.format(v) + (unita ? ' ' + unita : '');
const giorno = iso => iso ? new Date(iso + 'T12:00').toLocaleDateString('it-IT', { day: 'numeric', month: 'short', year: 'numeric' }) : '–';

// Le misure analizzate dal server: ordinate dalla più vicina al limite (al ritmo previsto) alla più lontana.
function misureDi(p) {
  return p.analisi.misure.map(m => ({ ...m, parte: m.usato / m.limite, parteprevista: (m.previsto === null ? m.usato : m.previsto) / m.limite, vicino: m.verdetto !== 'ok' }))
    .sort((a, b) => b.parteprevista - a.parteprevista);
}

function soldi(voci) {
  const somme = {};
  for (const v of voci) {
    const m = /^([\d.,]+)\s*(\S+)$/.exec(v['Pagato'] || '');
    if (m) somme[m[2]] = (somme[m[2]] || 0) + numero(m[1]);
  }
  const parti = Object.entries(somme).map(([valuta, tot]) => NF.format(tot) + ' ' + valuta);
  return parti.length ? parti.join(' + ') : '0';
}

const CLASSE_VERDETTO = { ok: 'positiva', guarda: 'avviso', passa: 'negativa' };
const dollari = som => { const parti = Object.entries(som).map(([v, t]) => new Intl.NumberFormat('it-IT', { maximumFractionDigits: 2, minimumFractionDigits: 2 }).format(t) + ' ' + v); return parti.length ? parti.join(' + ') : '0'; };

function kpiServizi(p, misure) {
  const daGuardare = misure.filter(m => m.verdetto !== 'ok').length;
  const salto = Object.keys(p.analisi.saltoDiPiano).length;
  const celle = [
    [String(p.servizi.length), 'servizi usati', ''],
    [String(daGuardare), daGuardare === 1 ? 'misura da guardare o da valutare' : 'misure da guardare o da valutare', daGuardare ? 'dato' : ''],
    [dollari(p.analisi.spesaMensile), 'spesa fissa al mese (rinnovi diviso 12)', ''],
    [salto ? '+ ' + dollari(p.analisi.saltoDiPiano) : 'nessuno', 'costo in più al mese se passi ai piani a pagamento necessari', ''],
  ];
  $('servizi-kpi').replaceChildren(...celle.map(([v, e, c]) => el('li', '', [el('b', c, [v]), el('span', '', [e])])));
}

const NS = 'http://www.w3.org/2000/svg';
const sv = (tag, attrs, figli) => { const n = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, v); (figli || []).forEach(f => n.append(f)); return n; };

// Schema: sorgenti a sinistra, servizi che fanno da centro in mezzo, servizi a cui si appoggiano a destra.
function schemaServizi(p, misure) {
  const archi = p.collegamenti.map(c => ({ da: c['Da'], a: c['A'], cosa: c['Cosa'] }));
  if (!archi.length) { $('servizi-schema').replaceChildren(vuoto('Nessun collegamento registrato.')); return; }
  const nomi = [...new Set(archi.flatMap(a => [a.da, a.a]))];
  const colonna = n => { const esce = archi.some(a => a.da === n), entra = archi.some(a => a.a === n); return esce && entra ? 1 : esce ? 0 : 2; };
  const cols = [0, 1, 2].map(i => nomi.filter(n => colonna(n) === i));
  const larg = 176, alt = 46, passo = 66, W = 900, margine = 8;
  const righe = Math.max(...cols.map(c => c.length));
  const H = righe * passo - (passo - alt) + 2 * margine;
  const x = i => margine + i * ((W - 2 * margine - larg) / 2);
  const pos = {};
  cols.forEach((c, i) => c.forEach((n, j) => { pos[n] = { x: x(i), y: margine + (H - 2 * margine - (c.length * passo - (passo - alt))) / 2 + j * passo }; }));
  const svg = sv('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'Schema dei collegamenti tra i servizi di ' + p.progetto });
  for (const a of archi) {
    const d = pos[a.da], e = pos[a.a];
    const x1 = d.x + larg, y1 = d.y + alt / 2, x2 = e.x, y2 = e.y + alt / 2, mx = (x1 + x2) / 2;
    svg.append(sv('path', { class: 'arco', d: `M${x1} ${y1} C${mx} ${y1} ${mx} ${y2} ${x2} ${y2}` }));
    const t = sv('text', { class: 'etichetta', x: mx, y: (y1 + y2) / 2 - 6, 'text-anchor': 'middle' }); t.textContent = a.cosa; svg.append(t);
  }
  for (const n of nomi) {
    const riga = p.servizi.find(s => s['Servizio'].toLowerCase().startsWith(n.toLowerCase()));
    const sue = misure.filter(m => m.servizio.toLowerCase() === n.toLowerCase());
    const peggio = sue[0];
    const g = sv('g', { class: 'nodo' + (peggio && peggio.vicino ? ' vicino' : '') });
    g.append(sv('rect', { x: pos[n].x, y: pos[n].y, width: larg, height: alt, rx: 8 }));
    const t1 = sv('text', { x: pos[n].x + 12, y: pos[n].y + 19 }); t1.textContent = n; g.append(t1);
    const sotto = peggio ? Math.round(peggio.parte * 100) + '% del limite' : (riga ? riga['Piano'] : '');
    const t2 = sv('text', { class: peggio ? 'dato' : 'piccolo', x: pos[n].x + 12, y: pos[n].y + 36 }); t2.textContent = sotto.length > 28 ? sotto.slice(0, 27) + '…' : sotto; g.append(t2);
    svg.append(g);
  }
  $('servizi-schema').replaceChildren(svg);
}

async function aggiornaMisura(p, m) {
  const nuovo = window.prompt('Nuovo valore di «' + m.misura + '» (' + m.unita + '), letto oggi dal pannello di ' + m.servizio + ':', String(m.usato).replace('.', ','));
  if (nuovo === null || !nuovo.trim()) return;
  try {
    const r = await fetch('/api/servizi/misura', { method: 'POST', headers: { 'X-Azione': 'conferma', 'Content-Type': 'application/json' },
      body: JSON.stringify({ progetto: p.progetto, servizio: m.servizio, misura: m.misura, usato: nuovo.trim() }) });
    if (!r.ok) throw new Error(r.status === 400 ? 'serve un numero maggiore o uguale a zero' : 'HTTP ' + r.status);
    avviso('Misura aggiornata: «' + m.misura + '».', false);
    aggiornaServizi();
  } catch (e) { avviso('Misura non aggiornata: ' + e.message, true); }
}

function consumiServizi(p, misure) {
  if (!misure.length) { $('servizi-misure').replaceChildren(vuoto('Nessuna misura registrata per questo progetto: i consumi si leggono nei pannelli dei servizi.')); return; }
  const etichette = p.analisi.etichette;
  $('servizi-misure').replaceChildren(el('ul', 'misure', misure.map(m => {
    const riempi = el('span', 'riempi', []);
    riempi.style.width = Math.min(100, m.parte * 100) + '%';
    const nodi = [riempi];
    if (m.previsto !== null) {
      const prev = el('span', 'previsto', []);
      prev.style.left = Math.min(100, m.parte * 100) + '%';
      prev.style.width = Math.max(0, Math.min(100, m.parteprevista * 100) - Math.min(100, m.parte * 100)) + '%';
      nodi.push(prev);
    }
    const soglia = el('span', 'soglia', []);
    soglia.style.left = Math.min(100, m.soglia / m.limite * 100) + '%';
    nodi.push(soglia);
    const barra = el('div', 'barra', nodi);
    barra.setAttribute('role', 'img');
    barra.setAttribute('aria-label', m.misura + ': ' + cifra(m.usato, m.unita) + ' di ' + cifra(m.limite, m.unita) + (m.previsto !== null ? ', previsto ' + cifra(Math.round(m.previsto * 10) / 10, m.unita) : ''));
    const aggiorna = el('button', '', ['Aggiorna']);
    aggiorna.type = 'button';
    aggiorna.addEventListener('click', () => aggiornaMisura(p, m));
    return el('li', '', [
      el('div', 'testata', [
        el('div', 'nome', [el('b', '', [m.misura]), el('span', '', [m.servizio])]),
        el('div', '', [el('span', 'percento', [Math.round(m.parte * 100) + '%']), ' ', el('span', 'pillola ' + CLASSE_VERDETTO[m.verdetto], [etichette[m.verdetto]])]),
      ]),
      barra,
      el('div', 'piede', [
        el('span', '', [cifra(m.usato) + ' di ' + cifra(m.limite, m.unita) + ' · soglia ' + cifra(m.soglia)]),
        ...(m.previsto !== null ? [el('span', '', [m.motivo + '.'])] : []),
        el('span', 'riga-misura', [
          'misurato il ' + giorno(m.misurato), m.vecchia ? el('span', 'pillola avviso', ['da aggiornare']) : '', aggiorna,
        ]),
      ]),
    ]);
  })));
}

function pianiServizi(p) {
  const verdetti = p.analisi.verdetti, etichette = p.analisi.etichette;
  $('servizi-pagamento').replaceChildren(p.piani.length ? tabella(['Servizio', 'Oggi', 'Verdetto', 'Passaggio', 'Costo'], p.piani.map(x => {
    const oggi = p.servizi.find(s => s['Servizio'].toLowerCase().startsWith(x['Servizio'].toLowerCase()));
    const v = verdetti[x['Servizio']];
    return [x['Servizio'], oggi ? oggi['Piano'] : '–',
      v ? el('span', 'pillola ' + CLASSE_VERDETTO[v], [etichette[v]]) : el('span', 'sub', ['nessuna misura']),
      x['Passaggio'], /^[\d.,]+$/.test(x['Costo']) ? x['Costo'] + ' ' + x['Valuta'] + ' al ' + x['Periodo'] : x['Costo']];
  })) : vuoto('Nessun piano a pagamento registrato.'));
  $('servizi-piani').replaceChildren(tabella(['Servizio', 'Piano', 'Prezzo', 'Verificato'], p.servizi.map(s => [
    el('details', '', [el('summary', '', [s['Servizio']]), el('p', 'sub', ['Serve a: ' + s['Serve a']]), el('p', 'sub', ['Limite: ' + s['Limite da guardare']]), el('p', 'sub', ['Fonte: ' + s['Fonte']])]),
    s['Piano'], s['Prezzo'], s['Verificato'],
  ])));
}

function renderServizi(lista) {
  if (!lista.length) { $('servizi-misure').replaceChildren(vuoto('Nessun servizio in docs/servizi.md.')); return; }
  if (!lista.some(p => p.progetto === progettoServizi)) progettoServizi = lista[0].progetto;
  $('servizi-scelta').replaceChildren(...lista.map(p => {
    const b = el('button', '', [p.progetto]);
    b.type = 'button'; b.setAttribute('aria-pressed', String(p.progetto === progettoServizi));
    b.addEventListener('click', () => { progettoServizi = p.progetto; renderServizi(lista); });
    return b;
  }));
  const p = lista.find(x => x.progetto === progettoServizi);
  const misure = misureDi(p);
  kpiServizi(p, misure);
  schemaServizi(p, misure);
  consumiServizi(p, misure);
  pianiServizi(p);
}

async function aggiornaServizi() {
  try {
    const r = await fetch('/api/servizi', { cache: 'no-store' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    renderServizi(await r.json());
    avviso('servizi letti alle ' + new Date().toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' }), false);
  } catch (e) { avviso('errore nel caricamento: ' + e.message, true); }
}

let calendarioPost = null, filtroPost = 'tutti';
const apertePost = new Set();
const CLASSE_STATO_POST = { pronto: 'positiva', pubblicato: 'positiva', 'da creare': 'avviso', 'da approvare': 'approvare', programmato: '', 'da fare': '' };
const STATI_POST = ['da creare', 'da approvare', 'pronto', 'da fare', 'programmato', 'pubblicato'];
const FORMATI_RICHIESTA = ['carosello', 'immagine', 'storia', 'video'];

const lunediDi = d => { const x = new Date(d.getFullYear(), d.getMonth(), d.getDate()); x.setDate(x.getDate() - ((x.getDay() + 6) % 7)); return x; };
const chiaveGiorno = d => d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
const giornoBreve = d => d.toLocaleDateString('it-IT', { weekday: 'short', day: 'numeric' });

function copiaTesto(testo, etichetta) {
  const b = el('button', '', [etichetta]);
  b.type = 'button';
  b.addEventListener('click', () => {
    navigator.clipboard.writeText(testo).then(() => { b.textContent = 'Copiato'; setTimeout(() => { b.textContent = etichetta; }, 1500); },
      () => avviso('Copia non riuscita: seleziona il testo e copialo a mano.', true));
  });
  return b;
}

async function cambiaStatoPost(cal, voce, stato) {
  try {
    const r = await fetch('/api/post/stato', { method: 'POST', headers: { 'X-Azione': 'conferma', 'Content-Type': 'application/json' },
      body: JSON.stringify({ progetto: cal.progetto, canale: cal.canale, id: voce.id, stato }) });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    voce.stato = stato;
    avviso('Stato di «' + voce.titolo + '»: ' + stato + '.', false);
    renderPost(listaPost);
  } catch (e) { avviso('Stato non cambiato: ' + e.message, true); }
}

function apriLightbox(url, alt) {
  $('lightbox-img').src = url; $('lightbox-img').alt = alt;
  $('lightbox').showModal();
}
$('lightbox-chiudi').addEventListener('click', () => $('lightbox').close());
$('lightbox').addEventListener('click', e => { if (e.target === $('lightbox')) $('lightbox').close(); });

const urlScarica = (cal, v, n) => '/api/post/scarica/' + cal.progetto + '/' + cal.canale + '/' + v.id + '/' + n;
const urlZip = (cal, v) => '/api/post/zip/' + cal.progetto + '/' + cal.canale + '/' + v.id;

// Il telefono: le immagini nell'ordine di pubblicazione, con frecce e contatore; la storia è 9:16.
function telefonoPost(cal, v) {
  const n = v.immagini.length;
  let corrente = 0;
  const schermo = el('div', 'schermo', []);
  const conta = el('span', 'conta', []);
  const prec = el('button', '', ['‹ Prima']), succ = el('button', '', ['Dopo ›']);
  prec.type = succ.type = 'button';
  const miniature = el('div', 'miniature', v.immagini.map((i, k) => {
    const scelta = el('button', '', [i.esiste ? (() => { const m = el('img', '', []); m.src = i.url; m.alt = ''; m.loading = 'lazy'; return m; })() : el('span', 'sub', ['non trovata'])]);
    scelta.type = 'button'; scelta.setAttribute('aria-label', 'Vai all\'immagine ' + (k + 1));
    scelta.addEventListener('click', () => mostra(k));
    const scarica = el('a', '', ['Scarica']);
    scarica.href = urlScarica(cal, v, k + 1); scarica.setAttribute('download', '');
    return el('figure', '', [scelta, el('figcaption', 'sub', [(k + 1) + (i.nota ? '' : '')]), i.esiste ? scarica : '']);
  }));
  function mostra(k) {
    corrente = (k + n) % n;
    const i = v.immagini[corrente];
    if (i.esiste) {
      const img = el('img', '', []); img.src = i.url; img.alt = i.nota || 'Immagine ' + (corrente + 1);
      schermo.replaceChildren(img);
      schermo.onclick = () => apriLightbox(i.url, img.alt);
    } else { schermo.replaceChildren(el('span', 'sub', ['Immagine non trovata'])); schermo.onclick = null; }
    conta.textContent = n > 1 ? (corrente + 1) + ' / ' + n : v.formato;
    [...miniature.children].forEach((f, j) => f.firstChild.setAttribute('aria-current', String(j === corrente)));
  }
  prec.addEventListener('click', () => mostra(corrente - 1));
  succ.addEventListener('click', () => mostra(corrente + 1));
  mostra(0);
  const comandi = el('div', 'comandi', n > 1 ? [prec, conta, succ] : [conta]);
  return el('div', '', [
    el('div', 'telefono' + (v.formato === 'storia' ? ' storia' : ''), [el('div', 'barra-ig', [cal.account || cal.canale]), schermo, comandi]),
    miniature,
  ]);
}

// Quello che Instagram mostra prima di «altro» sono i primi 125 caratteri.
function didascaliaMarcata(testo) {
  if (testo.length <= 125) return [el('p', 'didascalia', [testo])];
  return [el('p', 'didascalia', [el('mark', '', [testo.slice(0, 125)]), testo.slice(125)]),
    el('p', 'sub', ['Evidenziato: i primi 125 caratteri, quelli che si vedono su Instagram prima di «altro».'])];
}

async function inviaRichiesta(cal, campi) {
  const r = await fetch('/api/post/richiesta', { method: 'POST', headers: { 'X-Azione': 'conferma', 'Content-Type': 'application/json' },
    body: JSON.stringify({ progetto: cal.progetto, canale: cal.canale, ...campi }) });
  if (!r.ok) throw new Error('HTTP ' + r.status);
  return r.json();
}

const calendarioCorrente = () => listaPost.find(c => c.progetto + ' · ' + c.canale === calendarioPost);

$('chiedi-post').addEventListener('click', () => {
  const cal = calendarioCorrente();
  if (!cal) return;
  $('richiesta-per').textContent = cal.progetto + ' · ' + cal.canale;
  $('richiesta-form').reset();
  $('form-richiesta').showModal();
});
$('richiesta-annulla').addEventListener('click', () => $('form-richiesta').close());
$('richiesta-form').addEventListener('submit', async e => {
  e.preventDefault();
  const cal = calendarioCorrente(), f = new FormData($('richiesta-form'));
  $('richiesta-invia').disabled = true;
  try {
    await inviaRichiesta(cal, { formato: f.get('formato'), data_desiderata: f.get('data_desiderata') || null, tema: f.get('tema'), note: f.get('note') });
    $('form-richiesta').close();
    avviso('Richiesta inviata: la trovi in «Le mie richieste».', false);
    aggiornaPost(); aggiornaBadgePost();
  } catch (err) { avviso('Richiesta non inviata: ' + err.message, true); }
  $('richiesta-invia').disabled = false;
});

const CLASSE_RICHIESTA = { nuova: '', 'in lavorazione': 'avviso', 'bozza pronta': 'approvare', rifiutata: 'negativa', annullata: '' };

function renderRichieste(cal) {
  const lista = [...cal.richieste].reverse();
  if (!lista.length) { $('post-richieste').replaceChildren(vuoto('Nessuna richiesta. «Chiedi un post» ne crea una; qui vedi a che punto è.')); return; }
  $('post-richieste').replaceChildren(...lista.map(r => {
    const annulla = r.stato === 'nuova' ? el('button', '', ['Annulla']) : null;
    if (annulla) {
      annulla.type = 'button';
      annulla.addEventListener('click', async () => {
        try {
          const x = await fetch('/api/post/richiesta/annulla', { method: 'POST', headers: { 'X-Azione': 'conferma', 'Content-Type': 'application/json' }, body: JSON.stringify({ progetto: cal.progetto, canale: cal.canale, id: r.id }) });
          if (!x.ok) throw new Error('HTTP ' + x.status);
          aggiornaPost(); aggiornaBadgePost();
        } catch (err) { avviso('Richiesta non annullata: ' + err.message, true); }
      });
    }
    return el('div', 'richiesta', [
      el('div', '', [
        el('p', 'tema', [r.tema]),
        el('p', 'sub', [r.id + ' · ' + r.formato + (r.data_desiderata ? ' · per il ' + giorno(r.data_desiderata) : '') + (r.riferimento ? ' · modifica di ' + r.riferimento : '') + (r.voce_id ? ' · bozza ' + r.voce_id : '')]),
        ...(r.note ? [el('p', 'sub', ['Note: ' + r.note])] : []),
        ...(r.risposta ? [el('p', '', ['Risposta: ' + r.risposta])] : []),
      ]),
      el('div', '', [el('span', 'pillola ' + (CLASSE_RICHIESTA[r.stato] || ''), [r.stato]), ...(annulla ? [' ', annulla] : [])]),
    ]);
  }));
}

async function aggiornaBadgePost() {
  try {
    const { aperte } = await (await fetch('/api/post/aperte', { cache: 'no-store' })).json();
    $('post-badge').hidden = !aperte;
    $('post-badge').textContent = aperte;
    $('post-badge').setAttribute('aria-label', aperte + ' bozze da approvare');
  } catch (e) { /* il numero sul menu è un di più */ }
}

function modificaBozza(cal, v) {
  const testo = el('textarea', '', []);
  testo.rows = 2; testo.maxLength = 500; testo.placeholder = 'Per esempio: più corto, cambia la prima immagine';
  testo.setAttribute('aria-label', 'Modifica richiesta per ' + v.titolo);
  const invia = el('button', '', ['Chiedi la modifica']);
  invia.type = 'button';
  invia.addEventListener('click', async () => {
    if (!testo.value.trim()) return;
    invia.disabled = true;
    try {
      await inviaRichiesta(cal, { formato: FORMATI_RICHIESTA.includes(v.formato) ? v.formato : 'immagine', tema: testo.value, riferimento: v.id });
      testo.value = '';
      avviso('Richiesta di modifica inviata: la trovi in «Le mie richieste».', false);
      aggiornaPost(); aggiornaBadgePost();
    } catch (err) { avviso('Richiesta non inviata: ' + err.message, true); }
    invia.disabled = false;
  });
  return el('div', 'chiedi-modifica', [el('b', '', ['Chiedi una modifica a questa bozza']), testo, el('div', '', [invia])]);
}

function dettaglioPost(cal, v) {
  const colonna = [el('p', '', [v.descrizione])];
  const tutto = [v.didascalia, (v.hashtag || []).join(' ')].filter(Boolean).join('\n\n');
  if (v.immagini.length || v.didascalia) colonna.push(el('p', 'lista-passi', ['1 Scarica le immagini · 2 Copia il testo · 3 Programma in Meta Business Suite (o pubblica) · 4 Segna lo stato']));
  const azioni = [];
  if (v.immagini.some(i => i.esiste)) {
    const zip = el('a', 'bottone primario', [v.immagini.length > 1 ? 'Scarica tutte (ZIP)' : 'Scarica (ZIP con il testo)']);
    zip.href = urlZip(cal, v); zip.setAttribute('download', '');
    azioni.push(zip);
  }
  if (['post', 'storia'].includes(v.tipo)) {
    const apri = el('button', 'primario', ['Apri Meta Business Suite']); apri.type = 'button';
    apri.addEventListener('click', () => window.open('https://business.facebook.com/latest/composer', '_blank', 'noopener'));
    azioni.push(apri);
  }
  if (tutto) azioni.push(copiaTesto(tutto, 'Copia tutto'));
  if (v.didascalia) azioni.push(copiaTesto(v.didascalia, 'Copia didascalia'));
  if (v.hashtag && v.hashtag.length) azioni.push(copiaTesto(v.hashtag.join(' '), 'Copia hashtag'));
  const sel = el('select', '', STATI_POST.map(st => { const o = el('option', '', [st]); o.value = st; o.selected = st === v.stato; return o; }));
  sel.setAttribute('aria-label', 'Stato di ' + v.titolo);
  sel.addEventListener('change', () => cambiaStatoPost(cal, v, sel.value));
  azioni.push(el('span', 'sub', ['Stato']), sel);
  colonna.push(el('div', 'riga-azioni', azioni));
  if (v.didascalia) colonna.push(...didascaliaMarcata(v.didascalia));
  if (v.hashtag && v.hashtag.length) colonna.push(el('p', 'ht', [v.hashtag.join(' ')]));
  const righe = [];
  const voce = (k, val) => { if (val && (!Array.isArray(val) || val.length)) righe.push(el('dt', '', [k]), el('dd', '', [Array.isArray(val) ? val.join(' ') : val])); };
  voce('Come pubblicare', v.come_pubblicare);
  voce('Testo alternativo', (v.testo_alternativo || []).map((t, n) => (n + 1) + '. ' + t).join('  '));
  voce('Tempo stimato', v.tempo_stimato);
  voce('Ricorrenza', v.ricorrenza);
  voce('Fonte', v.fonte);
  if (v.tipo === 'storia' && /sondagg|domand/i.test(v.titolo + ' ' + v.descrizione)) colonna.push(el('p', 'sub', ['Da fare a mano dall\'app Instagram: sondaggi e domande nelle storie Business Suite non li ha.']));
  if (righe.length) colonna.push(el('dl', '', righe));
  if (['post', 'storia'].includes(v.tipo)) colonna.push(modificaBozza(cal, v));
  return el('div', 'dettaglio', [el('div', 'corpo-bozza' + (v.immagini.length ? '' : ' senza-immagini'), [...(v.immagini.length ? [telefonoPost(cal, v)] : []), el('div', '', colonna)])]);
}

const breve = t => { const prima = (t.split(/(?<=[.!?])\s/)[0] || t); return prima.length > 110 ? prima.slice(0, 109) + '…' : prima; };
function miniaturaPost(v) {
  const i = v.immagini.find(x => x.esiste);
  if (!i) return el('span', '', []);
  const m = el('img', 'mini', []); m.src = i.url; m.alt = ''; m.loading = 'lazy';
  return m;
}

let listaPost = [];
function renderPost(lista) {
  listaPost = lista;
  if (!lista.length) { $('post-agenda').replaceChildren(vuoto('Nessun calendario: aggiungi projects/<progetto>/post-<canale>.json.')); $('post-kpi').replaceChildren(); return; }
  const chiave = c => c.progetto + ' · ' + c.canale;
  if (!lista.some(c => chiave(c) === calendarioPost)) calendarioPost = chiave(lista[0]);
  $('post-scelta').replaceChildren(...lista.map(c => {
    const b = el('button', '', [chiave(c)]); b.type = 'button'; b.setAttribute('aria-pressed', String(chiave(c) === calendarioPost));
    b.addEventListener('click', () => { calendarioPost = chiave(c); renderPost(lista); });
    return b;
  }));
  const cal = lista.find(c => chiave(c) === calendarioPost);
  $('post-sub').textContent = (cal.account ? cal.account + ' · ' : '') + 'calendario aggiornato il ' + giorno(cal.aggiornato) + '.';
  $('post-nota').textContent = cal.nota || '';
  const oggi = new Date(); oggi.setHours(0, 0, 0, 0);
  const tra7 = new Date(oggi); tra7.setDate(tra7.getDate() + 7);
  const data = v => new Date(v.data + 'T12:00');
  const prossime = cal.voci.filter(v => data(v) >= oggi && data(v) <= tra7 && v.stato !== 'pubblicato').length;
  const conteggio = st => cal.voci.filter(v => v.stato === st).length;
  $('post-kpi').replaceChildren(...[[String(cal.voci.length), 'voci in calendario', ''], [String(prossime), 'nei prossimi 7 giorni', 'dato'],
    [String(conteggio('da creare')), 'da creare', ''], [String(conteggio('da approvare')), 'da approvare', ''], [String(conteggio('pubblicato')), 'pubblicati', '']].map(([v, e, c]) => el('li', '', [el('b', c, [v]), el('span', '', [e])])));
  const tipi = ['tutti', ...new Set(cal.voci.map(v => v.tipo))];
  $('post-filtri').replaceChildren(...tipi.map(t => {
    const b = el('button', '', [t === 'tutti' ? 'Tutti i tipi' : t[0].toUpperCase() + t.slice(1)]); b.type = 'button'; b.setAttribute('aria-pressed', String(t === filtroPost));
    b.addEventListener('click', () => { filtroPost = t; renderPost(lista); });
    return b;
  }));
  const voci = cal.voci.filter(v => filtroPost === 'tutti' || v.tipo === filtroPost).sort((a, b) => (a.data + a.ora).localeCompare(b.data + b.ora));
  const blocchi = [];
  let settimana = null;
  for (const v of voci) {
    const lun = lunediDi(data(v));
    if (chiaveGiorno(lun) !== settimana) {
      settimana = chiaveGiorno(lun);
      blocchi.push(el('h3', 'settimana', ['Settimana dal ' + lun.toLocaleDateString('it-IT', { day: 'numeric', month: 'long' })]));
    }
    const d = data(v);
    const classe = 'voce-post' + (d < oggi ? ' passata' : '') + (d >= oggi && d <= tra7 ? ' vicina' : '') + (d.getTime() === oggi.getTime() ? ' oggi' : '');
    const riga = el('details', classe, [
      el('summary', '', [
        el('span', 'giorno', [el('b', '', [giornoBreve(d)])]),
        el('span', 'ora', [v.ora === 'libera' ? 'orario libero' : v.ora]),
        miniaturaPost(v),
        el('span', 'titolo-voce', [v.titolo, el('span', '', [v.formato === 'attivita' ? v.tipo : v.formato + (v.tipo === 'storia' ? '' : ' · ' + v.tipo)]), ...(v.stato === 'da creare' ? [el('span', 'manca-riga', ['Manca: ' + breve(v.descrizione)])] : [])]),
        el('span', 'pillola ' + (CLASSE_STATO_POST[v.stato] || ''), [['post', 'storia'].includes(v.tipo) && v.stato === 'pronto' ? 'bozza pronta' : ['post', 'storia'].includes(v.tipo) && v.stato === 'da approvare' ? 'bozza da approvare' : v.stato]),
      ]),
      dettaglioPost(cal, v),
    ]);
    const id = cal.progetto + '/' + cal.canale + '/' + v.id;
    riga.open = apertePost.has(id);
    riga.addEventListener('toggle', () => { riga.open ? apertePost.add(id) : apertePost.delete(id); });
    blocchi.push(riga);
  }
  $('post-agenda').replaceChildren(el('section', '', blocchi.length ? blocchi : [vuoto('Nessuna voce per questo filtro.')]));
  renderRichieste(cal);
}

// Le due schede di Post: il calendario e le bozze della settimana.
let schedaPost = 'calendario';
function mostraSchedaPost(scheda) {
  schedaPost = scheda;
  $('post-calendario').hidden = scheda !== 'calendario';
  $('post-bozze').hidden = scheda !== 'bozze';
  for (const b of $('post-schede').children) b.setAttribute('aria-pressed', String(b.dataset.scheda === scheda));
  $('chiedi-post').hidden = scheda !== 'calendario';
  if (scheda === 'bozze') { $('post-sub').textContent = 'Post preparati dal sistema, da rileggere, copiare e pubblicare tu.'; aggiornaBozze(); }
  else if (listaPost.length) renderPost(listaPost);
}
for (const b of $('post-schede').children) b.addEventListener('click', () => mostraSchedaPost(b.dataset.scheda));

async function aggiornaBozze() {
  try {
    renderBozze(await (await fetch('/api/bozze', { cache: 'no-store' })).json());
  } catch (e) { avviso('errore nel caricamento delle bozze: ' + e.message, true); }
}

async function aggiornaPost() {
  // Chi sta scrivendo (una modifica, il menu dello stato) non perde il testo per una rilettura automatica.
  if (schedaPost === 'bozze') { aggiornaBozze(); return; }
  if (['TEXTAREA', 'INPUT', 'SELECT'].includes((document.activeElement || {}).tagName) && !$('post-vista').hidden) return;
  try {
    const r = await fetch('/api/post', { cache: 'no-store' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    renderPost(await r.json());
    avviso('post letti alle ' + new Date().toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' }), false);
  } catch (e) { avviso('errore nel caricamento: ' + e.message, true); }
}

// Ogni pagina ha il suo contenitore (id + '-vista') e la funzione che lo riempie.
const blocco = id => !$(id).hidden;  // un blocco di Consumi nascosto dai moduli non si carica
const CARICA = {
  mappa: () => { aggiorna(); window.Mappa && window.Mappa.carica(); },
  agenda: aggiorna, radar: aggiorna, post: aggiornaPost,
  consumi: () => Promise.all([blocco('consumi-servizi') && aggiornaServizi(), aggiornaPrestazioni(), aggiorna()]),
  avvii: () => { aggiornaAvvii(); aggiorna(); },
  configurazione: aggiornaConfigurazione,
};
const TITOLI = { mappa: 'Mappa', agenda: 'Agenda', radar: 'Radar', post: 'Post', consumi: 'Consumi', avvii: 'Avvii', configurazione: 'Configurazione' };
// Gli indirizzi delle pagine che non ci sono più portano alla pagina che le ha assorbite (e, per Consumi, alla sua sezione).
const ALIAS = { oggi: 'mappa', piano: 'mappa', progetti: 'mappa', bozze: 'post', servizi: 'consumi', claude: 'consumi', prestazioni: 'consumi' };
const SEZIONE = { servizi: 'consumi-servizi', claude: 'consumi-claude', prestazioni: 'consumi-locale' };
let vista = 'mappa';

// Le pagine dei moduli non scelti in setup.py non compaiono (/api/moduli); senza risposta si mostra tutto.
let MODULI = null;
function ammessa(nome) {
  const b = document.querySelector('.schede button[data-vista="' + nome + '"]');
  return !b || !b.hidden;
}
// Il modello dell'assistente viene da config.json: «locale» solo se lo è davvero (con Claude i dati vanno nel cloud).
function etichettaModello() {
  const m = MODULI && MODULI.modello;
  return !m ? 'un modello' : m.locale === null ? 'nessun modello' : m.locale ? 'il modello locale (' + m.nome + ')' : 'Claude (cloud)';
}
async function caricaModuli() {
  try { MODULI = await (await fetch('/api/moduli')).json(); } catch (e) { MODULI = null; }
  $('assistente-modello').textContent = etichettaModello() + ', risponde in sola lettura';
  const voci = [...document.querySelectorAll('.schede > *')];
  for (const b of document.querySelectorAll('[data-modulo]')) {  // voci del menu e sezioni di Consumi
    b.hidden = !!(MODULI && !b.dataset.modulo.split(' ').some(m => MODULI[m]));
  }
  voci.forEach((g, i) => {  // un gruppo senza pagine visibili sparisce
    if (!g.classList.contains('gruppo')) return;
    const sotto = [];
    for (let j = i + 1; j < voci.length && !voci[j].classList.contains('gruppo'); j++) sotto.push(voci[j]);
    g.hidden = sotto.length > 0 && sotto.every(b => b.hidden);
  });
}

function mostra(nuova) {
  const sezione = SEZIONE[nuova];
  nuova = ALIAS[nuova] || nuova;
  if (!CARICA[nuova] || !ammessa(nuova)) nuova = 'mappa';
  vista = nuova;
  for (const b of document.querySelectorAll('.schede button')) {
    if (b.dataset.vista === nuova) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
  }
  for (const nome of Object.keys(CARICA)) $(nome + '-vista').hidden = nome !== nuova;
  $('pagina').textContent = TITOLI[nuova];
  $('pagina').classList.toggle('solo-lettori', nuova === 'mappa');  // il saluto della mappa fa da titolo
  $('rail').classList.remove('aperto');
  $('menu').setAttribute('aria-expanded', 'false');
  try { history.replaceState(null, '', nuova === 'mappa' ? '#' : '#' + nuova); } catch (e) { /* hash opzionale */ }
  // scorre alla sezione quando i dati sono arrivati: prima la pagina è più corta
  Promise.resolve(CARICA[nuova]()).then(() => { if (sezione && !$(sezione).hidden) $(sezione).scrollIntoView(); });
}

for (const b of document.querySelectorAll('.schede button')) {
  b.addEventListener('click', () => mostra(b.dataset.vista));
}
for (const b of document.querySelectorAll('[data-vai]')) {
  b.addEventListener('click', () => mostra(b.dataset.vai));
}
$('menu').addEventListener('click', () => {
  const aperto = $('rail').classList.toggle('aperto');
  $('menu').setAttribute('aria-expanded', String(aperto));
});

// Su telefono Chiedi parte chiuso: la prima cosa da vedere è «Aspetta te».
if (!matchMedia('(min-width: 701px)').matches) document.querySelector('#assistente .chiedi').open = false;

// Tema: segue il sistema finché non lo scegli; la scelta resta in localStorage.
const temaAttuale = () => document.documentElement.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
function applicaTema(t) {
  document.documentElement.dataset.theme = t;
  $('tema').textContent = t === 'dark' ? 'Tema chiaro' : 'Tema scuro';
}
try { const salvato = localStorage.getItem('tema'); if (salvato === 'light' || salvato === 'dark') document.documentElement.dataset.theme = salvato; } catch (e) { /* senza storage resta il tema di sistema */ }
applicaTema(temaAttuale());
$('tema').addEventListener('click', () => {
  const nuovo = temaAttuale() === 'dark' ? 'light' : 'dark';
  applicaTema(nuovo);
  try { localStorage.setItem('tema', nuovo); } catch (e) { /* non salvato */ }
});

const hashIniziale = location.hash.slice(1);
caricaModuli().then(() => {
  mostra(hashIniziale);
  if (hashIniziale === 'bozze' && ammessa('post')) mostraSchedaPost('bozze');
  if (ammessa('post')) aggiornaBadgePost();
  setInterval(() => { CARICA[vista](); if (ammessa('post')) aggiornaBadgePost(); }, 30000);
});
