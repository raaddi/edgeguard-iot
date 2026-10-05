# Krok 18: osobna kalibracja i nowe warunki — protokół

Status: protokół zapisany przed wynikami nowego eksperymentu. Modele, skale
błędów i parametry reguł z kroku 16 pozostają zamrożone. Zmieniamy wyłącznie
sposób ustalenia progów na nowych normalnych sesjach. Nie wybieramy zwycięskiej
polityki na podstawie znanego rozwojowego testu.

## Dwie polityki

- `sample_max`: największy wynik spośród nowych normalnych próbek.
- `sustained_max`: największe minimum z każdej kolejnej trójki wyników wewnątrz
  normalnej sesji. Trójki nigdy nie przechodzą między sesjami.

Dla obu alarm zaczyna się na trzecim kolejnym ścisłym przekroczeniu progu.
Obie polityki dają zero alarmów na sesjach kalibracyjnych. To wspólny empiryczny
punkt odniesienia, bez gwarancji tego samego przyszłego budżetu fałszywych alarmów.
`Sustained_max` może pominąć izolowane błędy podczas legalnych przejść krańcówek;
nie wiemy jeszcze, czy poprawi wykrywanie przy akceptowalnych fałszywych alarmach.

## Podział i warunki

- Kalibracja: 16 nowych grup seedów 1000–1015; wyłącznie normalne sesje.
- Ocena rozwojowa: rozłączne grupy 2000–2015, normalne i trzy dotychczasowe
  przypadki usterek. To nowy eksperyment rozwojowy, nie końcowy test pracy.
- Runner odrzuci seedy występujące w podziale źródłowego modelu. Inny seed
  sam nie jest nowym typem zachowania: dodajemy jawne zmiany poniżej.
- Sesje mają 30 s, próbkowanie 50 ms i rozgrzewkę do 1000 ms. Każda sesja
  zaczyna od zamknięcia, z osobnym stanem cech i GRU.
- Kalibracja obejmuje spokojne cykle, legalne powtórzenia i bezczynność.
  Czas pełnego ruchu: 900–1500 ms, poprawna odpowiedź: 50/100/150/200 ms.
- Ocena obejmuje takie same rodziny aktywności z nowymi seedami oraz wydzielone
  warunki: wolniejszy ruch 1600–2000 ms z odpowiedzią 250/300/350 ms i gęstsze
  legalne odwrócenia kierunku/powtórzenia. Parametry nowych warunków nie
  wchodzą do kalibracji. Wyniki raportujemy osobno, nie mieszamy ich w treningu.
- Usterka opóźnienia: 1200 ms odpowiedzi w każdej rodzinie; pozostałe przypadki
  nadal oznaczają zablokowanie otwierania i nieaktywną krańcówkę otwarcia.
  Etykiety są rozbieżnością od normalnej pary o identycznym seedzie i ustawieniach.

Wszystkie cztery metody — GRU, ostatni odczyt, IF i reguły — korzystają z tych
samych sesji i czasu oceny. Progi zapisujemy przed generowaniem/odczytem oceny.
Nie dopasowujemy preprocessing ani wag. Raport zachowa wyniki per sesja/warunek,
precision/recall zdarzeń, pominięcia, opóźnienia, niedopasowane alarmy i alarmy/h
normalnej ekspozycji. Etykiety i konfiguracja symulatora pozostają poza wejściem.

Parametry są ilustracyjne: nie są pomiarami sprzętu ani ustalonymi limitami
bezpieczeństwa mechanizmu. Osiem sekund poprzedniego pilota oraz trzydzieści
sekund tutaj nie udają ciągłego wieloletniego życia domu.

## Interfejs

Rozwijamy istniejący czarny pulpit Qt: wyraźniejsza nawigacja, spójne karty oraz
osobny widok zapisanego eksperymentu ML z pomiarem/prognozą, progiem i alarmem.
To odczyt rzeczywistych wyników offline, bez sugerowania działającej inferencji
na żywo. Logika eksperymentu nadal działa bez Qt i elektroniki.

## Wykonanie — 05.10.2026

Runner `ml.gate_independent_calibration` zrealizował powyższy protokół bez
ponownego treningu. [Zweryfikowane wyniki](results/independent-calibration-20261005.md)
pokazują niewielką zmianę wykryć GRU i wzrost fałszywych alarmów w nowych
poprawnych warunkach. Protokół pozostaje zapisem założeń sprzed wyników.
Wyniki są rozwojowe; nie wybrano polityki do wdrożenia.

Widok **Laboratorium ML — zapisane wyniki** w istniejącym Qt odczytuje te osie
czasu oraz diagnostykę kroku 17. Obsługuje wybór kanału i metody, suwak czasu,
kliknięcie polecenia, osobne etykiety oraz braki danych. Regresja i ogląd
podglądów potwierdzają ten adapter offline; inferencja na żywo pozostaje planem.
