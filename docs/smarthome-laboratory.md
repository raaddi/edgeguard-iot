# Wirtualne laboratorium SmartHome

> Ten dokument opisuje zachowany interfejs Streamlit. Rozwijana aplikacja Qt
> ma [osobną instrukcję](desktop-laboratory.md) i korzysta z tego samego modelu.

## Co możesz zrobić bez sprzętu

W PowerShell przejdź do katalogu projektu i uruchom aplikację:

```powershell
cd A:\projects\edgeguard-iot
.\.venv\Scripts\python.exe -m streamlit run simulator_app.py
```

Przed pierwszym uruchomieniem zainstaluj zależności zgodnie z README.
Otwórz http://127.0.0.1:8501. Pozostaw terminal otwarty; Ctrl+C zatrzymuje aplikację.
Nie trzeba aktywować środowiska ani zmieniać zasad uruchamiania skryptów PowerShell.
Wszystkie węzły, pomiary i stany urządzeń w tej wersji są symulowane.

Wybraliśmy Python + Streamlit jako interfejs laboratorium na laptopie. Silnik
symulacji pozostaje niezależny od widoku. Osobne okno w PySide6 rozważymy dopiero,
jeśli konkretne wymagania uzasadnią przebudowę. Wdrożenie docelowego panelu na
Raspberry Pi wymaga osobnej oceny zasobów; nie jest jeszcze przesądzone.

## Konsola diagnostyczna

Jeden pulpit łączy mapę, sygnał, sterowanie i testy zachowania. Ciemna stylistyka,
liczniki, pasek sygnału oraz dziennik nawiązują do konsol diagnostycznych i strojenia.
Nie zmieniamy silnika ani kontraktu telemetrii; Streamlit pozostaje adapterem.

1. U góry wybierz **Strefę roboczą**. Ramka na mapie, kanał pomiarowy i lista
   elementów wykonawczych odnoszą się do tej strefy.
2. W **Sterowaniu strefą** wybierz element (np. światło albo skrzydło bramy)
   i wydaj polecenie. Wentylator ma osobny przycisk przywrócenia AUTO.
3. **Podgląd sygnału** pokazuje wartość modelu i wykres wyemitowanej telemetrii.
   Przerywana linia oznacza próg reguły. Przy braku czujnika w strefie wybierasz
   jawnie sygnał referencyjny; dodatkowe węzły mają osobną strefę wirtualną.
4. W **Teście zachowania** wybierz zdarzenie i czas, następnie **Dodaj zdarzenie**.
   Cel domyślnie odpowiada obserwowanemu kanałowi; możesz wybrać inny.
   Kliknij **Krok +1 s** albo **Start**. Harmonogram pokazuje oczekujące/aktywne zdarzenia.
5. Wskazania reguł dotyczą całego domu. Dziennik poniżej pokazuje ostatnie osiem
   poleceń i zaplanowanych scenariuszy, w tym odrzucone polecenia offline.

**Zapis przebiegu** na dole zawiera eksport JSON/CSV, sprawdzenie odtwarzalności
oraz reset. **Inwentarz** zawiera pełną listę komponentów. **Konfiguracja przebiegu**
u góry zawiera seed, identyfikator i liczbę węzłów. Formularz stosujesz przyciskiem
**Nowy przebieg**. Tempo odtwarzania jest obok Start/Pauza.

Reset i Nowy przebieg usuwają stan bieżącej sesji; najpierw pobierz eksport.
Reset jest dostępny przy pauzie. Mapa jest podglądem, a strefę wybierasz z listy.
Czas logiczny nie jest pomiarem wydajności komputera. Przerwy offline są przerwami
na wykresie; wskaźnik wartości modelu może nadal się zmieniać. Dziennik operacji
nie udaje jeszcze historii alarmów detektora.

Interfejs oferuje 1–3 węzły makiety i 0–9 dodatkowych. To limity panelu demonstracyjnego;
silnik ma osobny limit zasobów, po 32 węzły w każdej grupie. Nie zakłada konkretnej
liczby fizycznych ESP32. Dodatkowe węzły mają własny czujnik i nie są rysowane w domu.

## Podstawa odwzorowania

