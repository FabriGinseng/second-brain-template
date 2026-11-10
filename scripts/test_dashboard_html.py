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
        for pezzo in ("mappa-nuovo", "/api/mappa/nuovo", "maxlength", "Aggiungi un task", "Avvia in Claude", "aperti(n) === 0", "haCartella"):
            self.assertIn(pezzo, js)
        self.assertIn("#mappa-nuovo", css)
        self.assertIn("textContent", js)                                # il testo dell'utente entra solo come testo
        self.assertNotIn("innerHTML", js)

    def test_i_numeri_dei_nodi_si_spiegano_e_le_bozze_sono_in_sola_lettura(self):
        js = (D / "mappa.js").read_text(encoding="utf-8")
        css = (D / "dashboard.css").read_text(encoding="utf-8")
        for pezzo in ("task aperti", "nessun task nel piano con questo tag", "Il numero sul nodo = task aperti nel piano",
                      "bozze da pubblicare", "nessuna bozza da pubblicare", "Apri in Post", "t.bozza",
                      "n.nome === 'Social' || !t.bozza"):   # sui nodi dei progetti le bozze sono satelliti, non entrano nel numero
            self.assertIn(pezzo, js)
        self.assertIn("nota-mappa", css)                                # la legenda del numero resta visibile anche sotto i 760px

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
        import shutil, subprocess
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
        import shutil, subprocess
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
        self.assertEqual(re.findall(r'data-vista="(\w+)"', nav), ["mappa", "agenda", "post", "radar", "consumi", "avvii", "configurazione"])
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


if __name__ == "__main__":
    unittest.main()
