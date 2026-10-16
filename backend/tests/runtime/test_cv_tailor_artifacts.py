"""Concrete renderer validation and publication conflict contracts."""

import zipfile
import pytest
from app.services.docx_cv_builder import DocxCVBuilder
from app.services.tailor_service import _validate_rendered_cv_artifact
from app.schemas.tailor import TailoredCVResult, TailoredExperience


def test_promotion_conflict_never_deletes_a_peer_final_artifact(tmp_path) -> None:
    staged, final = tmp_path / "staged.docx", tmp_path / "final.docx"
    staged.write_bytes(b"ours")
    final.write_bytes(b"peer")
    with pytest.raises(RuntimeError, match="cv_artifact_promotion_conflict"):
        DocxCVBuilder.promote_staged(str(staged), str(final))
    assert final.read_bytes() == b"peer"
    assert staged.read_bytes() == b"ours"


def test_render_validator_rejects_xml_entity_expansion_and_missing_sections(tmp_path):
    cv = TailoredCVResult(summary="Engineer", skills=[{"category": "Cloud", "items": ["AWS"]}],
        experience=[TailoredExperience(role="Engineer", company="Example", period="2020", achievements=["Delivered AWS."])])
    artifact = tmp_path / "malformed.docx"
    with zipfile.ZipFile(artifact, "w") as archive:
        archive.writestr("word/document.xml", '<!DOCTYPE x [<!ENTITY x "Engineer AWS Example 2020 Delivered AWS.">]><x>&x;</x>')
    with pytest.raises(ValueError, match="cv_tailor_rendered_artifact_invalid"):
        _validate_rendered_cv_artifact(str(artifact), artifact.stat().st_size, cv)
