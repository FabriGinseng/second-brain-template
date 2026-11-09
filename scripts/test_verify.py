#!/usr/bin/env python3
"""Test di scripts/verify su vault temporanei."""
import pathlib
import subprocess
import sys
import tempfile
import unittest

VERIFY = pathlib.Path(__file__).resolve().parent / 'verify'

STATE_TEMPLATE = """# {{title}}

## Obiettivo attuale

## Dove sono

## Prossimi 3 passi

## Blocchi aperti

## Link utili
"""

GOOD_STATE = """# progetto-a
- **Repo:** nessuno
- **Aggiornato:** 2026-10-22
## Obiettivo attuale
Test.
## Dove sono
Test.
## Prossimi 3 passi
1. Test.
## Blocchi aperti
- nessuno
## Link utili
- nessuno
"""

GOOD_INDEX = """# Progetti attivi

| Progetto | Stack | Stato | Priorità | Ultimo aggiornamento |
|---|---|---|---|---|
| [[projects/progetto-a/STATE|progetto-a]] | Python | in corso | alta | 2026-10-22 |
"""


def make_vault(root, state=GOOD_STATE, index=GOOD_INDEX, extra=None):
    (root / 'templates').mkdir()
    (root / 'templates' / 'STATE.md').write_text(STATE_TEMPLATE, encoding='utf-8')
    (root / 'projects' / 'progetto-a').mkdir(parents=True)
    (root / 'projects' / 'INDEX.md').write_text(index, encoding='utf-8')
    (root / 'projects' / 'progetto-a' / 'STATE.md').write_text(state, encoding='utf-8')
    for name, text in (extra or {}).items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')


