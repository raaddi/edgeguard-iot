"""Five work areas of the local SmartHome laboratory."""

import csv
import io
import json
import streamlit as st
from simulator.house import HouseSimulation, SCENARIOS
from simulator.ui.floorplan import floorplan


def act(function, *args):
    try:
        result = function(*args)
        st.session_state.notice = "Polecenie odrzucone: węzeł jest offline." if result is False else "Zapisano działanie w symulacji."
        return result is not False
    except (ValueError, KeyError) as error:
        st.session_state.notice = str(error)
        return False


def device_controls(sim, room):
    for c in (c for c in sim.components.values() if c["room"] == room):
        cid = c["id"]
        if c["kind"] == "gas":
            st.metric(c["name"], f"{sim.sensors[cid]['value']:.3f}")
            continue
        state = sim.actuators[cid]
        with st.container(border=True):
            st.markdown(f"**{c['name']}**")
            st.caption(f"{cid} · {state['mode']}")
            opened = state["simulated"] > 0
            value = 0 if state["commanded"] else (110 if c["kind"] == "servo" else 1)
            label = ("Zamknij" if value == 0 else "Otwórz") if c["kind"] == "servo" else ("Wyłącz" if value == 0 else "Włącz")
            status, button = st.columns([1, 1])
            status.write(("Otwarte" if opened else "Zamknięte") if c["kind"] == "servo" else ("Włączone" if opened else "Wyłączone"))
            button.button(label, key=f"command_{cid}", width="stretch", on_click=act, args=(sim.command, cid, value))
            if c["kind"] == "fan":
                st.button("Tryb automatyczny", key=f"auto_{cid}", width="stretch", on_click=act, args=(sim.auto_fan, cid))
                st.caption(f"Zadane: {state['commanded']} · model: {state['simulated']}")


def model_view(sim):
    names = {r["id"]: r["name"] for r in sim.profile["rooms"]}
    room = st.selectbox("Wybierz strefę do sterowania", list(names), index=2, format_func=names.get, key="selected_room")
    left, right = st.columns([2.2, 1])
    with left:
        st.image(floorplan(sim, room), width="stretch")
        st.caption("Rzut orientacyjny na podstawie zdjęć. Podświetlona ramka = wybrana strefa. Złote punkty = LED-y.")
        st.caption("Widok pokazuje stan modelu także przy braku łączności. Pomiarów offline nie ma w telemetrii.")
    with right:
        st.subheader(names[room])
        node = sim.room_nodes[room]
        st.caption(f"{node} · {'online' if sim.nodes[node] else 'offline'}")
        device_controls(sim, room)
    if sim.alerts:
        st.warning("Aktywne wskazania reguł: " + ", ".join(f"{a['target']}: {a['rule']}" for a in sim.alerts))


def devices_view(sim):
    st.subheader("Węzły i wyposażenie")
    st.caption("Wszystkie węzły są teraz symulowane. Nazwa esp32_node oznacza przyszłą rolę urządzenia.")
    st.dataframe([{"Węzeł": node, "Łączność modelu": "online" if online else "offline",
                   "Komponenty": sum(c["node"] == node for c in sim.components.values())}
                  for node, online in sim.nodes.items()], hide_index=True, width="stretch")
    st.dataframe([{"ID": cid, "Nazwa": c["name"], "Typ": c["kind"], "Strefa": c["room"], "Węzeł": c["node"],
                   "Stan modelu": str(sim.sensors[cid]["value"] if c["kind"] == "gas" else sim.actuators[cid]["simulated"])}
                  for cid, c in sim.components.items()], hide_index=True, width="stretch")
    st.info("Podział komponentów między węzły jest zapisany w manifeście eksperymentu. Liczbę węzłów zmienisz w konfiguracji nowego przebiegu po lewej.")


def scenarios_view(sim):
    st.subheader("Scenariusze kontrolowane")
    st.write("Zdarzenie zacznie działać od następnego kroku. Czas trwania liczymy w sekundach symulacji.")
    kind = st.selectbox("Rodzaj zdarzenia", list(SCENARIOS), format_func=SCENARIOS.get)
    targets = list(sim.nodes) if kind == "node_offline" else [cid for cid, c in sim.components.items()
                if c["kind"] == ("fan" if kind == "fan_failure" else "gas")]
    with st.form("scenario"):
        target = st.selectbox("Cel", targets)
        duration = st.slider("Czas trwania [s]", 1, 120, 20)
        if st.form_submit_button("Dodaj zdarzenie", type="primary"):
            if act(sim.inject, kind, target, duration):
                st.success("Zdarzenie zapisane. Użyj Start lub Krok +1 s.")
            else:
                st.error(st.session_state.notice)
    st.markdown("**Ćwiczenie: gaz i awaria wentylatora**")
    st.write("Dodaj wzrost sygnału dla gas_01 oraz awarię fan_01. Po jednym kroku zobaczysz rozbieżność między stanem zadanym a stanem modelu wentylatora.")
    st.caption("Wentylacja jest sterowana progiem; nie modelujemy przepływu powietrza. Utrata łączności nie zatrzymuje lokalnej automatyki węzła.")
    if sim.scenarios:
        st.dataframe([{**s, "status": "oczekuje" if sim.time-1 < s["start"] else "aktywne" if sim.time-1 < s["end"] else "zakończone"}
                      for s in sim.scenarios], hide_index=True, width="stretch")
    else:
        st.info("Brak zdarzeń — trwa zwykły przebieg sygnałów.")


