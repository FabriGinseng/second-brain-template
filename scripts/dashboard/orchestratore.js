// Scheda Orchestratore: modelli aperti, frontiera, tipi di task e una casella per lanciare una richiesta con scelta correggibile.
// Parla solo con le rotte /api/orchestratore*; il server lancia lo smistatore e decide il livello. Il DOM si costruisce con
// createElement e textContent: nessun HTML da stringhe.
(function () {
  const STATO = { dati: null, proposta: null, montato: false, configSporca: false };
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
      disegnaConfig();
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
    const invalida = () => { STATO.proposta = null; proposta.replaceChildren(); };
    testo.addEventListener('input', invalida);
    repo.addEventListener('change', invalida);

    function mostraProposta(p) {
      STATO.proposta = p;
      const tipi = [['', '(nessun tipo)']].concat(Object.keys(valori().tipi).map(t => [t, t]));
      const tipoSel = scelta(tipi, p.tipo || ''), livSel = scelta(livelli().map(l => [l, l]), p.livello);
      tipoSel.addEventListener('change', () => { if (tipoSel.value) livSel.value = valori().tipi[tipoSel.value].livello; });
      const macos = d.sistema === 'darwin';
      const avvia = bottone('Avvia', async () => {
        // Si rimanda la decisione che l'utente vede (o la sua correzione), mai una nuova classificazione: potrebbe dare un'altra risposta.
        const corpo = { richiesta: testo.value, repo: repo.value, livello: livSel.value };
        if (tipoSel.value) corpo.tipo = tipoSel.value;
        if ((tipoSel.value || '') !== (p.tipo || '') || livSel.value !== p.livello) corpo.prima = p.tipo || undefined;
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
      } catch (e) { avviso(e.message, true); }
    }
    STATO.usaDaStorico = (voce) => { testo.value = voce.richiesta; const r = d.repo.find(x => x.split('/').pop() === voce.repo); if (r) repo.value = r; return classifica(voce.tipo_task || null); };
    return nodo('div', '', [testo, nodo('div', 'riga-azioni', [repo, bottone('Classifica', () => classifica(null), true)]), proposta]);
  }

  const ESITI = { verde: 'riuscita', da_rivedere: 'da rivedere', rosso: 'fallita', manomesso: 'fermata (manomissione)', errore: 'errore',
    avviato: 'avviata in Claude Code', 'in sessione': 'in questa sessione', 'in corso': 'in corso', 'non lanciata': 'solo classificata', a_fabrizio: 'tornata a te' };

  // Dove è andata la richiesta: harness (ciò che esegue), agente (chi lavora dentro), modello, esito. Chi non è stata lanciata non ha nulla di tutto questo.
  function esecuzione(v) {
    if (!v.harness) return nodo('div', 'sub', [ESITI[v.esito] || v.esito]);
    const pezzi = [['Harness', v.harness], ['Agente', v.agente], ['Modello', v.modello], ['Esito', ESITI[v.esito] || v.esito]];
    if (typeof v.costo === 'number') pezzi.push(['Costo', v.costo.toFixed(4) + ' $']);
    const riga = nodo('div', 'orch-esecuzione', pezzi.map(([k, x]) => nodo('span', 'orch-chip', [nodo('i', '', [k + ' ']), String(x)])));
    if (v.tentativi && v.tentativi.length > 1) {  // salita di livello: ogni passo con il suo modello
      riga.appendChild(nodo('div', 'sub', ['Tentativi: ' + v.tentativi.map(t => t.livello + ' (' + t.modello + ') ' + (ESITI[t.esito] || t.esito)).join(' → ')]));
    }
    return riga;
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
        nodo('span', 'sub', [dettaglio.join(' · ')]), ' ', bottone('Usa questo tipo', () => STATO.usaDaStorico(v)), esecuzione(v)]));
    });
    return lista;
  }

  function sezione(titolo, contenuto) { return nodo('section', '', [nodo('h2', '', [titolo]), contenuto]); }

  // La casella della richiesta e la sua proposta si montano una volta sola: né il refresh periodico né un salvataggio le cancellano.
  function monta() {
    STATO.nodoErrori = nodo('div');
    STATO.nodoStorico = nodo('div');
    STATO.nodoConfig = nodo('div');
    STATO.nodoConfig.addEventListener('input', () => { STATO.configSporca = true; });
    STATO.nodoConfig.addEventListener('change', () => { STATO.configSporca = true; });
    $('orch-contenuto').replaceChildren(STATO.nodoErrori, sezione('Richiesta', richiesta()), sezione('Cronologia', STATO.nodoStorico), STATO.nodoConfig);
    STATO.montato = true;
  }

  function disegnaStorico() { STATO.nodoStorico.replaceChildren(storico()); }

  function disegnaConfig() {
    const v = valori();
    const errori = STATO.dati.config.errori || [];
    STATO.nodoErrori.replaceChildren(errori.length ? nodo('p', 'sub errore', ['Impostazioni da correggere: ' + errori.join('; ')]) : nodo('span'));
    STATO.nodoConfig.replaceChildren(
      sezione('Tipi di task', righeTipi()),
      sezione('Modelli aperti', modelliAperti()),
      sezione('Frontiera', frontiera()),
      nodo('p', 'sub', ['Classificatore: ' + v.classificatore.backend + ' (' + (v.classificatore.backend === 'ollama' ? v.classificatore.ollama : v.classificatore.modello) + '). ' +
        'Repo riservati: ' + (v.riservati.length ? v.riservati.length : 'nessuno') + ' (si cambiano dal terminale: `smistatore config riservato`).']));
    STATO.configSporca = false;
    $('orch-dato').textContent = 'Un modello piccolo classifica la richiesta, la tabella dei tipi sceglie il livello.';
  }

  async function leggi(percorso) {
    try { return await (await fetch(percorso || '/api/orchestratore', { cache: 'no-store' })).json(); } catch (e) { return { attivo: false }; }
  }

  // La voce di menu compare solo se config.json ha la chiave «smistatore». Rotta leggera: non lancia lo smistatore, quindi
  // l'avvio della dashboard non lo aspetta.
  async function inizializza() {
    const d = await leggi('/api/orchestratore/attivo');
    const voce = document.querySelector('.schede button[data-vista="orchestratore"]');
    if (voce) voce.hidden = !d.attivo;
    return !!d.attivo;
  }

  function vuota(messaggio) {
    STATO.montato = false;
    $('orch-dato').textContent = messaggio;
    $('orch-contenuto').replaceChildren();
  }

  async function carica() {
    const d = await leggi();
    if (!d.attivo) return vuota('Lo smistatore non è collegato: serve la chiave «smistatore» in config.json.');
    if (d.errore) return vuota('Lo smistatore non risponde (' + (CODICI[d.errore] || d.errore) + ').');
    STATO.dati = d;
    if (!STATO.montato) monta();
    if (!STATO.configSporca) disegnaConfig();  // modifiche non salvate nella tabella non si cancellano
    disegnaStorico();
  }

  window.Orchestratore = { carica, inizializza };
})();
