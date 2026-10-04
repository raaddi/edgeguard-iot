# Niezależna kalibracja bramy — wyniki 05.10.2026

Wykonano protokół [kroku 18](../step-18-independent-calibration.md), zapisany
przed nowymi wynikami. Porównanie nie wykazało, że sama zmiana progu naprawia
wykrywanie opóźnionej odpowiedzi. Modele, preprocessing, skale reszt i limity
reguł pozostały zamrożone. Nie wybieramy polityki do wdrożenia na tym raporcie.

## Dane i pochodzenie

- 48 normalnych sesji kalibracyjnych: seedy 1000–1015, trzy rodziny aktywności.
- 320 sesji oceny rozwojowej: seedy 2000–2015, pięć warunków i cztery przypadki.
- Seedy są rozłączne z pierwotnym podziałem modelu (42–61). Powtórzenia jednego
  seeda w różnych warunkach/przypadkach są sparowane, nie niezależne replikacje.
- Sesja trwa 30 s, ocena od 1000 do 30000 ms co 50 ms: 581 próbek i 29 s ekspozycji.
  Stan cech i historia zaczynają się od nowa w każdej sesji.
- Normalna kalibracja: 1392 s. Normalna ocena: **2320 s = 38 min 40 s**,
  po 464 s w każdym warunku. Wszystkie metody mają identyczną ekspozycję.
- Obie polityki dały zero alarmów na normalnej kalibracji. Progi zapisano
  przed wygenerowaniem oceny, bez dopasowania do jej usterek.

Runner: `b5c89feb2821d73a3ddcf2d139c3bdc4c7a0206d`, czysty katalog roboczy.
Lokalny wynik: `experiments/runs/independent-calibration-20261004/report.json`.
SHA-256 raportu: `088a6fd152c14ec3833752dd5ecaa6799a7839de96f0e79ca0a9e85132408ebf`.
SHA-256 nowych progów: `8fab87256fe2b7dd45b828a9129bebb04744645633cd247102349f2037ffcd29`.

Źródłem są istniejące lokalne artefakty kroku 16. Manifest nowego przebiegu
zapisuje hashe modelu, wag, baseline, starych skal i podziału. Manifest treningu
źródłowego GRU oznacza katalog jako zmieniony (`8eb1138…`, `working_tree_dirty=true`);
nie ukrywamy tej wcześniejszej granicy odtwarzalności. Nowy eksperyment używa
konkretnych zamrożonych plików, sprawdza ich zgodność i nie trenuje ponownie.
Surowe dane, wagi i osie czasu pozostają lokalne zgodnie z `.gitignore`.

## Progi

Alarm wymaga trzech kolejnych ścisłych przekroczeń. `sustained_max` to maksimum
minimów kolejnych trójek wewnątrz sesji, a nie średnia ani wygładzanie wyniku.

| Metoda | sample_max | sustained_max |
|---|---:|---:|
| GRU | 16,037804 | 16,006054 |
| Ostatni odczyt | 9,695360 | 0,902559 |
| Isolation Forest | 0,675829 | 0,674459 |
| Reguły czasowe | 1,115385 | 1,038462 |

Próg GRU niemal się nie zmienił. Największy normalny błąd jest utrzymującym się
błędem krańcówki zamknięcia: seed 1000, spokojne cykle, 21650 ms, pomiar `0`,
prognoza `0,997370`. Trójka 21550/21600/21650 ms ma minimum `16,006054`.
To obserwacja z kalibracji: problem nie ogranicza się do izolowanej próbki.
Nie ustalamy na jej podstawie fizycznej przyczyny.

## Wspólna ocena zdarzeń

| Polityka | Metoda | Wykryte / 821 | Pominięte | Niedopasowane alarmy | Alarmy normalne | Alarmy / normalną h |
|---|---|---:|---:|---:|---:|---:|
| sample_max | GRU | 234 | 587 | 65 | 8 | 12,41 |
| sustained_max | GRU | 241 | 580 | 113 | 22 | 34,14 |
| sample_max | Ostatni odczyt | 0 | 821 | 0 | 0 | 0 |
| sustained_max | Ostatni odczyt | 0 | 821 | 0 | 0 | 0 |
| sample_max | Isolation Forest | 63 | 758 | 4 | 2 | 3,10 |
| sustained_max | Isolation Forest | 64 | 757 | 6 | 3 | 4,66 |
| sample_max | Reguły czasowe | 540 | 281 | 288 | 88 | 136,55 |
| sustained_max | Reguły czasowe | 544 | 277 | 304 | 96 | 148,97 |

Niedopasowane początki obejmują także dodatkowe alarmy podczas skonfigurowanej
usterki. Alarmy normalne są ich podzbiorem. Godzinowa częstość jest normalizacją
krótkiej ekspozycji, nie pomiarem długiej ciągłej pracy ani prognozą dzienną.

GRU: recall 28,50% → 29,35%, precision 78,26% → 68,08%. Siedem dodatkowych
wykryć to więcej wykrytych rozbieżności krańcówki otwarcia; nie opóźnienia.
Reguły wykrywają więcej zdarzeń, ale mają znacznie więcej fałszywych alarmów.
Nie ogłaszamy przewagi którejkolwiek metody przy wspólnym przyszłym budżecie
alarmów: zero na kalibracji nie zapewniło jednakowych częstości na ocenie.

