# Krok 15: pierwszy trening GRU na laptopie

## Co jest uczącym się elementem

GRU dostaje historię cech bramy i przewiduje odczyty 50 ms później: stany dwóch
krańcówek oraz prąd napędu. Podczas treningu zmienia wagi tak, żeby zmniejszyć
błąd prognoz na normalnych sesjach. Nie zna seeda, nazwy scenariusza, etykiety
usterki ani przyszłych poleceń. Dane wejściowe opisuje [krok 14](step-14-gate-sequences.md).

To **pierwszy predyktor offline**, jeszcze nie detektor zdarzeń alarmowych.
Mniejszy błąd przewidywania poprawnej pracy nie gwarantuje lepszego wykrywania
awarii. Przy nagłym legalnym poleceniu także może pojawić się duży błąd.

## Protokół ustalony przed pierwszym wynikiem

- Te same sesje i okna dla GRU oraz referencji „następny odczyt jak ostatni”.
- Trening tylko na normalnych sesjach z grup treningowych. Całe grupy pozostają
  rozdzielone; tasowanie minibatchy następuje dopiero wewnątrz treningu.
- Kolejność przed tasowaniem: grupa, profil, przypadek, ID sesji, czas.
- Mediany brakujących wejść i średnie/odchylenia skalowania liczymy wyłącznie
  z treningowych okien. Nakładające się wiersze są przy tym powtarzane, zgodnie
  z reprezentacją danych. Kanał całkowicie brakujący dostaje medianę 0;
  praktycznie stały kanał dostaje skalę 1. To uzupełnienie techniczne, nie pomiar.
- Do 20 przeskalowanych cech dodajemy 20 masek braków, również gdy w treningu
  dany kanał był zawsze dostępny. Rozmiar wejścia: 20 kroków × 40 liczb.
- Jedna jednokierunkowa warstwa GRU, 16 jednostek, liniowe wyjście o rozmiarze 3.
  Stan ukryty zaczyna od zera dla każdego okna. Nie przechodzi między sesjami.
- Krańcówki: dwa logity i binarna entropia krzyżowa (BCE); po sigmoidzie
  prawdopodobieństwa stanów. Do liczenia pomyłek stosujemy stałe 0,5.
- Prąd: regresja wartości standaryzowanej średnią/odchyleniem treningowych celów
  (minimalna skala 0,001 A). Strata to średnia BCE plus średni MSE dostępnych
  celów prądu, z wagami 1:1. Nie dodajemy bezpośrednio amperów do błędów binarnych.
- Brak celu prądu wyklucza go ze straty. Gdy trening nie zawiera żadnego celu
  prądu, ta część prognozy pozostaje niedostępna także podczas oceny.
- Adam, learning rate 0,003, batch 128, limit normy gradientu 1, seed 42,
  30 epok, CPU i jeden wątek obliczeniowy. To konfiguracja początkowa,
  nie wynik strojenia pod wcześniej obejrzany test.
- Zapisujemy epokę o najmniejszej stracie **normalnej walidacji**; remis wybiera
  wcześniejszą epokę. Wagi i preprocessing są zamrożone przed odczytem testu.
  Test sprawdza tę kolejność. Walidacja użyta do wyboru wag nie jest oceną końcową.

## Uruchomienie