def telemetry_view(sim):
    st.subheader("Telemetria i reguły")
    node = st.selectbox("Węzeł do obserwacji", list(sim.nodes))
    sensor_ids = [cid for cid, c in sim.components.items() if c["kind"] == "gas" and c["node"] == node]
    messages = [m for m in sim.history if m["device_id"] == node]
    if not sim.nodes[node]:
        st.warning("Węzeł jest offline. Poniżej ostatnie odebrane próbki, nie bieżący stan urządzenia.")
    if sensor_ids and messages:
        rows = [{"sekunda": m["sequence_number"], "czujnik": cid, "sygnal": m["sensors"][cid]["value"]}
                for m in messages[-180:] for cid in sensor_ids]
        st.vega_lite_chart(spec={"data": {"values": rows}, "height": 300,
            "mark": {"type": "line", "point": True},
            "encoding": {"x": {"field": "sekunda", "type": "quantitative", "title": "Czas symulacji [s]"},
                         "y": {"field": "sygnal", "type": "quantitative", "scale": {"domain": [0, 1]}, "title": "Sygnał [0–1]"},
                         "color": {"field": "czujnik", "type": "nominal"},
                         "tooltip": [{"field": "czujnik"}, {"field": "sekunda"}, {"field": "sygnal"}]}}, width="stretch")
    if messages:
        st.json(messages[-1], expanded=False)
    else:
        st.info("Brak wiadomości dla tego węzła.")
    st.caption(f"Wygenerowane wiadomości: {sim.message_count} · pominięte przez offline: {sim.suppressed_messages} · usunięte z bufora: {sim.evicted_messages}")
    st.dataframe(sim.alerts or [{"rule": "brak aktywnych wskazań", "target": "—"}], hide_index=True)
    st.caption("To wskazania prostych reguł oraz stan łączności znany symulatorowi. Nie są wynikiem ML ani dowodem ataku. Stan aktuatora jest symulowany, nie zmierzony sprzętowo.")


def experiments_view(sim):
    st.subheader("Eksperymenty i zapis przebiegu")
    st.write("Zapisz konfigurację, działania i dane w jednym pliku. Etykiety scenariuszy pozostają poza wiadomościami urządzeń.")
    if st.session_state.lab_running:
        st.info("Wstrzymaj symulację przyciskiem Pauza, aby przygotować spójny eksport.")
        return
    exported = sim.export(st.session_state.lab_code_version)
    st.download_button("Pobierz eksperyment JSON", json.dumps(exported, ensure_ascii=False, indent=2),
                       file_name=f"{sim.run_id}.json", mime="application/json", on_click="ignore", type="primary")
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(["device_id", "sequence_number", "timestamp", "sensor_id", "value", "unit"])
    for message in sim.history:
        for cid, sensor in message["sensors"].items():
            writer.writerow([message["device_id"], message["sequence_number"], message["timestamp"], cid, sensor["value"], sensor["unit"]])
    st.download_button("Pobierz pomiary CSV", buffer.getvalue(), file_name=f"{sim.run_id}.csv", mime="text/csv", on_click="ignore")
    if st.button("Sprawdź odtwarzalność przebiegu"):
        replay = HouseSimulation.replay(exported)
        if replay.export(st.session_state.lab_code_version) == exported:
            st.success("Odtworzono identyczny stan, telemetrię i zapis działań.")
        else:
            st.error("Wykryto różnicę w odtworzonym przebiegu.")
    st.caption("Eksport obejmuje ostatnie 3000 wiadomości i pełny dziennik maksymalnie 1000 działań. Limit przebiegu: 10 000 kroków. Utracone z bufora wiadomości są policzone w manifeście.")
    st.caption("CSV zawiera pomiary, nie metryki jakości modelu. Nie przekazuj go do eksportera tabel wyników ML bez osobnej ewaluacji.")
    with st.expander("Dziennik działań"):
        st.json(sim.actions, expanded=False)
    with st.expander("Jak będziemy się tego uczyć"):
        st.markdown("1. Makieta i ręczne sterowanie.\n2. Czujnik → próg → wentylator.\n3. Scenariusze i dane.\n4. Węzły, MQTT i zapis do bazy.\n5. Reguły, uczenie maszynowe i porównanie z fizyczną makietą.")
