# Krok 10 — trwała historia poleceń i odpowiedzi

Kolektor zapisuje teraz trzy strumienie: telemetrię, polecenia oraz wyniki
poleceń. Historia sterowania jest dostępna przez API. Nie dodajemy jeszcze
treningu ML ani przycisków sterujących przez MQTT w Qt.

## Dlaczego zapisujemy powtórzenia

Odbiornik poleceń i kolektor mają inne zadania:

- **Odbiornik węzła** nie wykonuje drugi raz tego samego polecenia. Odsyła
  zapamiętany wynik; inna treść pod tym samym ID oznacza konflikt.
- **Kolektor** zapisuje każde odebranie poprawnej wiadomości jako osobną
  obserwację. Zachowuje powtórzenia i sprzeczne treści. To materiał do badania
  komunikacji; nie zgaduje, że kolejne odebranie oznacza kolejne wykonanie.

Telemetria nadal jest deduplikowana kluczem `(device_id, boot_id, sequence_number)`.
Nowa tabela `control_observations` ma oddzielne rosnące ID obserwacji.
`command_id` identyfikuje żądanie aplikacyjne, nie pojedynczy odbiór MQTT.
Flaga `mqtt_duplicate` opisuje retransmisję pakietu MQTT, nie wszystkie możliwe
powtórzenia polecenia. Liczba rekordów nie jest liczbą działań użytkownika.

## Co zapisujemy

| Pole | Znaczenie |
|---|---|
| `id` | Kolejność zapisu obserwacji w tej bazie; kursor API |
| `kind` | `command` albo `result` |
| `message` w API / `payload` w SQLite | Zwalidowana wiadomość kontraktu 1.0 |
| `topic` | Adres MQTT, sprawdzony względem `device_id` |
| `received_at` | Rzeczywisty czas UTC odebrania przez kolektor |
| `received_monotonic_ns` | Czas monotoniczny do porównywania odstępów w sesji kolektora |
| `collector_session_id` | Nowe UUID przy uruchomieniu kolektora; pozostaje przy reconnect brokera |
| `mqtt_qos`, `mqtt_duplicate` | Metadane pakietu odebranego przez kolektor |

Indeksy przechowują też węzeł, komponent, ID polecenia i sesję wiadomości.
Dla polecenia sesją jest `target_boot_id`, dla odpowiedzi — rzeczywisty `boot_id`.
Przy `wrong_boot` mogą być różne. Powiązanie zaczynamy od węzła i `command_id`,
ale analizujemy również sesje, komponent i treść; API nie scala automatycznie
sprzecznych odpowiedzi w jeden „prawdziwy stan”.

Zapis następuje w transakcji **przed MQTT ACK kolektora**. Test sprawdza, że drugi
czytelnik SQLite widzi rekord, zanim kolektor potwierdzi wiadomość. Błąd zapisu
zatrzymuje kolektor bez ACK. To nie gwarantuje odzyskania po awarii: obecne sesje
MQTT są nietrwałe, a broker ma wyłączone persistence. Wymuszone zakończenie
procesu między zapisem i ACK może skutkować kolejną obserwacją tej samej treści.

## Uruchomienie i odczyt

Uruchom broker, kolektor i symulator z `--commands` według
[kroku 9](step-09-mqtt-control.md). Po aktualizacji **uruchom ponownie kolektor
i API**, jeśli działają stare procesy. Nowy kolektor dodaje tabelę i indeksy
do istniejącej bazy; nie usuwa starych odczytów. Historia zaczyna się od chwili
aktywnej subskrypcji — wcześniejszych poleceń nie odtworzymy z samych nastaw.

W kolejnym terminalu uruchom API z tego samego katalogu i z tą samą bazą:

```powershell
.\.venv\Scripts\python.exe -m edge.api --database data/telemetry.sqlite3 --port 8000
```

Wyślij polecenie w konfiguracji `--nodes 1`:

```powershell
.\.venv\Scripts\python.exe -m edge.command --device esp32_node_01 --component led_01 --value 1
```

Otwórz [historię sterowania](http://127.0.0.1:8000/devices/esp32_node_01/control-history)
albo odczytaj ją w PowerShell:

```powershell
$historia = Invoke-RestMethod 'http://127.0.0.1:8000/devices/esp32_node_01/control-history?limit=20'
$historia.items | ConvertTo-Json -Depth 8
```

Znajdź `command` oraz `result` z ID pokazanym przez nadawcę. `accepted` oznacza
przyjęcie nastawy; kolejny raport lampy powinien pokazać zmianę. Raport znajdziesz
w [historii telemetrii](http://127.0.0.1:8000/devices/esp32_node_01/telemetry/recent).
`reported` nadal pochodzi z symulatora. Brak pary w historii może wynikać z utraty
wiadomości albo późniejszego startu kolektora, a nie z pewnego braku wykonania.

Endpoint przyjmuje `limit` 1–200, `after_id` i opcjonalny `command_id`.
Kolejną stronę pobierasz, podając `next_after_id` jako `after_id` i zachowując
ten sam filtr. Strony są w kolejności zapisu, nie od najnowszej. Zmiana filtra
wymaga rozpoczęcia od `after_id=0`. Kursor dotyczy tej samej bazy; po jej podmianie
lub odbudowie zaczynamy od zera. Nie ma automatycznej retencji/usuwania historii.

Brak obserwacji zwraca pustą listę (także dla nieznanego węzła), nie status offline.
Odpowiedzi bez zaobserwowanych poleceń są zachowywane. Lista `/devices` nadal
dotyczy węzłów z telemetrią, więc sam zapis polecenia nie dodaje tam urządzenia.
Starsza baza bez nowej tabeli zwraca 503 dla nowego endpointu; API jej nie migruje.
`/health` nadal sprawdza dostępność tabeli telemetrii, nie kompletność historii
sterowania, dostępność brokera czy urządzeń. Schemat i parametry API opisuje
[lokalny Swagger](http://127.0.0.1:8000/docs).

## Co wolno wnioskować w badaniu ML

Kolejność odbioru na gatewayu nie dowodzi kolejności wykonania w rozproszonym
systemie. Różnica czasów odbioru polecenia i wyniku jest obserwowanym odstępem,
nie czystym czasem ruchu ani dokładnym RTT nadawcy. Nie odejmujemy czasu
logicznego symulatora od zegara UTC komputera; odstępy monotoniczne porównujemy
w tej samej `collector_session_id`. Nową sesję traktujemy jako granicę ciągłości.

Do przyszłych cech przydadzą się rytm żądań, powtórzenia, odrzucenia, brak wyniku
i relacja z telemetrią. Trzeba rozdzielić powtórzenia transportowe od logicznych
żądań, aby model nie nazywał retransmisji kolejnym cyklem bramy. Ten przyrost
zapisuje obserwacje; nie implementuje jeszcze cech, etykiet ani detektora.

To lokalny dziennik, nie niezmienny audyt bezpieczeństwa. Brak uwierzytelniania
klientów/ACL oznacza brak potwierdzenia nadawcy; treść poprawna względem schematu
może być fałszywa. Zwykła baza SQLite nie jest odporna na modyfikacje przez
użytkownika z dostępem do pliku. Uszkodzone i retained wiadomości liczymy,
ale nie zapisujemy ich treści w tej tabeli. Liczniki są tylko w pamięci procesu.
Limity brokera i brak trwałych sesji oznaczają możliwe luki; „zero wpisów”
nie dowodzi „zero zdarzeń”. Nie dodajemy etykiet generatora do obserwacji.

Testy: `python -m pytest tests/test_control_observations.py tests/test_mqtt_path.py -q`
w środowisku projektu. Obejmują także prawdziwy Mosquitto, powtórzenia bez
ponownego wykonania, restart brokera, SQLite i odczyt HTTP.
