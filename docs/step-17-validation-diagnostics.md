# Krok 17: dlaczego GRU pomija zdarzenie?

Diagnostyka korzysta z zamrożonych wag, skal błędu i progu z kroku 16.
Czyta wyłącznie sesje walidacyjne; nie trenuje modelu ani nie wybiera nowego
progu. Weryfikuje źródła, ponownie oblicza prognozy i sprawdza zgodność
wyników, etykiet oraz metryk z zapisanym porównaniem.

## Uruchomienie

Potrzebne są lokalne artefakty kroków 13–16. Jeśli ich nie ma, odtwórz je
poniższymi poleceniami. To nowy przebieg: wcześniejsze wagi nie znajdują się
w Git, a zgodność liczb między środowiskami wymaga sprawdzenia.
W PowerShell, z katalogu repozytorium i istniejącym środowiskiem `.venv`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-diagnostics.txt
.\.venv\Scripts\python.exe -m ml.gate_experiment --output experiments/runs/ml-rebuilt-20261004 --groups 20 --seed 42
.\.venv\Scripts\python.exe -m ml.gate_sequence_export experiments/runs/ml-rebuilt-20261004/split.json --output experiments/runs/sequences-rebuilt-20261004
.\.venv\Scripts\python.exe -m ml.gate_gru_experiment experiments/runs/sequences-rebuilt-20261004 --output experiments/runs/gru-rebuilt-20261004 --epochs 30 --seed 42
.\.venv\Scripts\python.exe -m ml.gate_alarm_experiment experiments/runs/sequences-rebuilt-20261004 experiments/runs/gru-rebuilt-20261004 --output experiments/runs/alarms-rebuilt-20261004
```

Dotychczasowe runnery odtwarzające pilot oceniają również stary podział testowy.
To znane dane rozwojowe. Nowy runner diagnostyczny poniżej nie czyta jego sesji:

```powershell
.\.venv\Scripts\python.exe -m ml.gate_validation_diagnostics experiments/runs/sequences-rebuilt-20261004 experiments/runs/gru-rebuilt-20261004 experiments/runs/alarms-rebuilt-20261004 --output experiments/runs/diagnostics-20261004
.\.venv\Scripts\python.exe -m ml.gate_validation_plots experiments/runs/diagnostics-20261004 --output experiments/runs/diagnostic-plots-20261004
```

Katalogi wynikowe muszą być nowe. Dla własnych wcześniejszych artefaktów podaj
ich ścieżki; sekwencje, GRU i porównanie muszą pochodzić z tego samego eksperymentu.
Surowe sesje muszą być dostępne pod ścieżkami zapisanymi w podziale.

## Czytanie diagnozy

`report.json` zawiera przyczynę operacyjną dla każdego przedziału etykiety:

- `detected`: początek alarmu przypada w zdarzeniu;
- `below_threshold`: żadna próbka zdarzenia nie przekracza progu;
- `insufficient_persistence_within_event`: przekroczenia są, ale alarm nie
  zdążył rozpocząć się w zdarzeniu przy wymaganiu trzech kolejnych próbek;
- `alarm_started_before_event`: alarm jest aktywny, ale rozpoczął się wcześniej
  i zgodnie z ustaloną metryką nie wykrywa nowego zdarzenia.

Stan alarmu jest liczony przez całą sesję, bez zerowania na granicach etykiet.
Równość z progiem nie wystarcza. Zapisujemy pierwszą i ostatnią próbkę zdarzenia,
liczbę próbek, maksimum wyniku, liczbę przekroczeń i ich najdłuższą serię
wewnątrz zdarzenia. Seria może rozpocząć się przed zdarzeniem; dlatego sam jej
wewnętrzny rozmiar nie wystarcza do wyznaczenia wykrycia.

Porównanie 1/3/5 kolejnych przekroczeń to **analiza wrażliwości przy tym samym
progu**, a nie wybór lepszego wariantu. Raport obejmuje też alarmy na normalnych
sesjach, niedopasowane alarmy i opóźnienia. Przesunięcie początku alarmu może
zmienić dopasowanie do przedziału, więc mniej wymaganych próbek nie musi dać
większej liczby wykrytych zdarzeń. Etykiety pozostają poza wejściem modelu.

## Wykresy

`timelines/` zapisuje pomiary, prognozy, błędy kanałów, polecenia i alarmy.
Eksporter PNG pokazuje wszystkie sesje opóźnienia oraz normalną sesję o
najwyższym wyniku. `index.md` zawiera odnośniki do wykresów.
Na wspólnej osi czasu widać polecenia i odpowiedzi, obie krańcówki, prąd,
znormalizowane błędy oraz alarm. Szare tło oznacza etykietę dostępną tylko
ocenie. Predykcja i jej błąd są datowane chwilą otrzymania docelowego pomiaru.

Brak przekroczenia progu nie dowodzi sam w sobie przyczyny w architekturze GRU.
Może oznaczać dobrze przewidywalną nieprawidłową pracę, niewłaściwy cel prognozy
lub zbyt zachowawczy punkt pracy. Wnioski wymagają oglądu kanałów i poleceń,
a rozstrzygnięcie przyczyn — osobnego eksperymentu na walidacji.
Wyniki syntetyczne nie zastępują nowych warunków, osobnej kalibracji i testu
końcowego ani walidacji fizycznej. Integracja z Qt pozostaje dalszym krokiem.
