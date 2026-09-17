# Krok 4 — prototyp garażu jako aplikacja desktopowa

To mały test sposobu obsługi w **Pythonie i PySide6 (Qt)**. Otwiera osobne okno.
Dotychczasowe laboratorium Streamlit pozostaje dostępne do porównania; prototyp
nie przenosi jeszcze wszystkich pomieszczeń, eksportu CSV i narzędzi eksperymentów.

## Uruchomienie w Windows

W katalogu repozytorium, z istniejącym środowiskiem `.venv`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-desktop.txt
.\.venv\Scripts\python.exe -m simulator.desktop
```

Instalację wykonujesz raz; potem wystarczy drugie polecenie. Nie trzeba aktywować
środowiska, zmieniać polityki PowerShell ani uruchamiać przeglądarki. Po instalacji
aplikacja działa bez Internetu i sprzętu. Nie wymaga działającego Streamlita.
Pakiet `PySide6-Essentials` udostępnia używane moduły QtCore, QtGui, QtWidgets i QtTest.

Przykład innego przypisania węzłów:

```powershell
.\.venv\Scripts\python.exe -m simulator.desktop --nodes 1 --extra-nodes 2 --seed 42
```

Silnik nadal symuluje cały dom. Okno udostępnia sterowanie garażem; dodatkowe
węzły nie są rysowane. Węzeł garażu wynika z konfiguracji, nie ze stałego ID.

## Ćwiczenie na kilka minut

1. Kliknij `led_01` na schemacie i **Włącz**. W panelu oraz na schemacie pojawi się ON.
2. Kliknij `servo_01` i **Otwórz**. Stan modelu zmieni się na 110°. To umowny,
   natychmiastowy stan serwa, nie pomiar ruchu mechanizmu.
3. Dodaj **Wzrost sygnału gazu**, a następnie wykonaj **Krok +1 s**. Wykres pokaże
   wzrost sygnału, a `fan_01` przejdzie w ON dzięki istniejącej regule progowej.
4. Dodaj **Awarię wentylatora**, wykonaj krok i kliknij `fan_01`. Porównaj stan
   zadany 1 ze stanem modelu 0 oraz wskazaniem reguły.
5. Dodaj **Utratę łączności węzła**, wykonaj krok i spróbuj sterować bramą.
   Dziennik pokaże odrzucenie. Wykres ma lukę; wewnętrzny stan modelu nadal istnieje.
6. **Zapisz przebieg…** zatrzymuje zegar i zapisuje pełny eksperyment JSON,
   zgodny z istniejącym `HouseSimulation.replay`. Zapisuj do ignorowanego
   katalogu `experiments/runs/`. Zamknięcie okna z niezapisanymi zmianami pyta o zapis.

Urządzenie można wybrać również z listy klawiaturą. Separatory między schematem,
wykresem i inspektorem można przeciągać. Wykres stale obserwuje `gas_01`, niezależnie
od wybranego aktuatora; pokazuje maksymalnie 120 ostatnich sekund logicznych.
Przerywana linia oznacza próg 330/1023, a nie skalibrowany próg bezpieczeństwa MQ-9.

## Co warto zrozumieć w kodzie

- `simulator/house.py` — istniejący silnik: polecenia, scenariusze i wiadomości.
- `simulator/desktop/window.py` — adapter Qt: zdarzenia przycisków, zegar,
  inspektor i zapis. `QTimer` wywołuje krok; nie zmienia znaczenia czasu modelu.
- `simulator/desktop/canvas.py` — rysowanie i wskazanie klikniętego urządzenia;
  nie zawiera osobnej logiki działania domu. Wykres nie łączy linii przez braki danych.
- `tests/test_desktop.py` — testy kliknięć Qt, scenariuszy, zmiany liczby węzłów,
  zegara i zgodności eksportu z odtwarzaniem.

Wszystkie wartości są syntetyczne. Rysunek jest schematem funkcjonalnym garażu,
nie odwzorowaniem CAD. Nie ma jeszcze MQTT, ML ani komunikacji ze sprzętem.
Tryb symulacji pracuje w wątku interfejsu; przyszłe operacje sieciowe i dłuższe
obliczenia muszą działać poza nim. To prototyp do oceny obsługi, nie gotowa dystrybucja
EXE ani potwierdzone wdrożenie na Raspberry Pi.
