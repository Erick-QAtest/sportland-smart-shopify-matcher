from datetime import date, datetime, timezone

import pytest

from smart_marketing import polls, templates, workflow


def item(status, **extra):
    return {"workflow_status": status, "topic": "Puma Softride", "channel": "WhatsApp comunidad",
            "scheduled_date": date(2026, 11, 2), **extra}


# ---------------------------------------------------------------- flujo de aprobación

def test_happy_path_requires_every_step():
    assert workflow.transition_errors(item("BORRADOR"), "EN_REVISION") == []
    assert workflow.transition_errors(item("EN_REVISION"), "APROBADO") == []
    approved = item("APROBADO", approved_at=datetime.now(timezone.utc))
    assert workflow.transition_errors(approved, "PROGRAMADO") == []
    assert workflow.transition_errors({**approved, "workflow_status": "PROGRAMADO"}, "PUBLICADO") == []
    assert workflow.transition_errors(item("PUBLICADO", approved_at=1), "MEDIDO", note="3 ventas en tienda") == []


@pytest.mark.parametrize("current", ["BORRADOR", "EN_REVISION", "DESCARTADO"])
def test_cannot_publish_without_approval(current):
    errors = workflow.transition_errors(item(current), "PUBLICADO")
    assert errors and "No se puede pasar" in errors[0]


def test_publish_is_refused_even_from_approved_if_no_approval_recorded():
    errors = workflow.transition_errors(item("APROBADO", approved_at=None), "PUBLICADO")
    assert errors == ["No se puede publicar sin una aprobación registrada."]


def test_rejection_needs_a_reason_and_measurement_needs_a_result():
    assert workflow.transition_errors(item("EN_REVISION"), "BORRADOR")
    assert workflow.transition_errors(item("EN_REVISION"), "BORRADOR", note="Falta precio") == []
    assert workflow.transition_errors(item("PUBLICADO", approved_at=1), "MEDIDO")


def test_review_needs_topic_and_channel():
    errors = workflow.transition_errors(item("BORRADOR", topic="", channel=""), "EN_REVISION")
    assert "Falta el tema de la publicación." in errors
    assert "Falta el canal." in errors


def test_measured_is_final_and_unknown_targets_are_refused():
    assert workflow.allowed_targets("MEDIDO") == ()
    assert workflow.transition_errors(item("BORRADOR"), "BORRAR")[0].startswith("Estado desconocido")


def test_editing_after_approval_requires_reopening_but_rescheduling_does_not():
    assert workflow.edit_errors(item("BORRADOR")) == []
    assert workflow.edit_errors(item("EN_REVISION")) == []
    assert "reábrela" in workflow.edit_errors(item("APROBADO"))[0]
    assert workflow.reschedule_errors(item("PROGRAMADO")) == []
    assert workflow.reschedule_errors(item("PUBLICADO"))


# ---------------------------------------------------------------- semana tipo

CAMPAIGN = {"campaign_id": 7, "name": "Comodidad diaria", "theme": "Comodidad diaria",
            "starts_on": date(2026, 11, 2), "ends_on": date(2026, 11, 8)}


def test_week_template_matches_the_plan_mix():
    drafts = templates.build_drafts(CAMPAIGN, ["WA_LOCAL", "WA_ONLINE"])
    local = [d for d in drafts if d["community_code"] == "WA_LOCAL"]
    online = [d for d in drafts if d["community_code"] == "WA_ONLINE"]
    assert [d["content_type"] for d in local].count("PRODUCTO") == 3
    assert [d["content_type"] for d in local].count("ENCUESTA") == 1
    assert [d["content_type"] for d in local].count("OFERTA") == 1
    assert [d["content_type"] for d in online].count("PRODUCTO") == 2
    assert [d["content_type"] for d in online].count("PAGOS") == 1
    # Jueves y domingo libres en la comunidad local.
    assert {d["scheduled_date"].weekday() for d in local} == {0, 1, 2, 4, 5}
    assert all(d["campaign_id"] == 7 and "Comodidad diaria" in d["topic"] for d in drafts)


def test_template_keys_are_stable_and_never_duplicate():
    a = templates.build_drafts(CAMPAIGN, ["WA_LOCAL"])
    b = templates.build_drafts({**CAMPAIGN, "campaign_id": 99, "theme": "Otra"}, ["WA_LOCAL"])
    assert [d["calendar_key"] for d in a] == [d["calendar_key"] for d in b]
    assert len({d["calendar_key"] for d in a}) == len(a)


def test_template_respects_campaign_bounds_and_unknown_communities():
    drafts = templates.build_drafts(CAMPAIGN, ["WA_LOCAL", "INSTAGRAM"], start=date(2026, 10, 1), end=date(2026, 11, 3))
    assert {d["scheduled_date"] for d in drafts} == {date(2026, 11, 2), date(2026, 11, 3)}


# ---------------------------------------------------------------- encuestas

PRICE_POLL = {"multi_select": True, "unique_voters": None}
PRICE_OPTIONS = [
    {"label": "$700–$900", "selections": 9},
    {"label": "$900–$1,200", "selections": 20},
    {"label": "$1,200–$1,500", "selections": 3},
    {"label": "Más de $1,500", "selections": 1},
]


def test_multiple_choice_selections_are_not_voters():
    s = polls.summarize(PRICE_POLL, PRICE_OPTIONS)
    assert s["total_selections"] == 33
    assert s["voters"] is None and not s["voters_known"]
    assert s["top_label"] == "$900–$1,200"
    assert any("no 33 personas" in w for w in s["warnings"])
    assert round(s["options"][1]["share_of_selections"], 4) == round(20 / 33, 4)
    assert s["options"][1]["share_of_voters"] is None


def test_known_voters_allow_share_of_people_above_100_percent_total():
    s = polls.summarize({"multi_select": True, "unique_voters": 25}, PRICE_OPTIONS)
    assert s["voters"] == 25
    assert sum(o["share_of_voters"] for o in s["options"]) > 1


def test_single_choice_uses_selections_as_voters_and_flags_mismatch():
    s = polls.summarize({"multi_select": False, "unique_voters": None}, PRICE_OPTIONS)
    assert s["voters"] == 33 and s["voters_known"]
    s = polls.summarize({"multi_select": False, "unique_voters": 30}, PRICE_OPTIONS)
    assert any("deberían sumar" in w for w in s["warnings"])


def test_poll_form_parsing_validates_options():
    form = {"opcion_label_0": ["Sí"], "opcion_sel_0": ["4"], "opcion_label_1": ["No"], "opcion_sel_1": ["-1"]}
    rows, errors = polls.parse_option_rows(form)
    assert len(rows) == 1 and any("entero" in e for e in errors)
    rows, errors = polls.parse_option_rows({"opcion_label_0": ["Solo una"], "opcion_sel_0": ["1"]})
    assert errors == ["Una encuesta necesita al menos 2 opciones."]
