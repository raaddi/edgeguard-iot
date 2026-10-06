# Krok 20: prognozy czasów odpowiedzi — protokół przed treningiem

## Pytanie i zakres

Czy przyczynowa historia przy wysłaniu polecenia pozwala przewidzieć czas ACK
oraz potwierdzenia krańcówką lepiej niż prosta mediana normalnego treningu?
[Krok 19](step-19-command-response-targets.md) przygotował przykłady.
Ten przyrost trenuje modele i ocenia prognozy. Skuteczność przyczynowych alarmów
wymaga kolejnego wspólnego eksperymentu; nie wynika z samego MAE.

Porównujemy GRU dwóch czasów i referencję median. Ponownie trenowany GRU
odczytów +50 ms ma ten sam koder, lecz inne cele i jednostki: jego Brier
krańcówek i MAE prądu raportujemy osobno. Różnica liczby przykładów oraz głowic
nie pozwala nazwać tego izolowaną ablacją skuteczności detekcji.

## Dane i kolejność dostępu

Źródłem jest zamknięty eksport `gate-response-export-1` kroku 19.
Czytnik sprawdza manifest, rozłączne grupy, pełną siatkę warunków/przypadków,
hashe i zgodność zapisanych przykładów z surowymi obserwacjami/zdarzeniami.
Pliki sesji odczytuje tylko dla żądanej roli. Ground truth nie wchodzi do X.

- `train`: seedy 3000–3015, normalne cycles/repeats/idle, 48 sesji.
- `selection`: 4000–4007, te same trzy normalne warunki, 24 sesje.
- `calibration`: 5000–5015, te same trzy normalne warunki, 48 sesji.
- `evaluation`: 6000–6015, pięć warunków i cztery przypadki, 320 sesji.

Fit korzysta tylko z `train`. Checkpoint wybieramy wyłącznie na normalnym
`selection`. Wagi wszystkich modeli, preprocessing i mediany zapisujemy,
ponownie wczytujemy i sprawdzamy identyczne prognozy przed odczytem
`calibration` i `evaluation`. Te dwie role służą tutaj raportowaniu błędów;
nie dobieramy na nich hiperparametrów. Późniejsza kalibracja alarmów wymaga
osobnego protokołu. To zbiór rozwojowy tego samego generatora, nie końcowy test.

## Wspólny koder i wejścia

20 próbek cech co 50 ms, 20 cech `gate-features-1`, reset stanu dla każdego
okna. GRU: jedna warstwa, 16 jednostek, jednokierunkowe, 40 kanałów po dodaniu
masek braków. Oba cele używają tych samych parametrów preprocessingu.
Medianę imputacji oraz średnią/odchylenie X dopasowujemy do wszystkich
normalnych treningowych historii odczytów +50 ms, w ustalonej kolejności
cech. Nie dopasowujemy ich osobno do rzadszych poleceń ani do innych ról.
Parametry skalowania celu prądu także pochodzą wyłącznie z `train`.

Historia odpowiedzi kończy się przy `command_sent`; późniejsze dane tworzą
wyłącznie Y. ID, seed, przypadek, warunek, follow_up i etykiety nie są cechami.
GRU odczytów kończy historię przy t i prognozuje t+50 ms. Wszystkie normalne
sesje, także idle, tworzą jego sekwencje; model czasów ma przykład na polecenie.
Zapisujemy tę różnicę liczności zamiast udawać identyczny zbiór okien.

## Cele, strata i referencje

**GRU odpowiedzi:** dwa wyjścia, ACK i krańcówka. Obserwowane czasy kodujemy
jako `log1p(duration_ms / 50)`. Głowica liniowa z softplus daje nieujemne
wartości w tej skali; prognozę dekodujemy jako `50 * expm1(output)` w ms.
Strata jest średnią MSE dwóch kanałów, każdy liczony po własnych obserwowanych
celach. Cenzury nie zastępujemy zerem ani follow_up. Trening i selection tego
pilota mają oba cele kompletne; ogólne maski mają testy. Brak obserwowanych
celów kanału w fit/selection oznacza błąd konfiguracji.

**Mediany odpowiedzi:** dwa czasy z normalnego `train`, w grupach określonych
przez znany cel polecenia (0/110) i stan właściwej krańcówki w ostatniej próbce X.
Brak grupy używa mediany celu, potem mediany globalnej. To jawna referencja
kontekstowa; nie korzysta z nazw warunków, etykiet lub ukrytego ruchu.

**GRU odczytów +50 ms:** dotychczasowa głowica trzech kanałów i strata:
średnia BCE krańcówek + MSE standaryzowanego prądu po obserwowanych celach.
Referencja odczytów powtarza ostatni dostępny pomiar (persistence).

## Trening i checkpoint

Wszystkie sieci: CPU, jeden wątek, algorytmy deterministyczne, Adam 0,003,
batch 128, gradient clip norm 1. Dokładnie 30 epok, bez early stopping.
Trzy ustalone seedy inicjalizacji: **7, 42, 73**. Pokazujemy każdy; nie wybieramy
zwycięskiego seeda na ocenie. Checkpoint ma najmniejszą stratę na normalnym
selection; przy remisie wybieramy najwcześniejszą epokę. Rejestrujemy historię,
liczbę parametrów i czas treningu na laptopie, bez traktowania go jako kosztu Pi.

## Raport i granice wnioskowania

Dla każdego czasu: liczności wszystkich/obserwowanych/cenzurowanych przykładów,
MAE, RMSE i średni błąd `prediction - actual` w ms, tylko na obserwowanych celach.
Osobno powody cenzury. Przeciwne polecenie jest zdarzeniem konkurującym;
480 przerwanych celów nie stanowi pełnych czasów ani automatycznie awarii.
Prognozy i metryki zapisujemy dla każdej sesji, roli, przypadku i warunku.
Dla trzech inicjalizacji raportujemy także minimum/medianę/maksimum MAE.
Normalne slow/reversals pozostają osobno widoczne jako warunki spoza treningu.

Duży błąd prognozy na celowo opóźnionym ACK może być użytecznym sygnałem,
ale nie jest zmierzonym alarmem. Późniejszy detektor ma porównywać upływający
czas z prognozą wystawioną przy wysłaniu, bez czekania na końcową odpowiedź.
Nie porównujemy bezpośrednio MAE sekund z amperami lub Brier krańcówek.
Nie uczymy klasyfikacji przyjęcia ACK: eksport nie zawiera odrzuconych ACK.
Live Qt/MQTT, końcowy test pracy, transfer na ESP32 i koszty Pi pozostają
osobnymi wymaganiami. Wagi, surowe dane i prognozy pozostają poza Git.

## Wykonanie — 06.10.2026

Wykonano wszystkie trzy inicjalizacje po 30 epok z czystego `387cfa2…`.
[Raport wyników](results/response-models-20261006.md) zachowuje zarówno poprawę
łącznego MAE odpowiedzi, jak i pogorszenia na legalnych nowych warunkach.
Pakiet sześciu modeli zapisano przed odczytem oceny. Nadal nie oceniano alarmów.
