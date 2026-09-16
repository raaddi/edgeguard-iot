"""Cohesive diagnostic workspace. All state changes go through the house model."""

from html import escape
import streamlit as st
from simulator.house import SCENARIOS
from simulator.ui.floorplan import floorplan
from simulator.ui.views import act, device_controls

RULES = {"gas_threshold": "Przekroczony próg sygnału", "actuator_mismatch": "Stan zadany ≠ stan modelu",
         "simulated_link_loss": "Brak łączności w modelu"}


def heading(number, label):
    st.html(f'<div class="panel-heading"><span>{number}</span>{escape(label)}</div>')


def status_bar(sim):
    fields = [("SESJA", "PRACA" if st.session_state.lab_running else "PAUZA", "accent"),
              ("CZAS LOGICZNY", f"{sim.time - 1:05d} s", ""),
              ("WĘZŁY MODELU ONLINE", f"{sum(sim.nodes.values())} / {len(sim.nodes)}", "good"),
              ("AKTYWNE WSKAZANIA", str(len(sim.alerts)), "accent" if sim.alerts else "good"),
              ("WIADOMOŚCI ŁĄCZNIE", str(sim.message_count), "")]
    st.html('<div class="console-status">' + ''.join(
        f'<div><small>{label}</small><strong class="{style}">{value}</strong></div>'
        for label, value, style in fields) + '</div>')


def signal_view(sim, sensor):
    node = sim.components[sensor]["node"]
    value = sim.sensors[sensor]["value"]
    threshold = sim.profile["threshold"]
    style = "warn" if value > threshold else ""
    st.html(f'<div class="signal-reading {style}"><strong>{value:.3f}</strong><small>SYGNAŁ / 0–1</small></div>'
            f'<div class="signal-track"><i style="width:{value * 100:.2f}%"></i>'
            f'<b style="left:{threshold * 100:.2f}%"></b></div>')
    st.caption(f"Stan modelu · próg reguły {threshold:.3f} · skala umowna, nie ppm")
    messages = [m for m in sim.history if m["device_id"] == node]
    if not sim.nodes[node]:
        st.warning("OFFLINE · wskaźnik pokazuje model; wykres zachowuje ostatnie wiadomości.")
    # A null row for a missing logical second prevents a line across offline gaps.
    recent = {m["sequence_number"]: m["sensors"][sensor]["value"] for m in messages[-180:]}
    start = max(0, sim.time - 180)
    rows = [{"czas": tick, "sygnał": recent.get(tick)} for tick in range(start, sim.time)]
    st.vega_lite_chart(spec={"data": {"values": rows}, "height": 175,
        "layer": [
            {"mark": {"type": "line", "point": True, "color": "#65d7c3", "invalid": "break-paths-show-domains"},
             "encoding": {"x": {"field": "czas", "type": "quantitative", "title": "Czas symulacji [s]"},
                          "y": {"field": "sygnał", "type": "quantitative", "scale": {"domain": [0, 1]}, "title": "Telemetria [0–1]"},
                          "tooltip": [{"field": "czas"}, {"field": "sygnał"}]}},
            {"data": {"values": [{"próg": threshold}]},
             "mark": {"type": "rule", "color": "#f5b544", "strokeDash": [5, 4]},
             "encoding": {"y": {"field": "próg", "type": "quantitative"}}}
        ]}, width="stretch")
    fans = [cid for cid, c in sim.components.items() if c.get("sensor") == sensor]
    for cid in fans:
        state = sim.actuators[cid]
        st.caption(f"{cid} / {state['mode'].upper()} · zadane {state['commanded']} → model {state['simulated']}")
    return messages


def scenario_controls(sim, sensor, node):
    heading("04", "TEST ZACHOWANIA")
    kind = st.selectbox("Zdarzenie", list(SCENARIOS), format_func=SCENARIOS.get, key="scenario_kind")
    targets = list(sim.nodes) if kind == "node_offline" else [cid for cid, c in sim.components.items()
                if c["kind"] == ("fan" if kind == "fan_failure" else "gas")]
    preferred = node if kind == "node_offline" else sensor
    if kind == "fan_failure":
        preferred = next((cid for cid in targets if sim.components[cid].get("sensor") == sensor), targets[0])
    # Context-specific widget keys prevent a stale target after switching zone/signal.
    target = st.selectbox("Cel zdarzenia", targets, index=targets.index(preferred),
                          key=f"target_{kind}_{sensor}")
    duration = st.select_slider("Czas zdarzenia [s]", [5, 10, 20, 30, 60, 120], value=20, key="scenario_duration")
    st.button("＋ Dodaj zdarzenie", key="inject_scenario", width="stretch", on_click=act,
              args=(sim.inject, kind, target, duration))
    st.caption("Zaczyna się w następnym kroku. Gaz + awaria odpowiedniego wentylatora pokażą rozbieżność stanów.")


