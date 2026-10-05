# Krok 19: cele odpowiedzi na polecenie — protokół przed eksportem

## Problem i zakres przyrostu

[W kroku 18](results/independent-calibration-20261005.md) GRU nie wykrył żadnego
z 433 przedziałów opóźnionej odpowiedzi. Teraz przygotowujemy **przyczynowe
przykłady danych**, bez nowego treningu, progów lub twierdzenia o lepszej detekcji.
Model odczytów +50 ms pozostaje punktem odniesienia przyszłej ablacji.
Kod eksportu działa bez Qt, MQTT i sprzętu.

## Moment prognozy i dwa różne cele

Prognozę wystawiamy w chwili `command_sent`. Wejściem jest 20 kolejnych próbek
co 50 ms, kończących się w tej chwili, z dotychczasowymi przyczynowymi cechami.
Wysłane właśnie polecenie jest znane. Późniejsze wyniki i pomiary nie wchodzą
do wejścia. Pierwszy format wymaga jednej komendy na chwilę i odpowiedzi
ściśle późniejszej od wysłania; już dostępnej odpowiedzi nie udajemy prognozy.

1. **ACK:** czas od wysłania do skorelowanego `command_result`. Osobna etykieta
   mówi, czy przyjęto, czy odrzucono polecenie. Przyjęcie nie dowodzi ruchu.
2. **Krańcówka:** czas od wysłania do pierwszego odczytu właściwej krańcówki
   w chwili przyjęcia lub później. Dla otwarcia to `open_contact`, dla zamknięcia
   `closed_contact`. Gdy pozycja była już osiągnięta, potwierdzenie jest pierwszą
   taką próbką po przyjęciu — nie czasem zero przed wysłaniem.

ID polecenia/runu służy korelacji i metadanym. Scenariusz, seed, konfiguracja
symulatora, ukryty kąt i ground truth nie wchodzą do funkcji tworzącej wejścia.
Zmiana przyszłego ACK/krańcówki może zmienić cel, lecz nie wejście tej prognozy.

## Zakończenie obserwacji i braki

Każdy cel zapisuje `observed`, `duration_ms`, `follow_up_ms` i `censor_reason`.
Nieobserwowany czas ma `duration_ms=null`; nie zastępujemy go zerem ani
szacowaną długością ruchu. `follow_up_ms` jest długością dostępnej obserwacji.

- ACK bez wyniku do końca zapisu: cenzurowany na końcu sesji. Luka pomiarów
  krańcówek nie usuwa rzeczywiście zalogowanego ACK — to różne kanały.
- Odrzucenie kończy ACK; cel fizyczny jest nieobserwowany z powodem `rejected`.
- Brak wyniku: cel fizyczny ma powód `no_result`, bez wnioskowania o przyjęciu.
- Zaakceptowany później przeciwny cel przerywa poprzednie potwierdzenie
  fizyczne: `superseded`. Próbka w tej samej chwili nie potwierdza starego celu,
  bo zdarzenia przetwarzane są przed próbką. Samo wysłanie nowego celu nie
  przerywa jeszcze ruchu. Powtórzenie tego samego celu nie przerywa obserwacji.
- Pierwsza brakująca próbka po wysłaniu cenzuruje nieukończony cel fizyczny:
  `sample_gap`. Nie przypisujemy pierwszemu odczytowi po luce nieznanego początku.
- Brak osiągnięcia celu do ostatniej próbki: `end_of_session`. Potwierdzenie
  dokładnie w ostatniej próbce jest nadal obserwowane.
- Niepełne lub nieciągłe 20 próbek wejścia: polecenie trafia do listy wyłączeń
  z powodem, zamiast dostać dopełnioną historię. Stan resetuje się między sesjami.

Powtórzenia mogą współdzielić fizyczne potwierdzenie. Liczba przykładów nie jest
liczbą niezależnych cykli. Przedłużenie zapisu może zakończyć wcześniej cenzurowany
cel; zachowuje wejścia i już zakończone cele, nie musi zachować etykiety cenzury.
Wersja 1 wymaga wspólnie zamkniętej sesji: żadne zdarzenie nie może wystąpić
po ostatniej próbce pomiarowej. Wewnętrzna luka pomiarów nie kasuje ACK, ale
urwana końcówka pomiarów z późniejszym logiem zdarzeń jest jawnie odrzucana.
Osobne końce obserwacji kanałów wymagają kolejnej wersji kontraktu.
To semantyka ograniczonego pilota offline, nie protokół czasu gatewaya na sprzęcie.

## Z góry ustalony eksport rozwojowy

| Rola grup seedów | Seedy | Dane |
|---|---|---|
| Przyszły trening | 3000–3015 | normalne cycles/repeats/idle |
| Przyszły wybór checkpointu | 4000–4007 | normalne cycles/repeats/idle |
| Przyszła kalibracja | 5000–5015 | normalne cycles/repeats/idle |
| Ocena rozwojowa | 6000–6015 | pięć warunków × normalne i trzy usterki |

Seedy są rozłączne z dotychczasowymi 42–61, 1000–1015 i 2000–2015.
Wszystkie warianty jednego seeda pozostają w jednej roli. Rodziny harmonogramów,
30 s, zakresy ruchu/opóźnień i trzy przypadki usterek pozostają dokładnie jak
w kroku 18, aby kolejny przyrost izolował zmianę celu. Zachowujemy konfigurację,
wersje kodu/cech/generatora, surowe dane oraz hashe. Docelowo 440 sesji.
Osobno raportujemy liczbę poleceń, wejścia wyłączone i cele obserwowane/cenzurowane.

Nowe seedy nie tworzą końcowego testu pracy: to ten sam rozwojowy generator.
Nie oglądamy nowych wyników detekcji ani nie dobieramy na nich hiperparametrów.
Eksport nie uczy preprocessingu i nie ładuje starego modelu lub joblib.

## Dalsza ablacja — wymaga osobnego protokołu przed treningiem

Porównać ponownie trenowany GRU odczytów +50 ms, GRU dwóch czasów odpowiedzi
z tym samym rozmiarem kodera i referencję median czasów z normalnego treningu.
Ustalić loss, maski/cenzurowanie, checkpoint, liczbę epok i seedy treningu przed
oceną. Wdrożony alarm czasu odpowiedzi musi porównywać **upływający czas**
z prognozą wystawioną przy wysłaniu. Nie może czekać na przyszły końcowy czas,
żeby dopiero wtedy ogłosić wykrycie opóźnienia. Margines ustala tylko oddzielna
normalna kalibracja; ocena używa wspólnej ekspozycji i niezmienionych etykiet.
Transfer na ESP32, live Qt i koszty Raspberry Pi pozostają osobnymi wymaganiami.

## Wykonanie — 06.10.2026

Pełny eksport z czystego `28233a5…` zakończył się 440 sesjami i 1872 przykładami.
[Raport wyników i audytu](results/command-response-examples-20261006.md) podaje
liczby celów, hashe i komendę odtworzenia. Jest to przygotowanie danych;
trening oraz porównanie skuteczności pozostają planem. Kopia `protocol.md`
w lokalnym przebiegu zachowuje treść protokołu sprzed tej sekcji.