| Przypadek | Zdarzenia | GRU sample_max | GRU sustained_max |
|---|---:|---:|---:|
| Opóźniona odpowiedź | 433 | 0 | 0 |
| Zablokowany ruch | 260 | 128 | 128 |
| Nieaktywna krańcówka otwarcia | 128 | 106 | 113 |

Etykiety to rozbieżności od poprawnej pary o tym samym seedzie, szumie i
harmonogramie, nie fizyczne początki awarii. Jedna sesja może zawierać wiele
przedziałów rozbieżności. **821 zdarzeń nie oznacza 821 niezależnych usterek.**
Bezczynność ma zero dodatnich zdarzeń także w przypadkach usterek, które
wymagają ruchu. Nie zmieniamy etykiet po obejrzeniu wyników.

## Nowe poprawne warunki

Wszystkie fałszywe alarmy normalnych sesji — dla każdej metody i obu polityk —
wystąpiły w wydzielonym wolniejszym ruchu z poprawną odpowiedzią 250–350 ms.
Warunek ten nie wchodził do kalibracji. Każda pozycja niżej ma 464 s normalnej
oceny; liczby wykryć dotyczą również usterek w danym warunku.

| Warunek | Zdarzenia | GRU sample / sustained wykryte | GRU sample / sustained normalne alarmy |
|---|---:|---:|---:|
| Spokojne cykle | 196 | 64 / 64 | 0 / 0 |
| Powtórzenia poleceń | 178 | 64 / 64 | 0 / 0 |
| Bezczynność | 0 | 0 / 0 | 0 / 0 |
| Wolniejszy ruch | 224 | 50 / 56 | 8 / 22 |
| Odwrócenia kierunku | 223 | 56 / 57 | 0 / 0 |

To ograniczona próba generalizacji: zmieniły się jawne parametry i harmonogram,
a model pozostaje ten sam. `report.json` zachowuje metryki per sesja, seed,
przypadek i warunek oraz listy opóźnień detekcji dla każdej metody/polityki.
Nie obliczamy niepewności z próbek lub przedziałów tak, jakby były niezależne.

## Odtworzenie i pokaz w GUI

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-gru.txt -r requirements-desktop.txt
.\.venv\Scripts\python.exe -m ml.gate_independent_calibration experiments/runs/alarms-rebuilt-20261004 --output experiments/runs/independent-calibration-repeat
.\.venv\Scripts\python.exe -m simulator.desktop
```

Argument źródłowy musi wskazywać **własny zaufany lokalny artefakt kroku 16**,
który obejmuje `baselines.joblib`. Nie pobieraj obcego pliku joblib; ten format
odtwarza obiekty Pythona. Przy braku modelu przygotuj artefakty według
[kroku 16](../step-16-gru-alarms.md). Nowy katalog wynikowy musi nie istnieć.
Nowy trening jest innym źródłem: nie oczekuj automatycznie tych samych hashy.

W pulpicie wybierz **Laboratorium ML — zapisane wyniki**, potem **Otwórz wyniki…**.
Przykład: `timelines/sustained_max/calibration-v1-evaluation-cycles-2000-motion_stall.json`.
Kanał **Prąd napędu [A]**, czas 4 s: pomiar 0,6891 A, prognoza GRU 0,1232 A,
wynik 22,5742 i aktywny alarm. Wybór metody zmienia wynik/próg/alarm;
wykres prognozy nadal jest jasno opisany jako GRU.

Włączanie etykiet tylko ujawnia osobny pas wiedzy eksperymentalnej. Kursor,
kliknięcie polecenia i lista sesji służą przeglądaniu zapisanych danych.
GUI nie wykonuje inferencji na żywo i nie zmienia urządzeń. Testy sprawdzają
prawdziwe sygnały Qt, zgodność wyświetlanych wartości i zachowanie ostatniego
wyniku po błędnym imporcie. Podglądy obejrzano przy 1440×940 i 1080×740;
małe okno ma przewijanie i stale dostępny suwak czasu.

Lokalna regresja: **342 zaliczone, 7 pominiętych, 8 podtestów zaliczonych**.
`test_mqtt_path.py` wyłączono z tego lokalnego uruchomienia; ono nie potwierdza
brokera. Pozostaje jedno ostrzeżenie zależności FastAPI/Starlette o httpx.

## Następny krok badawczy

Przed kolejnym treningiem zapisać osobną ablację celu prognozy: odpowiedź na
polecenie/czas do potwierdzenia wobec samych odczytów +50 ms. Zestaw nowych
warunków jest teraz obejrzany i rozwojowy. Kolejna ocena potrzebuje nowego,
zamrożonego podziału; nie można nazwać obecnych sesji końcowym testem.
Sprzęt ESP32, transfer na fizyczne odczyty, koszt inferencji na Pi 3 i
odporność docelowego detektora nadal wymagają osobnego wykonania i pomiarów.
