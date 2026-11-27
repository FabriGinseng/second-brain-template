"""Controlli statici su scripts/dashboard/index.html (nessun browser): la pagina non deve chiamare funzioni che non esistono.

Il redesign aveva tolto aggiornaVista ma setTimeout(aggiornaVista, 700) era rimasto: dopo ogni spunta riuscita la pagina
andava in ReferenceError, rimetteva la casella com'era e scriveva "spunta non salvata" anche se il file era salvato.
"""
import json
import re
import unittest
from pathlib import Path

D = Path(__file__).resolve().parent / "dashboard"


class _Pagina:
    """index.html più dashboard.js e dashboard.css: i controlli guardano tutta la pagina, non solo lo scheletro."""
    @staticmethod
    def read_text(encoding="utf-8"):
        return "".join((D / n).read_text(encoding=encoding) for n in ("index.html", "dashboard.js", "dashboard.css"))


HTML = _Pagina
TIMER = re.compile(r"set(?:Timeout|Interval)\(\s*([A-Za-z_$][\w$]*)\s*[,)]")


def funzioni_mancanti(html):
    """Nomi passati come funzione a setTimeout/setInterval e mai definiti (function, const, let, var)."""
    return sorted({n for n in TIMER.findall(html) if not re.search(rf"(?:function\s+|(?:const|let|var)\s+){re.escape(n)}\b", html)})


