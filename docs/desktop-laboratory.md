# EdgeGuard — desktopowe laboratorium SmartHome

## Start bez elektroniki

```powershell
cd A:\projects\edgeguard-iot
.\.venv\Scripts\python.exe -m pip install -r requirements-desktop.txt
.\.venv\Scripts\python.exe -m simulator.desktop
```

Instalację wykonujesz raz. Aplikacja otwiera własne okno; po instalacji działa offline.
Nie wymaga przeglądarki ani zmiany polityki PowerShell. Wygenerowane dane trzymaj
w ignorowanym `experiments/runs/`. Nie jest to jeszcze instalator ani pakiet EXE.

Po przygotowaniu środowiska możesz też uruchamiać aplikację dwuklikiem pliku
**start-laboratory.cmd** w głównym katalogu repozytorium. Korzysta on z lokalnego
`.venv`, nie wymaga zmiany polityki PowerShell i nie instaluje zależności.
Plik działa także z innego katalogu i przekazuje opcje startowe, np.:

```powershell
.\start-laboratory.cmd --nodes 1 --extra-nodes 2
```

Jeżeli okno przy dwukliku od razu się zamknie, uruchom ten plik z terminala,
aby przeczytać komunikat błędu. Skrypt zwraca kod zakończenia aplikacji.

Opcjonalne ustawienia startowe:

```powershell
.\.venv\Scripts\python.exe -m simulator.desktop --nodes 1 --extra-nodes 2 --seed 42 --run-id test-garaz-01
```

W menu **Eksperyment → Nowy…** ustawisz identyfikator, seed, 1–3 węzły makiety
i 0–9 dodatkowych węzłów wirtualnych. Wszystkie węzły są obecnie symulowane.

## Jeden spójny obszar pracy

| Obszar | Do czego służy |
|---|---|
| Drzewo instalacji | Wszystkie strefy i urządzenia, bieżące wartości, wyszukiwanie po ID, nazwie i węźle |
| Makieta | Rzut całego domu; kliknięcie wybiera urządzenie, dwuklik strefy otwiera zbliżenie |
| Inspektor | Wybrane urządzenie, węzeł, łączność, stan modelu, polecenia i AUTO wentylatora |
| Test zachowania | Cztery rodzaje zdarzeń, dowolny właściwy cel i czas 1–120 s |
| Wykresy | Domyślnie wszystkie czujniki obok siebie; opcjonalnie pojedynczy kanał; 120 ostatnich sekund telemetrii |
| Dziennik | Operacje użytkownika, odrzucenia, pojawienie się i ustąpienie reguł |
| Scenariusze | Pełny harmonogram; oczekujące, aktywne i zakończone zdarzenia |
| Reguły | Bieżące wskazania, ich cel i jawne źródło |
| Węzły | Łączność modelu, liczba komponentów i ostatnia sekwencja w buforze |
| Telemetria JSON | Ostatnia wiadomość węzła wybranego urządzenia; offline oznacza dane historyczne |
| Eksperyment | Manifest konfiguracji, mapowanie komponentów, wersje i liczniki utraty danych |

Separatory paneli są regulowane. Przy małym oknie inspektor przewija się niezależnie.
Wybór w drzewie, na makiecie i w liście inspektora jest synchronizowany. Wybranie
czujnika lub wentylatora ustawia odpowiadający mu kanał w trybie pojedynczym,
ale nie przełącza widoku wszystkich wykresów. Strefa bez czujnika
nie tworzy sztucznego odczytu: wykres zachowuje kanał jawnie wskazany na jego liście.

**Start całej makiety** (F5) uruchamia cały model i wszystkie węzły, niezależnie
od wybranego pomieszczenia. Cztery czujniki domu mają osobne wykresy w jednym rzędzie,
ze wspólną osią czasu i skalą 0–1. Dodatkowe węzły wirtualne dostają kolejne wykresy
w przewijanych rzędach; panel można powiększyć separatorem. Przełącznik w zakładce
Wykresy pozwala przejść do pojedynczego kanału i wrócić do całej makiety.
Odczyt w nagłówku wykresu pochodzi z telemetrii. Offline oznacza brak nowej próbki
i lukę na wykresie, nawet jeśli wewnętrzny stan modelu nadal się zmienia.
Start nie włącza wszystkich lamp ani nie otwiera bram — te urządzenia zachowują
ustawiony stan, a lokalna automatyka wentylatorów reaguje na sygnały.

