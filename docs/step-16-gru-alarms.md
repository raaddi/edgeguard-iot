# Krok 16: od prognozy do alarmu

GRU z [kroku 15](step-15-first-gru.md) przewiduje pomiary. Ten etap dodaje
wynik anomalii, próg i zdarzenia alarmowe. Porównujemy cztery metody na wspólnym
przedziale czasu: GRU, prognozę „jak ostatni odczyt”, Isolation Forest i reguły.
To eksperyment offline, bez zmiany pulpitu Qt lub sterowania urządzeniami.

## Reguły porównania ustalone przed wynikiem

1. Wczytujemy istniejący GRU bez ponownego treningu. Jego manifest musi wskazywać
   dokładnie ten sam eksport sekwencji i podział sesji. Sprawdzamy też wagi,
   surowe dane i zgodność każdego okna z obserwacjami. Ten pilot wymaga domyślnych
   identyfikatorów węzłów generatora, historii 20 próbek, horyzontu 50 ms,
   pełnego próbkowania i wszystkich trzech kanałów. Inne warianty odrzucamy.
2. Dla każdego kanału liczymy moduł błędu: `|pomiar − prognoza|`.
   Dla krańcówek prognoza jest prawdopodobieństwem; prąd ma jednostkę amperów.
3. Osobno dla GRU i referencji dopasowujemy trzy skale: RMS błędów na
   **normalnych oknach treningowych**. Wynik próbki to największy z trzech
   ilorazów `błąd / skala`. W ten sposób nie sumujemy amperów i stanów binarnych.
   Dolny limit skali `1e-6` w jednostce kanału chroni przed dzieleniem przez zero;
   nie opisuje fizycznego szumu. Nie dobieramy wag pod wynik testu.
4. Isolation Forest i limity reguł dopasowujemy ponownie, deterministycznie,
   z normalnych grup treningowych. Zachowujemy wcześniejszą konfigurację IF:
   100 drzew, do 256 próbek na drzewo. Modele korzystają z obserwacji tych samych
   normalnych sesji: GRU ma okna kończące się przyszłym celem, IF/reguły pełne
   161 wierszy cech na sesję. Liczności są jawne w `calibration.json`.
5. Każda metoda ma własny próg równy **maksymalnemu wynikowi normalnej walidacji**
   na wspólnym przedziale. To zachowawcza polityka z poprzedniego pilota, a nie
   próg optymalizowany pod wykrywalność usterek. Zero alarmów na tej walidacji
   nie gwarantuje zera alarmów w przyszłości. Walidacja była wcześniej użyta
   także do wyboru epoki GRU — nie jest niezależnym zbiorem kalibracyjnym.
6. Alarm zaczyna się na trzeciej kolejnej próbce z `score > threshold`.
   Przy próbkowaniu 50 ms oznacza to co najmniej 100 ms od pierwszego
   przekroczenia. Nie przesuwamy początku alarmu wstecz. Próbka równa progowi,
   niedostępny wynik lub luka przerywa serię. Stan alarmu zeruje się per sesja.
   Ten runner odrzuca niepełne pomiary; nie zamienia brakującego czujnika na zero.
7. Najpierw zapisujemy skale, progi i model referencyjny. Dopiero potem runner
   odczytuje sesje walidacyjne z usterkami i testowe do oceny. Nie wykorzystuje
   ich etykiet podczas dopasowania skal lub progów.

## Wspólna oś czasu i etykiety

Pierwsza prognoza dotyczy 1000 ms, ostatnia 8000 ms. Każda metoda dostaje
141 chwil oceny, od 1000 do 8000 ms. Wynik błędu prognozy i alarm są datowane
chwilą **otrzymania celu**, nie wcześniejszą chwilą wykonania prognozy.
IF/reguły mogą wtedy korzystać także z bieżącego pomiaru, tak jak wynik błędu GRU.

