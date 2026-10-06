# Prognozy czasów odpowiedzi — wyniki 06.10.2026

Wykonano [protokół kroku 20](../step-20-response-models.md), zapisany przed treningiem.
Wszystkie trzy GRU poprawiły łączny MAE normalnych czasów względem referencji median.
Wynik jest mieszany w nowych legalnych warunkach; nie oceniano jeszcze alarmów.

## Dane i pochodzenie

- Źródło: zweryfikowany eksport kroku 19, 440 sesji po 30 s.
- Normalny train: 48 sesji, 160 przykładów odpowiedzi i 27 888 sekwencji odczytów.
- Normalny selection: 24 sesje, 80 odpowiedzi i 13 944 sekwencje.
- Calibration: 48 normalnych sesji; evaluation: 320 sesji czterech przypadków.
- Normalna evaluation: 80 sesji, 368 ACK, 336 obserwowanych kontaktów,
  32 kontakty przerwane przeciwnym poleceniem oraz 46 480 celów odczytów.
- Wszystkie warianty seeda pozostają w jednej roli; okna i polecenia są skorelowane.
  Nowe seedy tego samego generatora nie tworzą końcowego testu pracy.

Runner: `387cfa290ca606368cf61493754e0608745e7bb4`, czysty katalog roboczy.
Lokalny wynik: `experiments/runs/response-models-20261006`.
Python 3.12.14, PyTorch 2.14.1+cpu, NumPy 2.5.3.

Źródłowy manifest, SHA-256: `ba2d655acfaf9f8e01e26095afa903a1be05759b81a36994b3e27da3beebf3cf`.

Kopia protokołu, SHA-256: `87a66b63c1b6111a5c02cabd850ff1f8b554fb0b396e8b05f4cb628330c398db`.

Pakiet zamrożonych modeli, SHA-256: `0172f09ce8086c7bac11bd85d84ff2c4f20711a9096b30279d7fcf21f92731a9`.

Raport, SHA-256: `fa7137123b4c2228597e15d7752405797c8fe139f6598daebf811833cdac6184`.

## Trening

Wspólne skalowanie X pochodzi wyłącznie z normalnych historii train.
Obie sieci mają GRU 16 jednostek, 40 wejść po maskach, jedną warstwę i reset
stanu dla okna. Głowica odpowiedzi ma 2 wyjścia i 2818 parametrów całego modelu;
głowica odczytów 3 wyjścia i 2835 parametrów. Każdy trening ma 30 epok.
Straty i checkpoint korzystają tylko z wcześniej określonych train/selection.
Wagi, preprocessing oraz mediany zapisano i odtworzono przed odczytem
calibration/evaluation; po ocenie sprawdzono niezmienność ich hashy.

| Seed inicjalizacji | Checkpoint odpowiedzi | Checkpoint odczytów |
|---|---:|---:|
| 7 | 30 | 25 |
| 42 | 30 | 19 |
| 73 | 27 | 17 |

Czasy samego treningu na laptopie: odpowiedzi 0,45–2,00 s, odczyty 52,20–54,70 s.
Podczas przebiegu trwały też testy; to nie kontrolowany benchmark sprzętu ani Pi.
160 odpowiedzi i 27 888 sekwencji dają różne liczby aktualizacji przy tych samych
epokach. Nie wyrównaliśmy budżetu uczenia i nie wybieramy zwycięskiej inicjalizacji.

## Normalne czasy odpowiedzi

Błędy w ms, tylko na rzeczywiście obserwowanych celach. Bias = prognoza − pomiar.
Agregaty ważą przykłady; 144 polecenia reversals mają większy udział niż 64 cycles.
Nie są to średnie średnich ani dowód istotności statystycznej.

| Metoda | MAE ACK | MAE krańcówki | RMSE krańcówki | Bias krańcówki |
|---|---:|---:|---:|---:|
| Mediany treningu | 59,10 | 375,74 | 489,65 | 14,43 |
| GRU 7 | 40,16 | 340,39 | 446,10 | -188,35 |
| GRU 42 | 52,53 | 366,48 | 523,86 | -256,31 |
| GRU 73 | 51,51 | 338,82 | 480,03 | -203,44 |

Dla GRU zakres MAE ACK to 40,16–52,53 ms, mediana inicjalizacji 51,51 ms;
krańcówka 338,82–366,48 ms, mediana 340,39 ms. GRU 42 poprawia MAE kontaktu,
ale ma gorszy RMSE od referencji: 523,86 vs 489,65 ms. Sama jedna miara ukrywa
większe błędy i systematyczne niedoszacowanie.

