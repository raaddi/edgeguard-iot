"""Local learning interface. Run: python -m streamlit run simulator_app.py."""

import argparse
import time

import streamlit as st

from simulator.__main__ import identifier
from simulator.session import SimulationSession
from simulator.telemetry import SENSOR_ID

st.set_page_config(page_title="EdgeGuard | Laboratorium", page_icon="◈", layout="wide")

if "simulation" not in st.session_state:
    st.session_state.simulation = SimulationSession()
    st.session_state.running = False
    st.session_state.last_tick = time.monotonic()


def toggle_playback():
    st.session_state.running = not st.session_state.running
    st.session_state.last_tick = time.monotonic()


def reset():
    st.session_state.running = False
    st.session_state.simulation.reset()


with st.sidebar:
    st.markdown("### ◈ EDGEGUARD")
    st.caption("LOKALNE LABORATORIUM IoT")
    st.divider()
    st.markdown("#### Ustawienia węzła")
    with st.form("configuration"):
        device = st.text_input("Identyfikator węzła", value="virtual_node_01", max_chars=64)
        seed = st.number_input("Seed", min_value=0, max_value=2**31 - 1, value=42, step=1,
                               help="Ten sam seed odtwarza ten sam przebieg.")
        apply = st.form_submit_button("Zastosuj i zresetuj", width="stretch", key="apply")
    if apply:
        try:
            identifier(device)
        except argparse.ArgumentTypeError:
            st.error("Identyfikator: 1–64 litery ASCII, cyfry, _ lub -.")
        else:
            st.session_state.simulation = SimulationSession(int(seed), device)
            st.session_state.running = False
    speed = st.select_slider("Tempo odtwarzania", options=[0.5, 1.0, 2.0, 5.0], value=1.0,
                             format_func=lambda value: f"{value:g}×")
    st.caption("Tempo zmienia szybkość odtwarzania, nie wartości pomiarów.")
    zoom = st.toggle("Powiększ wahania sygnału", value=False,
                     help="Zawęża oś pionową do 0,1–0,3. Nie zmienia danych.")
    st.divider()
    st.markdown("**Etap 01 · Sygnał i telemetria**")
    st.caption("1 wirtualny węzeł · 1 czujnik\n\nKolejny etap: komunikacja MQTT.")

st.caption("EDGEGUARD IoT / SYMULATOR")
st.title("Twoje laboratorium IoT")
st.write("Obserwuj pomiary, zatrzymaj czas i zajrzyj do wiadomości urządzenia.")

controls = st.columns([1, 1, 1, 2])
controls[0].button("Pauza" if st.session_state.running else "Start", type="primary",
                   on_click=toggle_playback, width="stretch", key="play")
controls[1].button("Krok +1 s", on_click=st.session_state.simulation.advance,
                   disabled=st.session_state.running, width="stretch", key="step")
controls[2].button("Reset", on_click=reset, width="stretch", key="reset")
controls[3].caption("Reset odtwarza przebieg od pierwszej próbki.")


@st.fragment(run_every=0.2 if st.session_state.running else None)
def live_view():
    simulation = st.session_state.simulation
    now = time.monotonic()
    if st.session_state.running and now - st.session_state.last_tick >= 1 / speed:
        simulation.advance()
        st.session_state.last_tick = now

    current = simulation.history[-1]
    value = current["sensors"][SENSOR_ID]["value"]
    previous = simulation.history[-2]["sensors"][SENSOR_ID]["value"] if len(simulation.history) > 1 else value
    metrics = st.columns(4)
    metrics[0].metric("Sygnał gazowy · 0–1", f"{value:.4f}", f"{value - previous:+.4f}",
                      delta_color="off", border=True)
    metrics[1].metric("Czas symulacji", f"{current['sequence_number']} s", border=True)
    metrics[2].metric("Liczba próbek", str(simulation.sequence), border=True)
    metrics[3].metric("Stan", "Odtwarzanie" if st.session_state.running else "Pauza", border=True)

    with st.container(border=True):
        st.subheader("Przebieg sygnału")
        st.caption(f"{simulation.device_id} / {SENSOR_ID} · seed {simulation.seed} · ostatnie 300 próbek")
        rows = [{"seconds": message["sequence_number"],
                 "value": message["sensors"][SENSOR_ID]["value"]} for message in simulation.history]
        st.vega_lite_chart(spec={
            "data": {"values": rows},
            "height": 310,
            "mark": {"type": "line", "color": "#58DFC1", "strokeWidth": 3,
                     "point": {"filled": True, "size": 20}},
            "encoding": {
                "x": {"field": "seconds", "type": "quantitative", "title": "Czas symulacji [s]",
                      "scale": {"domain": [rows[0]["seconds"], max(rows[0]["seconds"] + 1, rows[-1]["seconds"])]}},
                "y": {"field": "value", "type": "quantitative", "title": "Sygnał [0–1]",
                      "scale": {"domain": [0.1, 0.3] if zoom else [0, 1]}},
                "tooltip": [{"field": "seconds", "title": "Sekunda"},
                            {"field": "value", "title": "Sygnał", "format": ".6f"}],
            },
        }, width="stretch")

    with st.expander("Zajrzyj do wiadomości JSON"):
        st.caption("Ten sam format tworzy program w terminalu. Wiadomość nie jest jeszcze wysyłana przez MQTT.")
        st.json(current)


live_view()
st.caption("Dane syntetyczne · umowny sygnał 0–1 · bez kalibracji MQ-9 i bez klasyfikacji ML")
with st.expander("Jak to działa? · pierwsze ćwiczenie"):
    st.markdown("""
1. Kliknij **Krok +1 s** kilka razy. Każdy klik tworzy dokładnie jeden pomiar.
2. Kliknij **Reset** i powtórz kroki. Przy tym samym seedzie zobaczysz te same wartości.
3. Zmień **seed**, zastosuj ustawienia i porównaj przebieg.
4. Kliknij **Start**, a potem **Pauza**. Tempo odtwarzania nie zmienia czasu logicznego próbek.

**Pod spodem:** generator w Pythonie → wspólny format wiadomości → wykres.
Każda próbka pamięta poprzednią wartość, wraca delikatnie w stronę 0,2 i otrzymuje małe losowe wahanie.
Wykres przechowuje ostatnie 300 próbek. Odświeżenie strony rozpoczyna nową sesję;
dane nie są jeszcze zapisywane do bazy. W nieaktywnej karcie odtwarzanie może zwolnić.
""")