def run_verify(root):
    result = subprocess.run([sys.executable, str(VERIFY), str(root)], capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


class VerifyTest(unittest.TestCase):
    def test_vault_valido_passa(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_vault(pathlib.Path(tmp))
            code, out = run_verify(tmp)
            self.assertEqual(code, 0, out)

    def test_readme_che_non_cita_un_job_o_un_comando(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            make_vault(root)
            (root / 'scripts').mkdir(exist_ok=True)
            (root / 'scripts' / 'jobs.json').write_text('{"bozze": {}}', encoding='utf-8')
            (root / '.claude' / 'commands').mkdir(parents=True)
            (root / '.claude' / 'commands' / 'post.md').write_text('x', encoding='utf-8')
            (root / 'README.md').write_text('# Vault\n', encoding='utf-8')
            code, out = run_verify(tmp)
            self.assertEqual(code, 1)
            self.assertIn('non cita il job launchd bozze', out)
            self.assertIn('non cita il comando /post', out)
            (root / 'README.md').write_text('second-brain.bozze e /post', encoding='utf-8')
            code, out = run_verify(tmp)
            self.assertEqual(code, 0, out)

    def test_claude_md_che_cita_uno_script_inesistente(self):
        # CLAUDE.md citava avvio.sh quando il job lancia scripts/avvio.py: la prosa si allontana dalla realtà
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            make_vault(root, extra={'scripts/avvio.py': '', 'scripts/verify': ''})
            (root / 'CLAUDE.md').write_text('Al login `avvio.sh` e `scripts/verify`, poi `scripts/test_*.py` e `scripts/<nome>.py`.', encoding='utf-8')
            code, out = run_verify(tmp)
            self.assertEqual(code, 1, out)
            self.assertIn('CLAUDE.md: avvio.sh non esiste', out)
            self.assertNotIn('scripts/verify non esiste', out)
            self.assertNotIn('test_*', out)  # i pattern con * o <> non sono percorsi
            (root / 'CLAUDE.md').write_text('Al login `avvio.py` e `scripts/verify`.', encoding='utf-8')
            code, out = run_verify(tmp)
            self.assertEqual(code, 0, out)

    def test_un_adr_citato_che_non_esiste_e_un_problema(self):
        # il template pubblico citava ADR-001 e ADR-005, che nel template non c'erano: riferimenti vuoti per chi lo usa
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            make_vault(root, extra={'docs/adr/ADR-002-privacy.md': '# ADR-002', 'scripts/radar.py': '"""Vedi ADR-005 e ADR-002."""',
                                    'reports/vecchio.md': 'ADR-099 non ancora scritto', 'docs/specs/x.md': 'ADR-098',
                                    'scripts/test_x.py': '"""Un test che cita ADR-097 per finta."""'})
            (root / 'README.md').write_text('Decisioni: ADR-002 e ADR-007.', encoding='utf-8')
            code, out = run_verify(tmp)
            self.assertEqual(code, 1, out)
            self.assertIn('scripts/radar.py: ADR-005 non esiste', out)
            self.assertIn('README.md: ADR-007 non esiste', out)
            self.assertNotIn('ADR-002 non esiste', out)
            for ignorato in ('ADR-099', 'ADR-098', 'ADR-097'):  # reports, specifiche e test non sono il prodotto
                self.assertNotIn(ignorato, out)
            (root / 'docs' / 'adr' / 'ADR-005-filtro.md').write_text('# ADR-005', encoding='utf-8')
            (root / 'docs' / 'adr' / 'ADR-007-x.md').write_text('# ADR-007', encoding='utf-8')
            code, out = run_verify(tmp)
            self.assertEqual(code, 0, out)

    def test_gli_adr_citati_nei_worktree_non_tracciati_non_bloccano_verify(self):
        # un worktree di un agente (ignorato da git) con un ADR nuovo bloccava verify, e con lui il commit della chiusura delle 18:30
        import subprocess as sp
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            make_vault(root, extra={'docs/adr/ADR-002-privacy.md': '# ADR-002', 'scripts/a.py': '"""Vedi ADR-002."""',
                                    '.claude/worktrees/agent-x/README.md': 'ADR-012 su un ramo', '.claude/skills/terzi/SKILL.md': 'ADR-013 della skill di altri'})
            sp.run(['git', 'init', '-q', str(root)], check=True)
            sp.run(['git', '-C', str(root), 'add', 'docs', 'scripts', 'projects', 'templates'], check=True)  # tracciati: solo questi
            code, out = run_verify(tmp)
            self.assertEqual(code, 0, out)
            self.assertNotIn('ADR-012', out)
            self.assertNotIn('ADR-013', out)

    def test_gli_adr_citati_nei_file_del_template_si_controllano_tutti(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            make_vault(root, extra={'docs/adr/ADR-002-privacy.md': '# ADR-002', 'README.it.md': 'ADR-077', 'INIZIA.md': 'ADR-078',
                                    'setup.py': '"""ADR-079"""', 'CHANGELOG.md': 'ADR-080', 'templates/x.md': 'ADR-081'})
            code, out = run_verify(tmp)
            self.assertEqual(code, 1, out)
            for nome, adr in (('README.it.md', '077'), ('INIZIA.md', '078'), ('setup.py', '079'), ('CHANGELOG.md', '080'), ('templates/x.md', '081')):
                self.assertIn('%s: ADR-%s non esiste' % (nome, adr), out)

    def test_senza_cartella_adr_il_controllo_non_si_applica(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            make_vault(root)
            (root / 'README.md').write_text('ADR-001', encoding='utf-8')
            code, out = run_verify(tmp)
            self.assertEqual(code, 0, out)

    def test_cartella_riservata_scelta_al_setup_non_va_in_index(self):
        cfg = '{"moduli": {"riservata": {"attivo": true, "cartella": "projects/confidential-notes"}}}'
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            make_vault(root, extra={'config.json': cfg})
            (root / 'projects' / 'confidential-notes').mkdir()
            code, out = run_verify(tmp)
            self.assertEqual(code, 0, out)
            (root / 'projects' / 'altra-cartella').mkdir()  # una cartella qualunque resta un errore
            code, out = run_verify(tmp)
            self.assertEqual(code, 1)
            self.assertIn('altra-cartella', out)

    def test_vault_vuoto_non_esplode(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = run_verify(tmp)
            self.assertEqual(code, 1)
            self.assertIn('INDEX.md', out)
            self.assertNotIn('Traceback', out)

    def test_state_troppo_lungo(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_vault(pathlib.Path(tmp), state=GOOD_STATE + '\n'.join(['riga'] * 20))
            code, out = run_verify(tmp)
            self.assertEqual(code, 1)
            self.assertIn('righe', out)

    def test_riga_index_senza_cartella(self):
        index = GOOD_INDEX + '| [[fantasma]] | Go | ferma | bassa | 2026-10-22 |\n'
        with tempfile.TemporaryDirectory() as tmp:
            make_vault(pathlib.Path(tmp), index=index)
            code, out = run_verify(tmp)
            self.assertEqual(code, 1)
            self.assertIn('fantasma', out)

    def test_cartella_fuori_da_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_vault(pathlib.Path(tmp))
            (pathlib.Path(tmp) / 'projects' / 'nuovo').mkdir()
            code, out = run_verify(tmp)
            self.assertEqual(code, 1)
            self.assertIn('nuovo', out)

    def test_data_index_diversa_da_state(self):
        index = GOOD_INDEX.replace('2026-10-22', '2026-10-01')
        with tempfile.TemporaryDirectory() as tmp:
            make_vault(pathlib.Path(tmp), index=index)
            code, out = run_verify(tmp)
            self.assertEqual(code, 1)
            self.assertIn('Aggiornato', out)

    def test_sezione_obbligatoria_mancante(self):
        state = GOOD_STATE.replace('## Blocchi aperti\n- nessuno\n', '')
        with tempfile.TemporaryDirectory() as tmp:
            make_vault(pathlib.Path(tmp), state=state)
            code, out = run_verify(tmp)
            self.assertEqual(code, 1)
            self.assertIn('Blocchi aperti', out)

    def test_wikilink_rotto(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_vault(pathlib.Path(tmp), extra={'daily/2026-10-22.md': 'Vedi [[nota-inesistente]].'})
            code, out = run_verify(tmp)
            self.assertEqual(code, 1)
            self.assertIn('nota-inesistente', out)

    def test_wikilink_con_alias_valido(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_vault(pathlib.Path(tmp), extra={'daily/2026-10-22.md': 'Vedi [[projects/progetto-a/STATE|il progetto]].'})
            code, out = run_verify(tmp)
            self.assertEqual(code, 0, out)

    def test_state_mancante_segnalato(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_vault(pathlib.Path(tmp))
            (pathlib.Path(tmp) / 'projects' / 'nuovo').mkdir()
            (pathlib.Path(tmp) / 'projects' / 'INDEX.md').write_text(
                GOOD_INDEX + '| [[projects/nuovo/STATE|nuovo]] | Go | ferma | bassa | 2026-10-22 |\n', encoding='utf-8')
            code, out = run_verify(tmp)
            self.assertEqual(code, 1)
            self.assertIn('projects/nuovo/STATE.md: manca', out)

    def test_wikilink_in_blocco_di_codice_ignorato(self):
        text = 'Esempio:\n```\n[[nota-di-esempio]]\n```\n'
        with tempfile.TemporaryDirectory() as tmp:
            make_vault(pathlib.Path(tmp), extra={'daily/2026-10-22.md': text})
            code, out = run_verify(tmp)
            self.assertEqual(code, 0, out)

    def test_allegato_esistente_valido(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_vault(pathlib.Path(tmp), extra={'daily/2026-10-22.md': 'Vedi [[foto.png]].', 'inbox/foto.png': 'x'})
            code, out = run_verify(tmp)
            self.assertEqual(code, 0, out)

    def test_maiuscole_non_contano(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_vault(pathlib.Path(tmp), extra={'daily/2026-10-22.md': 'Vedi [[Projects/Progetto-A/STATE]].'})
            code, out = run_verify(tmp)
            self.assertEqual(code, 0, out)

    def test_alias_con_pipe_escapato_in_tabella(self):
        index = GOOD_INDEX.replace('[[projects/progetto-a/STATE|progetto-a]]', '[[projects/progetto-a/STATE\\|progetto-a]]')
        with tempfile.TemporaryDirectory() as tmp:
            make_vault(pathlib.Path(tmp), index=index)
            code, out = run_verify(tmp)
            self.assertEqual(code, 0, out)

    def test_riga_index_senza_data(self):
        index = GOOD_INDEX.replace('| 2026-10-22 |', '|  |')
        with tempfile.TemporaryDirectory() as tmp:
            make_vault(pathlib.Path(tmp), index=index)
            code, out = run_verify(tmp)
            self.assertEqual(code, 1)
            self.assertIn('progetto-a', out)

    def test_file_non_utf8_non_esplode(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_vault(pathlib.Path(tmp))
            (pathlib.Path(tmp) / 'daily').mkdir()
            (pathlib.Path(tmp) / 'daily' / '2026-10-22.md').write_bytes(b'\xff\xfe [[x]]')
            code, out = run_verify(tmp)
            self.assertNotIn('Traceback', out)


REGISTRO_HEAD = """# Registro dei template

| Nome | Tipo | Tecnologia | Profilo | Origine | Aggiornato |
|---|---|---|---|---|---|
"""


def make_scaffold(root, rows, profili=('personal', 'lavoro')):
    """Crea scaffold/registro.md con le righe date e i file dei profili."""
    make_vault(root)
    (root / 'scaffold' / 'profili').mkdir(parents=True)
    (root / 'scaffold' / 'registro.md').write_text(REGISTRO_HEAD + ''.join(r + '\n' for r in rows), encoding='utf-8')
    for nome in profili:
        (root / 'scaffold' / 'profili' / f'{nome}.md').write_text(f'# Profilo {nome}\n', encoding='utf-8')


class ScaffoldTest(unittest.TestCase):
    def check(self, rows, profili=('personal', 'lavoro'), cartella_locale=True):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            locale = root / 'progetti' / 'api'
            if cartella_locale:
                locale.mkdir(parents=True)
            make_scaffold(root, [r.replace('{locale}', str(locale)) for r in rows], profili)
            return run_verify(root)

    def test_registro_valido_passa(self):
        code, out = self.check([
            '| api | backend | Express | personal | locale:{locale} | 2026-11-03 |',
            '| tpl-nuxt-app | fullstack | Nuxt | personal | gh:utente/tpl-nuxt-app | 2026-11-03 |',
            '| express-api | backend | Express | lavoro | locale:{locale} | 2026-11-03 |',
        ])
        self.assertEqual(code, 0, out)

    def test_registro_vuoto_passa(self):
        code, out = self.check([])
        self.assertEqual(code, 0, out)

    def test_senza_registro_non_controlla(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_vault(pathlib.Path(tmp))
            code, out = run_verify(tmp)
            self.assertEqual(code, 0, out)

    def test_tipo_non_valido(self):
        code, out = self.check(['| api | mobile | Express | personal | locale:{locale} | 2026-11-03 |'])
        self.assertEqual(code, 1)
        self.assertIn('tipo "mobile"', out)

    def test_profilo_non_valido(self):
        code, out = self.check(['| api | backend | Express | azienda | locale:{locale} | 2026-11-03 |'])
        self.assertEqual(code, 1)
        self.assertIn('profilo "azienda"', out)

    def test_data_non_valida(self):
        code, out = self.check(['| api | backend | Express | personal | locale:{locale} | 2026-13-45 |'])
        self.assertEqual(code, 1)
        self.assertIn('data', out)

    def test_origine_non_riconosciuta(self):
        code, out = self.check(['| api | backend | Express | personal | https://x.y/z | 2026-11-03 |'])
        self.assertEqual(code, 1)
        self.assertIn('origine', out)

    def test_lavoro_solo_locale(self):
        code, out = self.check(['| api | backend | Express | lavoro | gh:azienda/api | 2026-11-03 |'])
        self.assertEqual(code, 1)
        self.assertIn('lavoro', out)

    def test_percorso_locale_inesistente(self):
        code, out = self.check(['| api | backend | Express | personal | locale:{locale} | 2026-11-03 |'],
                               cartella_locale=False)
        self.assertEqual(code, 1)
        self.assertIn('non esiste', out)

    def test_colonne_sbagliate(self):
        code, out = self.check(['| api | backend | Express | personal | locale:{locale} |'])
        self.assertEqual(code, 1)
        self.assertIn('colonne', out)

    def test_nome_duplicato(self):
        riga = '| api | backend | Express | personal | locale:{locale} | 2026-11-03 |'
        code, out = self.check([riga, riga])
        self.assertEqual(code, 1)
        self.assertIn('duplicato', out)

    def test_profilo_mancante(self):
        code, out = self.check([], profili=('personal',))
        self.assertEqual(code, 1)
        self.assertIn('profili/lavoro.md', out)


if __name__ == '__main__':
    unittest.main()
