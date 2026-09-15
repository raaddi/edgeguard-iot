"""Local laboratory shell; the simulation model is independent of Streamlit."""

import argparse
import time
import streamlit as st
from simulator.__main__ import code_version, identifier
from simulator.house import HouseSimulation
from simulator.ui import views


def new_run(seed=42, nodes=3, extra=0, run_id="house-demo"):
    st.session_state.lab = HouseSimulation(seed, nodes, extra, run_id)
    st.session_state.lab_running = False
    st.session_state.lab_tick = time.monotonic()
    st.session_state.lab_code_version = code_version()
    st.session_state.notice = ""


def advance():
    try:
        st.session_state.lab.step()
    except ValueError as error:
        st.session_state.lab_running = False
        st.session_state.notice = str(error)


def reset():
    sim = st.session_state.lab
    new_run(sim.seed, sim.node_count, sim.extra_nodes, sim.run_id)


def toggle():
    st.session_state.lab_running = not st.session_state.lab_running
    st.session_state.lab_tick = time.monotonic()


def main():
    st.set_page_config(page_title="EdgeGuard | Makieta SmartHome", page_icon="◈", layout="wide", initial_sidebar_state="collapsed")
    st.html('<style>.stMainBlockContainer {padding-top:2rem;padding-bottom:1rem} h1 {font-size:2rem!important}</style>')
    if "lab" not in st.session_state:
        new_run()
    with st.sidebar:
        st.markdown("### ◈ EDGEGUARD")
        st.caption("KONFIGURACJA PRZEBIEGU")
        with st.form("run"):
            seed = st.number_input("Seed", min_value=0, max_value=2**31-1, value=42)
            nodes = st.number_input("Węzły makiety (docelowo ESP32)", min_value=1, max_value=3, value=3)
            extra = st.number_input("Dodatkowe węzły wirtualne", min_value=0, max_value=9, value=0)
            run_id = st.text_input("Identyfikator przebiegu", value="house-demo", max_chars=64)
            if st.form_submit_button("Nowy przebieg", type="primary", key="new_run"):
                try:
                    identifier(run_id)
                    new_run(int(seed), int(nodes), int(extra), run_id)
                except (ValueError, argparse.ArgumentTypeError) as error:
                    st.error(str(error))
        speed = st.select_slider("Tempo", options=[0.5, 1.0, 2.0, 5.0], value=1.0, format_func=lambda x: f"{x:g}×")
        st.caption("Nowy przebieg i Reset usuwają dane bieżącej sesji. Wcześniej pobierz eksport w Eksperymentach.")
        st.divider()
        st.caption("Profil kodu inżynierskiego: 10 LED · 6 serw · 4 MQ-9 · 4 wentylatory. Rozmieszczenie jest przybliżone.")
    st.caption("EDGEGUARD IoT / WIRTUALNA MAKIETA")
    st.title("SmartHome — Twoje laboratorium")
    st.caption("Steruj domem, wywołuj zdarzenia i obserwuj dane. Wszystko lokalnie, bez elektroniki.")
    controls = st.columns([1, 1, 1, 3])
    controls[0].button("Pauza" if st.session_state.lab_running else "Start", key="lab_play", type="primary", on_click=toggle, width="stretch")
    controls[1].button("Krok +1 s", key="lab_step", on_click=advance, disabled=st.session_state.lab_running, width="stretch")
    controls[2].button("Reset", key="lab_reset", on_click=reset, width="stretch")
    controls[3].caption("Konfiguracja w panelu bocznym · czas symulacji ≠ czas pomiaru wydajności")
    page = st.radio("Obszar pracy", ["Makieta", "Urządzenia", "Scenariusze", "Telemetria", "Eksperymenty"], horizontal=True, key="lab_page", label_visibility="collapsed")

    @st.fragment(run_every=0.2 if st.session_state.lab_running else None)
    def live():
        sim = st.session_state.lab
        now = time.monotonic()
        if st.session_state.lab_running and now - st.session_state.lab_tick >= 1 / speed:
            advance()
            st.session_state.lab_tick = now
            if not st.session_state.lab_running:
                st.rerun()
        metrics = st.columns(4)
        metrics[0].metric("Czas symulacji", f"{sim.time-1} s")
        metrics[1].metric("Węzły online", f"{sum(sim.nodes.values())}/{len(sim.nodes)}")
        lights = [s for cid,s in sim.actuators.items() if sim.components[cid]['kind']=='light']
        metrics[2].metric("Oświetlenie", f"{sum(s['simulated'] for s in lights)}/{len(lights)}")
        metrics[3].metric("Wskazania reguł", len(sim.alerts))
        if st.session_state.notice:
            st.caption(st.session_state.notice)
        {"Makieta": views.model_view, "Urządzenia": views.devices_view,
         "Scenariusze": views.scenarios_view, "Telemetria": views.telemetry_view,
         "Eksperymenty": views.experiments_view}[page](sim)
    live()
    st.caption("MODEL BEHAWIORALNY · dane syntetyczne · brak kalibracji MQ-9 · MQTT i fizyczne ESP32: kolejny etap")
