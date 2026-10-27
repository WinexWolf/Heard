import pytest
from backend.app.pipeline.patch import apply_edits, PatchError, parse_patch
from backend.app.schemas import Edit


def site(tmp_path):
    (tmp_path / "index.html").write_text('<button id="a"></button><button id="b"></button>')
    return tmp_path


def test_unique_match_applies(tmp_path):
    d = site(tmp_path)
    apply_edits(d, [Edit(file="index.html", old_str='<button id="a">', new_str='<button id="a" aria-label="A">')])
    assert 'aria-label="A"' in (d / "index.html").read_text()


def test_ambiguous_match_fails_cleanly(tmp_path):
    d = site(tmp_path)
    with pytest.raises(PatchError, match="matched 2"):
        apply_edits(d, [Edit(file="index.html", old_str="</button>", new_str="X</button>")])
    assert (d / "index.html").read_text() == '<button id="a"></button><button id="b"></button>'


def test_missing_match_and_missing_file(tmp_path):
    d = site(tmp_path)
    with pytest.raises(PatchError): apply_edits(d, [Edit(file="index.html", old_str="nope", new_str="x")])
    with pytest.raises(PatchError): apply_edits(d, [Edit(file="other.html", old_str="a", new_str="b")])
    with pytest.raises(PatchError): apply_edits(d, [Edit(file="../evil.html", old_str="a", new_str="b")])


def test_no_partial_write_when_second_edit_fails(tmp_path):
    d = site(tmp_path)
    with pytest.raises(PatchError):
        apply_edits(d, [Edit(file="index.html", old_str='id="a"', new_str='id="a" x'), Edit(file="index.html", old_str="zzz", new_str="y")])
    assert " x" not in (d / "index.html").read_text()


def test_parse_accepts_list_or_object():
    assert parse_patch('[{"file":"index.html","old_str":"a","new_str":"b"}]').edits[0].new_str == "b"
    assert parse_patch('{"edits":[{"file":"index.html","old_str":"a","new_str":"b"}],"rationale":"r"}').rationale == "r"
