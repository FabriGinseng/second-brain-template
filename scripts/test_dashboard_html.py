"""Controlli statici su scripts/dashboard/index.html (nessun browser): la pagina non deve chiamare funzioni che non esistono.

Il redesign aveva tolto aggiornaVista ma setTimeout(aggiornaVista, 700) era rimasto: dopo ogni spunta riuscita la pagina
andava in ReferenceError, rimetteva la casella com'era e scriveva "spunta non salvata" anche se il file era salvato.
"""
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
        self.assertLessEqual(agenda.count('<li><b id="kpi-'), 3)
        # Chiedi sta in fondo e su telefono si apre solo se serve
        self.assertGreater(agenda.index('id="assistente"'), agenda.index('id="aspetta-novita"'))
        self.assertIn('<details class="chiedi"', agenda)
        self.assertIn("matchMedia", html)

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
        self.assertNotRegex(re.sub(r"dialog[^{]*\{[^}]*\}", "", css), r"gradient|box-shadow")

    def test_attesa_controlla_la_risposta_e_mostra_il_dato_mancante(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("if (!ra.ok)", html)           # una pagina d'errore non va letta come JSON
        self.assertIn("a.conteggi.skill ?? '–'", html)  # dato assente: un trattino, non zero

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


if __name__ == "__main__":
    unittest.main()
