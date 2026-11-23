import json

from scripts.composio_catalog import check_agreement


def test_pass2_scored_only_on_apps_it_contains(tmp_path, make_row):
    catalog = [
        {"id": 1, "app": "App1", "slug": "app1", "authSchemes": ["OAUTH2"]},
        {"id": 2, "app": "App2", "slug": "app2", "authSchemes": ["API_KEY"]},
        {"id": 3, "app": "App3", "slug": "app3", "authSchemes": ["S2S_OAUTH2"]},
    ]
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

    def dump(path, rows):
        path.write_text(json.dumps([r.model_dump(mode="json") for r in rows]), encoding="utf-8")

    pass1 = tmp_path / "pass1.json"
    pass2 = tmp_path / "pass2.json"
    dump(pass1, [make_row(id=1), make_row(id=2, auth_methods=["api_key"]), make_row(id=3)])
    dump(pass2, [make_row(id=1), make_row(id=3)])

    out = tmp_path / "out.json"
    rc = check_agreement(pass1, pass2, catalog_path=catalog_path, meta_path=tmp_path / "none.json", out_path=out)

    report = json.loads(out.read_text(encoding="utf-8"))
    assert rc == 0
    assert report["pass1"]["n"] == 3
    assert report["pass2"]["n"] == 2
    # S2S_OAUTH2 maps to oauth2, so app 3 (agent says oauth2) agrees fully.
    assert report["pass2"]["covers_all"] == 2


def test_missing_pass2_file_returns_error(tmp_path, capsys):
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text("[]", encoding="utf-8")
    p1 = tmp_path / "pass1.json"
    p1.write_text("[]", encoding="utf-8")
    rc = check_agreement(p1, tmp_path / "missing.json", catalog_path=catalog_path, out_path=tmp_path / "o.json")
    assert rc == 1
    assert "not found" in capsys.readouterr().err
