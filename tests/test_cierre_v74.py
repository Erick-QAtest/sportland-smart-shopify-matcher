from datetime import datetime, timedelta, timezone
import json
import os

from smart_portal.cierre_v74 import render_cierre_panel, request_path, request_run

NOW = datetime(2026, 10, 16, 23, 0, tzinfo=timezone.utc)


def write_status(root, **fields):
    path = root / "logs" / "ops" / "latest_daily_status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fields), encoding="utf-8")


def test_request_writes_the_trigger_file(tmp_path):
    write_status(tmp_path, status="OK", started_at=(NOW - timedelta(hours=8)).isoformat(), finished_at=(NOW - timedelta(hours=7)).isoformat())
    assert request_run(tmp_path, actor="socio", now=NOW) == "solicitado"
    assert json.loads(request_path(tmp_path).read_text())["actor"] == "socio"


def test_no_second_run_while_one_is_running(tmp_path):
    write_status(tmp_path, status="RUNNING", started_at=(NOW - timedelta(minutes=5)).isoformat(), updated_at=(NOW - timedelta(minutes=1)).isoformat())
    assert request_run(tmp_path, actor="socio", now=NOW) == "en_curso"
    assert not request_path(tmp_path).exists()


def test_stale_running_status_does_not_block_forever(tmp_path):
    write_status(tmp_path, status="RUNNING", started_at=(NOW - timedelta(hours=9)).isoformat(), updated_at=(NOW - timedelta(hours=8)).isoformat())
    assert request_run(tmp_path, actor="socio", now=NOW) == "solicitado"


def test_double_click_does_not_request_twice(tmp_path):
    write_status(tmp_path, status="OK", started_at=(NOW - timedelta(hours=8)).isoformat())
    real_now = datetime.now(timezone.utc)
    assert request_run(tmp_path, actor="socio", now=real_now) == "solicitado"
    assert request_run(tmp_path, actor="socio", now=real_now + timedelta(seconds=5)) == "ya_solicitado"
    # Pasado el margen se puede volver a pedir.
    old = (real_now - timedelta(minutes=10)).timestamp()
    os.utime(request_path(tmp_path), (old, old))
    assert request_run(tmp_path, actor="socio", now=real_now) == "solicitado"


def test_panel_shows_state_and_disables_button_while_running(tmp_path):
    write_status(tmp_path, status="RUNNING", started_at=NOW.isoformat(), updated_at=NOW.isoformat(), current_step="3/8 <Demand>")
    html = render_cierre_panel(tmp_path, csrf_token="tok", return_to="/registro", now=NOW)
    assert "disabled" in html and "&lt;Demand&gt;" in html and "<Demand>" not in html
    write_status(tmp_path, status="FAILED", failed_step="7/8 PostgreSQL Backup", finished_at=NOW.isoformat())
    html = render_cierre_panel(tmp_path, csrf_token="tok", return_to="/registro", message_key="solicitado", now=NOW)
    assert "falló en 7/8 PostgreSQL Backup" in html and "el cierre del día empezó" in html
    assert "<button type=\"submit\">" in html
