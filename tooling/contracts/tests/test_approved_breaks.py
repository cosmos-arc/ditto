"""Tests for the approved-breaks registry loader and matcher."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from tooling.contracts import approved_breaks, check_contract, oasdiff

_VALID_DOCUMENT = """\
schema: ditto.approved-breaks.v1
breaks:
  - fingerprint: "695650e2a4fa"
    id: response-property-enum-value-added
    approved-by: "#658 / #664"
    added: "2026-11-04"
    note: weekly enum, generated types only
"""


def _entry(**overrides: str) -> approved_breaks.ApprovedBreak:
    fields = {
        "fingerprint": "695650e2a4fa",
        "rule_id": "response-property-enum-value-added",
        "approved_by": "#658 / #664",
        "added": "2026-11-04",
        "note": "",
    }
    fields.update(overrides)
    return approved_breaks.ApprovedBreak(**fields)


def _finding(rule_id: str, fingerprint: str) -> approved_breaks.Finding:
    return approved_breaks.Finding(
        rule_id=rule_id, fingerprint=fingerprint, text="some finding"
    )


class TestParseRegistry:
    def test_valid_document_round_trips(self) -> None:
        entries = approved_breaks.parse_registry(_VALID_DOCUMENT)
        assert entries == [
            _entry(note="weekly enum, generated types only"),
        ]

    def test_no_breaks_key_is_empty(self) -> None:
        assert (
            approved_breaks.parse_registry("schema: ditto.approved-breaks.v1\n") == []
        )

    @pytest.mark.parametrize(
        "payload",
        [
            "not a mapping",
            "schema: wrong.schema.v0\n",
            "schema: ditto.approved-breaks.v1\nbreaks: {}\n",
        ],
    )
    def test_malformed_documents_are_rejected(self, payload: str) -> None:
        with pytest.raises(approved_breaks.ApprovedBreaksError):
            approved_breaks.parse_registry(payload)

    def test_entry_requires_all_reference_fields(self) -> None:
        payload = (
            "schema: ditto.approved-breaks.v1\nbreaks:\n"
            '  - fingerprint: "695650e2a4fa"\n'
            "    id: response-property-enum-value-added\n"
        )
        with pytest.raises(approved_breaks.ApprovedBreaksError, match="missing"):
            approved_breaks.parse_registry(payload)

    def test_unknown_keys_are_rejected(self) -> None:
        payload = _VALID_DOCUMENT.replace(
            "    note: weekly enum, generated types only\n",
            "    note: weekly enum, generated types only\n    wildcard: true\n",
        )
        with pytest.raises(approved_breaks.ApprovedBreaksError, match="unknown keys"):
            approved_breaks.parse_registry(payload)

    def test_non_hex_fingerprint_is_rejected(self) -> None:
        payload = _VALID_DOCUMENT.replace("695650e2a4fa", "NOTHEX!!")
        with pytest.raises(approved_breaks.ApprovedBreaksError, match="hex"):
            approved_breaks.parse_registry(payload)

    def test_blank_approved_by_is_rejected(self) -> None:
        payload = _VALID_DOCUMENT.replace(
            'approved-by: "#658 / #664"', 'approved-by: "   "'
        )
        with pytest.raises(approved_breaks.ApprovedBreaksError, match="missing"):
            approved_breaks.parse_registry(payload)

    @pytest.mark.parametrize("bad_date", ["2026-13-99", "2026-02-30", "20261104"])
    def test_impossible_added_dates_are_rejected(self, bad_date: str) -> None:
        payload = _VALID_DOCUMENT.replace('added: "2026-11-04"', f'added: "{bad_date}"')
        with pytest.raises(approved_breaks.ApprovedBreaksError):
            approved_breaks.parse_registry(payload)

    def test_unquoted_yaml_date_is_rejected(self) -> None:
        payload = _VALID_DOCUMENT.replace('added: "2026-11-04"', "added: 2026-11-04")
        with pytest.raises(approved_breaks.ApprovedBreaksError):
            approved_breaks.parse_registry(payload)

    def test_duplicate_entry_key_is_rejected(self) -> None:
        payload = _VALID_DOCUMENT.replace(
            '    added: "2026-11-04"\n',
            '    added: "2026-11-04"\n    fingerprint: "9b128d1b912d"\n',
        )
        with pytest.raises(approved_breaks.ApprovedBreaksError):
            approved_breaks.parse_registry(payload)

    def test_duplicate_top_level_breaks_is_rejected(self) -> None:
        payload = _VALID_DOCUMENT + 'breaks:\n  - fingerprint: "ffffffffffff"\n'
        with pytest.raises(approved_breaks.ApprovedBreaksError):
            approved_breaks.parse_registry(payload)

    def test_unknown_top_level_key_is_rejected(self) -> None:
        payload = _VALID_DOCUMENT + "wildcards: true\n"
        with pytest.raises(approved_breaks.ApprovedBreaksError, match="top-level"):
            approved_breaks.parse_registry(payload)

    def test_duplicate_entries_are_rejected(self) -> None:
        entry_block = _VALID_DOCUMENT.split("breaks:\n", 1)[1]
        payload = (
            f"schema: ditto.approved-breaks.v1\nbreaks:\n{entry_block}{entry_block}"
        )
        with pytest.raises(approved_breaks.ApprovedBreaksError, match="duplicates"):
            approved_breaks.parse_registry(payload)


class TestLoadRegistry:
    def test_missing_file_means_no_exemptions(self, tmp_path: Path) -> None:
        assert approved_breaks.load_registry(tmp_path / "absent.yaml") == []

    def test_file_is_loaded_from_disk(self, tmp_path: Path) -> None:
        path = tmp_path / "approved-breaks.yaml"
        path.write_text(_VALID_DOCUMENT, encoding="utf-8")
        assert approved_breaks.load_registry(path) == [
            _entry(note="weekly enum, generated types only"),
        ]

    def test_non_utf8_registry_fails_closed(self, tmp_path: Path) -> None:
        path = tmp_path / "approved-breaks.yaml"
        path.write_bytes(b'schema: ditto.approved-breaks.v1\nnote: "\xff\xfe"\n')
        with pytest.raises(approved_breaks.ApprovedBreaksError, match="UTF-8"):
            approved_breaks.load_registry(path)


class TestUnapproved:
    def test_exact_match_is_covered(self) -> None:
        findings = [_finding("response-property-enum-value-added", "695650e2a4fa")]
        assert approved_breaks.unapproved(findings, [_entry()]) == []

    def test_unmatched_finding_is_rejected(self) -> None:
        findings = [_finding("response-property-enum-value-added", "ffffffffffff")]
        assert approved_breaks.unapproved(findings, [_entry()]) == findings

    def test_rule_id_mismatch_is_rejected(self) -> None:
        findings = [_finding("response-property-removed", "695650e2a4fa")]
        assert approved_breaks.unapproved(findings, [_entry()]) == findings

    def test_entry_is_consumed_once(self) -> None:
        finding = _finding("response-property-enum-value-added", "695650e2a4fa")
        assert approved_breaks.unapproved([finding, finding], [_entry()]) == [finding]

    def test_empty_registry_rejects_everything(self) -> None:
        findings = [_finding("response-property-enum-value-added", "695650e2a4fa")]
        assert approved_breaks.unapproved(findings, []) == findings


class TestApprovalLine:
    def test_line_carries_the_approval_reference(self) -> None:
        line = approved_breaks.approval_line(_entry(note="weekly enum"))
        assert "response-property-enum-value-added" in line
        assert "695650e2a4fa" in line
        assert "#658 / #664" in line
        assert "2026-11-04" in line
        assert line.endswith("— weekly enum")


class TestCollectBreakingFindings:
    """Guards on the JSON enumeration that exemption matching depends on."""

    @staticmethod
    def _resolution() -> oasdiff.BaselineResolution:
        return oasdiff.BaselineResolution(
            kind="merge-base",
            status="found",
            ref="main",
            commit="a" * 40,
            reason="test baseline",
            contract_bytes=b'{"openapi": "3.1.0"}',
        )

    @staticmethod
    def _fake_run(
        monkeypatch: pytest.MonkeyPatch,
        returncode: int,
        stdout: bytes,
    ) -> None:
        def fake_invocation(**_options: object) -> subprocess.CompletedProcess[bytes]:
            return subprocess.CompletedProcess(
                args=[], returncode=returncode, stdout=stdout
            )

        monkeypatch.setattr(oasdiff, "_run_oasdiff_breaking", fake_invocation)

    def test_valid_findings_round_trip(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stdout = (
            b'[{"id":"response-property-enum-value-added","fingerprint":'
            b'"695650e2a4fa","text":"added weekly"}]'
        )
        self._fake_run(monkeypatch, returncode=1, stdout=stdout)
        findings = oasdiff.collect_breaking_findings(
            resolution=self._resolution(),
            current_path=Path("/dev/null"),
            dist_dir=Path("/dev/null"),
        )
        assert findings == [
            approved_breaks.Finding(
                rule_id="response-property-enum-value-added",
                fingerprint="695650e2a4fa",
                text="added weekly",
            )
        ]

    def test_passing_json_run_after_failing_text_gate_diverges(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._fake_run(monkeypatch, returncode=0, stdout=b"[]")
        with pytest.raises(oasdiff.OasdiffError, match="passed while"):
            oasdiff.collect_breaking_findings(
                resolution=self._resolution(),
                current_path=Path("/dev/null"),
                dist_dir=Path("/dev/null"),
            )

    @pytest.mark.parametrize(
        "stdout",
        [
            b'{"breaking": []}',
            b'"not a list"',
            b"[{}]",
            b'[{"id": "r"}]',
            b'[{"id": 1, "fingerprint": "f", "text": "t"}]',
            b"not json",
            b"\xff\xfe",
        ],
    )
    def test_malformed_json_shapes_fail_closed(
        self,
        monkeypatch: pytest.MonkeyPatch,
        stdout: bytes,
    ) -> None:
        self._fake_run(monkeypatch, returncode=1, stdout=stdout)
        with pytest.raises(oasdiff.OasdiffError):
            oasdiff.collect_breaking_findings(
                resolution=self._resolution(),
                current_path=Path("/dev/null"),
                dist_dir=Path("/dev/null"),
            )


class TestGateStalenessEnforcement:
    """The gate must fail on registry entries no finding consumed this run."""

    @staticmethod
    def _resolution() -> oasdiff.BaselineResolution:
        return oasdiff.BaselineResolution(
            kind="merge-base",
            status="found",
            ref="main",
            commit="a" * 40,
            reason="test baseline",
            contract_bytes=b'{"openapi": "3.1.0"}',
        )

    def test_consumed_entries_pass_and_register_consumption(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        finding = _finding("response-property-enum-value-added", "695650e2a4fa")
        monkeypatch.setattr(
            oasdiff,
            "collect_breaking_findings",
            lambda **_options: [finding],
        )
        entries = [_entry()]
        consumed: set[tuple[str, str]] = set()
        check_contract._approve_or_fail(
            resolution=self._resolution(),
            dist_dir=Path("/dev/null"),
            entries=entries,
            consumed=consumed,
        )
        assert consumed == {("response-property-enum-value-added", "695650e2a4fa")}
        assert "approved versioned break" in capsys.readouterr().out
        check_contract._reject_stale_entries(entries, consumed)

    def test_unmatched_finding_fails_with_details(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        finding = _finding("response-property-enum-value-added", "ffffffffffff")
        monkeypatch.setattr(
            oasdiff,
            "collect_breaking_findings",
            lambda **_options: [finding],
        )
        with pytest.raises(oasdiff.OasdiffError, match="not covered"):
            check_contract._approve_or_fail(
                resolution=self._resolution(),
                dist_dir=Path("/dev/null"),
                entries=[_entry()],
                consumed=set(),
            )

    def test_empty_enumeration_fails_closed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            oasdiff,
            "collect_breaking_findings",
            lambda **_options: [],
        )
        with pytest.raises(oasdiff.OasdiffError, match="no findings"):
            check_contract._approve_or_fail(
                resolution=self._resolution(),
                dist_dir=Path("/dev/null"),
                entries=[_entry()],
                consumed=set(),
            )

    def test_unconsumed_entry_fails_the_run(self) -> None:
        stale = _entry(fingerprint="9b128d1b912d")
        with pytest.raises(oasdiff.OasdiffError, match="stale"):
            check_contract._reject_stale_entries([stale], set())

    def test_green_run_with_nonempty_registry_fails_as_stale(self) -> None:
        with pytest.raises(oasdiff.OasdiffError, match="stale"):
            check_contract._reject_stale_entries([_entry()], set())
