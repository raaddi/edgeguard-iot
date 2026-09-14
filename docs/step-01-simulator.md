# Krok 1: pierwszy generator danych

Cel: zrozumieć drogę od modelu sygnału do wiadomości JSON i uzyskać
powtarzalny wynik. To pierwszy fragment Milestone 1, nie kompletny symulator.
Wymagany Python: 3.11 lub nowszy. CI sprawdza 3.11 i 3.14.

## Uruchomienie w PowerShell

Otwórz terminal w katalogu repozytorium. Jednorazowo utwórz środowisko
i pobierz narzędzia testowe (to wymaga internetu):

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Środowisko `.venv` przechowuje zależności tego projektu. Korzystamy bezpośrednio
z jego Pythona, więc nie musisz aktywować środowiska ani zmieniać polityki PowerShell.
Jeżeli środowisko już istnieje, pomiń jego tworzenie.

```powershell
.\.venv\Scripts\python.exe -m simulator --seed 42 --samples 5
.\.venv\Scripts\python.exe -m pytest -q
```

Generator używa wyłącznie biblioteki standardowej Pythona. Po instalacji pytest
także testy działają offline. Program kończy się sam po zadanej liczbie pomiarów.

## Czytamy kod w tej kolejności

1. `simulator/normal_activity.py`: funkcja `gas_signal` generuje kolejne wartości.
2. `simulator/__main__.py`: odczyt argumentów, metadane i budowanie wiadomości.
3. `tests/test_simulator.py`: sprawdzenie powtarzalności i błędnych argumentów.

`Random(seed)` tworzy własny generator liczb pseudolosowych. Przy tym samym
seedzie, kodzie i wersji Pythona uzyskujemy ten sam przebieg. Nie korzystamy
ze współdzielonego globalnego generatora, co ułatwi późniejsze dodawanie węzłów.
Źródło: [dokumentacja Python random](https://docs.python.org/3/library/random.html).

Sygnał zaczyna od 0,2. Każda kolejna wartość zależy od poprzedniej, delikatnie
wraca w stronę 0,2 i otrzymuje losową zmianę między -0,01 a 0,01.
`yield` oddaje jedną wartość i zapamiętuje stan funkcji do następnego `next()`.
Nie musimy przechowywać całej serii w pamięci.

To ilustracyjny sygnał gazowy w skali 0–1. **Nie jest to ppm, pomiar ADC ani
skalibrowany model MQ-9.** Parametry są umowne; nie stanowią jeszcze podstawy
do wniosków o skuteczności wykrywania anomalii w fizycznym systemie.

## Wiadomości i czas

Każdy wiersz standardowego wyjścia (`stdout`) jest osobnym obiektem JSON.
Pole `sensors` zawiera komponenty identyfikowane po nazwie, np. `gas_01`.
Pozwala to rozbudować urządzenie o kolejne czujniki bez tworzenia pól
`gas_1`, `gas_2` w głównej części wiadomości.

| Pole | Znaczenie |
|---|---|
| schema_version | Robocza wersja formatu: 0.1-draft |
| device_id | Tożsamość węzła, zmieniana przez --device-id |
| boot_id | Tożsamość sesji, wyliczana z run_id i device_id |
| sequence_number | Numer wiadomości od zera, w obrębie sesji |
| timestamp | Logiczny czas pomiaru, w UTC |
| sensors | Mapa identyfikatorów czujników i ich pomiarów |

Symulacja zaczyna logicznie od 2026-01-01 00:00:00 UTC i przesuwa czas
o sekundę na pomiar. Program wypisuje całą serię od razu, bez czekania:
sekunda symulacji nie musi oznaczać sekundy działania programu.
Obsługę tempa publikacji dodamy przy MQTT.

Format jest propozycją do rozwinięcia przed integracją MQTT: pełna walidacja,
deklaracje możliwości urządzeń, brakujące pomiary, stany aktuatorów oraz czas
odbioru przez bramkę pozostają do zrobienia. Obecny program nie łączy się z brokerem.

Osobny wiersz na `stderr` zawiera metadane przebiegu: seed, konfigurację,
pochodzenie syntetyczne, pusty harmonogram scenariuszy, commit, stan zmian
w repozytorium i wersję Pythona. Nie jest to błąd programu.
Metadane nie trafiają do telemetrii ani przyszłych cech modelu.
Poza repozytorium Git identyfikator wersji może mieć wartość null.

Domyślny `run_id=lesson-01` służy powtarzaniu ćwiczenia. W przyszłych niezależnych
eksperymentach używaj nowego `--run-id`, aby sesje nie miały tych samych identyfikatorów.
Ten sam run_id i device_id odtwarzają tę samą sesję. Manifest z brudnym drzewem
Git nie odtwarza niezapisanych zmian; do badań używaj zatwierdzonej wersji kodu.

## Ćwiczenie

Uruchom polecenie z `--seed 42` dwa razy. Porównaj wartości i czasy pomiarów.
Następnie zmień seed na 43 i sprawdź, co się zmieniło, a co pozostało takie samo.
Na końcu użyj `--device-id virtual_node_02`: zmieni się tożsamość węzła,
ale przy tym samym seedzie sygnał pozostanie taki sam.
To na razie jeden węzeł na uruchomienie; niezależne strumienie wielu węzłów
dodamy w następnym etapie rozwoju symulatora.

Do przemyślenia: dlaczego do porównania dwóch algorytmów warto użyć tych samych
danych, a do końcowej oceny potrzebujemy również innych przebiegów?

## Git i następny krok

`git diff` pokazuje zmiany; commit zapisuje lokalny punkt historii;
push wysyła go na GitHub. Gałąź oddziela rozwijaną zmianę od `main`.
Pull request pozwala przejrzeć różnice oraz wyniki automatycznych testów.

Przed następnym etapem omówimy funkcję generatora i wynik ćwiczenia.
Dalej doprecyzujemy kontrakt telemetrii i uruchomimy lokalny broker MQTT.
Układ rozdziałów LaTeX pozostaje bez zmian; ta notatka będzie materiałem
pomocniczym do rozdziałów o implementacji i powtarzalności eksperymentów.