Analiza dostarczonych materiałów z pracy inżynierskiej (2025):

- PDF, rozdział 6.2.1, strona 26: garaż, korytarz, łazienka, toaleta, kuchnia i podwórko;
- PDF, strony 30–35: wizualizacje konstrukcji; fotografie `5.png`, `6.png` i `makieta*.png`;
- PDF, strony 37–46 oraz `arduino.txt`: 10 LED-ów, 6 serw, 4 czujniki i 4 wentylatory;
- `index.html.txt`: garaż A/B, wjazd A/B, drzwi wejściowe i furtka; pozycje serw 0 i 110;
- kod Arduino: wentylator pracuje, gdy odczyt jest **większy niż 330**.

Rozbieżność z wcześniejszym PROJECT_SPEC (9 LED / 4 serwa / 3 MQ-9) zapisujemy
jako profil dostarczonego kodu, nie jako potwierdzoną inwentaryzację fizycznego sprzętu.
Plik PDF zawiera też różne opisy ESP32/Raspberry Pi; nie przenosimy ich automatycznie
do docelowej architektury. Źródłem architektury magisterskiej pozostaje PROJECT_SPEC.

Plan nie jest pomiarem CAD. Nazwy pomieszczeń przypisano orientacyjnie do fotografii.
Pozycje LED-ów i mapowanie ich numerów na strefy są założeniem konfiguracyjnym.
Dwa kanały garażu i dwa kanały wjazdu pokazujemy jako skrzydła; należy potwierdzić
to z autorem. Pokój z przodu po prawej ma etykietę do potwierdzenia.
Pełne materiały źródłowe pozostają poza repozytorium; nie są potrzebne do działania aplikacji.

SHA-256 analizowanych plików:

- arduino.txt: `dc11b0c6604da597ef716b10bbc805370135eefd0ae1dfb86363869263bf39e1`
- index.html.txt: `dcc0092b518210ac7e164aa24140fd1fa0158d9af2078a25d5dd859cad3915aa`

## Podział kodu

```text
simulator/config/house.json  strefy, komponenty, geometria, próg
simulator/house.py           stan domu, polecenia, czas, scenariusze, telemetria
simulator/ui/floorplan.py    wizualizacja SVG
simulator/ui/console.py      pulpit, sygnały, scenariusze i dziennik
simulator/ui/views.py        sterowanie, inwentarz i eksport
simulator/ui/console.css     styl konsoli
simulator/ui/app.py          sesja, konfiguracja i odtwarzanie
simulator_app.py            punkt uruchomienia
```

Silnik nie importuje Streamlit. Stan domu jest niezależny od konkretnego widoku.
Można dodawać komponenty w konfiguracji, a urządzenia grupować w węzły.
Obecnie strefy rozdzielane są kolejno między węzły; czujnik i przypisany wentylator
muszą pozostawać na tym samym węźle. Manifest zapisuje pełne przypisanie.
Docelowy adapter sprzętowy/MQTT będzie osobnym modułem; nie istnieje jeszcze.

Podstawowe ćwiczenie jednego sygnału zachowano w `simulator/lesson_app.py`:
`python -m streamlit run simulator/lesson_app.py --server.port 8502`.
CLI `python -m simulator` również nadal działa. Ćwiczenie i profil domu używają
wspólnego kontraktu **1.0**, opisanego w [kroku 3](step-03-telemetry-contract.md).
Wersje robocze 0.1-draft i 0.2-draft zostały zastąpione; stare archiwa odtwarzaj
na ich oryginalnym commicie. Nowy model ma wersję `house-behaviour-v2`.

## Semantyka modelu

- Krok to 1 sekunda logiczna. Stan początkowy obejmuje próbkę w chwili 0.
- Start/Pauza steruje zegarem, ale ręczne polecenia można wydawać także przy pauzie.
- Polecenie zmienia stan modelu natychmiast; nowa wiadomość pojawia się przy kolejnym kroku.
- Zdarzenia zaczynają się od następnego kroku i kończą po podanej liczbie kroków.
- Każdy czujnik ma osobny generator, którego seed wynika z seeda przebiegu i ID czujnika.
  Zmiana liczby węzłów nie zmienia sygnałów istniejących czujników.