Kolory na czarnym tle: turkus — czujnik, zieleń — wentylator, żółty — światło,
fiolet — serwo, czerwony — offline, pomarańczowy — przekroczony próg czujnika.
Kolor typu nie oznacza włączenia; stan ON/OFF, kąt lub wartość jest podany tekstem.
Rzut i przypisanie pokoju są orientacyjne, zgodnie z profilem opisanym w
[laboratorium przeglądarkowym](smarthome-laboratory.md).

## Krótki przebieg demonstracyjny

1. Wybierz `led_01`, włącz światło. Wybierz `servo_06`, otwórz furtkę.
2. Wybierz `gas_01`, dodaj wzrost gazu i wykonaj krok. `fan_01` powinien pracować w AUTO.
3. Wybierz `fan_01`, dodaj awarię i wykonaj krok. Porównaj stan zadany 1 ze stanem modelu 0.
4. Dodaj utratę łączności jego węzła. Po kroku polecenie zostanie odrzucone,
   na wykresie zabraknie próbki, a JSON pokaże ostatnią wiadomość.
5. Zapisz JSON, wyeksportuj CSV, sprawdź odtwarzalność. Otwórz zapisany JSON,
   aby wrócić do jego stanu i kontynuować eksperyment.

**Skróty:** F5 start/pauza, F6 krok, Ctrl+N nowy, Ctrl+O otwórz, Ctrl+S zapisz.
Reset, nowy przebieg, import i zamknięcie chronią niezapisane zmiany pytaniem o zapis.
Anulowanie importu albo błędny plik nie zastępują bieżącej sesji.

## Zapis i odtwarzanie

Zapis JSON zatrzymuje zegar i atomowo zapisuje pełny eksperyment. CSV eksportuje
tylko pomiary aktualnego bufora, więc nie zastępuje archiwum JSON. Eksport CSV
nie oznacza oznaczenia całego eksperymentu jako zapisanego.

Import w osobnym wątku odtwarza model z seeda i działań, następnie porównuje manifest,
telemetrię, scenariusze oraz stan końcowy. Dopiero poprawny wynik zastępuje sesję.
Podczas pracy importera sterowanie jest wstrzymane; okno pozostaje responsywne,
a zamknięcie jest możliwe po zakończeniu. Obsługiwany jest aktualny standardowy profil,
format `edgeguard-house-run-v1` i model `house-behaviour-v2`, do 16 MB, 10 000 kroków
i 1000 działań. Pliki innych profili lub niezgodne dane są odrzucane.

Dalsza praca po imporcie dostaje bieżącą wersję kodu; oryginalny plik nie jest
modyfikowany. Import może porównywać dane z innej wersji Pythona, lecz zgodność
wyników jest sprawdzana, a nie zakładana. Pełna historia działań jest w JSON;
panel dziennika jest ograniczony do 250 wierszy, po imporcie pokazuje ostatnie
200 działań. Historyczne przejścia reguł są lokalnym podglądem, nie osobnym trwałym
rejestrem alarmów; bieżące reguły można odtworzyć z modelu.

## Granice obecnego etapu

To komplet obszarów **lokalnego laboratorium**, nie ukończony system magisterski.
Gaz jest umowny (0–1), stany aktuatorów są modelowane, a offline oznacza utratę
komunikacji przy nadal działającej automatyce. Bufor 3000 wiadomości raportuje
usunięcia i pominięcia offline. Czas logiczny nie mierzy wydajności.

MQTT, collector, SQLite, ML, fizyczne ESP32 i ocena Raspberry Pi pozostają do realizacji.
Nie ma jeszcze detekcji cyberataku, automatycznego blokowania ani importu danych
z fizycznych urządzeń. Silnik działa niezależnie od Qt; widok go nie kopiuje.
Streamlit jest zachowany jako wcześniejsze narzędzie, a nowe prace nad obsługą
laboratorium skupiają się na aplikacji desktopowej.

## Weryfikacja dla autora

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Testy Qt działają bez ekranu i sprawdzają kliknięcia, mapowanie wszystkich urządzeń,
zmiany konfiguracji, scenariusze, braki telemetrii, CSV, zgodność archiwów,
odtwarzanie w tle oraz ochronę sesji. CI na Linuksie instaluje `libegl1` i `libopengl0`,
wymagane przez Qt również przy testach offscreen. Testy nie potwierdzają jeszcze
zgodności fizycznej ani zużycia zasobów na Raspberry Pi.