W PowerShell, w katalogu repozytorium, z istniejącym środowiskiem `.venv`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-gru.txt
.\.venv\Scripts\python.exe -m ml.gate_gru_experiment experiments/runs/gate-sequences-20260928-verified --output experiments/runs/gate-gru-01 --epochs 30 --seed 42
```

Pakiet PyTorch CPU jest dodatkową zależnością do treningu na Windows/Linux.
Nie jest wymagany do samego uruchamiania symulatora. Pobranie zależności wymaga
Internetu; później trening i prognozowanie działają lokalnie. Zgodność i zasoby
Raspberry Pi trzeba dopiero sprawdzić. Nie zmieniamy obecnego programu EXE.
CI instaluje zależności GRU i wykonuje testy na Pythonie 3.11 i 3.14; przy lokalnym
uruchomieniu testów bez PyTorch dwa moduły testowe GRU są jawnie pomijane.

Katalog sekwencji musi mieć status `completed`. Świeży komputer wymaga wykonania
[eksportu z kroku 14](step-14-gate-sequences.md), a następnie wskazania jego katalogu.
Wczytanie sprawdza manifest, podział, sumy plików, nazwy cech, czasy i kształt
okien. Nie wymaga surowych plików z dawnych ścieżek zapisanych w planie.
Sesja większa niż 64 MiB jest odrzucana: to ograniczony pilot, nie trening
wieloletniej historii. Katalog wyjściowy musi być nowy.

## Co odczytać z wyniku

- `manifest.json`: `completed`/`failed`, commit, wersje, konfiguracja i ograniczenia.
- `model.json` + `weights.pt`: preprocessing, kolejność cech, konfiguracja okna,
  suma kontrolna i wybrane wagi. Wczytujemy własne lokalne artefakty przez
  `weights_only=True`, bez serializowania całego obiektu modelu.
- `training.json`: strata walidacyjna każdej epoki, wybrana epoka, liczba
  przykładów/parametrów i czas treningu na tej stacji roboczej.
- `report.md` i `report.json`: prognozy GRU kontra referencja; metryki osobno
  dla normalnych sesji i każdego rodzaju usterki oraz dla walidacji/testu.
- `predictions/`: rzeczywiste cele, prognozy obu metod i czasy, osobno per sesja.
  Kolejność trzech kanałów jest zapisana w `model.json`. Nie ma tu alarmów.

Prąd oceniamy przez MAE/RMSE w amperach. Krańcówki przez liczbę pomyłek,
odsetek błędów i Brier score (błąd prawdopodobieństw). Raport rozdziela przykłady,
w których krańcówka zmieniła się względem ostatniego wejścia, od pozostałych.
Wspólna podstawa porównania wymaga dostępnego celu i ostatniego odczytu;
brak prognozy jest liczony osobno, nigdy jako zero błędu. To nie metryki ataków.
Regresja prądu nie ma wymuszonego ograniczenia do dodatnich liczb; ewentualne
niepoprawne fizycznie prognozy także wchodzą do błędu.

Ważne pytania do samodzielnego wyjaśnienia:

1. Dlaczego model nie może korzystać z następnego polecenia ani z etykiety usterki?
2. Dlaczego niska średnia pomyłek na długim bezruchu może być myląca?
3. Czym wybór epoki na walidacji różni się od końcowej oceny metody?
4. Dlaczego dobra prognoza nie jest jeszcze skutecznym detektorem anomalii?

## Granice i następny etap

Wcześniej oglądany test tego pilota traktujemy jako dane rozwojowe. Nie deklarujemy
generalizacji na nieznane profile ani sprzęt. Do pracy potrzeba nowego,
zamrożonego testu końcowego, szerszych warunków i późniejszej walidacji fizycznej.
Ustalenie seeda i algorytmów deterministycznych nie gwarantuje identycznych liczb
między różnymi systemami, wersjami bibliotek i procesorami. Zapis/wczytanie oraz
powtórzenie treningu są sprawdzane w jednym środowisku.

Kolejny etap: ustalenie wyniku anomalii z błędów kanałów, kalibracja na normalnej
walidacji i porównanie alarmów z regułami oraz Isolation Forest. Dopiero potem
wyniki w Qt. Model nie przejmuje sterowania urządzeniami. Całość nadal działa
bez elektroniki i pozostawia architekturę dla 1–3 ESP32 oraz symulowanych węzłów.

Dokumentacja użytej biblioteki: [GRU](https://docs.pytorch.org/docs/2.14/generated/torch.nn.GRU.html),
[odtwarzalność](https://docs.pytorch.org/docs/2.14/notes/randomness.html),
[zapis i wczytywanie wag](https://docs.pytorch.org/docs/stable/generated/torch.load.html).