- Wzrost sygnału dodaje umowny składnik 0,6; po zakończeniu zanika on geometrycznie.
- Zamrożenie utrzymuje raportowaną wartość, podczas gdy stan środowiska modelu nadal się zmienia.
- Awaria wentylatora zeruje jego stan symulowany; żądany stan pozostaje widoczny.
- Tryb auto porównuje odczyt z 330/1023. Jest to przeniesienie liczbowej reguły z kodu,
  nie kalibracja sensora, próg bezpieczeństwa ani przeliczenie ppm.
- Ręczne włączenie/wyłączenie wentylatora przełącza go w tryb manualny; auto przywracasz przyciskiem.
- Offline oznacza utratę komunikacji, nie zasilania. Węzeł nadal generuje próbki i wykonuje
  lokalną automatykę, ale nie emituje wiadomości; zdalne polecenia są odrzucane.
- Makieta pokazuje wewnętrzny stan symulatora, także offline. Telemetria pokazuje tylko
  wyemitowane wiadomości; licznik sekwencji ujawnia przerwę po powrocie węzła.
- Reguły progowe i rozbieżności są przeliczane na kroku symulacji. Stan offline jest
  znany bezpośrednio silnikowi; nie stanowi jeszcze detektora opartego na heartbeat.

Nie modelujemy obwodów, charakterystyki chemicznej MQ-9, wentylacji powietrza,
opóźnień mechaniki ani poboru energii. Serwo idealnie wykonuje polecenie 0/110.
Wewnętrzny stan `simulated` jest stanem modelu, a nie niezależnym fizycznym sprzężeniem
zwrotnym. Telemetria przekazuje go jako `reported` z jawnym `feedback: "simulated"`.
Nie ma jeszcze MQTT, SQLite, API, modeli ML i bezpiecznego przełączania na sprzęt.
To działające laboratorium zachowań, nie zakończony Milestone 1.

## Dane i odtwarzanie

Eksport JSON zawiera manifest, wersję Pythona, wersję kodu z początku przebiegu,
konfigurację, harmonogram scenariuszy, dziennik działań, telemetrię i końcowy stan modelu.
Etykiety scenariuszy i ukryty stan środowiska nie trafiają do wiadomości urządzeń.
Całego pliku eksperymentu nie wolno traktować jako macierzy cech ML.
Przed kontrolowanym eksperymentem użyj czystego commita i nowego identyfikatora przebiegu.
Nie edytuj kodu podczas zbierania danych. Reset odtwarza tę samą tożsamość sesji.

`HouseSimulation.replay(exported)` odtwarza model z seeda i działań; przycisk w aplikacji
sprawdza zgodność. To odtwarzanie własnego przebiegu symulatora, nie replay fizycznej telemetrii.
CSV zawiera wyłącznie pomiary. Ocena algorytmów i eksport tabel do LaTeX są osobnym etapem.

Bufor przechowuje 3000 wiadomości. Manifest raportuje liczbę usuniętych i pominiętych
przez offline wiadomości; nie oznacza ich jako utraconych w rzeczywistej sieci.
Cały dziennik mieści do 1000 działań, a przebieg do 10 000 kroków. Po limicie trzeba
zapisać dane i rozpocząć nowy przebieg. Karta przeglądarki przechowuje niezależną sesję;
odświeżenie lub zamknięcie może ją utracić. Eksporty zapisuj w ignorowanym `experiments/runs/`.

## Nauka krok po kroku

1. Wybierz strefę Garaż, włącz światło A; wybierz skrzydło A i otwórz je.
2. W Teście zachowania dodaj wzrost sygnału gas_01, wykonaj krok i sprawdź automatykę fan_01.
3. Dodaj awarię fan_01: porównaj stan zadany i symulowany oraz wskazanie reguły.
4. Pod wykresem rozwiń Ostatnią wiadomość JSON i prześledź dane węzła garażu.
5. Wstrzymaj odtwarzanie. W Zapisie przebiegu pobierz dane i sprawdź odtwarzalność.
6. Następnie wspólnie rozwijamy kontrakt MQTT, zapis do SQLite i testy niezawodności.
