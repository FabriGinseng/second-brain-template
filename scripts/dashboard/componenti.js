// Aiutanti condivisi delle pagine secondarie. Costruiscono nodi con createElement, mai da stringhe HTML.
(function () {
  function nodo(tag, classe, figli) {
    const n = document.createElement(tag);
    if (classe) n.className = classe;
    (figli || []).forEach(f => n.appendChild(typeof f === 'string' ? document.createTextNode(f) : f));
    return n;
  }

  // Pillola di stato: tono ok | attenzione | errore | neutro (il testo dice sempre lo stato, il colore non basta)
  function stato(testo, tono) {
    return nodo('span', 'stato ' + (['ok', 'attenzione', 'errore'].includes(tono) ? tono : 'neutro'), [testo]);
  }

  // Le prime `max` righe in vista, il resto dietro «Mostra tutto (N)»
  function mostraTutto(voci, max, disegna, etichetta) {
    const f = document.createDocumentFragment();
    voci.slice(0, max).forEach(v => f.appendChild(disegna(v)));
    if (voci.length > max) {
      // il <details> sta dentro un <li>, con una sua <ul>: un <ul> ha solo <li> come figli
      const ul = nodo('ul', '', voci.slice(max).map(disegna));
      f.appendChild(nodo('li', 'resto-li', [nodo('details', 'resto', [nodo('summary', '', [(etichetta || 'Mostra tutto') + ' (' + voci.length + ')']), ul])]));
    }
    return f;
  }

  function cornice(frase) {
    return nodo('p', 'cornice', [frase]);
  }

  function errore(frase, riprova) {
    const b = nodo('button', 'link', ['Riprova']);
    b.type = 'button';
    b.addEventListener('click', riprova);
    return nodo('p', 'cornice errore-blocco', [frase + ' ', b]);
  }

  // Gruppo di pulsanti a scelta singola: aria-pressed, frecce sinistra/destra, Home e End, Tab entra solo sulla scheda attiva
  function schede(contenitore, voci, attiva, cambia, etichetta) {
    contenitore.classList.add('scelta');
    contenitore.setAttribute('role', 'group');
    if (etichetta) contenitore.setAttribute('aria-label', etichetta);
    const bottoni = voci.map(v => {
      const b = nodo('button', '', [v.etichetta]);
      b.type = 'button';
      b.dataset.id = v.id;
      b.setAttribute('aria-pressed', String(v.id === attiva));
      b.tabIndex = v.id === attiva ? 0 : -1;
      b.addEventListener('click', () => cambia(v.id));
      b.addEventListener('keydown', e => {
        const i = bottoni.indexOf(b);
        const j = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: bottoni.length - 1 }[e.key];
        if (j === undefined) return;
        e.preventDefault();
        const prossimo = bottoni[(j + bottoni.length) % bottoni.length];
        prossimo.focus();
        cambia(prossimo.dataset.id);
      });
      return b;
    });
    contenitore.replaceChildren(...bottoni);
  }

  // Toglie il primo #tag e gli spazi attorno; il tag torna a parte, senza il cancelletto
  function senzaTag(testo) {
    // stessa regola del server (TAG in server.py): il tag è all'inizio o dopo uno spazio e comincia con una lettera
    const m = /(?:^|\s)#([A-Za-z][\w-]*)/.exec(testo);
    if (!m) return { testo: testo.trim(), tag: null };
    const fine = m.index + m[0].length;
    return { testo: (testo.slice(0, fine - m[1].length - 1) + ' ' + testo.slice(fine)).replace(/\s+/g, ' ').trim(), tag: m[1].toLowerCase() };
  }

  // Le prime frasi intere che stanno in `max` caratteri (almeno una, mai tagliata a metà), senza backtick; il resto a parte
  function prima(testo, max) {
    const frasi = testo.replace(/`/g, '').trim().split(/(?<=[.!?])\s+/);
    let n = 1, len = frasi[0].length;
    while (n < frasi.length && len + 1 + frasi[n].length <= max) len += 1 + frasi[n++].length;
    return { testo: frasi.slice(0, n).join(' '), resto: frasi.slice(n).join(' ') };
  }

  // Le voci (già ordinate) delle prime `n` settimane, e le altre; `chiave` dà la settimana di una voce
  function limitaSettimane(voci, chiave, n) {
    const viste = [], altre = [], chiavi = new Set();
    for (const v of voci) {
      chiavi.add(chiave(v));
      (chiavi.size <= n ? viste : altre).push(v);
    }
    return { viste, altre };
  }

  // Riga grigia sotto il titolo della pagina
  function dato(idPagina, testo) {
    const id = idPagina + '-dato';
    let p = document.getElementById(id);
    if (!p) {
      p = nodo('p', 'dato');
      p.id = id;
      const t = document.getElementById(idPagina + '-vista');
      const titolo = t && t.querySelector('.titolo');
      if (titolo) titolo.insertAdjacentElement('afterend', p); else if (t) t.prepend(p);
    }
    p.textContent = testo;
  }

  window.Comp = { stato, mostraTutto, cornice, errore, schede, senzaTag, dato, prima, limitaSettimane };
})();
