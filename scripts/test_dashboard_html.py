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
        html = HTML.read_text(encoding="utf-8")
        oggi = html[html.index('id="oggi-vista"'):html.index('id="progetti-vista"')]
        self.assertIn('id="aspetta-te"', oggi)
        self.assertIn("'/api/attesa'", html)
        for tolto in ("kpi-job", "kpi-scartate", "kpi-vault"):  # numeri che non portano a nessuna azione
            self.assertNotIn(tolto, html, tolto)
        self.assertLessEqual(oggi.count('<li><b id="kpi-'), 3)
        # Chiedi sta in fondo e su telefono si apre solo se serve
        self.assertGreater(oggi.index('id="assistente"'), oggi.index('id="oggi-progetti"'))
        self.assertIn('<details class="chiedi"', oggi)
        self.assertIn("matchMedia", html)

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