class HtmlDashboard(unittest.TestCase):
    def test_la_mappa_non_usa_innerhtml_use_o_random_e_ha_il_livello_dei_satelliti(self):
        js = (D / "mappa.js").read_text(encoding="utf-8")
        for vietato in ("innerHTML", "<use", "'use'", '"use"', "Math.random"):
            self.assertNotIn(vietato, js)
        self.assertIn("mappa-satelliti", js)
        self.assertNotIn("x1: p.x, y1: p.y", js)  # i fili della zona di aggancio partono dal bordo del disco, non dal centro: il disco resta cliccabile
        self.assertIn("prefers-reduced-motion", (D / "dashboard.css").read_text(encoding="utf-8"))
        self.assertIn("dati.nome", js)  # il saluto dice «Buonasera, <nome>.»
        self.assertIn("PAROLE_FUNZIONE", js)  # il saluto non finisce su una preposizione
        self.assertIn("#mappa-pannello { display: contents; }", (D / "dashboard.css").read_text(encoding="utf-8"))  # su telefono la prossima azione sta sotto il saluto

    def test_il_clic_su_un_task_porta_al_task_e_il_clic_altrove_lo_toglie(self):
        js = (D / "mappa.js").read_text(encoding="utf-8")
        css = (D / "dashboard.css").read_text(encoding="utf-8")
        self.assertEqual(js.count("function scegliTask"), 1)
        self.assertGreaterEqual(js.count("scegliTask("), 4)           # satelliti (clic e tastiera), lista, definizione
        self.assertNotRegex(js, r"selezione = v\.t; pannello\(\)")     # nessun percorso salta lo scorrimento
        self.assertIn("scrollTop", js)
        self.assertRegex(css, r"\.task\.scelto \{[^}]*border-left: 3px")
        self.assertIn("selezione = null; pannello();", js)             # clic fuori dal task evidenziato

    def test_la_mappa_si_zooma_e_si_sposta_senza_librerie(self):
        js = (D / "mappa.js").read_text(encoding="utf-8")
        css = (D / "dashboard.css").read_text(encoding="utf-8")
        for pezzo in ("K_MIN", "K_MAX", "'wheel'", "passive: false", "pointerdown", "pointermove", "mappa-mondo", "ctrlKey"):
            self.assertIn(pezzo, js)
        for nome in ("Ingrandisci", "Riduci", "Adatta alla vista"):
            self.assertIn(nome, js)
        self.assertRegex(css, r"#mappa-svg \{[^}]*touch-action: none")
        self.assertIn("var(--k", css)                                   # il testo resta della stessa grandezza a schermo
        self.assertNotRegex(js, r"https?://(?!www\.w3\.org/2000/svg)")   # nessuna richiesta esterna (il namespace SVG non lo è)
        self.assertNotRegex(js, r"\bimport\b|require\(")

    def test_azioni_sui_nodi_piu_per_i_vuoti_avvia_e_nuovo_task(self):
        js = (D / "mappa.js").read_text(encoding="utf-8")
        css = (D / "dashboard.css").read_text(encoding="utf-8")
        for pezzo in ("mappa-nuovo", "/api/mappa/nuovo", "maxlength", "Aggiungi un task", "Avvia in Claude", "haCartella"):
            self.assertIn(pezzo, js)
        # the «+» is on every node that can take a task (user decision 2026-11-12), not only on the ones with nothing open
        self.assertNotIn("aperti(n) === 0", js)
        self.assertIn("if (puoAggiungere(n)) G.append(piu(n, pos.get(n.nome)));", js)
        self.assertIn("...(puoAggiungere(n) ? [piu(n, p)] : [])", js)
        self.assertIn("'aria-label': 'Aggiungi un task a ' + n.nome", js)
        self.assertIn("#mappa-nuovo", css)
        self.assertIn("textContent", js)                                # il testo dell'utente entra solo come testo
        self.assertNotIn("innerHTML", js)

    def test_archivia_progetto_sempre_dietro_una_conferma(self):
        js = (D / "mappa.js").read_text(encoding="utf-8")
        css = (D / "dashboard.css").read_text(encoding="utf-8")
        corpo = js[js.index("function archivia(n)"):js.index("function decidiHarness")]
        for atteso in ("inProva()", "/api/mappa/archivia", "showModal()", "annulla.focus()", "'Archivia'", "'Annulla'",
                       "'Archiviare ' + n.nome + '? La riga sparisce da INDEX e la cartella va in projects/_archivio/' + n.nome + '. I task del piano restano.'"):
            self.assertIn(atteso, corpo, atteso)
        # offered only where the server could accept it, and never from the panel without the dialog
        self.assertIn("NOME_PROGETTO.test(n.nome) ? h('div', 'riga-azioni azioni-progetto', [", js)
        self.assertIn("bottone('Archivia progetto', '', () => archivia(n))", js)
        self.assertEqual(js.count("/api/mappa/archivia"), 1)
        self.assertIn("archivio: ", js[js.index("const ERRORI_409"):])
        self.assertIn("#mappa-archivia", css)
        # the dialog gives the focus back to a button the archive removed: it goes to the panel title instead of the page
        self.assertIn("fuocoAlPannello()", corpo)
        aiuto = js[js.index("function fuocoAlPannello"):js.index("\n  }", js.index("function fuocoAlPannello"))]
        for atteso in ("'tabindex', '-1'", ".focus()"):
            self.assertIn(atteso, aiuto, atteso)

    def test_imposta_cartella_di_un_progetto_senza_repo(self):
        js = (D / "mappa.js").read_text(encoding="utf-8")
        css = (D / "dashboard.css").read_text(encoding="utf-8")
        corpo = js[js.index("function impostaCartella(n)"):js.index("function decidiHarness")]
        for atteso in ("inProva()", "/api/mappa/cartella", "maxlength: '400'", "r.stato === 400", "CAMPO_NON_VALIDO[", "showModal()"):
            self.assertIn(atteso, corpo, atteso)
        self.assertNotIn("innerHTML", corpo)
        # offered only on a project of the index whose STATE names no folder (the server's boolean), never on work projects
        self.assertIn("n.senzaRepo ? bottone('Imposta cartella', '', () => impostaCartella(n)) : null", js)
        self.assertIn("'ha-repo': ", js[js.index("const ERRORI_409"):])
        self.assertIn("#mappa-cartella", css)

    def test_le_animazioni_solo_per_un_cambio_voluto(self):
        # motion only for a change the user caused: one WAAPI helper, ease-out, transform/opacity, nothing under reduced motion;
        # no CSS keyframe on the satellites or the band, which would replay on every redraw (the first paint included)
        js = (D / "mappa.js").read_text(encoding="utf-8")
        css = (D / "dashboard.css").read_text(encoding="utf-8")
        corpo = lambda nome: js[js.index(nome):js.index("\n  }", js.index(nome))]
        aiuto = corpo("function anima(")
        self.assertIn("MOTO_RIDOTTO.matches", aiuto)
        self.assertIn("cubic-bezier(0.23, 1, 0.32, 1)", js)
        uscita = corpo("function esce(")
        for atteso in ("cloneNode(true)", "removeAttribute('tabindex')", "'aria-hidden'", "MOTO_RIDOTTO.matches", ".remove()"):
            self.assertIn(atteso, uscita, atteso)
        self.assertRegex(css, r"\.uscita \{[^}]*pointer-events: none")
        for vecchio in ("@keyframes entra", "@keyframes appare", ".sat-dentro { animation"):
            self.assertNotIn(vecchio, css, vecchio)
        # satellites fan in (staggered) and out, the band reveals and folds, the panel fades, the thread draws in
        sat = corpo("function disegnaSatelliti")
        self.assertIn("anima(dentro", sat)
        self.assertIn("esce(", sat)
        self.assertIn("if (rivelato) anima(G", js)
        self.assertIn("esce(", js[js.index("const premi = ()"):js.index("P.addEventListener('click', premi)")])
        self.assertIn("strokeDashoffset", corpo("function filo"))
        self.assertIn("anima($('mappa-dettaglio')", corpo("function pannello"))
        self.assertIn("G.addEventListener('pointerenter', () => apri(n.nome, false, true));", js)
        self.assertIn("anima(G.querySelector('.alone')", js)   # the ring of the node a click fixes
        # opening a node from keyboard focus never animates: only the pointer passes `anima`
        self.assertIn("G.addEventListener('focus', () => { if (G.matches(':focus-visible')) portaInVista(n.nome); apri(n.nome); });", js)
        self.assertRegex(css, r"prefers-reduced-motion[^}]*\.obiettivo\.rivelato")

    def test_il_nodo_scelto_si_inquadra_e_si_torna_indietro(self):
        js = (D / "mappa.js").read_text(encoding="utf-8")
        corpo = lambda nome: js[js.index(nome):js.index("\n  }", js.index(nome))]
        self.assertIn("inquadra(nome)", corpo("function scegli(nome)"))
        for nome in ("function deseleziona", "function scegliObiettivo"):
            self.assertIn("torna()", corpo(nome), nome)
        # the flight: requestAnimationFrame, a jump under reduced motion, never on the narrow list, inside the zoom limits
        self.assertIn("requestAnimationFrame(passo)", corpo("function vola"))
        self.assertIn("MOTO_RIDOTTO.matches", corpo("function vola"))
        self.assertIn("prefers-reduced-motion: reduce", js)
        inq = corpo("function inquadra")
        for atteso in ("svg.clientWidth < 2", "K_MIN", "K_MAX", "vola(limita("):
            self.assertIn(atteso, inq, atteso)
        # every user gesture stops a flight where it is
        for nome in ("function zoomA", "function sposta", "function adatta", "function portaInVista"):
            self.assertIn("cancelAnimationFrame(volo)", js[js.index(nome):js.index(nome) + 160], nome)   # the first line of the body
        # on the narrow list the map is hidden: the view goes back as it was, no flight over a zero-width svg
        tor = corpo("function torna")
        self.assertIn("clientWidth < 2", tor)
        self.assertIn("vista = ritorno", tor)

    def test_nuovo_progetto_e_priorita_dalla_mappa(self):
        js = (D / "mappa.js").read_text(encoding="utf-8")
        for pezzo in ("mappa-progetto", "/api/mappa/progetto", "/api/mappa/priorita", "Nuovo progetto", "Priorità del progetto", "Non per i progetti di lavoro", "n.tipo === 'progetto' && n.haCartella"):
            self.assertIn(pezzo, js, pezzo)

    def test_harness_dalla_mappa(self):
        js = (D / "mappa.js").read_text(encoding="utf-8")
        for pezzo in ("/api/mappa/harness", "Adegua all\\'harness", "Non adeguare questo progetto", "Harness da decidere", "/ai-native-harness:audit",
                      "harness-da-decidere", "n.tipo === 'progetto' && n.haCartella && n.harness", "decisione: "):
            self.assertIn(pezzo, js, pezzo)
        # il rifiuto si sceglie per esteso, e con un repo la scelta è obbligatoria anche nel dialogo del nuovo progetto
        self.assertIn("conHarness && repo.value.trim() && !harness.value", js)
        self.assertIn("harness-da-decidere", (D / "dashboard.css").read_text(encoding="utf-8"))

    def test_i_numeri_dei_nodi_si_spiegano_e_le_bozze_sono_in_sola_lettura(self):
        js = (D / "mappa.js").read_text(encoding="utf-8")
        css = (D / "dashboard.css").read_text(encoding="utf-8")
        for pezzo in ("pronti", "nessun task nel piano con questo tag", "Il numero sul nodo = task pronti da avviare",
                      "bozze da pubblicare", "nessuna bozza da pubblicare", "Apri in Post", "t.bozza",
                      "n.nome === 'Social' || !t.bozza"):   # sui nodi dei progetti le bozze sono satelliti, non entrano nel numero
            self.assertIn(pezzo, js)
        self.assertIn("nota-mappa", css)                                # la legenda del numero resta visibile anche sotto i 760px

    def test_la_mappa_disegna_quattro_stati_e_il_filo(self):
        js = (D / "mappa.js").read_text(encoding="utf-8")
        css = (D / "dashboard.css").read_text(encoding="utf-8")
        for atteso in ("st-pronto", "st-in_attesa", "mappa-dipendenze", "statoVisivo", "Pronti da avviare", "In attesa"):
            self.assertIn(atteso, js)
        self.assertRegex(css, r"\.arco\.st-in_attesa[^}]*stroke-dasharray")  # in attesa si legge dal tratteggio, non solo dal colore (il tratteggio dell'harness esiste già e non conta)

    def test_la_mappa_disegna_gli_obiettivi(self):
        js = (D / "mappa.js").read_text(encoding="utf-8")
        css = (D / "dashboard.css").read_text(encoding="utf-8")
        for atteso in ("mappa-obiettivi", "'obiettivi', 'Obiettivi'", "obiettivo:", "obiettivoPer", "non definito", "Nessun passo nel piano con questo obiettivo"):
            self.assertIn(atteso, js)
        self.assertRegex(css, r"\.obiettivo\b")
        # td.obiettivo (Progetti table) already matches the line above: the goal node itself must exist, dashed when undefined
        self.assertRegex(css, r"\.obiettivo\.non-definito [^}]*stroke-dasharray")
        # a selected goal hidden by the filter must not leave the map dimmed: the dimming is tied to the goal being drawn
        fn = js[js.index("function evidenziaObiettivo"):js.index("// satelliti del nodo aperto")]
        self.assertIn("obiettiviVisibili().includes(obiettivoPer(fissato))", fn)
        self.assertNotIn("const o = obiettivoPer(fissato)", fn)
        # launched from a goal panel, a task still starts in its own project folder: the row is built with the task's node,
        # and that row's «Avvia» is conferma(n, t), i.e. conferma(nodoPer(t.nodo), t)
        self.assertIn("rigaTask(nodoPer(t.nodo), t, true)", js)
        self.assertIn("() => conferma(n, t))", js[js.index("function rigaTask"):js.index("function dettaglioNodo")])

    def test_la_mappa_mostra_i_repo(self):
        js = (D / "mappa.js").read_text(encoding="utf-8")
        for atteso in ("stesso repo di un task in corso", "repo sconosciuto", "repo non indicato", "scegli_repo", "name: 'repo'", "Repo: "):
            self.assertIn(atteso, js)

    def test_avvia_spiega_i_repo_gemelli(self):
        # twin short names: without a valid repo: the server refuses (409 cartella), so the dialog says why and offers no choice
        js = (D / "mappa.js").read_text(encoding="utf-8")
        corpo = js[js.index("function conferma"):js.index("// ---- struttura fissa")]
        self.assertIn("Due repo di questo progetto hanno lo stesso nome (", corpo)
        self.assertIn("rinomina una delle cartelle o togli una riga Repo dallo STATE.", corpo)
        self.assertIn("n.repoDoppi", corpo)
        self.assertIn("doppi.length", corpo[corpo.index("avvia.disabled ="):])

    def test_le_etichette_tagliate_hanno_il_nome_intero(self):
        # a cut repo name keeps the whole one in the tooltip and for screen readers; the SVG label gets a <title> child
        js = (D / "mappa.js").read_text(encoding="utf-8")
        aiuto = js[js.index("function tagliata"):js.index("\n  }\n", js.index("function tagliata"))]
        for atteso in ("title", "'aria-hidden'", "solo-lettori"):
            self.assertIn(atteso, aiuto, atteso)
        self.assertIn("tagliata(r, 24)", js[js.index("function segniRepo"):js.index("// ---- dati di prova")])
        self.assertIn("tagliata(r, 24)", js[js.index("function filtroPerRepo"):js.index("function dettaglioNodo")])
        self.assertIn("s('title', {}, ['repo: ' + repo.join(', ')])", js)

    def test_il_pannello_del_nodo_tiene_dentro_i_testi_per_i_lettori(self):
        # regression: the .solo-lettori spans are position: absolute; if the scrolling panel is not their containing block
        # they escape its clip and a long project (e.g. second-brain) stretched the page with empty space below
        css = (D / "dashboard.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"\.solo-lettori \{[^}]*position: absolute")
        self.assertRegex(css, r"#mappa-dettaglio \{[^}]*position: relative[^}]*overflow-y: auto")

    def test_il_task_porta_al_suo_obiettivo(self):
        # a goal folded behind a pill is reachable from its task rows: a native button, so Enter and Space work
        js = (D / "mappa.js").read_text(encoding="utf-8")
        css = (D / "dashboard.css").read_text(encoding="utf-8")
        aiuto = js[js.index("function segnoObiettivo"):js.index("\n  }\n", js.index("function segnoObiettivo"))]
        for atteso in ("bottone(", "'obiettivo: '", "scegliObiettivo(o.slug)", "obiettiviSvg.get(o.slug)", ".focus()", "isConnected", "fuocoAlPannello()"):
            self.assertIn(atteso, aiuto, atteso)
        for riga in ("function rigaTask", "function rigaLista"):
            corpo = js[js.index(riga):js.index("\n  }\n", js.index(riga))]
            self.assertIn("conNodo ? null : segnoObiettivo(t)", corpo, riga)
        self.assertIn(".chip-obiettivo", css)
        # under «Progetti»/«Argomenti» the band is not drawn: the chip switches the filter first, through the one filter helper
        self.assertIn("impostaFiltro('tutto')", aiuto)
        self.assertIn("impostaFiltro(k)", js[js.index("function struttura"):])
        # a long title and its marks: the marks wrap under it as a block, never the title letter by letter
        self.assertRegex(css, r"\.task-testo \{[^}]*flex-wrap: wrap")

    def test_la_riga_della_scadenza_sta_nel_riquadro(self):
        # «scade … · a rischio» too long for a narrow box: measured before the band is laid out, the state word goes on a line of its own
        js = (D / "mappa.js").read_text(encoding="utf-8")
        corpo = js[js.index("function disegna()"):js.index("function evidenziaObiettivo")]
        self.assertIn("getComputedTextLength()", corpo)
        self.assertIn("lunghi.has(o)", corpo)
        self.assertLess(corpo.index("getComputedTextLength()"), corpo.index("for (const o of layout("))   # before the nodes are placed

    def test_la_mappa_mostra_scadenze_rischio_e_fascia_comprimibile(self):
        js = (D / "mappa.js").read_text(encoding="utf-8")
        css = (D / "dashboard.css").read_text(encoding="utf-8")
        for atteso in ("'scade '", "'a rischio'", "'scaduto'", "'entro il '", "'senza stima'", " completati'", " altri'",
                       "Le date ipotizzano che i task indipendenti procedano in parallelo.", "aria-expanded"):
            self.assertIn(atteso, js, atteso)
        # one folded goal reads «+1 altro» / «+1 completato», in the label too; more keep the plural
        pastiglia = js[js.index("if (pastiglia) {"):js.index("const premi = ()")]
        for atteso in ("piegati === 1", "(uno ? ' altro' : ' altri')", "(uno ? ' completato' : ' completati')",
                       "(uno ? ' obiettivo' : ' obiettivi')", "(uno ? ': obiettivo' : ': obiettivi')"):
            self.assertIn(atteso, pastiglia, atteso)
        # a goal without a deadline shows no date and no «NaN»: every deadline read is guarded, the day counts are checked integers
        self.assertEqual(js.count("giornoBreve(o.scadenza)"), 1)
        self.assertIn("o.scadenza ? 'scade ' + giornoBreve(o.scadenza) : ''", js)
        self.assertIn("Number.isInteger(o.giorniNecessari)", js)
        # the computed date and «senza stima» are one helper, shared by the panel row and the list row
        for riga in ("function rigaTask", "function rigaLista"):
            corpo = js[js.index(riga):js.index("\n  }\n", js.index(riga))]
            self.assertIn("segniScadenza(t)", corpo, riga)
        # the fixed goal is never folded away, and the pills are not dimmed nor a pan start
        self.assertIn("os.filter(o => o !== scelto)", js[js.index("function fascia"):js.index("function disegna")])
        self.assertIn(".pastiglia", js[js.index("svg.addEventListener('pointerdown'"):js.index("svg.addEventListener('pointermove'")])
        self.assertRegex(css, r"\.obiettivo\.a-rischio [^}]*stroke")
        self.assertRegex(css, r"prefers-reduced-motion[^}]*\.obiettivo\.rivelato")

    def test_la_fascia_degli_obiettivi_si_ripiega(self):
        # fascia() runs alone in node, with stubs for the band state: what is drawn, in which order, and what each pill hides
        import shutil
        import subprocess
        import tempfile
        if not shutil.which("node"):
            self.skipTest("node non c'è")
        js = (D / "mappa.js").read_text(encoding="utf-8")
        corpo = js[js.index("  function fascia"):js.index("  // ---- disegno ----")]
        prova = ("let fissato = null, banda = { altri: false, completati: false }, rivela = null, V = [];"
                 "const obiettiviVisibili = () => V, obiettivoPer = k => V.find(o => 'obiettivo:' + o.slug === k);"
                 "eval(require('fs').readFileSync(process.argv[1], 'utf8'));"
                 "const g = (slug, tot, fatti) => ({ slug, task: Array(tot).fill(0), conteggi: { fatti } });"
                 "const vedi = c => fascia(c).map(v => v.o ? v.o.slug : '+' + v.pastiglia + ':' + v.k).join(' ');"
                 "const out = {};"
                 "V = [...Array(12)].map((_, i) => g('a' + i, 2, 1)).concat([g('vuoto', 0, 0), g('f1', 2, 2), g('f2', 1, 1)]);"
                 "out.piegato = vedi(3);"
                 "fissato = 'obiettivo:a11'; out.sceltoAperto = vedi(3);"
                 "fissato = 'obiettivo:f2'; out.sceltoFinito = vedi(3); fissato = null;"
                 "banda.completati = true; out.completatiAperti = vedi(3); banda.completati = false;"
                 "banda.altri = true; out.altriAperti = vedi(3); banda.altri = false;"
                 "V = [g('f1', 2, 2), g('f2', 1, 1)]; out.tuttiFatti = vedi(3);"
                 "V = [g('vuoto', 0, 0)]; out.soloVuoto = vedi(3);"
                 "console.log(JSON.stringify(out));")
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "fascia.js"
            f.write_text(corpo, encoding="utf-8")
            out = json.loads(subprocess.run(["node", "-e", prova, str(f)], capture_output=True, text=True, timeout=30, check=True).stdout)
        self.assertEqual(out, {
            # 3 columns, two rows: 6 slots, one kept for «+k completati», one for «+k altri»; a goal with no task is still open
            "piegato": "a0 a1 a2 a3 +altri:9 +completati:2",
            "sceltoAperto": "a0 a1 a2 a3 a11 +altri:8 +completati:2",   # the fixed goal is never folded
            "sceltoFinito": "a0 a1 a2 a3 +altri:9 f2 +completati:1",
            "completatiAperti": "a0 a1 a2 a3 +altri:9 f1 f2 +completati:0",   # each pill sits after its own group
            "altriAperti": "a0 a1 a2 a3 a4 a5 a6 a7 a8 a9 a10 a11 vuoto +altri:0 +completati:2",
            "tuttiFatti": "+completati:2",
            "soloVuoto": "vuoto",
        })

    def test_il_grafo_dell_obiettivo_va_a_righe(self):
        # the goal graph's pure layout runs alone in node, on realistic plan shapes: rows, ghosts, cycles, done, wraps
        import shutil
        import subprocess
        import tempfile
        if not shutil.which("node"):
            self.skipTest("node non c'è")
        js = (D / "mappa.js").read_text(encoding="utf-8")
        corpo = js[js.index("  // ---- grafo dell'obiettivo: impaginazione pura"):js.index("  // ---- zoom e spostamento")]
        prova = r"""
const GRAFO = eval(require('fs').readFileSync(process.argv[1], 'utf8') + ';GRAFO');   // the functions leak out of eval, a const does not
// t(id, goal, dopo, stato): a task as the server sends it, with its node
const t = (id, obiettivo, dopo, stato) => ({ id, testo: id, data: null, stato: stato || 'da_fare', obiettivo, dopo: dopo || [], nodo: 'n' });
const goal = (slug, tutti) => ({ slug, task: tutti.filter(x => x.obiettivo === slug) });
const righe = (o, tutti, fatti) => { const n = nodiGrafo(o, tutti, fatti), s = stratiGrafo(n);
  const r = []; for (const x of n) (r[s.strato.get(x.chiave)] = r[s.strato.get(x.chiave)] || []).push(x.t.id + (x.fantasma ? '?' + x.fantasma : ''));
  return r.map(z => z.join(',')); };
// every segment of every arrow stays clear of every box but its own two ends
const libere = (g) => g.archi.every(a => {
  const num = a.d.match(/-?[\d.]+/g).map(Number), pt = [[num[0], num[1]]];
  let i = 2; for (const c of a.d.slice(1).match(/[VH]/g)) { const [x, y] = pt[pt.length - 1]; pt.push(c === 'V' ? [x, num[i++]] : [num[i++], y]); }
  return [...g.posti.values()].filter(b => b.chiave !== a.da && b.chiave !== a.a).every(b => pt.slice(1).every((q, j) => {
    const p = pt[j], x0 = Math.min(p[0], q[0]), x1 = Math.max(p[0], q[0]), y0 = Math.min(p[1], q[1]), y1 = Math.max(p[1], q[1]);
    return x1 <= b.x || x0 >= b.x + b.w || y1 <= b.y || y0 >= b.y + b.h; })); });
const out = {};
// a diamond, and t8 feeds a task of another goal
const hn = ['t1', 't2:t1', 't3:t1', 't4:t3', 't5:t1', 't6:t2,t3,t4,t5', 't7:t6', 't8:t7', 't9:t8'].map(s => { const [id, d] = s.split(':'); return t(id, 'hn', d ? d.split(',') : []); });
const tutti1 = [...hn, t('h15', 'secondo', ['t8']), t('h9', 'secondo', [])];
out.diamante = righe(goal('hn', tutti1), tutti1, false);
const g1 = impaginaGrafo(nodiGrafo(goal('hn', tutti1), tutti1, false), 480, 56);
out.diamanteStretto = { perRiga: g1.perRiga, lineeRiga1: g1.strati[1].linee, radici: g1.archi.filter(a => a.radice).length, archi: g1.archi.length, libere: libere(g1) };
out.diamanteLargo = impaginaGrafo(nodiGrafo(goal('hn', tutti1), tutti1, false), 1400, 56).strati.map(s => s.linee).join('');
// nine rows, w-uso (same goal) feeds s9 five rows below
const st = ['w-base', 'w-uso:w-base', 's1', 's2:s1', 's3:s1,s2', 's4:s3', 's5:s3,s4', 's6:s5', 's7:s6', 's8:s7', 's9:s6,w-uso', 's10:s8,s9'].map(s => { const [id, d] = s.split(':'); return t(id, 'st', d ? d.split(',') : []); });
out.nove = righe(goal('st', st), st, false);
const g2 = impaginaGrafo(nodiGrafo(goal('st', st), st, false), 700, 56);
out.noveLibere = libere(g2);
out.noveAlto = g2.alto > 9 * 100;
// no arrow runs in the left gutter, where the bracket of a wrapped row sits
out.fuoriDalMargine = [g1, impaginaGrafo(nodiGrafo(goal('st', st), st, false), 480, 56)].every(g => g.archi.every(a => {
  const num = a.d.match(/-?[\d.]+/g).map(Number); let x = num[0], i = 2, ok = x >= GRAFO.lato;
  for (const c of a.d.slice(1).match(/[VH]/g)) { if (c === 'H') { x = num[i]; ok = ok && x >= GRAFO.lato; } i++; }
  return ok; }));
// ghosts: a blocker in another goal sits just above its waiter, one in no goal too; a dependent sits below; not expanded further
const gh = [t('a', 'g'), t('b', 'g', ['a']), t('c', 'g', ['b']), t('d', 'g', ['c', 'x', 'y']), t('x', 'altro', ['w']), t('w', 'altro'), t('y', null), t('z', 'altro', ['b'])];
out.fantasmi = righe(goal('g', gh), gh, false);
// a cycle and what waits on it go to a last row; the rest is laid out as usual; an id held twice is no edge
const cy = [t('p', 'c', ['q']), t('q', 'c', ['p']), t('r', 'c', ['p']), t('s', 'c'), t('u', 'c', ['dd']), t('dd', 'c'), t('dd', 'altro')];
cy[6].testo = 'dd2';
const sc = stratiGrafo(nodiGrafo(goal('c', cy), cy, false));
out.ciclo = righe(goal('c', cy), cy, false);
out.avanzo = [...sc.avanzo].sort().join(',');
// done hidden by default; shown, they are laid out too (their links included)
const ca = [t('c1', 'ca', [], 'fatto'), t('c2', 'ca', ['c1'], 'fatto'), t('c6', 'ca', ['c2']), t('c7', 'ca', ['c6']), t('c8', 'ca', ['c6']), t('c9', 'ca', ['c7', 'c8']), t('e', 'altro', ['c9'], 'fatto')];
out.senzaFatti = righe(goal('ca', ca), ca, false);
out.conFatti = righe(goal('ca', ca), ca, true);
// barycenter: the row below follows its blockers left to right, not plan order
const bc = [t('l', 'b'), t('r', 'b'), t('sotto-r', 'b', ['r']), t('sotto-l', 'b', ['l'])];
const g3 = impaginaGrafo(nodiGrafo(goal('b', bc), bc, false), 1000, 56);
out.baricentro = g3.strati[1].chiavi.join(',');
// a first row wrapped onto two lines: the goal links to its first line only, the bracket ties the second
out.radiciPrimaLinea = impaginaGrafo(nodiGrafo(goal('b', bc), bc, false), 300, 56).archi.filter(a => a.radice).map(a => a.a).join(',');
// no shown task: just the root
const g4 = impaginaGrafo([], 800, 56);
out.vuoto = [g4.strati.length, g4.archi.length, g4.alto];
console.log(JSON.stringify(out));
"""
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "grafo.js"
            f.write_text(corpo, encoding="utf-8")
            r = subprocess.run(["node", "-e", prova, str(f)], capture_output=True, text=True, timeout=30)
            self.assertEqual(r.returncode, 0, r.stderr)
            out = json.loads(r.stdout)
        self.assertEqual(out["diamante"], ["t1", "t2,t3,t5", "t4", "t6", "t7", "t8", "t9,h15?altro obiettivo"])
        # 480 px: two boxes per line, so the parallel row wraps onto two lines; one root link (t1), twelve dependency arrows
        self.assertTrue(out["fuoriDalMargine"])
        self.assertEqual(out["diamanteStretto"], {"perRiga": 2, "lineeRiga1": 2, "radici": 1, "archi": 13, "libere": True})
        self.assertEqual(out["diamanteLargo"], "1111111")
        self.assertEqual(out["nove"], ["w-base,s1", "w-uso,s2", "s3", "s4", "s5", "s6", "s7,s9", "s8", "s10"])
        self.assertTrue(out["noveLibere"])   # w-uso -> s9 skips four rows through a free lane
        self.assertTrue(out["noveAlto"])
        self.assertEqual(out["fantasmi"], ["a", "b", "c,x?altro obiettivo,y?senza obiettivo,z?altro obiettivo", "d"])
        self.assertEqual(out["ciclo"], ["s,u,dd", "p,q,r"])
        self.assertEqual(out["avanzo"], "|p,|q,|r")
        self.assertEqual(out["senzaFatti"], ["c6", "c7,c8", "c9"])
        self.assertEqual(out["conFatti"], ["c1", "c2", "c6", "c7,c8", "c9", "e?altro obiettivo"])
        self.assertEqual(out["baricentro"], "|sotto-l,|sotto-r")
        self.assertEqual(out["radiciPrimaLinea"], "|l")
        self.assertEqual(out["vuoto"], [0, 0, 114])

    def test_la_vista_del_grafo_si_apre_e_si_chiude(self):
        js = (D / "mappa.js").read_text(encoding="utf-8")
        css = (D / "dashboard.css").read_text(encoding="utf-8")
        corpo = lambda nome: js[js.index(nome):js.index("\n  }\n", js.index(nome))]
        # the band box opens the graph; the panel chip only selects the goal
        self.assertIn("G.addEventListener('click', () => apriGrafo(o.slug));", js)
        self.assertNotIn("apriGrafo", corpo("function segnoObiettivo"))
        # Esc leaves the graph before it deselects; a pick in the graph is not undone by the click that bubbles to the page
        self.assertLess(js.index("if (grafo && $('mappa-grafo').clientWidth) chiudiGrafo();"), js.index("else if (fissato || aperto) deseleziona();"))
        self.assertIn(".grafo-azioni", js[js.index("document.addEventListener('click'"):])
        self.assertEqual(corpo("function disegnaGrafo").count("e.stopPropagation()"), 2)   # the root and every box
        # every box is a focusable button with a name; the arrows have their own marker (the map's lives in a hidden svg)
        grafo = corpo("function disegnaGrafo")
        for atteso in ("tabindex: 0, role: 'button', 'aria-label': etichetta", "'aspetta: '", "'sblocca: '", "'grafo-freccia'", "anima(box", "strokeDashoffset", "if (!conMoto) return;"):
            self.assertIn(atteso, grafo, atteso)
        self.assertIn("aggiornaGrafo()", corpo("function pannello"))
        # opening the graph leaves the map's view alone (a framed node stays framed underneath for «Mappa»)
        self.assertIn("if (!grafo) torna();", corpo("function scegliObiettivo"))
        self.assertLess(corpo("function apriGrafo").index("grafo = true"), corpo("function apriGrafo").index("scegliObiettivo(slug)"))
        # a goal gone while the focus is in its graph: the focus goes to the panel title, never to the page
        agg = corpo("function aggiornaGrafo")
        self.assertLess(agg.index("box.contains(document.activeElement)"), agg.index("box.replaceChildren()"))
        self.assertIn("if (dentro) fuocoAlPannello();", agg)
        # the map underneath keeps its size (visibility, not display); no graph on phones, where the list groups by row
        self.assertRegex(css, r"\.mappa-box\.con-grafo #mappa-svg[^{]*\{ visibility: hidden; \}")
        self.assertRegex(css, r"@media \(max-width: 760px\) \{\n  #mappa-svg, \.legenda, \.mappa-zoom, \.mappa-grafo \{ display: none; \}")
        self.assertIn("'Passo ' + (i + 1)", corpo("function passiLista"))
        self.assertIn("passiLista(o)", corpo("function lista()"))
        regole = css[css.index(".mappa-grafo {"):css.index(".grafo-nota")]
        self.assertNotRegex(regole, r"#[0-9a-fA-F]{3,6}\b|rgb\(")   # theme variables only, so the dark theme works

    def test_in_ritardo_e_bloccato_resta_rosso(self):
        # a late task that waits is never the next action: the spec wants it flagged, and the grey of «in attesa» must not hide the red
        js = (D / "mappa.js").read_text(encoding="utf-8")
        css = (D / "dashboard.css").read_text(encoding="utf-8")
        self.assertIn("in ritardo e bloccato", js[js.index("function motivi"):js.index("function gruppi")])
        self.assertRegex(css, r"\.sat\.st-in_attesa\.ritardo text \{ fill: var\(--late\)")
        self.assertRegex(css, r"\.task\.st-in_attesa \.task-testo\.ritardo \{ color: var\(--late\)")

    def test_la_mappa_conosce_i_codici_409_e_la_tastiera_dei_satelliti(self):
        js = (D / "mappa.js").read_text(encoding="utf-8")
        for codice in ("doppia", "cartella", "ripetuto", "apertura"):
            self.assertIn(codice + ":", js)
        self.assertIn("Due voci uguali in piano.md: correggi in Obsidian.", js)
        self.assertIn("'ArrowRight'", js)
        self.assertIn("'ArrowLeft'", js)
        self.assertIn("Riavvia", js)
        self.assertIn(".mappa-lista:focus-within", (D / "dashboard.css").read_text(encoding="utf-8"))
        self.assertEqual((D / "dashboard.js").read_text(encoding="utf-8").count("fetch('/api/oggi'"), 1)  # la mappa riusa la lettura di aggiorna()

    def test_componenti_js_servito_e_senza_innerhtml(self):
        self.assertIn('"/componenti.js": ("componenti.js"', (D / "server.py").read_text(encoding="utf-8"))
        js = (D / "componenti.js").read_text(encoding="utf-8")
        self.assertNotIn("innerHTML", js)
        for nome in ("stato", "mostraTutto", "cornice", "errore", "schede", "senzaTag", "dato"):
            self.assertIn(nome + "(", js)

    def test_index_carica_componenti_prima_di_dashboard(self):
        html = (D / "index.html").read_text(encoding="utf-8")
        self.assertLess(html.index('src="/componenti.js"'), html.index('src="/dashboard.js"'))

    def test_i_timer_chiamano_solo_funzioni_definite(self):
        self.assertEqual(funzioni_mancanti(HTML.read_text(encoding="utf-8")), [])

    def test_ogni_voce_senza_casella_sta_in_una_riga_aspetta(self):
        # `.voce` è una griglia con una colonna di 20px per la casella: senza `riga-aspetta` sul <li> il titolo
        # delle novità finiva in quella colonna e andava a capo una parola per riga.
        html = HTML.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"el\('li', '',\s*\[el\('span', 'voce senza-casella'", html))

    def test_la_navigazione_non_promette_ruoli_aria_che_non_implementa(self):
        # role=tablist/tab promettono frecce, tabpanel e aria-controls: non ci sono. Una navigazione di pagine usa aria-current.
        html = HTML.read_text(encoding="utf-8")
        for vietato in ('role="tablist"', 'role="tab"', "aria-selected"):
            self.assertNotIn(vietato, html, vietato)
        self.assertIn('aria-current="page"', html)
        self.assertIn("setAttribute('aria-current', 'page')", html)

    def test_avvii_non_mostra_stati_inglesi_di_launchctl_ne_ferma_su_ogni_riga(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("STATI_JOB", html)                      # running / not running tradotti
        self.assertNotIn("'in corso' : 'ferma'", html)        # «ferma» ripetuto su ogni riga non dice nulla
        self.assertIn("Servizi e vault", html)                # ogni sezione dice cosa contiene
        self.assertNotIn("<h2>Job e vault</h2>", html)

    def test_avvii_niente_sezione_log_separata(self):
        indice = (D / "index.html").read_text(encoding="utf-8")
        avvii = indice[indice.index('id="avvii-vista"'):indice.index('id="configurazione-vista"')]
        self.assertNotIn('id="esecuzioni"', avvii)
        self.assertNotIn("Avvii a mano e log", indice)
        self.assertIn('id="avvii-dato"', avvii)
        self.assertEqual(avvii.count('class="primario"'), 0)
        js = (D / "dashboard.js").read_text(encoding="utf-8")
        r = js[js.index("function rigaAvvio"):js.index("async function aggiornaAvvii")]
        self.assertIn("Comp.dato('avvii'", r)
        self.assertIn("aria-expanded", r)
        self.assertIn("Avvia ora", r)
        self.assertIn("Nessun log", r)
        self.assertNotIn("innerHTML", r)

    def test_avvii_saltato_non_e_un_allarme(self):
        js = (D / "dashboard.js").read_text(encoding="utf-8")
        m = re.search(r"TONO_AVVIO = \{([^}]*)\}", js)
        self.assertIsNotNone(m)
        toni = dict(re.findall(r"'?([\w-]+)'?: '(\w+)'", m.group(1)))
        self.assertEqual(toni["saltato"], "neutro")
        self.assertEqual(toni["fallito"], "errore")
        self.assertEqual(toni["mancato"], "attenzione")
        self.assertEqual(toni["ok"], "ok")

    def test_oggi_risponde_a_cosa_aspetta_me(self):
        # «Aspetta te» e il prossimo passo stanno nella mappa; Agenda tiene il resto di Oggi.
        html = HTML.read_text(encoding="utf-8")
        mappa = html[html.index('id="mappa-vista"'):html.index('id="agenda-vista"')]
        self.assertIn('id="aspetta-te"', mappa)
        for contenitore in ("mappa-saluto", "mappa-area", "mappa-pannello", "mappa-dettaglio", "prossimi-giorni"):
            self.assertIn(f'id="{contenitore}"', mappa, contenitore)
        agenda = html[html.index('id="agenda-vista"'):html.index('id="radar-vista"')]
        self.assertNotIn('id="aspetta-te"', agenda)
        self.assertIn("'/api/attesa'", html)
        for tolto in ("kpi-job", "kpi-scartate", "kpi-vault"):  # numeri che non portano a nessuna azione
            self.assertNotIn(tolto, html, tolto)
        self.assertIn("matchMedia", html)

    def _agenda(self):
        html = (D / "index.html").read_text(encoding="utf-8")
        return html[html.index('id="agenda-vista"'):html.index('id="radar-vista"')]

    def test_agenda_ha_un_solo_primario(self):
        self.assertEqual(self._agenda().count('class="primario"'), 1)
        self.assertEqual(self._agenda().count("<form"), 1)  # una sola barra: la domanda e «Aggiungi: ...» stanno nella stessa casella

    def test_agenda_senza_contatori_ne_novita(self):
        agenda = self._agenda()
        for tolto in ("kpi-", "aspetta-novita", 'data-vai="avvii"', "<details class=\"chiedi\""):
            self.assertNotIn(tolto, agenda, tolto)
        self.assertNotIn("kpi-radar", (D / "dashboard.js").read_text(encoding="utf-8"))

    def test_agenda_toglie_i_tag_dal_testo(self):
        js = (D / "dashboard.js").read_text(encoding="utf-8")
        self.assertIn("Comp.senzaTag(", js)
        self.assertIn("Comp.mostraTutto(", js)
        self.assertIn("avviaVoce", (D / "mappa.js").read_text(encoding="utf-8"))
        self.assertIn("-webkit-line-clamp: 2", (D / "dashboard.css").read_text(encoding="utf-8"))

    def test_agenda_avvia_solo_con_cartella_e_nodo_dalla_mappa(self):
        js = (D / "dashboard.js").read_text(encoding="utf-8")
        riga = js[js.index("function rigaAgenda"):js.index("const elencoAgenda")]
        self.assertIn("nodoDi(tag)", riga)
        self.assertIn("haCartella", riga)
        self.assertIn("piano && tag && window.Mappa", riga)   # scadenze show their tag but are not in piano.md: no «Avvia»
        self.assertIn("v.fonte === 'scadenze' ? Comp.senzaTag(v.testo).tag", riga)   # the tag comes from the raw testo, vista has none
        mappa = (D / "mappa.js").read_text(encoding="utf-8")
        voce = mappa[mappa.index("async function avviaVoce"):mappa.index("window.Mappa =")]
        self.assertNotIn("cartella: null", voce)
        self.assertIn("conferma(n,", voce)

    def test_mostra_tutto_non_mette_details_dentro_la_ul(self):
        js = (D / "componenti.js").read_text(encoding="utf-8")
        corpo = js[js.index("function mostraTutto"):js.index("function cornice")]
        self.assertIn("nodo('li', 'resto-li'", corpo)
        self.assertNotIn("f.appendChild(resto)", corpo)
        self.assertIn(".elenco-agenda li { font-size: inherit", (D / "dashboard.css").read_text(encoding="utf-8"))

    def test_schede_con_nome_e_tasti_home_end(self):
        comp = (D / "componenti.js").read_text(encoding="utf-8")
        for parte in ("etichetta)", "aria-label", "Home:", "End:"):
            self.assertIn(parte, comp[comp.index("function schede"):comp.index("function senzaTag")])
        js = (D / "dashboard.js").read_text(encoding="utf-8")
        self.assertIn("'Sezioni dei consumi'", js)
        self.assertIn("'Sezioni della configurazione'", js)

    def test_senza_tag_come_il_server(self):
        import shutil
        import subprocess
        if not shutil.which("node"):
            self.skipTest("node non c'è")
        prova = ("global.window={};global.document={};eval(require('fs').readFileSync(process.argv[1],'utf8'));"
                 "console.log(JSON.stringify(['#x Testo','Fix bug #12 della dashboard','PR#3','C#-tool','url#frag','Foo #Beta bar'].map(window.Comp.senzaTag)))")
        out = subprocess.run(["node", "-e", prova, str(D / "componenti.js")], capture_output=True, text=True, timeout=30, check=True).stdout
        self.assertEqual(json.loads(out), [
            {"testo": "Testo", "tag": "x"}, {"testo": "Fix bug #12 della dashboard", "tag": None},
            {"testo": "PR#3", "tag": None}, {"testo": "C#-tool", "tag": None},
            {"testo": "url#frag", "tag": None}, {"testo": "Foo bar", "tag": "beta"}])

    def _comp(self, espressione):
        import shutil
        import subprocess
        if not shutil.which("node"):
            self.skipTest("node non c'è")
        prova = ("global.window={};global.document={};eval(require('fs').readFileSync(process.argv[1],'utf8'));"
                 "console.log(JSON.stringify(" + espressione + "))")
        return json.loads(subprocess.run(["node", "-e", prova, str(D / "componenti.js")], capture_output=True, text=True, timeout=30, check=True).stdout)

    def test_prima_frase_senza_backtick_e_senza_taglio_a_meta(self):
        lungo = "Uso fermo ai dati vecchi: `~/.claude/usage-live.json` lo aggiorna solo la barra. Le sessioni desktop no. " + "Altro testo. " * 20
        r = self._comp("window.Comp.prima(%s, 110)" % json.dumps(lungo))
        self.assertEqual(r["testo"], "Uso fermo ai dati vecchi: ~/.claude/usage-live.json lo aggiorna solo la barra. Le sessioni desktop no.")
        self.assertNotIn("`", r["testo"] + r["resto"])
        self.assertTrue(r["resto"].startswith("Altro testo."))
        self.assertEqual(self._comp("window.Comp.prima('Breve.', 140)"), {"testo": "Breve.", "resto": ""})
        # una sola frase lunga resta intera: mai un «…» a meta frase
        r = self._comp("window.Comp.prima(%s, 20)" % json.dumps("Una frase molto lunga senza punti intermedi"))
        self.assertEqual(r, {"testo": "Una frase molto lunga senza punti intermedi", "resto": ""})

    def test_limita_settimane_tiene_le_prime_n(self):
        voci = [{"s": s} for s in ("a", "a", "b", "c", "c", "d")]
        r = self._comp("window.Comp.limitaSettimane(%s, v => v.s, 2)" % json.dumps(voci))
        self.assertEqual([v["s"] for v in r["viste"]], ["a", "a", "b"])
        self.assertEqual([v["s"] for v in r["altre"]], ["c", "c", "d"])
        self.assertEqual(self._comp("window.Comp.limitaSettimane([], v => v, 3)"), {"viste": [], "altre": []})

    def _radar(self):
        html = (D / "index.html").read_text(encoding="utf-8")
        return html[html.index('id="radar-vista"'):html.index('id="consumi-vista"')]

    def test_radar_ha_un_solo_primario(self):
        self.assertEqual(self._radar().count('class="primario"'), 1)
        self.assertIn('id="radar-dato"', self._radar())
        self.assertIn("Aggiorna il radar", self._radar())

    def test_radar_aggiungi_al_piano_chiede_conferma(self):
        js = (D / "dashboard.js").read_text(encoding="utf-8")
        self.assertIn("Aggiungi al piano", js)
        self.assertIn("showModal()", js)
        self.assertEqual(js.count("/api/piano/aggiungi"), 1)  # una sola chiamata, dentro l'invio del dialogo
        conferma = js[js.index("function confermaPiano"):js.index("function rigaNovita")]
        self.assertLess(conferma.index("addEventListener('submit'"), conferma.index("/api/piano/aggiungi"))
        self.assertIn("showModal()", conferma)
        fetch = js[js.index("/api/piano/aggiungi"):][:300]
        self.assertIn("'X-Azione': 'conferma'", fetch)
        self.assertIn('maxLength = 200', js)

    def test_radar_senza_barre_dell_imbuto(self):
        js = (D / "dashboard.js").read_text(encoding="utf-8")
        self.assertNotIn("imbutoRadar", js)
        self.assertNotIn("riga-imbuto", js[js.index("function renderRadar"):js.index("function renderSistema")])

    def test_post_tre_contatori(self):
        js = (D / "dashboard.js").read_text(encoding="utf-8")
        r = js[js.index("function renderPost"):js.index("// Le due schede di Post")]
        for e in ("nei prossimi 7 giorni", "da approvare", "da creare"):
            self.assertIn(e, r)
        for e in ("voci in calendario", "'pubblicati'"):
            self.assertNotIn(e, r)
        self.assertIn("Mostra le passate", r)
        self.assertIn("Comp.dato('post'", r)
        indice = (D / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("post-sub", indice + js)
        self.assertIn('id="post-dato"', indice)

    def test_post_ha_ancora_chiedi_un_post_e_le_bozze(self):
        indice = (D / "index.html").read_text(encoding="utf-8")
        post = indice[indice.index('id="post-vista"'):indice.index('id="avvii-vista"')]
        for i in ("chiedi-post", "post-bozze", "form-richiesta"):
            self.assertIn(i, indice)
        self.assertEqual(post.count('class="primario"'), 1)

    def _consumi(self):
        html = (D / "index.html").read_text(encoding="utf-8")
        return html[html.index('id="consumi-vista"'):html.index('id="post-vista"')]

    def test_consumi_tre_schede_e_hash_vecchi(self):
        c = self._consumi()
        self.assertIn('id="consumi-dato"', c)
        self.assertIn('id="consumi-schede"', c)
        self.assertEqual(c.count('class="primario"'), 0)
        js = (D / "dashboard.js").read_text(encoding="utf-8")
        self.assertIn("Comp.schede($('consumi-schede')", js)
        for voce in ("'claude'", "'servizi'", "'locale'"):
            self.assertIn(voce, js[js.index("const SCHEDE_CONSUMI"):][:300])
        alias = js[js.index("const ALIAS"):][:300]
        for h in ("servizi: 'consumi'", "claude: 'consumi'", "prestazioni: 'consumi'"):
            self.assertIn(h, alias)
        sezione = js[js.index("const SEZIONE"):][:200]
        for h in ("servizi: 'servizi'", "claude: 'claude'", "prestazioni: 'locale'"):
            self.assertIn(h, sezione)

    def test_consumi_contenuto_claude_invariato(self):
        c = self._consumi()
        self.assertIn('id="p-claude"', c)
        self.assertIn('id="p-consumo"', c)
        self.assertLess(c.index('id="consumi-claude"'), c.index('id="p-claude"'))

    def test_consumi_dettagli_in_details_e_schema_leggibile(self):
        c = self._consumi()
        for titolo in ("Come gira", "Quando conviene passare a pagamento", "Piani e prezzi"):
            self.assertRegex(c, r'<details[^>]*>\s*<summary>' + titolo)
        js = (D / "dashboard.js").read_text(encoding="utf-8")
        schema = js[js.index("function schemaServizi"):js.index("async function aggiornaMisura")]
        self.assertIn("etichetta-fondo", schema)  # le etichette degli archi stanno su un fondo opaco, non si leggono sovrapposte

    def _conf_js(self):
        js = (D / "dashboard.js").read_text(encoding="utf-8")
        return js[js.index("function pulsanteControlla"):js.index("async function aggiornaConfigurazione")]

    def test_configurazione_senza_gergo_dello_scanner_in_vista(self):
        indice = (D / "index.html").read_text(encoding="utf-8")
        conf = indice[indice.index('id="configurazione-vista"'):indice.index('<dialog id="form-richiesta"')]
        self.assertNotIn("punteggio", conf)
        self.assertIn('id="conf-dato"', conf)
        self.assertIn('id="conf-schede"', conf)
        self.assertRegex(conf, r'<details[^>]*>\s*<summary>Cosa non si vede qui')
        js = self._conf_js()
        i = js.index("function dettaglioScanner")
        fine = js.index("\n}\n", i)
        self.assertNotIn("punteggio", js[:i] + js[fine:])  # il gergo sta solo nel dettaglio per riga
        self.assertIn("el('details'", js[i:fine])
        self.assertIn("Comp.dato('conf'", js)
        self.assertIn("Comp.schede($('conf-schede')", js)
        self.assertIn("Comp.stato(", js)
        self.assertIn("si può aggiornare", js)
        self.assertIn("chiede la tua conferma", js)
        self.assertNotIn("innerHTML", js)

    def test_configurazione_un_solo_primario(self):
        js = self._conf_js()
        self.assertEqual(len(re.findall(r"'primario'", js)), 2)  # «Aggiorna tutte» oppure l'unica riga, mai insieme
        self.assertIn("aggiornabili.length > 1", js)

    def test_configurazione_mantiene_le_azioni(self):
        js = self._conf_js()
        self.assertEqual(js.count("'/api/configurazione/aggiorna'"), 2)  # singola e «Aggiorna tutte»
        self.assertIn("'/api/azioni/controllo-skill'", js)
        self.assertIn("'/api/configurazione/interruttore'", js)
        self.assertIn("function pulsanteAggiornaTutte", js)
        self.assertIn("Controlla ora", js)

    def test_menu_a_quattro_gruppi(self):
        indice = (D / "index.html").read_text(encoding="utf-8")
        nav = indice[indice.index('id="schede"'):indice.index("</nav>")]
        self.assertEqual(re.findall(r'data-vista="(\w+)"', nav), ["mappa", "agenda", "post", "radar", "consumi", "avvii", "orchestratore", "configurazione"])
        self.assertEqual(re.findall(r'class="gruppo">([^<]+)<', nav), ["Contenuti", "Risorse", "Sistema"])

    def test_hash_vecchi_hanno_un_alias(self):
        js = (D / "dashboard.js").read_text(encoding="utf-8")
        alias = re.search(r"const ALIAS = \{([^}]*)\}", js)
        self.assertIsNotNone(alias)
        self.assertEqual(sorted(re.findall(r"(\w+):", alias.group(1))),
                         sorted(["oggi", "piano", "progetti", "bozze", "servizi", "claude", "prestazioni"]))

    def test_consumi_raccoglie_servizi_claude_e_modello_locale(self):
        indice = (D / "index.html").read_text(encoding="utf-8")
        consumi = indice[indice.index('id="consumi-vista"'):indice.index('id="avvii-vista"')]
        for sezione in ("consumi-servizi", "consumi-claude", "consumi-locale"):
            self.assertIn(f'id="{sezione}"', consumi, sezione)
        self.assertRegex(consumi, r'id="consumi-locale"[^>]*data-modulo="radar assistente"')

    def test_il_colore_sta_solo_sugli_stati(self):
        css = (D / "dashboard.css").read_text(encoding="utf-8")
        self.assertNotIn("--accent", css + (D / "index.html").read_text(encoding="utf-8"))

    def test_piede_del_menu_su_telefono_solo_a_menu_aperto(self):
        css = (D / "dashboard.css").read_text(encoding="utf-8")
        self.assertIn(".piede-menu { display: none; }", css)
        self.assertIn(".rail.aperto .piede-menu { display: flex; }", css)

    def test_nessun_colore_fisso_fuori_dai_token(self):
        css = (D / "dashboard.css").read_text(encoding="utf-8")
        fuori = re.sub(r":root[^{]*\{[^}]*\}", "", css)
        self.assertEqual(re.findall(r"#[0-9a-fA-F]{3,6}\b|rgba?\(", fuori), [])
        # il gradiente è ammesso solo come maschera (la sfumatura che dice «la barra scorre»), mai come sfondo
        senza_maschere = re.sub(r"mask-image:[^;]*;", "", re.sub(r"dialog[^{]*\{[^}]*\}", "", css))
        self.assertNotRegex(senza_maschere, r"gradient|box-shadow")

    def test_attesa_controlla_la_risposta(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("if (!ra.ok)", html)           # una pagina d'errore non va letta come JSON

    def test_nessuna_richiesta_a_font_esterni_e_solo_font_di_sistema(self):
        # a ogni apertura partiva una richiesta a Google, e senza rete la pagina cambiava carattere
        pagina = HTML.read_text(encoding="utf-8")
        for esterno in ("fonts.googleapis.com", "fonts.gstatic.com", "Bricolage", "DM Mono", "DM+Mono"):
            self.assertNotIn(esterno, pagina, esterno)
        self.assertRegex(pagina, r"--font:\s*system-ui")
        self.assertRegex(pagina, r"--mono:\s*ui-monospace")

    def test_il_controllo_riconosce_il_difetto_di_prima(self):
        self.assertEqual(funzioni_mancanti("setTimeout(aggiornaVista, 700);"), ["aggiornaVista"])
        self.assertEqual(funzioni_mancanti("function a(){}\nsetInterval(a, 5);\nsetTimeout(() => a(), 1);"), [])


class GraficiConsumi(unittest.TestCase):
    """I grafici di Consumi avevano viewBox fisso a 900: scalato a 1090px il testo di 12 unità diventava 14,5px, a 390px 4,5px."""
    def test_viewbox_dalla_larghezza_reale(self):
        js = (D / "dashboard.js").read_text(encoding="utf-8")
        self.assertNotRegex(js, r"W = 900, H = 240")
        self.assertGreaterEqual(js.count("larghezzaGrafico("), 2)  # una per grafico

    def test_larghezza_minima_con_scroll_e_giorni_senza_sovrapposizioni(self):
        css = (D / "dashboard.css").read_text(encoding="utf-8")
        self.assertIn("#p-consumo svg { min-width: 560px; }", css)
        self.assertIn("#p-consumo .scorri { overflow-x: auto; }", css)
        self.assertIn(".giorni span:not(:first-child):not(:last-child) { visibility: hidden; }", css)
        self.assertIn("Math.max(560,", (D / "dashboard.js").read_text(encoding="utf-8"))

    def test_testo_degli_assi_non_oltre_12px(self):
        css = (D / "dashboard.css").read_text(encoding="utf-8")
        m = re.search(r"#p-consumo \.asse-testo[^{]*\{[^}]*font: 400 ([\d.]+)px", css)
        self.assertTrue(m)
        self.assertLessEqual(float(m.group(1)), 12)
        self.assertGreaterEqual(float(m.group(1)), 11)


class SchedaOrchestratore(unittest.TestCase):
    """La scheda Orchestratore: il menu parte nascosto (compare solo con la chiave «smistatore»), il file JS è servito e non costruisce HTML da stringhe."""

    def setUp(self):
        self.js = (D / "orchestratore.js").read_text(encoding="utf-8")
        self.html = (D / "index.html").read_text(encoding="utf-8")

    def test_il_menu_parte_nascosto_e_la_sezione_c_e(self):
        self.assertRegex(self.html, r'<button[^>]*data-vista="orchestratore"[^>]*\bhidden\b')
        self.assertIn('id="orchestratore-vista" hidden', self.html)
        self.assertIn('src="/orchestratore.js"', self.html)

    def test_il_file_e_servito(self):
        server = (D / "server.py").read_text(encoding="utf-8")
        self.assertIn('"/orchestratore.js": ("orchestratore.js", "text/javascript; charset=utf-8")', server)

    def test_nessun_innerhtml_e_nessuna_valutazione_di_stringhe(self):
        for vietato in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
            self.assertNotIn(vietato, self.js)

    def test_ogni_id_usato_esiste_in_index_html(self):
        usati = set(re.findall(r"""(?:getElementById|\$)\(\s*['"]([\w-]+)['"]""", self.js))
        self.assertTrue(usati)
        for i in usati:
            self.assertIn('id="%s"' % i, self.html, i)

    def test_nessun_percorso_personale(self):
        for nome in ("orchestratore.js", "orchestratore.py", "index.html"):
            testo = (D / nome).read_text(encoding="utf-8")
            for vietato in ("/Users/", "/home/", "C:\\\\Users"):
                self.assertNotIn(vietato, testo, nome)

    def test_le_rotte_chiamate_esistono_nel_server(self):
        server = (D / "server.py").read_text(encoding="utf-8")
        for rotta in set(re.findall(r"'(/api/orchestratore[\w/]*)'", self.js)):
            self.assertIn('"%s"' % rotta, server, rotta)

    def test_la_cronologia_mostra_harness_agente_modello_ed_esito(self):
        self.assertIn("sezione('Cronologia'", self.js)
        for campo in ("v.harness", "v.agente", "v.modello", "v.esito", "v.tentativi"):
            self.assertIn(campo, self.js)

    def test_l_avvio_della_dashboard_non_aspetta_lo_smistatore(self):
        dash = (D / "dashboard.js").read_text(encoding="utf-8")
        self.assertNotIn("inizializza()).then", dash)  # nessuna catena che aspetti la scheda prima di mostrare la prima pagina
        self.assertIn("/api/orchestratore/attivo", self.js)

    def test_il_refresh_non_cancella_la_casella_ne_la_proposta(self):
        carica = self.js[self.js.index("async function carica()"):]
        self.assertNotIn("richiesta()", carica)  # la casella si monta una volta (monta), non a ogni refresh
        self.assertIn("configSporca", carica)

    def test_il_lancio_rimanda_tipo_e_livello_dell_anteprima(self):
        self.assertIn("livello: livSel.value", self.js)

    def test_il_lancio_dice_che_e_solo_macos(self):
        self.assertIn("darwin", self.js)

    def test_dashboard_js_carica_e_mostra_la_vista(self):
        dash = (D / "dashboard.js").read_text(encoding="utf-8")
        self.assertIn("orchestratore: () =>", dash)
        self.assertIn("orchestratore: 'Orchestratore'", dash)


if __name__ == "__main__":
    unittest.main()
