# Krok 5 — symulator → MQTT → kolektor → SQLite

Cel ćwiczenia: wiadomości mają przejść przez **prawdziwy broker Mosquitto**
i pozostać w bazie po zamknięciu programów. Nie potrzebujesz elektroniki.
To osobna ścieżka terminalowa; obecne okno Qt nadal pracuje lokalnie w pamięci.

## Przygotowanie na Windows

W katalogu repozytorium, z wcześniej utworzonym `.venv`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-mqtt.txt
.\.venv\Scripts\python.exe scripts/setup-mqtt.py
```

Druga komenda pobiera oficjalne Mosquitto 2.1.2 i narzędzia 7-Zip 26.03,
sprawdza przypięte SHA-256 i rozpakowuje je do ignorowanego `.tools/`.
Nie uruchamia instalatorów, nie tworzy usługi Windows i nie zmienia PATH.
Dotyczy Windows x64; na Linux użyj systemowego pakietu `mosquitto`.
Pierwsze przygotowanie wymaga Internetu, późniejsza praca odbywa się lokalnie.

## Uruchomienie w trzech terminalach

W każdym terminalu przejdź do głównego katalogu repozytorium.

**1. Broker — przekazuje wiadomości odbiorcom:**

```powershell
.\.tools\mosquitto\mosquitto.exe -c mqtt/mosquitto-local.conf
```

Na Linux: `mosquitto -c mqtt/mosquitto-local.conf`. Konfiguracja nasłuchuje
wyłącznie na `127.0.0.1:1883`. Jeżeli port jest zajęty, nie zatrzymuj obcej
usługi: zmień port w konfiguracji i podaj ten sam `--port` w obu klientach.

**2. Kolektor — waliduje i zapisuje wiadomości:**

```powershell
.\.venv\Scripts\python.exe -m edge.collector --database data/telemetry.sqlite3
```

Poczekaj na `READY: MQTT subscription active`. Pojawia się dopiero po
potwierdzeniu subskrypcji. Kolektor kończysz Ctrl+C; wtedy wypisze liczniki.
Opcja `--seconds 30` kończy odbiór po zadanym czasie (z możliwym opóźnieniem
krótkiej próby połączenia podczas awarii).

**3. Symulator — wysyła odczyty:**

```powershell
.\.venv\Scripts\python.exe -m simulator.mqtt --nodes 3 --extra-nodes 2 --steps 10 --seed 42
```

Oczekiwany wynik: `broker_acked: 50` — 5 węzłów × 10 kroków.
Każdy krok to sekunda czasu modelu; pomiędzy krokami publisher czeka sekundę.
Wysyłanie i oczekiwanie na potwierdzenia wydłużają czas rzeczywisty.
Identyfikatory węzłów i konfiguracja pozostają niezależne od sprzętu.

Domyślny identyfikator przebiegu jest unikalny. Możesz podać `--run-id cwiczenie-01`,
ale nie używaj ponownie tej samej nazwy: determinuje `boot_id`, a archiwum
`experiments/runs/<run-id>-mqtt.json` nie jest nadpisywane. Archiwum zawiera
seed, wersję kodu/modelu, profil i wynik wysyłania; etykiety są osobno od telemetrii.
Kod wyniku `completed` oznacza potwierdzenia brokera, nie potwierdzony zapis kolektora.
Przy przerwaniu transmisji archiwum oznacza niepowodzenie i liczbę otrzymanych
potwierdzeń; dostarczenie ostatniej wiadomości może pozostawać niepewne.

## Sprawdzenie bazy

Po wysłaniu i zatrzymaniu kolektora możesz odczytać liczbę rekordów per węzeł:

```powershell
.\.venv\Scripts\python.exe -c "import sqlite3; db=sqlite3.connect('data/telemetry.sqlite3'); print(db.execute('SELECT device_id, COUNT(*) FROM telemetry GROUP BY device_id').fetchall()); db.close()"
```

W nowej bazie ćwiczenie powinno dać po 10 rekordów dla każdego z pięciu węzłów.
W istniejącej bazie liczby obejmują również wcześniejsze sesje.
Pliki `.sqlite3`, WAL i SHM oraz archiwa przebiegów pozostają poza Git.

## Co robi kod

| Element | Odpowiedzialność |
|---|---|
| `simulator/mqtt.py` | Istniejący model domu, ograniczona liczba kroków i publikacja telemetrii 1.0 |
| `edge/mqtt.py` | MQTT 3.1.1, lokalne połączenie, QoS 1 i potwierdzenia brokera |
| `edge/collector.py` | Subskrypcja wszystkich węzłów, walidacja, liczniki i ponowne połączenie |
| `edge/storage.py` | SQLite, deduplikacja i zachowanie czasu odbioru osobno od czasu urządzenia |

Klucz rekordu: `(device_id, boot_id, sequence_number)`. Identyczna wiadomość
z tym kluczem zwiększa `duplicate`; inna treść zwiększa `conflict` i nie nadpisuje
oryginału. Kolektor sprawdza zgodność topicu z `device_id`, ale to nie jest
uwierzytelnienie klienta. Czas urządzenia w tym generatorze jest logiczny;
`received_at` jest rzeczywistym czasem UTC kolektora. `received_monotonic_ns`
pomaga mierzyć odstępy na tym samym uruchomionym systemie, nie czas między komputerami.

## Zachowanie przy problemach

- QoS 1 może dostarczyć duplikaty. Zapisujemy przed potwierdzeniem odbioru.
  Błąd SQLite zatrzymuje kolektor bez ACK dla tej wiadomości.
- Niepoprawne JSON/schema/topic są odrzucane (`invalid`). Migawki z flagą
  retained dostarczone przy subskrypcji są liczone jako `retained`, bez zapisu.
- Po restarcie brokera kolektor ponownie łączy się i subskrybuje. Publisher
  przerywa przebieg przy błędzie zamiast deklarować udane dostarczenie.
- Limit payloadu to 32 KiB, pakietu brokera 40 000 bajtów, kolejki brokera na
  klienta 128 wiadomości / 4 MiB. Kolektor przetwarza w jednym wątku bez osobnej
  kolejki aplikacyjnej. Limity chronią pamięć, nie gwarantują braku strat.
- Broker bez trwałej sesji/persistence nie odtworzy wiadomości wysłanych przy
  nieobecnym kolektorze. Przy przepełnieniu może odrzucać wiadomości; PUBACK
  nie jest dowodem zapisu SQLite. Pełne rozliczanie strat i test przeciążenia
  pozostają do wykonania. Liczniki kolektora dotyczą bieżącego procesu.

To laboratorium loopback bez haseł i TLS, nie konfiguracja do sieci domowej.
Przed ESP32 i badaniami cyberbezpieczeństwa dodamy tożsamości klientów oraz ACL.
API, integracja Qt z kolektorem, nowe czujniki, ML i pełne zamknięcie Milestone 1
pozostają kolejnymi etapami. Baza nie dodaje ukrytych stanów ani etykiet do cech ML.

## Testy i źródła

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_mqtt_path.py -q
```

Testy używają własnego procesu Mosquitto na wolnym porcie i tymczasowej bazy.
Szukają programu w PATH, `.tools/mosquitto/mosquitto.exe` lub zmiennej
`MOSQUITTO_EXECUTABLE`. Bez brokera testy sieciowe są pomijane; ustawienie
`REQUIRE_MQTT_TESTS=1` zamienia jego brak w błąd (tak działa CI).

Sprawdzamy rzeczywiste dostarczenie z wielu węzłów, luki offline, walidację,
duplikaty i konflikty, trwałość SQLite, restart brokera, retained, błąd zapisu
oraz archiwum nieudanego przebiegu. Nie są to wyniki skuteczności ML.

- [Mosquitto — oficjalne pobieranie](https://mosquitto.org/download/)
- [Mosquitto — konfiguracja i limity](https://mosquitto.org/man/mosquitto-conf-5.html)
- [Paho — klient i manual acknowledgements](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html)
