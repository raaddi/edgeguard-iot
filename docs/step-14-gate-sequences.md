# Krok 14: historia pomiarów i przewidywanie następnego odczytu

## Co już działa

`ml.gate_sequences.iter_sequences` przygotowuje przykłady predykcyjne z jednej
sesji pilota bramy. To przygotowanie danych, jeszcze nie trening GRU ani
integracja z pulpitem. Wersja formatu: `gate-sequences-1`.

Domyślnie jeden przykład wygląda tak:

| Część | Czas logiczny | Zawartość |
|---|---|---|
| Wejście `x` | 0, 50, …, 950 ms | 20 kolejnych zestawów 20 cech obserwowanych do danej chwili |
| Chwila prognozy | 950 ms | Ostatnia chwila dostępna modelowi |
| Cel `y` | 1000 ms | Dwie krańcówki i prąd silnika |

Polecenie wysłane w 1000 ms nie może znaleźć się we wejściu prognozy z 950 ms.
Nie znamy przyszłego harmonogramu. Taka legalna, nowa komenda może powodować
błąd predykcji — sam błąd nie dowodzi awarii ani ataku.

20 próbek co 50 ms to okno `(t - 1000 ms, t]`; między pierwszą i ostatnią
próbką jest 950 ms. `history_samples` i `horizon_samples` przyjmują całkowite
wartości 1–200. Horyzont 5 oznacza prognozę o 250 ms naprzód, a nie pięć
kolejnych wyjść. Domyślne 50 ms jest punktem startowym, nie wynikiem optymalizacji.

## Jak unikamy przecieku danych

1. Najpierw dzielimy całe sesje według istniejącego planu grup seedów.
   Dopiero w każdej sesji tworzymy okna. Nigdy nie losujemy okien do podziałów.
2. Funkcja odrzuca mieszanie sesji i źródeł, korzystając z walidacji pilota.
3. Wszystkie wejścia powstają z obserwacji i poleceń dostępnych do chwili prognozy.
   Przyszły odczyt trafia osobno do `y`. Etykiety usterek nie są wejściem.
4. Przykład pomijamy, jeśli brakuje próbki w jego historii lub drodze do celu.
   Nie sklejamy odczytów oddzielonych luką, udając regularne próbkowanie.
5. Brak prądu zostaje `null`, nie zerem. Na tym etapie niczego nie dopasowujemy
   ani nie uzupełniamy. Przyszłe skalowanie/imputacja będą uczone tylko na treningu;
   brakujący cel wymaga maski w funkcji straty i w ocenie.

Cechy agregowane nadal mają własne okno 1000 ms opisane w
[kroku 12](step-12-gate-features.md). Dlatego wejście zawiera również podsumowanie
przeszłości sprzed pierwszego wiersza sekwencji, zawsze z tej samej sesji.
To nie jest deklaracja, że całkowity dostęp do historii wynosi dokładnie sekundę.
Test prefiksu i zmiana przyszłego odczytu sprawdzają przyczynowość wejść.

## Ćwiczenie bez elektroniki

W Pythonie uruchomionym w katalogu repozytorium:

```python
from simulator.gate_pilot import simulate_session
from ml.gate_sequences import iter_sequences

observations, events, _ = simulate_session(
    seed=42, case="normal", run_id="sequence-demo"
)
examples = list(iter_sequences(observations, events))
print(len(examples))                 # 141 z sesji zawierającej 161 próbek
print(examples[0]["prediction_ms"])  # 950
print(examples[0]["target_ms"])      # 1000
print(examples[0]["y"])
```

## Eksport i prosta prognoza odniesienia

Eksporter działa na zapisanym `split.json`, zachowując istniejący podział.
Jeżeli masz lokalny wynik pierwszego eksperymentu, w PowerShell uruchom:

```powershell
.\.venv\Scripts\python.exe -m ml.gate_sequence_export experiments/runs/ml-first-20260928-verified/split.json --output experiments/runs/gate-sequences-01
```

Na innym komputerze najpierw wygeneruj własny pilot według [kroku 13](step-13-first-ml.md)
i podaj jego `split.json`. Plan zawiera lokalne ścieżki do surowych sesji.
Katalog docelowy musi być nowy; eksport nie nadpisuje wcześniejszych wyników.
Parametry `--history-samples 20 --horizon-samples 5` pozwalają jawnie zmienić
konfigurację. Nie dobieramy jej na podstawie końcowego testu.

Wynik obejmuje:

- `train/`, `validation/`, `test/`: JSONL osobno dla każdej sesji; pola wejściowe
  `x`, przyszłe cele `y`, czasy i osobne pole `persistence` z prognozą referencji;
- `manifest.json`: wersje, konfiguracja, status, liczby przykładów, commit i sumy
  SHA-256 źródeł/wyjść; `completed` oznacza ukończony eksport, `failed` nie;
- `source-split.json`: dokładną kopię podziału; scenariusze awarii z grup
  treningowych pozostają wykluczone;
- `persistence-report.json`: wyniki osobno dla każdego podziału i rodzaju przypadku.

Eksport ma limit 100 000 przykładów. Powtarza nakładające się okna w czytelnym
JSONL, więc zajmuje więcej miejsca niż surowe sesje. To format małego pilota,
nie magazyn wieloletniej telemetrii. Dane i raporty pozostają w ignorowanym
`experiments/runs/`, a na GitHub trafiają kod, testy i instrukcje.

Dla pierwszego pilota z 20 grupami seedów eksport domyślny daje 24 816 przykładów
ze 176 sesji: 6768 treningowych, 9024 walidacyjnych i 9024 testowych. To okna
nakładające się, nie 24 816 niezależnych eksperymentów. JSONL zajmuje około 256 MiB.

Referencja kopiuje ostatni odczyt każdego kanału, bez treningu i imputacji.
Raport podaje **MAE/RMSE prądu w amperach** oraz **odsetek błędów krańcówek**.
Brak celu lub brak przewidywania wyklucza parę z metryki danego kanału;
oba rodzaje braków są jawnie policzone. Brak par daje `null`, nigdy zero błędu.
Nie sumujemy błędów o różnych jednostkach w jeden wynik.

Przy prognozie o 50 ms taka referencja może być bardzo mocna, bo większość
próbek nie zawiera zmiany stanu. Raport pokazuje więc `target_changes` i
`unchanged_pairs` krańcówek. Dla tej konkretnej referencji każda zmiana względem
ostatniego wejścia jest błędem; duży udział bezruchu może dawać pozornie świetną
średnią. Te liczniki nie mierzą wykrytych usterek, ataków ani alarmów.

## Następny etap

Trening GRU i porównanie prognoz opisuje [krok 15](step-15-first-gru.md).
Dobór progu alarmowego na walidacji, ocena zdarzeń i pokazanie wyników w Qt
pozostają kolejnymi etapami. Mniejsze błędy prognozy nie gwarantują lepszej detekcji anomalii.
Pilotażowe seedy i cztery znane profile nie zastępują nowych warunków testowych
ani pomiarów na sprzęcie. Wcześniej obejrzany test pierwszego eksperymentu jest
zbiorem rozwojowym dla kolejnych decyzji; potrzebny będzie świeży test końcowy.
