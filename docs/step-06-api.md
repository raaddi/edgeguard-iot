# Krok 6 — odczyt danych przez API

API to umówiony sposób pobierania danych przez inne programy. Kolektor zapisuje
wiadomości w SQLite, a API udostępnia ich historię przez HTTP. Docelowo skorzysta
z niego [konsola Qt](step-07-collector-view.md). Serwer API i konsolę uruchamiamy osobno.

## Uruchomienie

W katalogu repozytorium, po przygotowaniu `.venv`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-api.txt
.\.venv\Scripts\python.exe -m edge.api --database data/telemetry.sqlite3
```

Instalację zależności wykonujesz raz z dostępem do Internetu. API działa potem
lokalnie, także bez elektroniki, brokera i uruchomionego kolektora, jeśli baza
już istnieje. Zatrzymujesz je przez Ctrl+C. Port zmienisz przez `--port 8001`.

Jeśli jeszcze nie masz bazy, wykonaj [ćwiczenie MQTT](step-05-mqtt.md).
W obu programach wskaż ten sam plik. API celowo nie tworzy pustej bazy przy
literówce w ścieżce. Kolektor może dalej dopisywać dane podczas odczytu przez API.
Samo klikanie makiety Qt nie zapisuje jeszcze wiadomości w tej bazie.

Otwórz w przeglądarce:

- [Stan odczytu bazy](http://127.0.0.1:8000/health).
- [Lista zaobserwowanych węzłów](http://127.0.0.1:8000/devices).
- [Ostatni raport esp32_node_01](http://127.0.0.1:8000/devices/esp32_node_01).
- [Pierwsze trzy raporty](http://127.0.0.1:8000/devices/esp32_node_01/telemetry?limit=3).

Interaktywna dokumentacja jest pod `/docs`: rozwiń operację GET, wybierz
**Try it out**, wpisz parametry i naciśnij **Execute**. Domyślny Swagger pobiera
skrypty i style z CDN, więc ten pomocniczy ekran wymaga Internetu lub cache
przeglądarki. Same adresy JSON oraz `/openapi.json` działają offline.

## Co oznaczają odpowiedzi

| Adres | Znaczenie |
|---|---|
| `GET /health` | Sprawdza dostęp do tabeli i wymaganych kolumn; nie testuje brokera, wszystkich rekordów ani połączenia ESP32 |
| `GET /devices` | Węzły obecne w historii, liczba zapisanych wiadomości i czas odbioru ostatnio zapisanego raportu |
| `GET /devices/{device_id}` | Liczba wiadomości i ostatnio zapisany raport danego węzła |
| `GET /devices/{device_id}/telemetry` | Strona zapisanych raportów w kolejności ich dodania do bazy |
| `GET /devices/{device_id}/telemetry/recent` | Ostatnie maksymalnie 200 raportów do podglądu konsoli; również w kolejności zapisu |

Raport zawiera `telemetry` w dotychczasowym formacie 1.0 oraz osobno informacje
kolektora: `received_at`, `received_monotonic_ns` i `topic`. Pole `id` służy do
stronicowania odczytu bazy; nie zastępuje `sequence_number` ani `boot_id` węzła.
Czas urządzenia może być logiczny, a zegar systemowy może zostać skorygowany.
Dlatego „ostatni” oznacza kolejność zapisu, nie największy timestamp.
Monotoniczny czas odbioru porównujemy tylko w ramach tego samego uruchomienia
systemu operacyjnego.

**Węzeł widoczny w historii nie musi być online.** API nie zna jeszcze statusu
połączenia. `reported: null` pozostaje brakiem odczytu; przerw w sekwencji nie
uzupełniamy zerami ani danymi modelu. Wartości `feedback: simulated` nadal
oznaczają symulację, nie fizyczny pomiar.

Kody odpowiedzi: `200` — poprawny odczyt (także pusta strona), `404` — brak
historii wskazanego węzła, `422` — niepoprawny parametr, `503` — niedostępna,
niezgodna lub uszkodzona baza/odczytywany raport. Szczegóły błędu są w terminalu;
odpowiedź nie ujawnia lokalnej ścieżki. Błędy zapytań nie modyfikują danych.

## Małe ćwiczenie: pobierz następną stronę

```powershell
$page = Invoke-RestMethod 'http://127.0.0.1:8000/devices/esp32_node_01/telemetry?limit=3'
$page.items
$cursor = $page.next_after_id
Invoke-RestMethod "http://127.0.0.1:8000/devices/esp32_node_01/telemetry?limit=3&after_id=$cursor"
```

Domyślny `limit` wynosi 100, maksymalny 200. `has_more` mówi, czy w chwili
odczytu zostały kolejne wpisy. Po pustej stronie `next_after_id` zachowuje
poprzednią wartość, więc możesz ponowić odczyt po dopisaniu wiadomości.
Lista węzłów ma podobny mechanizm `after_device` / `next_after_device`, z porządkiem
leksykograficznym ID. Odśwież ją od początku, żeby wykryć wszystkie nowe węzły.

Kursor telemetrii wykorzystuje SQLite `rowid` i obowiązuje dla tego samego pliku
z historią wyłącznie dopisywaną przez kolektor. Po wymianie/odtworzeniu bazy,
usuwaniu danych lub `VACUUM` odczyt zacznij od `after_id=0`. Nie jest to trwały
identyfikator badania ani mechanizm eksportu spójnego zbioru treningowego.
Każde żądanie widzi spójną migawkę; kolejne strony mogą już obejmować nowe wpisy.

## Decyzje i zakres

- FastAPI jest zgodne ze specyfikacją; ma opis kontraktu HTTP i walidację parametrów.
- Osobne połączenie SQLite na żądanie, tryb `mode=ro`, krótka transakcja odczytu
  i istniejący WAL pozwalają odczytywać dane obok kolektora. API nie używa klasy
  zapisującej `TelemetryStore` i nie przeprowadza migracji.
- Brak nowego silnika bazy, zależności od Qt i stałej liczby węzłów. Limity stron
  ograniczają rozmiar odpowiedzi; nie stanowią pomiaru wydajności na Raspberry Pi.
- Uruchomienie CLI nasłuchuje wyłącznie na `127.0.0.1`. Ten etap nie dodaje
  uwierzytelniania, zdalnego dostępu, poleceń sterujących ani modeli ML.
  Konsola odczytuje historię; sterowanie MQTT, rejestr eksperymentów i pozostałe
  endpointy są kolejnymi krokami.

Weryfikacja:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_api.py tests/test_mqtt_path.py -q
```

Testy sprawdzają prawdziwe SQLite, stronicowanie podczas dopisywania, reset
sekwencji po restarcie węzła, brak nadpisania duplikatów, braki odczytów,
błędy i tryb tylko do odczytu. Test integracyjny przechodzi przez prawdziwy
Mosquitto, kolektor i SQLite do odpowiedzi API przy działającym kolektorze.

Dokumentacja użytych mechanizmów: [FastAPI TestClient](https://fastapi.tiangolo.com/tutorial/testing/)
i [SQLite w Pythonie](https://docs.python.org/3/library/sqlite3.html).