| Normalny warunek | Mediany: MAE krańcówki | GRU 7 | GRU 42 | GRU 73 |
|---|---:|---:|---:|---:|
| cycles | 168,75 | 174,42 | 155,07 | 157,96 |
| repeats | 226,04 | 164,29 | 156,52 | 130,71 |
| slow | 756,25 | 692,98 | 919,77 | 674,17 |
| reversals | 404,91 | 384,69 | 351,08 | 428,94 |

W slow GRU 42 pogarsza także ACK: 150,62 vs 146,88 ms referencji.
Wszystkie trzy modele zaniżają czas kontaktu w slow o średnio 674–920 ms.
GRU 7 przegrywa kontakt w cycles, a GRU 73 w reversals. To legalne zachowanie,
więc niskie przewidywane czasy mogą utrudnić późniejsze ograniczenie fałszywych alarmów.
Nie zmieniamy teraz hiperparametrów na podstawie evaluation. Idle ma zero
prognoz odpowiedzi, lecz pozostaje w raporcie i porównaniu odczytów.

## Odczyty +50 ms — osobne jednostki i cele

Normalne 80 sesji: 46 480 celów na kanał. Brier dotyczy prawdopodobieństw,
MAE prądu amperów; nie porównujemy tych liczb z MAE czasów.

| Metoda | MAE prądu [A] | Brier closed | Brier open |
|---|---:|---:|---:|
| Ostatni odczyt | 0,016085 | 0,006885 | 0,005508 |
| GRU 7 | 0,015874 | 0,010341 | 0,008407 |
| GRU 42 | 0,017159 | 0,010254 | 0,006752 |
| GRU 73 | 0,017816 | 0,015492 | 0,009430 |

Brier obu krańcówek jest gorszy dla wszystkich GRU niż dla ostatniego odczytu.
GRU trafia więcej samych zmian, lecz popełnia też błędy na niezmienionych próbkach.
W slow trafia wszystkie momenty zmian przy progu 0,5, a jednocześnie daje
297–374 błędnych stanów closed i 313–364 open poza chwilami zmian.
Raportowanie wyłącznie trafień przejść zawyżyłoby obraz jakości.

## Usterki, cenzura i audyt

Evaluation wszystkich przypadków: 1472 ACK i 992 obserwowane / 480 cenzurowane
kontakty. Cenzury `superseded` nie zamieniamy na czas końca ani etykietę awarii.
W motion_stall i open_contact_stuck_low po 208 z 368 celów kontaktu jest
cenzurowanych; MAE opisuje tylko pozostałe 160 ukończonych celów każdego przypadku.
Na opóźnionym ACK GRU ma resztę około −1040..−1049 ms, a mediana −1050 ms.
To różnica prognozy od późniejszej obserwacji, bez zmierzonej skuteczności alarmu.

Sprawdzono 803 hashe modeli, konfiguracji, prognoz i metadanych. Zapisano prognozy
dla 392 sesji selection/calibration/evaluation: 1712 poleceń i 227 752 celów
odczytów. Wszystkie normalne MAE odpowiedzi przeliczono niezależnie z zapisanych
prognoz, a nie z podsumowań. Testy sprawdzają odroczony dostęp do oceny,
maski cenzury, deterministyczność, roundtrip wag, integralność i puste sesje.
Lokalnie: 462 testy i 8 podtestów zaliczone, 7 pominiętych;
`tests/test_mqtt_path.py` wyłączono lokalnie. Integrację MQTT sprawdza CI.

## Odtworzenie i dalszy krok

Po zainstalowaniu `requirements-gru.txt`, z nowym katalogiem wyjściowym:

~~~powershell
.\.venv\Scripts\python.exe -m ml.gate_response_experiment experiments/runs/response-examples-20261006 --output experiments/runs/response-models-new
~~~

Jeśli brak źródła, odtwórz je komendą eksportera kroku 19. Runner odmawia
nadpisania i zachowuje manifest `failed` po błędzie. Kopia protokołu zachowuje
wersję sprzed dopisania tego raportu. Wagi, dane i prognozy pozostają poza Git.

Kolejny eksperyment ma zamrozić przyczynowe timeouty i marginesy na osobnej
normalnej kalibracji, a potem porównać detekcję i fałszywe alarmy na wspólnej
ekspozycji. Prognoza czasu musi powstać przy poleceniu, a alarm korzystać
z upływającego czasu. Qt na żywo, końcowy test pracy, walidacja fizyczna
i pomiary Raspberry Pi nadal wymagają osobnej implementacji i dowodów.