def action_log(sim):
    heading("05", "DZIENNIK POLECEŃ I SCENARIUSZY / OSTATNIE 8")
    lines = []
    for action in reversed(sim.actions[-8:]):
        target = action["target"]
        if action["type"] == "scenario":
            label = f"ZAPLANOWANO / {SCENARIOS[action['kind']]} / {target} / {action['end'] - action['start']} s"
        else:
            accepted = "PRZYJĘTO" if action["accepted"] else "ODRZUCONO — OFFLINE"
            value = "AUTO" if action["type"] == "auto" else str(action["value"])
            label = f"{accepted} / {target} → {value}"
        lines.append(f'<div><time>krok {action["at_step"]:05d}</time><span>{escape(label)}</span></div>')
    st.html('<div class="event-log">' + (''.join(lines) or '<span>Gotowy. Wybierz strefę, wydaj polecenie lub dodaj zdarzenie.</span>') + '</div>')


def console_view(sim):
    names = {r["id"]: r["name"] for r in sim.profile["rooms"]}
    if sim.extra_nodes:
        names["virtual"] = "Dodatkowe węzły wirtualne"
    if st.session_state.get("selected_room") not in names:
        st.session_state.selected_room = "garage"
    room = st.selectbox("Strefa robocza — makieta, odczyty i sterowanie", list(names),
                        format_func=names.get, key="selected_room")
    with st.container(key="workspace"):
        model, monitor, controls = st.columns([1.05, 1.25, 1], gap="medium")
        with model, st.container(border=True):
            heading("01", "MAPA INSTALACJI")
            st.image(floorplan(sim, room), width="stretch")
            st.caption("Bursztynowa ramka: wybrana strefa. Rzut orientacyjny; pokazuje stan modelu także offline.")
            if room == "virtual":
                st.caption("Dodatkowe węzły działają poza makietą.")
        with monitor, st.container(border=True):
            heading("02", "PODGLĄD SYGNAŁU")
            sensors = [cid for cid, c in sim.components.items() if c["kind"] == "gas" and c["room"] == room]
            if not sensors:
                st.caption("Ta strefa nie ma czujnika gazu. Poniżej wybierz sygnał referencyjny z innej strefy.")
                sensors = list(sim.sensors)
            sensor = st.selectbox("Kanał pomiarowy", sensors,
                                  format_func=lambda cid: f"{cid} · {sim.components[cid]['name']}", key=f"signal_{room}")
            node = sim.components[sensor]["node"]
            st.caption(f"{node} · telemetria syntetyczna")
            messages = signal_view(sim, sensor)
            st.divider()
            st.markdown("**Aktywne wskazania reguł · cały dom**")
            if sim.alerts:
                for alert in sim.alerts:
                    st.caption(f"⚠ {alert['target']} · {RULES[alert['rule']]}")
            else:
                st.caption("● Brak aktywnych wskazań")
            st.caption("Reguły liczone na kroku symulacji. To jeszcze nie detekcja ML ani ocena cyberataku.")
            with st.expander("Ostatnia wiadomość JSON · wybrany kanał"):
                if messages:
                    st.json(messages[-1], expanded=False)
                else:
                    st.caption("Brak wiadomości w buforze.")
        with controls, st.container(border=True):
            heading("03", "STEROWANIE STREFĄ")
            device_controls(sim, room)
            st.divider()
            scenario_controls(sim, sensor, node)
    pending = [s for s in sim.scenarios if s["end"] > sim.time - 1]
    if pending:
        with st.expander(f"Harmonogram zdarzeń · aktywne / oczekujące: {len(pending)}", expanded=True):
            st.dataframe([{"Zdarzenie": SCENARIOS[s["kind"]], "Cel": s["target"],
                           "Status": "oczekuje" if sim.time - 1 < s["start"] else "aktywne",
                           "Start [s]": s["start"], "Koniec [s] (wyłączny)": s["end"]} for s in pending],
                          hide_index=True, width="stretch")
    action_log(sim)
    st.caption(f"Bufor: {len(sim.history)} wiadomości · pominięte offline: {sim.suppressed_messages} · usunięte z bufora: {sim.evicted_messages}")
