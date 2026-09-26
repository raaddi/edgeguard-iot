# Krok 12 — obserwacje zamieniamy w wejścia ML

Stan 27.09.2026: działa wyliczanie i eksport cech dla pilota bramy. Model nie
jest jeszcze trenowany. Cechy to liczby opisujące stan i historię dostępną
detektorowi, np. „wysłano otwarcie 300 ms temu, odpowiedź przyszła po 50 ms,
kontakt otwarcia nadal nieaktywny”. Samo wyliczanie tych liczb nie jest ML.

## Uruchomienie bez sprzętu

Z katalogu repozytorium wykonaj kolejno, używając nowych nazw katalogów:

```powershell
.\.venv\Scripts\python.exe -m simulator.gate_pilot --suite-id lesson-features --profile standard
.\.venv\Scripts\python.exe -m ml.gate_split experiments/runs/lesson-features --output experiments/runs/lesson-features/split.json
.\.venv\Scripts\python.exe -m ml.gate_feature_export experiments/runs/lesson-features/split.json --output experiments/runs/lesson-features-export
```

Pierwsza komenda generuje 12 sesji. Druga dzieli trzy grupy na trening,
walidację i test. Trzecia zapisuje **20 cech, 9 sesji i 1449 wierszy**;
trzy warianty usterek z grupy treningowej są wyłączone. Jeden normalny przebieg
treningowy wystarcza do sprawdzenia narzędzia, nie do oceny jakości modelu.
Kolejne uruchomienia wymagają nowych nazw; istniejących wyników nie nadpisujemy.
Kilka profili należy najpierw połączyć w jednym planie podziału, zgodnie z
[krokiem 11](step-11-gate-pilot.md).

## Co jest wejściem modelu

Każdy wiersz ma `logical_ms` do wyrównywania czasu i słownik **`x`** z cechami.
Uczymy wyłącznie na wybranych polach `x`, nie na nazwach katalogów, identyfikatorach,
etykietach ani absolutnym numerze próbki. Wersja: `gate-features-1`.

| Pola w `x` | Znaczenie i jednostka |
|---|---|
| `closed_contact`, `open_contact` | Aktualne stany kontaktów, 0/1 |
| `current_a`, `current_missing` | Bieżący prąd [A] albo null; maska braku 0/1 |
| `current_mean_a`, `current_max_a` | Średnia i maksimum z dostępnych pomiarów w oknie [A]; null, gdy nie ma pomiarów |
| `current_available_fraction`, `sample_coverage` | Udział dostępnych pomiarów prądu i wszystkich próbek względem oczekiwanej siatki 50 ms |
| `history_span_ms` | Nominalna rozpiętość okna od początku sesji, maks. window_ms−50; informacja o rozgrzewaniu historii, nie dowód kompletności |
| `sample_gap_ms` | Odstęp od poprzedniej dostępnej próbki [ms]; null przy pierwszej |
| `contact_transitions` | Liczba zaobserwowanych zmian obu kontaktów w oknie, bez łączenia odczytów przez lukę |
| `commands_in_window`, `pending_commands` | Liczba wysłanych poleceń w oknie oraz poleceń jeszcze bez odpowiedzi w sesji |
| `last_command_degrees`, `command_age_ms` | Ostatnia wysłana nastawa i czas od jej wysłania [ms]; null przed pierwszą |
| `last_result_delay_ms`, `last_result_accepted` | Opóźnienie ostatniej odpowiedzi względem jej polecenia [ms] i zaakceptowanie 0/1; null przed odpowiedzią |
| `accepted_target_degrees`, `accepted_target_age_ms` | Ostatnia zaakceptowana nastawa i czas od akceptacji [ms]; odrzucenie nowej komendy ich nie zmienia |
| `target_contact_delay_ms` | Czas od ostatniej akceptacji do pierwszego dostępnego odczytu pasującego kontaktu; null, dopóki go nie zobaczymy |

