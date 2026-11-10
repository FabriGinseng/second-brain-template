#!/usr/bin/env python3
"""Hook delle regole deterministiche (.claude/hooks/regole.py): ogni variante di aggiramento ha la sua riga.

L'hook gira come sottoprocesso, come in Claude Code. SB_HOOKS_DIR punta a un'altra cartella dell'hook (sviluppo, test sulle
regole mancanti o malformate); di solito è .claude/hooks del repo. Home e radice sono cartelle temporanee, mai quelle vere.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS = Path(os.environ.get("SB_HOOKS_DIR") or Path(__file__).resolve().parent.parent / ".claude" / "hooks")

CHIEDI = [
    "git push", "git push origin main", "git -C . push", "git -c x=y push", "git --git-dir=.git push", "git --no-pager push",
    "rtk git push", "/usr/bin/git push", "\\git push", "command git push", "env A=1 git push", "A=1 git push", "nohup git push",
    "sh -c 'git push'", 'bash -lc "git push"', "zsh -c 'cd x && git push'", "eval git push", "echo $(git push)", "echo `git push`",
    "xargs git push", "{ git push; }", "if true; then git push; fi", "timeout 60 git push", "git status && git push", "git status; git push", "$G push", "${G} push",
    "gh pr create", "rtk gh pr create", "gh -R a/b pr merge 3", "gh repo delete x", "gh release create v1",
    "npm publish", "pnpm publish", "yarn publish", "vercel --prod", "netlify deploy", "fly deploy", "kubectl apply -f x",
    "docker push img", "ssh host", "scp a b:c", "rsync -a x host:/y", "rm x", "rm -rf node_modules", "launchctl load x",
    # revisione finale
    "git commit -m wip#3 && git push", "git checkout -b fix#12; git push", "rtk bypass rm -rf x", "rtk err git push",
    "npx vercel --prod", "npx -y vercel --prod", "bunx vercel", "pnpm dlx vercel", "npm exec -- vercel", "yarn dlx netlify deploy",
    "docker buildx build --push .", "docker image push x", "yarn npm publish", "bun publish", "npm --registry x publish",
    "find . -delete", "find . -exec rm {} \\;", "gh api -X POST repos/a/b/issues", "gh api repos/a/b/issues -f title=x",
    "gh workflow run deploy.yml", "bash -o pipefail -c 'git push'",
]
NEGA = [
    "git push --force", "git push -f", "git push origin +main", "git -C . push --force-with-lease", "git push --force-with-lease=main",
    "sh -c 'git push -f'", "rtk git push --force", "git reset --hard", "git reset --hard HEAD~1", "git clean -fd",
    "git rebase -i HEAD~3", "git rebase main", "git filter-branch --all", "git filter-repo --path x", "git commit --amend",
    "git commit -an -m x", "git commit --no-verif -m x", "git commit --no-verify -m x", "git commit -m x -n",
    "git -c core.hooksPath=/dev/null commit -m x", "git config core.hooksPath /dev/null",
    # dai test del vecchio no_bypass.py
    "git commit --no-veri -m x", "git commit --no-v -m x", "git commit -qn -m x", "git commit -a -n", "cd /tmp && git commit -m y -n",
    "git add . && git commit --no-verify -m z",
    # revisione finale: a capo con \, # dentro una parola, sottocomandi di rtk, abbreviazioni lunghe, --mirror, opzioni della shell
    "git commit \\\n  --no-verify -m x", "git reset \\\n  --hard", "git push \\\n  --force origin main", "echo a#b; git push --force",
    "rtk bypass git push --force", "rtk proxy git push --force", "git reset --ha HEAD", "git commit --am -m x", "git commit --ame",
    "git push --mirror", "bash -o pipefail -c 'git push -f'", "bash -c -- 'git push -f'",
]
NIENTE = [
    "git status", "git log --oneline", 'git commit -m "push later"', "grep -r push docs/", "cat ~/.claude/settings.json",
    "git push-helper", 'echo "git push"', "rsync -a a/ b/", "git rebase --abort", "git rebase --continue", "git rebase --skip",
    "git tag -n", "git log -n 5", "cd x && git commit -m y", "git config core.hooksPath scripts/hooks", "echo 'git commit -n'",
    "git commit -am 'msg'", "git add . && git commit -m x", "ls -la", "python3 -I -m unittest", "git diff HEAD~1",
    # dai test del vecchio no_bypass.py
    "git commit -m 'add -noise filter'", 'git commit -q -m "fix: x" -m "Co-Authored-By: Claude <n@x>"', "git commit -m x --allow-empty", "ls -n",
    # revisione finale
    "git status # push dopo", "npm run build", "npx vitest run", "find . -name x", "gh api repos/a/b", "docker buildx build .",
    "git commit --all -m x", "git push-x --forc",
]


def lancia(evento, home, radice, cartella=None):
    """(azione, motivo, stdout) come li vede Claude Code: exit 2 = nega, JSON ask = chiedi, altrimenti niente."""
    env = dict(os.environ) if os.name == "nt" else {"PATH": "/usr/bin:/bin:/opt/homebrew/bin"}  # Windows: serve SYSTEMROOT
    env.update({"HOME": str(home), "USERPROFILE": str(home), "CLAUDE_PROJECT_DIR": str(radice)})
    dati = evento if isinstance(evento, str) else json.dumps(evento)
    r = subprocess.run([sys.executable, "-I", str(Path(cartella or HOOKS) / "regole.py")], input=dati, capture_output=True, text=True, env=env)
    if r.returncode == 2:
        return "nega", r.stderr.strip(), r.stdout
    if r.returncode == 0 and r.stdout.strip():
        uscita = json.loads(r.stdout)["hookSpecificOutput"]
        return ("chiedi" if uscita.get("permissionDecision") == "ask" else uscita.get("permissionDecision")), uscita.get("permissionDecisionReason", ""), r.stdout
    return ("" if r.returncode == 0 else "errore %d: %s" % (r.returncode, r.stderr)), "", r.stdout


def bash(comando):
    return {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": comando}}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name).resolve()
        self.home, self.radice = base / "home", base / "repo"
        self.home.mkdir()
        self.radice.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def decisione(self, evento, cartella=None):
        return lancia(evento, self.home, self.radice, cartella)


class Bash(Base):
    def tabella(self, casi, attesa):
        for c in casi:
            with self.subTest(comando=c):
                self.assertEqual(self.decisione(bash(c))[0], attesa)

    def test_chiede_conferma(self):
        self.tabella(CHIEDI, "chiedi")

    def test_nega(self):
        self.tabella(NEGA, "nega")

    def test_lascia_decidere_ai_settings(self):
        self.tabella(NIENTE, "")

    def test_heredoc_nel_messaggio_non_chiede(self):
        c = "git commit -m \"$(cat <<'EOF'\nfix: niente push qui\nrm vecchi file\ngit push dopo\n\nCo-Authored-By: x\nEOF\n)\""
        self.assertEqual(self.decisione(bash(c))[0], "")

    def test_annidamento_profondo(self):
        self.assertEqual(self.decisione(bash("bash -c \"sh -c 'zsh -c \\\"git push\\\"'\""))[0], "chiedi")
        troppo = "git status"
        for _ in range(7):
            troppo = "sh -c %s" % json.dumps(troppo)
        self.assertEqual(self.decisione(bash(troppo))[0], "chiedi")

    def test_non_analizzabile_chiede(self):
        self.assertEqual(self.decisione(bash("git commit -m 'x"))[0], "chiedi")

    def test_json_rotto_chiede(self):
        self.assertEqual(self.decisione("{non json")[0], "chiedi")

    def test_regole_mancanti_chiedono(self):
        cartella = Path(self.tmp.name) / "hook"
        cartella.mkdir()
        shutil.copy(HOOKS / "regole.py", cartella)
        self.assertEqual(self.decisione(bash("ls"), cartella)[0], "chiedi")

    def test_regole_malformate_chiedono(self):
        cartella = Path(self.tmp.name) / "hook"
        cartella.mkdir()
        shutil.copy(HOOKS / "regole.py", cartella)
        (cartella / "regole.json").write_text(json.dumps({"regole": [{"azione": "forse", "comando": ["x"], "motivo": "m"}]}), encoding="utf-8")
        self.assertEqual(self.decisione(bash("ls"), cartella)[0], "chiedi")

    def test_mai_allow(self):
        for c in CHIEDI[:5] + NEGA[:3] + NIENTE[:5]:
            self.assertNotIn('"allow"', self.decisione(bash(c))[2], c)

    def test_ogni_regola_ha_un_caso(self):
        regole = json.loads((HOOKS / "regole.json").read_text(encoding="utf-8"))["regole"]
        visti = {self.decisione(bash(c))[:2] for c in CHIEDI + NEGA}
        for r in regole:
            if "comando" in r:
                self.assertIn((r["azione"], r["motivo"]), visti, r)


def modifica(percorso, strumento="Edit"):
    chiave = "notebook_path" if strumento == "NotebookEdit" else "file_path"
    return {"hook_event_name": "PreToolUse", "tool_name": strumento, "tool_input": {chiave: percorso}}


class Percorsi(Base):
    """I guardrail non si modificano: né con Edit|Write né con una scrittura da Bash. Leggerli è libero."""

    def vault(self):
        (self.radice / ".claude" / "hooks").mkdir(parents=True)
        (self.radice / ".claude" / "hooks" / "regole.json").write_text("{}", encoding="utf-8")

    def test_edit_guardrail_negato(self):
        for p, strumento in ((str(self.home / ".claude" / "hooks" / "regole.py"), "Edit"), (str(self.home / ".claude" / "settings.json"), "Write"),
                             ("~/.claude/settings.json", "MultiEdit"), (".claude/hooks/x.py", "Edit"), (".CLAUDE/Hooks/x.py", "Write"),
                             (".claude/hooks/x.ipynb", "NotebookEdit")):
            with self.subTest(percorso=p):
                azione, motivo, _ = self.decisione(modifica(p, strumento))
                self.assertEqual(azione, "nega")
                self.assertIn("guardrail", motivo)

    def test_edit_guardrail_del_vault_negato(self):
        self.vault()
        for p in ("scripts/verify", "scripts/hooks/pre-commit", str(self.radice / "SCRIPTS" / "Verify")):
            with self.subTest(percorso=p):
                self.assertEqual(self.decisione(modifica(p))[0], "nega")

    def test_percorsi_equivalenti(self):
        (self.radice / "sub").mkdir()
        for p in ("sub/../.claude/hooks/x.py", str(self.home / ".CLAUDE" / "settings.json"), "~/.claude/hooks/../hooks/regole.json"):
            with self.subTest(percorso=p):
                self.assertEqual(self.decisione(modifica(p))[0], "nega")

    def test_scripts_verify_fuori_dal_vault_passa(self):
        for p in ("scripts/verify", "scripts/hooks/pre-commit"):
            self.assertEqual(self.decisione(modifica(p))[0], "", p)

    def test_edit_normale_passa(self):
        self.vault()
        for p in ("daily/x.md", "CLAUDE.md", ".claude/settings.json", ".claude/commands/x.md", str(Path(self.tmp.name) / "fuori.txt"), "scripts/verify-altro.py"):
            self.assertEqual(self.decisione(modifica(p))[0], "", p)

    def test_scrittura_bash_su_guardrail_negata(self):
        self.vault()
        for c in ("cp x ~/.claude/hooks/regole.py", "sed -i '' s/a/b/ scripts/verify", "echo x > ~/.claude/settings.json", "echo x >> scripts/verify",
                  "tee -a .claude/hooks/a.py", "mv .claude/hooks/regole.py /tmp/", "rm ~/.claude/hooks/regole.py", "sh -c 'echo x > ~/.claude/settings.json'",
                  "perl -pi -e s/a/b/ scripts/hooks/pre-commit", "dd if=x of=scripts/verify", "chmod 000 ~/.claude/hooks/regole.py", "ln -sf x scripts/verify"):
            with self.subTest(comando=c):
                self.assertEqual(self.decisione(bash(c))[0], "nega")

    def test_scrittura_con_home_come_variabile_negata(self):
        for c in ("echo {} > $HOME/.claude/settings.json", 'cp x "$HOME/.claude/hooks/regole.py"', "sed -i '' s/a/b/ ${HOME}/.claude/settings.json"):
            with self.subTest(comando=c):
                self.assertEqual(self.decisione(bash(c))[0], "nega")

    def test_percorso_relativo_si_risolve_dalla_cartella_della_shell(self):
        # la cartella del tool Bash resta tra una chiamata e l'altra: cd ~/.claude, poi echo > settings.json
        (self.home / ".claude").mkdir()
        evento = dict(bash("echo {} > settings.json"), cwd=str(self.home / ".claude"))
        self.assertEqual(self.decisione(evento)[0], "nega")

    def test_lettura_bash_passa(self):
        self.vault()
        for c in ("cat ~/.claude/settings.json", "grep -r x .claude/hooks", "diff a .claude/hooks/regole.py", "cp .claude/hooks/regole.py /tmp/copia.py",
                  "sed -n 1,5p scripts/verify", "python3 -I scripts/verify", "ls ~/.claude/hooks"):
            with self.subTest(comando=c):
                self.assertEqual(self.decisione(bash(c))[0], "")

    def test_senza_radice(self):
        env = dict(os.environ) if os.name == "nt" else {"PATH": "/usr/bin:/bin"}
        env.update({"HOME": str(self.home), "USERPROFILE": str(self.home)})
        env.pop("CLAUDE_PROJECT_DIR", None)
        r = subprocess.run([sys.executable, "-I", str(HOOKS / "regole.py")], input=json.dumps(modifica("daily/x.md")), capture_output=True,
                           text=True, env=env, cwd=self.radice)
        self.assertEqual((r.returncode, r.stdout), (0, ""), r.stderr)

    def test_ogni_regola_di_percorso_ha_un_caso(self):
        self.vault()
        regole = json.loads((HOOKS / "regole.json").read_text(encoding="utf-8"))["regole"]
        visti = {self.decisione(modifica(p))[:2] for p in ("~/.claude/settings.json", ".claude/hooks/x.py", "scripts/verify", "~/.claude/hooks/x")}
        for r in regole:
            if "percorsi" in r:
                self.assertIn((r["azione"], r["motivo"]), visti, r)


if __name__ == "__main__":
    unittest.main()
