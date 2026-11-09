#!/usr/bin/env python3
"""Il workflow di CI di riferimento per i repo Node (scaffold/ci/node.yml): permessi minimi, nessun deploy, nessun segreto oltre al token del repo."""
import re
import unittest
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
FILE = RADICE / "scaffold" / "ci" / "node.yml"
PNPM = RADICE / "scaffold" / "ci" / "pnpm.yml"


class WorkflowCiTest(unittest.TestCase):
    FILE = FILE
    GESTORE = "npm ci"
    LANCIA = {"lint": "npm run lint --if-present", "typecheck": "npm run typecheck --if-present", "test": "npm test --if-present", "build": "npm run build --if-present"}

    def setUp(self):
        self.testo = self.FILE.read_text(encoding="utf-8")

    def test_permessi_minimi_e_trigger(self):
        self.assertRegex(self.testo, r"(?m)^permissions:\n  contents: read\n")
        self.assertIn("pull_request:", self.testo)
        self.assertRegex(self.testo, r"push:\n    branches: \[main\]")

    def test_nessun_deploy_e_nessun_segreto_oltre_al_token_del_repo(self):
        codice = "\n".join(r.split("#")[0] for r in self.testo.splitlines())  # i commenti possono nominare il deploy
        self.assertNotRegex(codice.lower(), r"deploy|vercel|cloudflare|wrangler")
        segreti = set(re.findall(r"secrets\.(\w+)", self.testo))
        self.assertLessEqual(segreti, {"GITHUB_TOKEN"})

    def test_le_azioni_hanno_una_versione_e_gitleaks_vede_la_storia(self):
        for uso in re.findall(r"uses: (\S+)", self.testo):
            self.assertRegex(uso, r"@v\d+", uso)
        self.assertIn("fetch-depth: 0", self.testo)  # senza, gitleaks scansiona un solo commit

    def test_usa_solo_script_che_esistono_con_if_present_e_npm_ci(self):
        self.assertIn(self.GESTORE, self.testo)
        for passo, comando in self.LANCIA.items():
            self.assertIn(comando, self.testo, passo)


class WorkflowCiPnpmTest(WorkflowCiTest):
    FILE = PNPM
    GESTORE = "pnpm install --frozen-lockfile"
    LANCIA = {p: "pnpm run %s --if-present" % p for p in ("lint", "typecheck", "test", "build")}

    def test_la_versione_di_pnpm_viene_da_package_json(self):
        self.assertIn("pnpm/action-setup@v4", self.testo)
        self.assertNotRegex(self.testo, r"version:\s*\d+\.\d+")  # nessuna versione scritta qui: si legge packageManager


if __name__ == "__main__":
    unittest.main()
