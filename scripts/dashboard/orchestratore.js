// Scheda Orchestratore: modelli aperti, frontiera, tipi di task e una casella per lanciare una richiesta con scelta correggibile.
// Parla solo con le rotte /api/orchestratore*; il server lancia lo smistatore e decide il livello. Il DOM si costruisce con
// createElement e textContent: nessun HTML da stringhe.
(function () {
  const STATO = { dati: null, proposta: null, forzato: null };
  const $ = id => document.getElementById(id);

  function nodo(tag, classe, figli) {
    const n = document.createElement(tag);
    if (classe) n.className = classe;
    (figli || []).forEach(f => n.appendChild(typeof f === 'string' ? document.createTextNode(f) : f));
    return n;
  }
  function bottone(testo, quandoClicca, primario) {
    const b = nodo('button', primario ? 'primario' : '', [testo]);
    b.type = 'button';
    b.addEventListener('click', async () => {
      b.disabled = true;
      try { await quandoClicca(); } finally { b.disabled = false; }
    });
    return b;
  }
  function campo(valore, segnaposto, lunghezza) {
    const i = nodo('input');
    i.type = 'text';
    i.value = valore || '';
    if (segnaposto) i.placeholder = segnaposto;
    i.maxLength = lunghezza || 200;
    return i;
  }
  function scelta(opzioni, valore) {
    const s = nodo('select');
    opzioni.forEach(([v, testo]) => {
      const o = nodo('option', '', [testo]);
      o.value = v;
      s.appendChild(o);
    });
    s.value = valore == null ? '' : valore;
    return s;
  }
  function avviso(testo, errore) {
    const e = $('orch-esito');
    e.textContent = testo || '';
    e.className = 'sub' + (errore ? ' errore' : '');
  }

  const SPIEGAZIONI = { 400: 'richiesta non valida', 404: 'repo non trovato', 403: 'richiesta rifiutata', 501: 'il lancio funziona solo su macOS' };
  const CODICI = { assente: 'lo smistatore non risponde', timeout: 'lo smistatore ci mette troppo', uscita: 'risposta dello smistatore non valida',
    ripetuto: 'già partita: attendi qualche secondo', apertura: 'il terminale non si è aperto', errore: 'operazione non riuscita' };

  async function chiama(percorso, corpo) {
    const r = await fetch(percorso, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Azione': 'conferma' }, body: JSON.stringify(corpo) });
    let dati = null;
    try { dati = await r.json(); } catch (e) { /* senza corpo */ }
    if (!r.ok) throw new Error(r.status === 409 && dati && dati.errore ? (CODICI[dati.errore] || dati.errore) : (SPIEGAZIONI[r.status] || 'HTTP ' + r.status));
    return dati;
  }
  async function cambia(corpo) {
    try {
      const config = await chiama('/api/orchestratore/config', corpo);
      STATO.dati.config = config;
      disegna();
      avviso('Salvato.', false);
    } catch (e) { avviso(e.message, true); }
  }

  const valori = () => STATO.dati.config.valori;
  const livelli = () => STATO.dati.config.livelli;

  function modelliAperti() {
    const v = valori();
    const corpo = nodo('div');
    const elenco = nodo('ul', 'orch-elenco');
    v.modelli_aperti.forEach(m => {
      elenco.appendChild(nodo('li', '', [nodo('code', '', [m]), ' ', bottone('Togli', () => cambia({ azione: 'modello-aperto', verbo: 'togli', id: m }))]));
    });
    const nuovo = campo('', 'openrouter/azienda/modello');
    corpo.append(elenco, nodo('div', 'riga-azioni', [nuovo, bottone('Aggiungi', () => cambia({ azione: 'modello-aperto', verbo: 'aggiungi', id: nuovo.value.trim() }))]));
    return corpo;
  }

  function frontiera() {
    const f = campo(valori().frontiera, 'opus');
    return nodo('div', 'riga-azioni', [f, bottone('Salva', () => cambia({ azione: 'frontiera', modello: f.value.trim() })),
      nodo('span', 'sub', ['Il modello per i lavori di livello alto: parte in Claude Code, nel terminale.'])]);
  }

  function righeTipi() {
    const v = valori();
    const livelliOpz = livelli().map(l => [l, l]);
    const modelliOpz = [['nessuno', 'quello del livello']].concat(v.modelli_aperti.map(m => [m, m]));
    const tabella = nodo('table', 'orch-tipi');
    tabella.appendChild(nodo('thead', '', [nodo('tr', '', ['Tipo', 'Descrizione', 'Livello', 'Modello', ''].map(t => nodo('th', '', [t])))]));
    const corpo = nodo('tbody');
    Object.keys(v.tipi).forEach(nome => {
      const t = v.tipi[nome];
      const d = campo(t.descrizione, '', 200), l = scelta(livelliOpz, t.livello), m = scelta(modelliOpz, t.modello || 'nessuno');
      corpo.appendChild(nodo('tr', '', [nodo('td', '', [nodo('b', '', [nome])]), nodo('td', '', [d]), nodo('td', '', [l]), nodo('td', '', [m]),
        nodo('td', 'riga-azioni', [
          bottone('Salva', () => cambia({ azione: 'tipo', nome, descrizione: d.value, livello: l.value, modello: m.value })),
          bottone('Rimuovi', () => cambia({ azione: 'tipo-rimuovi', nome }))])]));
    });
    const nome = campo('', 'nuovo-tipo', 60), d = campo('', 'a cosa serve', 200), l = scelta(livelliOpz, livelli()[0]), m = scelta(modelliOpz, 'nessuno');
    corpo.appendChild(nodo('tr', '', [nodo('td', '', [nome]), nodo('td', '', [d]), nodo('td', '', [l]), nodo('td', '', [m]),
      nodo('td', '', [bottone('Aggiungi', () => cambia({ azione: 'tipo', nome: nome.value.trim(), descrizione: d.value, livello: l.value, modello: m.value }))])]));
    tabella.appendChild(corpo);
    return tabella;
  }

  function richiesta() {
    const d = STATO.dati;
    const testo = nodo('textarea');
    testo.rows = 4;
    testo.maxLength = 4000;
    testo.placeholder = 'Che cosa vuoi fare?';
    const repo = scelta(d.repo.map(r => [r, r]), d.repo[0]);
    const proposta = nodo('div', 'orch-proposta');
    const invalida = () => { STATO.proposta = null; STATO.forzato = null; proposta.replaceChildren(); };
    testo.addEventListener('input', invalida);
    repo.addEventListener('change', invalida);

    function mostraProposta(p) {
      STATO.proposta = p;
      const tipi = [['', '(nessun tipo)']].concat(Object.keys(valori().tipi).map(t => [t, t]));
      const tipoSel = scelta(tipi, p.tipo || ''), livSel = scelta(livelli().map(l => [l, l]), p.livello);
      tipoSel.addEventListener('change', () => { if (tipoSel.value) livSel.value = valori().tipi[tipoSel.value].livello; });
      const macos = d.sistema === 'darwin';
      const avvia = bottone('Avvia', async () => {
        const corpo = { richiesta: testo.value, repo: repo.value };
        if (tipoSel.value && tipoSel.value !== (p.tipo || '')) { corpo.tipo = tipoSel.value; corpo.prima = p.tipo || undefined; }
        else if (livSel.value !== p.livello) { corpo.livello = livSel.value; corpo.prima = p.tipo || undefined; }
        else if (STATO.forzato) corpo.tipo = STATO.forzato;
        try {
          const r = await chiama('/api/orchestratore/avvia', corpo);
          avviso('Partita (' + r.livello + ', ' + r.modello + ', ' + (r.esecutore === 'paseo' ? 'su Paseo' : 'nel terminale') + ').', false);
          await carica();
        } catch (e) { avviso(e.message, true); }
      }, true);
      avvia.disabled = !macos;
      proposta.replaceChildren(
        nodo('p', 'sub', [p.riservato ? 'Repo riservato: solo il modello di frontiera.' : (p.motivo || 'Scelta del classificatore.')]),
        nodo('div', 'riga-azioni', [nodo('label', '', ['Tipo ', tipoSel]), nodo('label', '', ['Livello ', livSel]),
          nodo('span', 'sub', ['modello: ' + p.modello]), avvia]),
        macos ? nodo('span') : nodo('p', 'sub', ['Il lancio dalla dashboard funziona solo su macOS.']));
    }

    async function classifica(forzato) {
      avviso('', false);
      const corpo = { richiesta: testo.value, repo: repo.value };
      if (forzato) corpo.tipo = forzato;
      try {
        mostraProposta(await chiama('/api/orchestratore/classifica', corpo));
        STATO.forzato = forzato || null;
      } catch (e) { avviso(e.message, true); }
    }
    STATO.usaDaStorico = (voce) => { testo.value = voce.richiesta; const r = d.repo.find(x => x.split('/').pop() === voce.repo); if (r) repo.value = r; return classifica(voce.tipo_task || null); };
    return nodo('div', '', [testo, nodo('div', 'riga-azioni', [repo, bottone('Classifica', () => classifica(null), true)]), proposta]);
  }

  function storico() {
    const voci = STATO.dati.storico;
    if (!voci.length) return nodo('p', 'sub', ['Ancora nessuna richiesta.']);
    const lista = nodo('ul', 'orch-storico');
    voci.forEach(v => {
      const dettaglio = [v.repo, (v.tipo_task || 'senza tipo') + ' → ' + v.livello];
      if (v.proposto) dettaglio.push('proposto: ' + v.proposto);
      else if (v.corretto_in) dettaglio.push('corretto in ' + v.corretto_in);
      lista.appendChild(nodo('li', '', [nodo('span', 'dato', [new Date(v.quando).toLocaleString('it-IT')]), ' ', nodo('b', '', [v.richiesta]), ' ',
        nodo('span', 'sub', [dettaglio.join(' · ')]), ' ', bottone('Usa questo tipo', () => STATO.usaDaStorico(v))]));
    });
    return lista;
  }

  function sezione(titolo, contenuto) { return nodo('section', '', [nodo('h2', '', [titolo]), contenuto]); }

  function disegna() {
    const v = valori(), d = STATO.dati;
    const errori = d.config.errori || [];
    $('orch-contenuto').replaceChildren(
      errori.length ? nodo('p', 'sub errore', ['Impostazioni da correggere: ' + errori.join('; ')]) : nodo('span'),
      sezione('Richiesta', richiesta()),
      sezione('Storico', storico()),
      sezione('Tipi di task', righeTipi()),
      sezione('Modelli aperti', modelliAperti()),
      sezione('Frontiera', frontiera()),
      nodo('p', 'sub', ['Classificatore: ' + v.classificatore.backend + ' (' + (v.classificatore.backend === 'ollama' ? v.classificatore.ollama : v.classificatore.modello) + '). ' +
        'Repo riservati: ' + (v.riservati.length ? v.riservati.length : 'nessuno') + ' (si cambiano dal terminale: `smistatore config riservato`).']));
    $('orch-dato').textContent = 'Un modello piccolo classifica la richiesta, la tabella dei tipi sceglie il livello.';
  }

  async function leggi() {
    try { return await (await fetch('/api/orchestratore', { cache: 'no-store' })).json(); } catch (e) { return { attivo: false }; }
  }

  // La voce di menu compare solo se config.json ha la chiave «smistatore».
  async function inizializza() {
    const d = await leggi();
    const voce = document.querySelector('.schede button[data-vista="orchestratore"]');
    if (voce) voce.hidden = !d.attivo;
    return !!d.attivo;
  }

  async function carica() {
    const d = await leggi();
    if (!d.attivo) { $('orch-dato').textContent = 'Lo smistatore non è collegato: serve la chiave «smistatore» in config.json.'; $('orch-contenuto').replaceChildren(); return; }
    if (d.errore) { $('orch-dato').textContent = 'Lo smistatore non risponde (' + (CODICI[d.errore] || d.errore) + ').'; $('orch-contenuto').replaceChildren(); return; }
    STATO.dati = d;
    disegna();
  }

  window.Orchestratore = { carica, inizializza };
})();
