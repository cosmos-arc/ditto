from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CANONICAL_GENERATOR = (
    ROOT / "apps" / "web" / "scripts" / "page-contract" / "generate.mjs"
)
CANONICAL_VALIDATOR = (
    ROOT
    / "apps"
    / "web"
    / "scripts"
    / "page-contract"
    / "validators"
    / "contract-validator.mjs"
)
SYSTEM_AGENT_OPS_CONTRACT = (
    ROOT / "apps" / "web" / "contracts" / "pages" / "system-agent-ops.contract.json"
)


class PageContractGeneratorPathTests(unittest.TestCase):
    def test_generator_targets_web_workspace_from_either_working_directory(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = (
                root / "apps" / "web" / "scripts" / "page-contract" / "generate.mjs"
            )
            script.parent.mkdir(parents=True)
            shutil.copytree(
                CANONICAL_GENERATOR.parent, script.parent, dirs_exist_ok=True
            )
            (root / "apps/web/node_modules").symlink_to(
                ROOT / "apps/web/node_modules", target_is_directory=True
            )

            web_root = root / "apps" / "web"
            contracts = web_root / "contracts" / "pages"
            contracts.mkdir(parents=True)
            contract = json.loads(SYSTEM_AGENT_OPS_CONTRACT.read_text())
            contract["route"] = "/fixture"
            (contracts / "fixture.contract.json").write_text(
                json.dumps(contract), encoding="utf-8"
            )

            from_root = subprocess.run(
                ["bun", str(script)],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )

            assert from_root.returncode == 0, from_root.stderr
            generated = web_root / "src/features/shell/page-contracts.generated.ts"
            first_contents = generated.read_bytes()
            assert b'route: "/fixture"' in first_contents

            retired_output = web_root / "scripts" / "visual-audit.config.generated.mjs"
            assert not retired_output.exists()
            retired_output.write_text("local historical output")

            from_web = subprocess.run(
                ["bun", str(script)],
                cwd=web_root,
                check=False,
                capture_output=True,
                text=True,
            )

            assert from_web.returncode == 0, from_web.stderr
            assert retired_output.read_text() == "local historical output"
            assert generated.read_bytes() == first_contents
            assert not (root / "docs" / "contracts" / "pages").exists()
            assert not (root / "src" / "features" / "shell").exists()
            assert not (root / "scripts" / "visual-audit.config.generated.mjs").exists()
            fixture = contracts / "fixture.contract.json"
            original = fixture.read_text()
            for field in (
                "prototypeRef",
                "visualThresholds",
                "pixelDiffRatio",
                "consoleErrors",
            ):
                invalid = json.loads(original)
                invalid["route"] = "/must-not-persist"
                if field in ("prototypeRef", "visualThresholds"):
                    del invalid[field]
                else:
                    invalid["visualThresholds"][field] = -1
                fixture.write_text(json.dumps(invalid))
                rejected = subprocess.run(
                    ["bun", str(script)],
                    cwd=root,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                assert rejected.returncode != 0
                assert "JSON Schema validation failed" in rejected.stderr
                assert field in rejected.stderr
                assert generated.read_bytes() == first_contents
                fixture.write_text(original)

    def test_validator_loads_isolated_web_dependencies_without_node_path(self) -> None:
        environment = dict(os.environ)
        environment.pop("NODE_PATH", None)
        program = f"await import({json.dumps(CANONICAL_VALIDATOR.as_uri())});"

        for cwd in (ROOT, ROOT / "apps" / "web"):
            with self.subTest(cwd=cwd.relative_to(ROOT).as_posix() or "."):
                result = subprocess.run(
                    ["bun", "-e", program],
                    cwd=cwd,
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                )

                assert result.returncode == 0, result.stderr


class PageContractValidatorPathTests(unittest.TestCase):
    def _schema_check_for_test_ref(self, test_ref: str) -> dict[str, object]:
        validator_uri = json.dumps(CANONICAL_VALIDATOR.as_uri())
        contract_path = json.dumps(str(SYSTEM_AGENT_OPS_CONTRACT))
        web_root = json.dumps(str(ROOT / "apps" / "web"))
        program = f"""
import {{ readFile }} from "node:fs/promises";
const {{ validateContract }} = await import({validator_uri});
const contract = JSON.parse(await readFile({contract_path}, "utf8"));
contract.landing.reactTestRefs = [{json.dumps(test_ref)}];
const result = await validateContract(contract, {{ root: {web_root} }});
console.log(JSON.stringify(result.checks[0]));
"""
        result = subprocess.run(
            ["bun", "-e", program],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    def test_react_test_refs_allow_workflow_owned_page_composition(self) -> None:
        check = self._schema_check_for_test_ref(
            "src/workflows/system-agent-ops/system-agent-ops-page.test.tsx"
        )

        assert check["pass"] is True, check["message"]

    def test_react_test_refs_still_reject_non_feature_or_workflow_paths(self) -> None:
        check = self._schema_check_for_test_ref("src/routes/system-agent-ops.test.tsx")

        assert check["pass"] is False
        assert "JSON Schema validation failed" in str(check["message"])


if __name__ == "__main__":
    unittest.main()