Liczymy 7 s ocenianego czasu na normalną sesję, czyli 112 s przy 16 sesjach.
Nie wliczamy czasu rozgrzewki jako normalnej pracy detektora. Wszystkie metody
zaczynają liczyć serię przekroczeń od tej samej chwili. Gdy etykieta zdarzenia
występuje w pominiętej rozgrzewce, porównanie kończy się błędem zamiast usuwać
zdarzenie lub skracać czas jego wykrycia. Obecne scenariusze spełniają ten warunek.

Etykiety pozostają rozbieżnościami od sparowanej poprawnej symulacji, zgodnie
z [krokiem 13](step-13-first-ml.md). To obserwowalne odstępstwa, nie dowód ataku.
Początek alarmu dopasowujemy do jednego przedziału etykiety. Dodatkowy początek
alarmu w już wykrytym przedziale jest niedopasowany, choć może nadal przypadać
na usterkę. Raport rozdziela niedopasowane alarmy, alarmy w normalnych sesjach,
pominięte zdarzenia oraz opóźnienia. Nie stosuje rozszerzania trafień na cały
przedział, aby zawyżyć wynik (*point adjustment*).

## Uruchomienie lokalne

Po [krokach 14](step-14-gate-sequences.md) i [15](step-15-first-gru.md):

```powershell
.\.venv\Scripts\python.exe -m ml.gate_alarm_experiment experiments/runs/gate-sequences-20260928-verified experiments/runs/gate-gru-20260930-verified --output experiments/runs/gate-alarms-01
```

Używamy istniejących zależności `requirements-gru.txt`. Podaj własne katalogi,
jeśli nazwałeś je inaczej. Runner potrzebuje także surowych sesji pod ścieżkami
z `source-split.json`, aby zweryfikować etykiety i odtworzyć cechy referencji.
Na nowym komputerze wygeneruj pilot i kolejne artefakty zgodnie z instrukcjami;
samo skopiowanie wag i planu z nieaktualnymi ścieżkami nie wystarczy.
Katalog wyjściowy musi być nowy; błąd zostawia `status: failed`.

W katalogu wynikowym znajdziesz:

- `manifest.json` i kopie manifestów źródłowych: wersje i pochodzenie danych;
- `gru/`, `baselines.joblib`: zamrożone modele lokalnego eksperymentu;
- `calibration.json`: skale, progi, polityka alarmu i liczności;
- `predictions/`: czasy, wyniki i flagi alarmów czterech metod;
- osobne `labels/`: etykiety do oceny, nigdy wejście detektora;
- `report.md` i `report.json`: wspólne liczniki oraz wyniki według przypadku.

Artefakty pozostają poza Git. Nie wczytuj obcych plików `joblib`; zapis dotyczy
własnego modelu referencyjnego. Ten runner dopasowuje go z danych zamiast ładować
dowolny zewnętrzny plik.

## Jak interpretować rezultat

[Zapis zweryfikowanego porównania](results/gate-alarms-20261001.md) zawiera
pochodzenie wyniku, liczby zdarzeń, podział przypadków i ograniczenia.

Porównuj metody w tym samym nowym raporcie. Poprzednie raporty IF/reguł obejmowały
pełne osiem sekund i inne próbki kalibracyjne, więc liczb nie należy mieszać.
Wcześniej oglądany test pozostaje **zbiorem rozwojowym**. To jeden mały pilot,
znane profile, jedna inicjalizacja GRU i krótki czas normalnej pracy.
Również wynik gorszy od reguł zapisujemy bez zmieniania zasad po fakcie.

Następne decyzje powinny wynikać z analizy walidacji: przyczyny pominięć,
stabilność na kolejnych sesjach i nowych warunkach, osobny zbiór kalibracyjny
oraz zamrożony nowy test końcowy. Integracja wykresów/alarmów z Qt i walidacja
na 1–3 ESP32 pozostają kolejnymi etapami; symulator nadal działa bez sprzętu.
