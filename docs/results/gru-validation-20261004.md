# Diagnostyka GRU na walidacji — 04.10.2026

**Wszystkie 29 pominiętych zdarzeń opóźnienia polecenia pozostawało poniżej
zamrożonego progu.** W tym przebiegu skrócenie wymaganego czasu przekroczenia
nie rozwiązuje tych pominięć. Próg wyznaczył błąd krańcówki podczas poprawnego
otwarcia. To obserwacja pilota, nie dowód jednej przyczyny słabości GRU.

## Pochodzenie i odtwarzalność

- Diagnostyka: [75611361cfe89337491800b18e986e1de83b4a3a](https://github.com/raaddi/edgeguard-iot/commit/75611361cfe89337491800b18e986e1de83b4a3a),
  czyste drzewo, `status: completed`, wyłącznie sesje walidacyjne.
- Raport: `experiments/runs/diagnostics-20261004-verified/report.json`.
  SHA-256: `a5fba4b8cdc2af16a1096f6f978cc9f4b90b0b02d40306bff1eca11c0c33e149`.
- Powtórzenie dało identyczny raport i wszystkie 64 pliki osi czasu.
- W tym checkoutcie nie było wcześniejszych lokalnych danych ani wag. Pilot,
  eksport, 30-epokowy GRU (seed 42) i alarmy odtworzono jako nowe przebiegi
  `ml-rebuilt-20261004`, `sequences-rebuilt-20261004`, `gru-rebuilt-20261004`,
  `alarms-rebuilt-20261004`. Nie są to odzyskane artefakty z 30.09/01.10.
- Pilot bazowy ma commit `ea47f13`, eksport sekwencji, GRU i alarmy mają
  commit `8eb1138`. Wszystkie mają `working_tree_dirty: true`:
  podczas ich wykonywania powstawały pliki diagnostyki, wykresów i instrukcji.
  Kod treningu, symulatora i kalibracji pozostał bez zmian. Czysty commit
  powtórzenia diagnostyki nie zmienia tej informacji o źródłach.
- Manifest odtworzonego GRU SHA-256:
  `125db06a09c58b409f3ef06c63867131c4a04a21164108b3d791cd0eeb97aca9`.
  Manifest porównania SHA-256:
  `c78ae55d0dc9d122d91ad3b9699e8358b596ccf25db6582c4a1bd5bccb3d421e`.
- Python 3.12.14, NumPy 2.5.3, PyTorch 2.14.1+cpu, scikit-learn 1.8.0.
  Normalna walidacja ponownie wybrała epokę 29. Diagnostyka nie zmienia wag,
  skal ani progu; sprawdza zgodność odtworzonych wyników z porównaniem alarmów.

Instrukcja i znaczenie kategorii: [krok 17](../step-17-validation-diagnostics.md).
Wykresy PNG są lokalnymi artefaktami, poza Git. Wyeksportowano 16 sesji
opóźnienia i jedną normalną sesję wyznaczającą próg; obejrzano przykład
opóźnienia oraz normalny przebieg kalibracyjny.

## Co pokazała walidacja

| Przypadek | Zdarzenia | Wykryte | Pominięte poniżej progu |
|---|---:|---:|---:|
| Opóźnienie polecenia | 33 | 4 | 29 |
| Zablokowanie ruchu | 24 | 12 | 12 |
| Krańcówka otwarcia stale nieaktywna | 12 | 12 | 0 |
| Razem | 69 | 28 | 41 |

To **walidacja**, więc liczby różnią się od testowych 27/64 w poprzednim
raporcie. Próg GRU wynosił **14,6579734** w jednostkach błędu podzielonego przez
RMS treningowy. Maksima 29 pominiętych opóźnień mieściły się w zakresie
0,9041352–13,2741853. Żadne nie miało choćby jednej próbki powyżej progu.
Nie wystąpiły pominięcia zaklasyfikowane jako zbyt krótka seria przekroczeń
ani jako alarm rozpoczęty przed zdarzeniem przy polityce trzech próbek.

Normalna sesja `f100ac59-a827-57e0-91a6-8526cc17aa17` (`standard`) osiąga
maksimum w 2000 ms, podczas przejścia krańcówki otwarcia do 1. GRU przewiduje
wtedy prawdopodobieństwo około 0,09314. Znormalizowany błąd tej krańcówki
wynosi 14,65797, a prądu 9,14799. Maksimum poprawnego przejścia ustala więc
próg wyższy niż wszystkie maksima pominiętych opóźnień.

## Dlaczego jedna próbka nie poprawia wyniku

Przy niezmienionym progu i tych samych sesjach:

| Wymagane przekroczenia | Wykryte opóźnienia | Wszystkie wykryte zdarzenia | Niedopasowane alarmy | Alarmy na normalnych sesjach |
|---|---:|---:|---:|---:|
| 1 próbka | 0/33 | 24/69 | 16 | 0 |
| 3 próbki (bieżąca polityka) | 4/33 | 28/69 | 3 | 0 |
| 5 próbek | 4/33 | 28/69 | 3 | 0 |

Normalna ekspozycja to tylko 112 s, już użyta do ustawienia progu. Zero alarmów
na niej wynika z kalibracji i nie potwierdza małej częstości alarmów w przyszłości.
Pięć próbek opóźnia początki o dodatkowe 100 ms względem trzech w tym przebiegu.

Przykład: sesja `01564fb9-3da9-57f2-86cf-233947e14da3` (`early_return`).
W 3000 ms wynik 15,36 przekracza próg, lecz etykieta jest ujemna. Nowy dodatni
przedział zaczyna się w 3050 ms. Alarm z jednej próbki zaczyna się za wcześnie
i pozostaje aktywny; z trzech zaczyna się w 3100 ms i zostaje dopasowany.
To efekt granic syntetycznej rozbieżności i zasady liczenia początku alarmu,
nie dowód, że późniejsza reakcja jest ogólnie lepsza. Nie zmieniamy etykiet
po obejrzeniu wyniku; opisujemy ograniczenie obecnej oceny.

## Następny eksperyment — plan, jeszcze bez implementacji

Najpierw warto rozdzielić wpływ kalibracji i celu prognozy:

1. Na oddzielnych normalnych sesjach kalibracyjnych porównać obecne maksimum
   pojedynczej próbki z progiem wyznaczanym dla utrzymującego się błędu.
   Przykład do uprzedniego zdefiniowania: maksimum minimów kolejnych trójek
   wyników, liczone osobno w sesjach. Pozwala sprawdzić wpływ pojedynczych
   poprawnych przejść bez wybierania progu pod usterki.
2. Przy zamrożonym protokole ocenić nowe legalne opóźnienia, intensywne używanie
   i awarie. Zachować te same dane oraz budżet fałszywych alarmów dla metod;
   raportować także pominięcia, opóźnienia i rozrzut między sesjami.
3. Osobno zbadać hipotezę, że przewidywanie samych odczytów za 50 ms nie daje
   wystarczającego sygnału opóźnionej odpowiedzi na polecenie. Cechy zawierają
   kontekst poleceń, ale cel treningu obejmuje tylko krańcówki i prąd.
   Ewentualny cel związany z odpowiedzią mechanizmu wymaga osobnej ablacji.

Nie wykazaliśmy jeszcze, która zmiana poprawi generalizację. Nie obniżamy
teraz progu, nie zmieniamy modelu ani nie ogłaszamy przewagi ML. Nowe warunki,
niezależna kalibracja, zamrożony test końcowy, Qt i sprzęt pozostają do wykonania.

Weryfikacja kodu: 21 testów diagnostyki/reszt/metryk, 2 testy runnera oraz
regresja obejmująca 286 zaliczonych testów, 9 pominiętych i 8 podtestów.
Moduł `test_mqtt_path.py` wyłączono z tej lokalnej regresji; dostępny zestaw
nie potwierdza działania brokera ani Qt na tym komputerze. Eksport wykresów
sprawdzono przez rzeczywiste wykonanie i ogląd wyników.
