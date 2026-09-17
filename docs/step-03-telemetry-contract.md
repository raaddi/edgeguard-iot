# Krok 3: wspólny kontrakt telemetrii

Kontrakt to umowa określająca, jak urządzenie opisuje pomiar. Generator CLI
i makieta używają teraz tego samego formatu **1.0**. Przyszły ESP32 będzie
tworzyć taki sam JSON w C++; nie będzie uruchamiać Pythona ani biblioteki jsonschema.
Nie ma jeszcze brokera MQTT, kolektora ani zapisu do SQLite.

## Uruchom i zobacz

W terminalu otwartym w katalogu repozytorium:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt -r requirements-ui.txt
.\.venv\Scripts\python.exe -m simulator --samples 3 --run-id contract-lesson
.\.venv\Scripts\python.exe -m simulator --samples 3 --run-id contract-lesson | .\.venv\Scripts\python.exe -m contracts
```

Instalacja zależności wymaga internetu, jeśli nie są już dostępne lokalnie.
Samo ćwiczenie działa offline. Pierwsze uruchomienie pokazuje JSON, drugie
przekazuje trzy wiadomości do walidatora. Oczekiwany komunikat:
`Validated 3 telemetry messages (schema 1.0).`
Manifest wyświetlany na stderr pozostaje osobno i nie jest przesyłany potokiem.
Walidator przyjmuje też ścieżkę do pliku **JSONL** (jedna wiadomość na wiersz).
Pełny eksport eksperymentu JSON ma inny format i nie jest plikiem JSONL.

## Czytamy jedną wiadomość

| Pole | Znaczenie |
|---|---|
| schema_version | Wersja umowy; teraz dokładnie `1.0` |
| device_id | Stała tożsamość węzła, niezależna od liczby urządzeń |
| boot_id | UUID sesji; na sprzęcie nowy przy restarcie, w symulatorze wyliczony z run_id i device_id |
| sequence_number | Licznik próbek od zera w sesji; przerwy mogą wskazywać pominięte wiadomości |
| timestamp | Czas urządzenia w UTC albo `null`, gdy zegar nie jest zsynchronizowany |
| uptime_ms | Czas od początku sesji; pozwala zachować lokalny porządek bez zegara UTC |
| sensors | Pełna mapa czujników skonfigurowanych na danym węźle |
| actuators | Pełna mapa aktuatorów skonfigurowanych na danym węźle |

`(device_id, boot_id, sequence_number)` będzie kluczem wykrywania duplikatów.
Ponowne wysłanie tej samej próbki zachowa wszystkie trzy pola. Przed przepełnieniem
32-bitowego licznika trzeba rozpocząć nową sesję. Symulator zwiększa licznik także
w czasie braku łączności. Czas `received_at` zapisze osobno przyszły kolektor;
nie zastępuje on czasu urządzenia. Walidator pojedynczej wiadomości nie sprawdza
jeszcze kolejności między wiadomościami ani stałości wyposażenia między próbkami.

Przy MQTT temat będzie miał postać `edgeguard/devices/{device_id}/telemetry`.
Funkcja `decode_telemetry(payload, topic=...)` sprawdza zgodność identyfikatora
w temacie i JSON. To kontrola spójności, a nie uwierzytelnienie nadawcy.
QoS, ponowienia, heartbeat, komendy i potwierdzenia opracujemy przy adapterze MQTT.

## Zero, brak odczytu i brak czujnika

- `status: "ok", value: 0` oznacza poprawny odczyt równy zero.
- `status: "unavailable", value: null` oznacza skonfigurowany czujnik bez odczytu.
- Brak identyfikatora w mapie oznacza komponent niewchodzący w skład konfiguracji węzła.
  Wiadomości są pełnymi migawkami, nie częściowymi aktualizacjami.

Puste mapy są dozwolone, np. dla węzła bez czujników. Typ i jednostka przy każdym
komponencie deklarują jego możliwości w tej wersji. Osobny rejestr urządzeń będzie
zadaniem kolektora; dziś nie ma potwierdzania konfiguracji względem takiego rejestru.
Wersja 1.0 obsługuje sygnał gazowy 0–1, lampy, wentylatory i serwa.
Nowe rodzaje pomiarów wymagają jawnego rozszerzenia wersji kontraktu.
`normalized` nie oznacza ppm; regułę normalizacji fizycznego ADC trzeba opisać
w konfiguracji/manifestach przed porównywaniem danych ze sprzętu i symulatora.

## Polecenie nie jest pomiarem

Aktuator ma `kind`, `unit`, `mode` oraz:

- `commanded`: stan zadany; 0/1 dla lampy i wentylatora, 0–180 stopni dla serwa;
- `reported`: stan raportowany albo `null`;
- `feedback`: `simulated`, `measured` lub `unavailable`.

Makieta raportuje stan modelu z `feedback: "simulated"`. Fizyczne serwo bez
czujnika położenia musi raportować `reported: null, feedback: "unavailable"`.
Sam zapis GPIO lub kąta do biblioteki serwa nie jest niezależnym pomiarem ruchu.
`measured` wymaga rzeczywistego sprzężenia zwrotnego. Dobór jego źródła będzie
decyzją sprzętową. Brak pomiaru ogranicza możliwość wykrywania awarii aktuatora.

Przykład w `contracts/examples/physical-node.json` ilustruje zerowy odczyt,
niedostępny czujnik, brak zegara UTC i różne rodzaje sprzężenia zwrotnego.
**To ręcznie przygotowany przykład kontraktu, nie dane z fizycznego urządzenia.**
Etykiety scenariuszy i ukryty stan środowiska pozostają poza telemetrią.
Metadana `feedback` opisuje pochodzenie stanu; przy ML trzeba świadomie wybrać
cechy i uwzględnić brak fizycznego sprzężenia, a nie korzystać z etykiet scenariuszy.

## Granice i wersjonowanie

JSON Schema jest wspólną, niezależną od języka definicją w
`contracts/telemetry-v1.schema.json`. Python używa jej przez `jsonschema`.
Dodatkowe kontrole dekodera odrzucają powtórzone klucze JSON, NaN/nieskończoność,
niepoprawny UTF-8, zbyt duże wiadomości i rozbieżności tematu.
Limit wynosi 32 KiB na wiadomość oraz po 64 czujniki i aktuatory na węzeł.
To granice pojedynczego komunikatu, nie limit liczby węzłów w architekturze.
UART/MQTT bufory ESP32 i rzeczywisty rozmiar pakietów trzeba sprawdzić na sprzęcie.

Znacznik czasu ma format UTC z `Z` lub `+00:00`, opcjonalnie do sześciu cyfr
ułamka sekundy. Sekundy przestępne nie są obsługiwane w tej wersji.
Nieznane pola i wersje są odrzucane. Kontrakt jest wersjonowany ściśle:
zmiana struktury wymaga nowej wersji i jawnego wsparcia odbiorcy.

Formaty 0.1-draft i 0.2-draft zostały zastąpione. Stare pliki pozostają ważnymi
archiwami, ale nie są automatycznie przyjmowane jako 1.0. Zmiana eksportowanej
telemetrii podnosi wersję modelu do `house-behaviour-v2`; replay odrzuca v1,
zamiast po cichu zmieniać wynik. Stare przebiegi odtwarza się z ich commita.
Po aktualizacji kodu uruchom nową sesję aplikacji; nie mieszaj wersji w jednym przebiegu.

## Ćwiczenie i następny etap

1. Wygeneruj trzy wiadomości i znajdź licznik, czas oraz odczyt.
2. Otwórz przykład fizycznego węzła i wyjaśnij różnicę między `0` i `null`.
3. W makiecie wywołaj awarię wentylatora przy wysokim sygnale gazowym.
   Pod wykresem konsoli rozwiń ostatnią wiadomość JSON i porównaj `commanded`, `reported` i `feedback`.
4. Przeczytaj test odrzucający wartość `2` dla wentylatora i jednostkę `ppm` dla
   naszego sygnału. Walidacja formatu nie oznacza jeszcze detekcji anomalii:
   poprawnie zapisany, wysoki odczyt powinien dotrzeć do przyszłego detektora.

Następny krok: lokalny Mosquitto, publikacja zgodnych wiadomości i odbiór przez
kolektor. Potem SQLite z zachowaniem czasu odbioru i kontrolą duplikatów.

Źródła: [JSON Schema — obiekty](https://json-schema.org/understanding-json-schema/reference/object),
[warunki](https://json-schema.org/understanding-json-schema/reference/conditionals),
[walidacja jsonschema](https://python-jsonschema.readthedocs.io/en/stable/validate/).
