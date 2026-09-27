# Krok 13 — pierwszy eksperyment ML

## Protokół oceny ustalony przed treningiem — 28.09.2026

Najpierw uczciwa definicja etykiet: skonfigurowana usterka nie oznacza anomalii
we wszystkich próbkach. Dla każdego przypadku generujemy odpowiadający mu
przebieg bez usterki: ten sam seed, profil, siatka czasu i losowania szumu.
`gate-counterfactual-1` oznacza przedziały, w których różnią się bieżące
kontakty, dostępny prąd, liczba poleceń oczekujących na odpowiedź lub ostatnia
zaakceptowana nastawa. Identyfikatory i etykieta scenariusza nie są porównywane.
W bezczynności usterka może pozostać nieobserwowalna i nie otrzymać zdarzenia.

To **syntetyczna rozbieżność od sparowanego przebiegu**, nie fizyczny moment
uszkodzenia ani uniwersalna definicja anomalii. Drobne różnice timingu mogą
tworzyć krótkie zdarzenia. Etykiety zależą od ilustracyjnej fizyki i dostępnych
kanałów; nie dowodzą przenoszenia wyników na sprzęt. Nie można tworzyć takiej
referencji dla rzeczywistego domu. Nie używamy jej do cech ani treningu.

`gate-events-1` definiuje wspólną ocenę metod:

- Wynik musi przekraczać próg przez trzy kolejne próbki. Alarm zaczyna się
  przy trzeciej próbce, bez cofania daty. Spadek poniżej progu kończy alarm.
- Zdarzenia to maksymalne ciągłe dodatnie przedziały etykiet. Nie rozszerzamy
  trafienia na całe zdarzenie ani nie łączymy przedziałów przez przerwy.
- Początek alarmu wewnątrz zdarzenia może wykryć je jeden raz. Alarm rozpoczęty
  przed zdarzeniem nie dostaje za nie punktu. Kolejne alarmy w już wykrytym
  zdarzeniu są niedopasowane.
- Raport obejmie liczbę zdarzeń wykrytych/pominiętych, precyzję i recall zdarzeń,
  listę opóźnień od początku rozbieżności oraz wszystkie niedopasowane alarmy.
- Fałszywe alarmy/h liczymy na sesjach bez usterek, podając rzeczywisty czas
  normalnej ekspozycji. Dodatkowo liczymy FPR próbek we wszystkich ujemnych
  przedziałach. Krótki pilot nie pozwala potwierdzić małej liczby alarmów/h.

## Uruchomienie pełnego eksperymentu

