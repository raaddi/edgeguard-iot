# Zrzuty interfejsu

Dwie wybrane ilustracje README pochodzą z rzeczywistego okna Qt, nie z makiety
graficznej. Pokazują lokalny `HouseSimulation`: seed 42, 3 węzły, 24 komponenty.
`desktop-house.png` przedstawia normalną pracę w t=60 s; `desktop-garage.png`
przedstawia wzrost gazu i awarię wentylatora w t=72 s. Zadany ON i raportowany OFF
są wynikiem modelu, a dwa wskazania pochodzą z prostych reguł. To nie fizyczny
pomiar ani nowy wynik detektora ML.

Po zainstalowaniu `requirements-desktop.txt`, z katalogu repozytorium:

~~~powershell
.\.venv\Scripts\python.exe scripts/capture-desktop.py
~~~

Skrypt korzysta z istniejących kontrolek i stałej sekwencji działań. Renderuje
okno 1600×1060 przez Qt offscreen, zapisując tylko te dwa PNG. Nie otwiera serwera,
nie publikuje MQTT i nie eksportuje archiwum ani danych eksperymentu. Wygląd tekstu
może zależeć od dostępnych fontów systemowych. Na Windows używa lokalnego Segoe UI
i Consolas, bez dołączania plików fontów do repozytorium.

Dla roboczego podglądu podaj ignorowany katalog:

~~~powershell
.\.venv\Scripts\python.exe scripts/capture-desktop.py --output tmp/desktop-preview
~~~

Do Git trafiają wyłącznie sprawdzone ilustracje dokumentacji i skrypt. Zdjęcie
referencyjne użytkownika, robocze zrzuty, wagi i surowe dane nie są dołączone.