Domyślne okno to **(t−1000 ms, t]**, czyli maksymalnie 20 próbek. Zmiana:
`--window-ms 2000`. Początek jest wyłączony, koniec włączony. Okno nie przekracza
granic sesji ani części podziału. Stan ostatnich poleceń/odpowiedzi jest pamiętany
także poza oknem; agregaty prądu, przejść i licznik poleceń dotyczą tylko okna.
Wartość `last_result_delay_ms` dotyczy ostatniej odebranej odpowiedzi, która nie
musi odpowiadać najnowszemu wysłanemu poleceniu.

Przy dłuższej luce nie rekonstruujemy przejść kontaktów. `target_contact_delay_ms`
oznacza moment **zaobserwowania**, nie dokładny czas fizycznego ruchu. Może wynieść
zero, gdy brama była już w żądanej pozycji; po nowej akceptacji pomiar zaczyna się
od nowa. Osiągnięcie kontaktu nie dowodzi bezpieczeństwa ani intencji sterowania.

## Jak chronimy poprawność badania

- Dla chwili t dostępne są tylko próbki i zdarzenia z czasem ≤ t. Test porównuje
  wynik dla uciętej historii z początkiem pełnego przebiegu; zmiana przyszłego
  pomiaru nie zmienia dawnych cech. Zdarzenia z t poprzedzają próbkę z t,
  zgodnie z kolejnością w pilocie.
- Eksporter czyta `observations.jsonl` i `events.jsonl`, nie `ground_truth.json`.
  Etykiety pozostają tylko w kopii planu podziału. Liczymy cechy również dla
  walidacji/testu, ale nie dopasowujemy na nich skalera ani uzupełniania braków.
- Null nie jest zerem. Są maski i pokrycie okna. Dobór imputacji, skalowania,
  progów i modelu będzie osobnym etapem; parametry preprocessingu dopasujemy
  wyłącznie do treningu.
- `x(t)` zawiera aktualne pomiary. Dla przyszłego predyktora GRU trzeba jawnie
  dobrać późniejszy cel; nie wolno oceniać przewidywania pomiaru t, podając go
  jednocześnie na wejściu. Tego treningu ani budowy etykiet tu jeszcze nie ma.
- Obsługujemy tylko jedną sesję pilota na wywołanie: siatkę 50 ms, jeden mechanizm,
  nastawy 0/110 i jedno źródło komend. Feedback może mieć inny identyfikator węzła.
  Odrzucamy mieszane sesje, błędne rekordy, niefinitywne liczby, powtórzone klucze
  JSON, nieuporządkowany czas i niepasujące odpowiedzi. Ten adapter nie obsługuje
  jeszcze duplikatów MQTT, osieroconych odpowiedzi ani różnych zegarów sprzętu.

## Wyniki i odtwarzalność

W katalogu eksportu są `train/`, `validation/`, `test/`: jeden plik JSONL na
sesję. `manifest.json` zawiera wersję i kolejność cech, okno, commit, liczbę
wierszy i SHA-256 odczytanych danych. `source-split.json` to dokładna kopia
planu. Eksporter sprawdza zgodność jego przydziałów z regułą grupowania.
Status musi być `completed`; po błędzie powstaje `failed` i częściowych plików
nie należy używać. Dane są ignorowane przez Git; źródła i testy są wersjonowane.

Skróty wiążą eksport z danymi odczytanymi **teraz**, nie dowodzą, że dane nie
zmieniły się od utworzenia wcześniejszego splitu. Nie modyfikujemy zamrożonych
eksperymentów. Limit adaptera to 10 000 próbek i 1000 zdarzeń na sesję, 8 MiB
na plik oraz 1000 sesji na eksport. Nie jest to jeszcze generator wielu lat.

**Następny etap:** poszerzyć trening o legalne profile/parametry, przygotować
reguły odniesienia i pierwszy trening Isolation Forest. Potem predykcja
sekwencyjna, rzetelne porównanie oraz pokaz wyników i błędów w Qt. Fizyczna
kalibracja i test na Raspberry Pi nadal są wymagane; syntetyczne wyniki ich
nie zastępują.