Z katalogu repozytorium, instalacja zależności jednorazowo:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-ml.txt
.\.venv\Scripts\python.exe -m ml.gate_experiment
```

Runner wypisze katalog wyników i liczbę wykrytych zdarzeń. Domyślnie tworzy
320 sesji: 20 grup seedów × 4 legalne profile × 4 przypadki. To **2560 sekund
symulacji**, nie tyle czasu oczekiwania. Grupy dzielimy 12/4/4; do treningu
trafia 48 sesji normalnych (7728 wierszy cech), do walidacji i testu po 64 sesje.
144 warianty usterek z grup treningowych są wyłączone. Nie robimy losowego
podziału pojedynczych wierszy.
Kolejność treningu jest ustalona według grupy i profilu, niezależnie od ścieżek
i UUID. Nazwy zestawów zawierają seed, aby różne konfiguracje nie używały tych
samych identyfikatorów sesji. Wersje bibliotek zapisujemy do manifestu; nie
zakładamy identycznych wyników numerycznych między różnymi środowiskami.

Opcje: `--groups 5` do krótkiego sprawdzenia (zakres 5–25), `--seed 42`
i `--output experiments/runs/moja-nowa-proba`. Istniejącego katalogu nie
nadpisujemy. Domyślna nazwa zawiera nowy UUID. Nazwy/ścieżki sesji nie są cechami.

## Co rzeczywiście się uczy

**Isolation Forest:** 100 drzew, maksymalnie 256 próbek na drzewo, ustalony seed.
Model dostaje 20 cech z kroku 12; nie dostaje nazw usterek, profili ani etykiet.
Braki zastępujemy medianami wyliczonymi wyłącznie na normalnym treningu,
z wskaźnikami brakujących wartości i zachowaniem pustych kolumn. Dla tych drzew
nie dopasowujemy skalera. Wynik anomalii to negacja `score_samples`.

**Reguły czasowe i prądowe:** wynik jest maksimum trzech ilorazów: aktualny
prąd / maksimum normalnego treningu, czas oczekiwania na odpowiedź / największe
normalne opóźnienie oraz czas od akceptacji do jeszcze niepotwierdzonego kontaktu /
najdłuższy normalny czas potwierdzenia. Reguła zna znaczenie tych kanałów;
to jawnie zaprojektowana metoda odniesienia. Parametry pochodzą z tego samego
treningu. Ten eksperyment ma włączony prąd; ablacja bez prądu pozostaje do zrobienia.

Dla obu metod próg to **największy wynik na normalnej walidacji**, a porównanie
jest ostre (`score > threshold`). To jeden z góry ustalony, ostrożny punkt pracy:
zero obserwowanych alarmów na normalnej walidacji, bez gwarancji na przyszłość.
Nie wybieramy progu na testowych awariach ani nie obniżamy go po zobaczeniu wyniku.
Model i progi zapisujemy przed odczytem sesji testowych. `contamination="auto"`
nie wyznacza tu alarmów — stosujemy własny jawny próg do `score_samples`.

Sposób działania biblioteki opisują dokumentacje
[Isolation Forest](https://scikit-learn.org/1.8/modules/generated/sklearn.ensemble.IsolationForest.html)
i [SimpleImputer](https://scikit-learn.org/1.8/modules/generated/sklearn.impute.SimpleImputer.html).
To wykorzystanie standardowej implementacji; wkład projektu obejmuje scenariusze,
przepływ danych, cechy, protokół oceny i analizę, nie autorstwo algorytmu.

## Pliki wynikowe

- `manifest.json`: status, wersje bibliotek/protokołów, seed, commit i ograniczenia.
- `raw/`, `split.json`, `features/`: źródła, podział i wersjonowane cechy.
- `detectors.joblib`: wytrenowany model i preprocessing oraz parametry reguł;
  plik lokalny, nie trafia do Git. Wczytujemy tylko własne zaufane artefakty.
- `calibration.json`: kolejność cech, progi, parametry i liczność treningu/walidacji.
- `predictions/` oraz osobno `labels/`: rzeczywiste wyniki i etykiety do oceny.
- `report.md`: czytelne podsumowanie; `report.json`: metryki i wyniki według usterek.

Status musi być `completed`. Po błędzie zachowujemy `failed`, a częściowych
wyników nie traktujemy jako ukończonego badania. Testy sprawdzają m.in. stałość
preprocessingu podczas predykcji, odtworzenie modelu po zapisie, rozdzielenie
etykiet i predykcji oraz brak zawyżania trafień zdarzeń.

## Jak interpretować wynik

To pierwszy działający trening i test, nadal **pilot syntetyczny**. Cztery
harmonogramy są ustalone, rozkłady fizyki w podziałach podobne, a podział seedów
nie jest testem nowej rodziny zachowań. Do raportu trzeba brać wynik obu metod,
również zerową wykrywalność ML. Zero fałszywych alarmów z detektora, który nie
wykrywa niczego, nie jest sukcesem. Test zawiera jedynie 128 s normalnej pracy.

To nie benchmark ataków cybernetycznych, nie GRU ani wdrożenie na Raspberry Pi.
Usterki nadal nie dowodzą intencji przeciwnika. Integracja predykcji z Qt,
kalibracja na makiecie i pomiary sprzętowe pozostają kolejnymi etapami.
Po pierwszym wyniku analizujemy walidację i relacje między cechami, poszerzamy
profile/parametry i planujemy predykcję sekwencyjną. Każdą zmianę metody opisujemy
jako nowy eksperyment; nie stroimy jej ukradkiem na odczytanym teście pilota.
