"""Shared controls, inventory and experiment export panels."""

import csv
import io
import json
import streamlit as st
from simulator.house import HouseSimulation


def act(function, *args):
    try:
        result = function(*args)
        st.session_state.notice = "Polecenie odrzucone: węzeł jest offline." if result is False else "Zapisano działanie w symulacji."
        return result is not False
    except (ValueError, KeyError) as error:
        st.session_state.notice = str(error)
        return False


def device_controls(sim, room):
    devices = [c for c in sim.components.values() if c["room"] == room and c["kind"] != "gas"]
    if not devices:
        st.caption("Brak elementów wykonawczych w tej strefie.")
        return
    ids = [c["id"] for c in devices]
    default = next((cid for cid in ids if sim.components[cid]["kind"] == "light"), ids[0])
    cid = st.selectbox("Element wykonawczy", ids, index=ids.index(default),
                       format_func=lambda value: sim.components[value]["name"], key=f"actuator_{room}")
    c, state = sim.components[cid], sim.actuators[cid]
    st.caption(f"{cid} / {state['mode'].upper()} / {c['node']}")
    value = 0 if state["commanded"] else (110 if c["kind"] == "servo" else 1)
    label = ("Zamknij" if value == 0 else "Otwórz") if c["kind"] == "servo" else ("Wyłącz" if value == 0 else "Włącz")
    status, button = st.columns([1, 1], vertical_alignment="center")
    status.metric("Stan modelu", f"{state['simulated']}°" if c["kind"] == "servo" else "ON" if state["simulated"] else "OFF")
    button.button(label, key=f"command_{cid}", width="stretch", on_click=act, args=(sim.command, cid, value))
    if c["kind"] == "fan":
        st.button("Przywróć AUTO", key=f"auto_{cid}", width="stretch", on_click=act, args=(sim.auto_fan, cid))
    st.caption(f"Zadane: {state['commanded']} → model: {state['simulated']}. Telemetria i reguły odświeżą się w kolejnym kroku.")


def devices_view(sim):
    st.subheader("Węzły i wyposażenie")
    st.caption("Wszystkie węzły są teraz symulowane. Nazwa esp32_node oznacza przyszłą rolę urządzenia.")
    st.dataframe([{"Węzeł": node, "Łączność modelu": "online" if online else "offline",
                   "Komponenty": sum(c["node"] == node for c in sim.components.values())}
                  for node, online in sim.nodes.items()], hide_index=True, width="stretch")
    st.dataframe([{"ID": cid, "Nazwa": c["name"], "Typ": c["kind"], "Strefa": c["room"], "Węzeł": c["node"],
                   "Stan modelu": str(sim.sensors[cid]["value"] if c["kind"] == "gas" else sim.actuators[cid]["simulated"])}
                  for cid, c in sim.components.items()], hide_index=True, width="stretch")
    st.info("Podział komponentów między węzły jest zapisany w manifeście eksperymentu. Liczbę węzłów zmienisz w rozwijanej konfiguracji u góry konsoli.")


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
