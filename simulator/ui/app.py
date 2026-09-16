"""Local laboratory shell; the simulation model is independent of Streamlit."""

import argparse
import time
from pathlib import Path
import streamlit as st
from simulator.__main__ import code_version, identifier
from simulator.house import HouseSimulation
from simulator.ui import console, views


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
    st.set_page_config(page_title="EdgeGuard | Konsola diagnostyczna", page_icon="◈", layout="wide", initial_sidebar_state="collapsed")
    st.html(f"<style>{Path(__file__).with_name('console.css').read_text(encoding='utf-8')}</style>")
    if "lab" not in st.session_state:
        new_run()
    st.html('<div class="console-brand"><span>EG / LAB</span><h1>EDGEGUARD <em>CONSOLE</em></h1>'
            '<p>DIAGNOSTYKA SMARTHOME &nbsp; / &nbsp; SYMULACJA LOKALNA</p></div>')
    with st.expander("Konfiguracja przebiegu · seed / węzły / identyfikator"):
        st.caption("Nowy przebieg usuwa dane bieżącej sesji. Najpierw pobierz eksport z panelu Zapis przebiegu.")
        with st.form("run"):
            config = st.columns(4)
            seed = config[0].number_input("Seed", min_value=0, max_value=2**31-1, value=42)
            nodes = config[1].number_input("Węzły makiety (docelowo ESP32)", min_value=1, max_value=3, value=3)
            extra = config[2].number_input("Dodatkowe węzły wirtualne", min_value=0, max_value=9, value=0)
            run_id = config[3].text_input("Identyfikator przebiegu", value="house-demo", max_chars=64)
            if st.form_submit_button("Nowy przebieg", type="primary", key="new_run"):
                try:
                    identifier(run_id)
                    new_run(int(seed), int(nodes), int(extra), run_id)
                except (ValueError, argparse.ArgumentTypeError) as error:
                    st.error(str(error))
    controls = st.columns([1, 1, 1.4, 3], vertical_alignment="bottom")
    controls[0].button("Ⅱ Pauza" if st.session_state.lab_running else "▶ Start", key="lab_play", type="primary", on_click=toggle, width="stretch")
    controls[1].button("Krok +1 s", key="lab_step", on_click=advance, disabled=st.session_state.lab_running, width="stretch")
    speed = controls[2].selectbox("Tempo odtwarzania", [0.5, 1.0, 2.0, 5.0], index=1, format_func=lambda x: f"{x:g}×", label_visibility="collapsed")
    controls[3].caption("01 Wybierz strefę → 02 Steruj lub dodaj zdarzenie → 03 Wykonaj krok i sprawdź reakcję")

    @st.fragment(run_every=0.2 if st.session_state.lab_running else None)
    def live():
        sim = st.session_state.lab
        now = time.monotonic()
        if st.session_state.lab_running and now - st.session_state.lab_tick >= 1 / speed:
            advance()
            st.session_state.lab_tick = now
            if not st.session_state.lab_running:
                st.rerun()
        console.status_bar(sim)
        if st.session_state.notice:
            st.caption(st.session_state.notice)
        console.console_view(sim)
        with st.expander("Zapis przebiegu · JSON / CSV / odtwarzalność"):
            views.experiments_view(sim)
            st.caption("Reset usuwa bieżące dane i odtwarza ten sam seed oraz identyfikator. Najpierw pobierz eksport.")
            st.button("Reset przebiegu", key="lab_reset", on_click=reset, disabled=st.session_state.lab_running)
        with st.expander("Inwentarz · komponenty i przypisanie do węzłów"):
            views.devices_view(sim)
    live()
    st.caption("MODEL BEHAWIORALNY · dane syntetyczne · brak kalibracji MQ-9 · MQTT i fizyczne ESP32: kolejny etap")
