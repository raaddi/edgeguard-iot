# Krok 11 — co naprawdę wiemy o ruchu bramy?

Ten krok dodaje **osobny pilot offline**: ruch mechanizmu, kontakty krańcowe
i opcjonalny syntetyczny prąd. Nie zmienia domu w Qt. Nie potrzebuje elektroniki,
brokera ani API. To podstawa danych badawczych, jeszcze bez treningu ML.

## Uruchomienie

W katalogu repozytorium, z istniejącym środowiskiem:

```powershell
.\.venv\Scripts\python.exe -m simulator.gate_pilot
```

Powstaje 12 sesji: po trzy normalne, z opóźnieniem polecenia, zatrzymaniem bramy
i uszkodzonym kontaktem otwarcia. Każda trwa 8 sekund **logicznych**, zawiera
161 próbek co 50 ms. Program nie czeka 96 sekund. Otwieranie zlecamy w 1000 ms,
zamykanie w 5000 ms. Wyniki i katalog zobaczysz w terminalu.

Wariant bez prądu, z feedbackiem przypisanym innemu węzłowi:

```powershell
.\.venv\Scripts\python.exe -m simulator.gate_pilot --sessions-per-case 1 --without-current --feedback-device-id virtual_feedback_02
```

To przypisanie logiczne, nie drugi klient MQTT ani dowód niezależnego zaufania.
Dostępne są też `--device-id`, `--seed` i `--suite-id`. Domyślnie zestaw ma nowy
UUID; istniejącego katalogu nie nadpiszemy. Limit: 1–25 sesji na przypadek.

## Wynik

- `result delay`: czas od wysłania polecenia do obsługi/odpowiedzi w modelu.
  Normalnie 50–150 ms, przy opóźnieniu 1200 ms. Powrót odpowiedzi jest natychmiastowy;
  to nie jest pomiar opóźnienia prawdziwego MQTT.
- `open seen`: czy przed poleceniem zamknięcia zaobserwowano kontakt otwarcia.
- `peak current`: największy syntetyczny prąd w amperach; `None` oznacza brak
  kanału, nie 0 A.

Zatrzymanie przy połowie otwierania i kontakt stale wskazujący brak otwarcia
mogą dać takie same kontakty w spoczynku. Prąd pomaga w **tym uproszczonym modelu**.
Pełne historie mogą dodatkowo różnić się czasem zamknięcia. Nie dowodzi to,
że czujnik rozróżni realne awarie. Po zatrzymaniu zamknięcie jest dozwolone;
nie modelujemy wszystkich rodzajów zacięcia. Parametry wymagają kalibracji fizycznej.

## Dane i osobne odpowiedzi

W ignorowanym przez Git `experiments/runs/<suite_id>/`:

| Plik | Znaczenie |
|---|---|
| `manifest.json` | Wersje modelu/danych, commit i stan zmian kodu, Python, seed, konfiguracja, sesje, status completed/failed |
| `<run_id>/observations.jsonl` | Obserwacje, próbka na linię |
| `<run_id>/events.jsonl` | Wysłanie komendy i odpowiedź; payloady walidowane kontraktami 1.0 |
| `<run_id>/ground_truth.json` | Przypadek, seed, parametry i grupa parowania; poza wejściem ML |
| `<run_id>/summary.json` | Podsumowanie obserwacji; nie predykcja ani diagnoza ML |

Format lokalny **`gate-pilot-0.1`**: `run_id`, `device_id`, `boot_id`, `mechanism_id`
identyfikują źródło; `sequence_number` liczy próbki od zera, `logical_ms` to wspólny
zegar symulacji od zera. `closed_contact` i `open_contact` to bool; `current_a`
to skończona liczba amperów albo null przy wyłączonym kanale. Wszystko jest
syntetyczne. Kontakty nie mierzą ciągłego kąta; wewnętrzny kąt nie jest eksportowany.
Identyfikatory także nie powinny być cechami detektora.

**To nie telemetria MQTT 1.0.** Ten kontrakt dopuszcza tylko `gas_signal`
w sensorach. Kolektor odrzuci rekordy pilota. Przed integracją z MQTT/ESP32/Qt
rozszerzymy kontrakt pomiarów, opiszemy zegary i przetestujemy adaptery. Osobny
pilot sprawdza sens kanałów bez łamania kolektora. Nie implementuje sieci,
jej strat, ponowień ani deduplikacji. Wspólny format komend nie oznacza testu
integracji przez broker. Wspólny zegar nie rozwiązuje synchronizacji ESP32.

## Dlaczego jeszcze nie trenujemy na tych 12 sesjach?

To test obserwowalności, nie reprezentatywny dataset. Cztery przypadki danego
seeda mają ten sam nominalny czas ruchu i szum: to kontrolowane porównanie.
`paired_group` zostaje w jednym podzbiorze także przy łączeniu zestawów.
Sama zmiana seeda nie wystarcza: potrzebne są różne legalne profile i parametry,
odrębne warunki testowe oraz kalibracja. Etykieta opisuje skonfigurowany stan
sesji, nie przedział zdarzenia; nie liczymy z niej czasu wykrycia. Wysoki wynik
na tych łatwych przypadkach byłby mało przekonujący.

Następnie: różne normalne cykle, podział sesji, cechy dostępne w chwili decyzji,
reguły i pierwszy ML. Aktywna diagnoza i wybór testów pozostają planem z
[kierunków AI](ai-directions.md). Rzeczywiste predykcje i błędy pokażemy potem w Qt.

Do samodzielnego sprawdzenia: dlaczego `accepted` nie oznacza `open_contact=True`?
Co stracisz po wyłączeniu prądu? Dlaczego `case` nie może być cechą ML?
