# Krok 2: lokalna aplikacja z wykresem

Uwaga: ten dokument opisuje wcześniejsze ćwiczenie jednego węzła, zachowane w
`simulator/lesson_app.py`. Główna aplikacja została rozbudowana o
[wirtualną makietę i pięć działów laboratorium](smarthome-laboratory.md).
Poniższa instrukcja otwiera ćwiczenie jednego węzła. Pełne laboratorium
uruchom zgodnie z osobnym przewodnikiem podlinkowanym powyżej.

Interfejs Streamlit uruchamia się na laptopie i jest dostępny w przeglądarce
pod http://127.0.0.1:8502. Po pobraniu zależności działa bez internetu.
Nie wymaga konta, chmury, brokera MQTT ani elektroniki.

## Uruchomienie

W PowerShell, w katalogu projektu, z istniejącym środowiskiem `.venv`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-ui.txt
.\.venv\Scripts\python.exe -m streamlit run simulator/lesson_app.py --server.port 8502
```

Instalacja wymaga internetu, jeśli zależności nie są dostępne lokalnie.
Następnym razem uruchom tylko drugie polecenie.
Jeżeli nie masz środowiska, utwórz je wcześniej poleceniem `py -3.14 -m venv .venv`.
Otwórz http://127.0.0.1:8502. Osobny port pozwala równolegle uruchomić makietę
na porcie 8501. Terminal utrzymuje aplikację; Ctrl+C ją zatrzymuje.
Bezpośrednie uruchomienie Pythona nie wymaga aktywowania środowiska ani zmiany
polityki PowerShell dotyczącej plików `.ps1`. Skrypt `scripts/start-simulator.ps1`
uruchamia pełną makietę, a nie opisane tutaj ćwiczenie.

Serwer nasłuchuje tylko na 127.0.0.1. Statystyki użycia Streamlit są wyłączone.
Nie używamy zewnętrznych fontów, map ani zasobów wykresu.

## Pierwsze ćwiczenie

1. Na początku widzisz pierwszy pomiar, a odtwarzanie jest wstrzymane.
2. Klikaj **Krok +1 s**: za każdym razem powstaje jeden nowy pomiar.
3. Kliknij **Reset**, powtórz kroki i porównaj wartości.
4. Kliknij **Start**, zmień tempo, a następnie kliknij **Pauza**.
5. Zmień seed i kliknij **Zastosuj i zresetuj**. To rozpoczyna przebieg od nowa.
6. Rozwiń podgląd JSON i odszukaj identyfikator, numer próbki oraz wartość czujnika.

Przełącznik **Powiększ wahania sygnału** zawęża oś pionową z 0–1 do 0,1–0,3.
Ułatwia obserwowanie drobnych zmian; nie modyfikuje wartości pomiarów.

Zmiany wpisane w formularzu obowiązują dopiero po zastosowaniu. Reset zachowuje
ostatnio zastosowaną konfigurację. Tempo wpływa wyłącznie na odtwarzanie;
odstęp logiczny pozostaje równy jednej sekundzie. Timer przeglądarki nie jest
zegarem do pomiarów wydajności: obciążenie i nieaktywna karta mogą go spowolnić.
Nie nadrabiamy zaległych próbek seriami po powrocie do karty.

## Jak połączony jest kod

```text
normal_activity.py → session.py → lesson_app.py → wykres
                          ↓
                    telemetry.py → podgląd JSON
```

`normal_activity.py` zawiera dotychczasowy generator sygnału.
`telemetry.py` buduje ten sam format wiadomości dla CLI i interfejsu.
`session.py` przechowuje stan przebiegu i ostatnie 300 próbek; licznik jest ciągły.
`simulator/lesson_app.py` odpowiada za przyciski, ustawienia i prezentację ćwiczenia.
Stan każdej karty przeglądarki jest niezależny. Pełne odświeżenie strony może
utracić sesję. Ćwiczenie nie ma trwałego zapisu ani eksportu eksperymentu;
pełna makieta udostępnia osobno eksport JSON/CSV.
Domyślna tożsamość sesji służy ćwiczeniu, zgodnie z krokiem 1.

To nadal jeden węzeł i ilustracyjny sygnał gazowy 0–1, bez kalibracji MQ-9.
Wykres nie wykrywa anomalii i nie potwierdza sprawności fizycznego czujnika.
Wiele węzłów i kontrolowane scenariusze są dostępne w pełnej makiecie.
Integracja MQTT pozostaje kolejnym etapem projektu.

## Weryfikacja

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt -r requirements-ui.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Testy sprawdzają zgodność sygnału, ograniczenie pamięci, krokowanie, pauzę,
reset oraz zastosowanie i odrzucenie konfiguracji. Automatyczne odtwarzanie
i wygląd wykresu należy dodatkowo sprawdzić w przeglądarce.
Źródła: [instalacja Streamlit](https://docs.streamlit.io/get-started/installation/command-line),
[odświeżanie fragmentów](https://docs.streamlit.io/develop/tutorials/execution-flow/start-and-stop-fragment-auto-reruns).
