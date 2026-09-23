# ML, interfejs i makieta — kierunek badań

Zapis decyzji i rekomendacji z 17.09.2026. Dokument rozwija
[PROJECT_SPEC](../PROJECT_SPEC.md), zwłaszcza kryteria jakości z 15.09.
**Status: plan badań, nie wyniki ani opis gotowego detektora.**

## Dwa ważne wymagania użytkownika

- ML jest głównym wkładem badawczym magisterki na specjalności AI/ML.
  Projekt ma obejmować dane, trening, ocenę, wdrożenie i analizę błędów.
- Interfejs jest kluczową częścią produktu: jedna czytelna, interaktywna konsola
  do obsługi makiety, obserwowania danych i rozumienia decyzji detektora.

Oceny 5,5 nie da się zagwarantować. Zakres i kryteria uczelni należy uzgodnić
z promotorem. Jakość wykazujemy eksperymentami i zrozumiałym wkładem własnym.

Tytuł roboczy: **Detekcja anomalii w rozproszonym systemie SmartHome
z wykorzystaniem uczenia maszynowego i analizy wielowymiarowych szeregów
czasowych na urządzeniu brzegowym.**

## Konkretny problem ML

Z historii obserwowanych poleceń, odpowiedzi mechanizmu i komunikacji przewidywać
kolejne obserwacje. Z błędów predykcji wyznaczać wynik anomalii, a następnie
zdarzenia alarmowe. Model uczy zależności czasowych z danych; reguły automatyki
domu i ograniczenia elementów wykonawczych działają niezależnie.

Główna hipoteza: historia i połączenie poleceń z niezależnym pomiarem odpowiedzi
poprawiają wykrywanie wybranych nieprawidłowości przy porównywalnej liczbie
fałszywych alarmów. Sprawdzamy ją, nie zakładamy jej prawdziwości.

Zestaw metod planowany do porównania:

1. Mały predyktor **GRU** jako główna metoda sekwencyjna. Okno 60 s jest punktem
   wyjścia do pilota, nie zatwierdzonym parametrem. Dobór okna, próbkowania,
   liczby jednostek i funkcji straty zależy od danych i budżetu Raspberry Pi.
   Wyjścia ciągłe i binarne wymagają odpowiednich strat i skalowania błędów;
   nie sumujemy bezpośrednio amperów, sekund i stanów logicznych.
2. **Isolation Forest** na cechach z okien: liczności, odstępy, powtórzenia,
   przejścia stanów i opóźnienia odpowiedzi. To również pełnoprawna metoda ML.
3. Reguły progowe i czasowe, w tym limity poleceń i timeout osiągnięcia pozycji,
   oraz prosta referencja predykcyjna „następny stan jak ostatni”.

Wszystkie metody dostają porównywalny dostęp do obserwacji. Próg wyniku ML
dobieramy na walidacji. Końcowe `if score > threshold` nie zastępuje uczenia:
to sposób zamiany wyuczonego wyniku na alarm. Nie dodajemy kolejnych sieci
bez konkretnego pytania badawczego. GRU jest kandydatem do zweryfikowania,
nie obietnicą przewagi ani potwierdzeniem zgodności runtime z Raspberry Pi.

## Ponowna ocena makiety: najpierw obserwowalność

Obecny model serwa natychmiast wykonuje polecenie. Pole `simulated` nie jest
pomiarem fizycznej pozycji. Odczyty gazu nie mają zweryfikowanego modelu
wentylacji. Trening na tych uproszczeniach nie wystarczy do wykazania działania
detektora na prawdziwym sprzęcie.

**Rekomendacja: zachować dom, ale szczegółowo oprzyrządować jeden mechanizm
bramy lub garażu.** Wybrać go po potwierdzeniu inwentarza i miejsca montażu.

| Zmiana proponowana | Co rzeczywiście obserwujemy | Priorytet |
|---|---|---|
| Dwa czujniki krańcowe, np. kontaktrony z magnesami | Osiągnięcie pozycji zamkniętej i otwartej; czas przejścia | Pierwszy fizyczny eksperyment |
| Rejestr poleceń i odbioru wiadomości na gatewayu MQTT | Treść, kolejność, rytm, korelacja polecenia i odpowiedzi | Podstawa programowa, bez nowego czujnika |
| Pomiar prądu pojedynczego napędu, np. układ klasy INA219 | Zmiany obciążenia elektrycznego, dodatkowy kanał do badań | Opcjonalnie po pilocie |
| Ciągły pomiar położenia, np. enkoder lub serwo z wyjściem feedback | Przebieg ruchu zamiast samych punktów końcowych | Jeśli krańcówki okażą się niewystarczające |

Kontaktrony nie mierzą kąta pomiędzy końcami, a prąd nie dowodzi ruchu.
Dwa nieaktywne czujniki oznaczają pozycję pośrednią/nieznaną, nie automatycznie
awarię; oba aktywne wymagają oceny geometrii i spójności. Uwzględnić drgania
styków, opóźnienia i utratę pomiarów. Nie zamieniać polecenia PWM na „zmierzony kąt”.

Nie trzeba wyposażać wszystkich sześciu serw. Gaz, wentylatory i oświetlenie
zostają częścią makiety i testów porównawczych. Nie dodajemy kamery, mikrofonu
ani dodatkowych pomieszczeń bez potrzeby badawczej.

Dobór modułu, zakresu prądu, bocznika, zasilania i poziomów logicznych wymaga
sprawdzenia konkretnego napędu i ESP32. To nie jest gotowa lista zakupowa.
Testy obciążenia nie zakładają blokowania napędu; kontrolowane błędy komunikacji
i wstrzyknięcia w adapterze wystarczą na początek. Limit cykli chroni mechanizm.

## Cyberbezpieczeństwo i granice wnioskowania

| Scenariusz | Zmiana w laboratorium | Porównanie z normalnym zachowaniem |
|---|---|---|
| Nadużycie uprawnień sterownika | Poprawne polecenia MQTT w nietypowych sekwencjach, także poniżej prostego limitu częstości | Intensywne legalne użytkowanie, anulowanie operacji, ponowienia |
| Replay/manipulacja odpowiedzi | Starszy fragment pomiaru w nowych wiadomościach, przy zachowaniu obserwowalnego bieżącego kontekstu | Naturalnie stały odczyt, opóźnienie, buforowanie i duplikaty |
| Prosta anomalia kontrolna | Jawny nadmiar poleceń albo brak odpowiedzi po poleceniu | Przypadki, w których reguły powinny być mocne |

Replay pomiaru to scenariusz cybernetyczny, nie obecne odtworzenie własnego
archiwum eksperymentu. Manipulacja gazem zostaje kandydatem drugorzędnym:
najpierw pilot musi wykazać użyteczny związek odczytu z dostępnym kontekstem.

Dla każdego eksperymentu deklarujemy, co kontroluje przeciwnik i co pozostaje
wiarygodne. Logowanie na gatewayu daje obserwacje odbioru, nie potwierdza
prawdziwości treści wysłanej przez przejęty węzeł. Pomiar pozycji na tym samym
przejętym ESP32 nie jest niezależną granicą zaufania. Drugi ESP32 dla feedbacku
jest wariantem eksperymentu, nie wymaganiem dla minimalnego układu z jednym węzłem.
Jeśli wszystkie obserwacje są nierozróżnialne od legalnej pracy, detektor nie
rozpozna ataku. Alarm oznacza podejrzane zachowanie, nie dowód intencji.

Zachowujemy uwierzytelnianie klientów i ACL topiców. Tożsamości klienta nie
wywodzimy z samego `device_id` w payloadzie. Automatyczne blokowanie przez ML
nie wchodzi do początkowego eksperymentu.

## Co zmienimy w danych i symulatorze

- Wersjonowany profil badawczy jednego mechanizmu obok istniejącego profilu domu.
  Ruch ma trwać w czasie; model kontaktów i opcjonalnego prądu musi dopuszczać
  naturalną zmienność. Parametry zweryfikujemy później na sprzęcie.
- Wiele prawidłowych przebiegów: okresy bezczynności, różne rytmy użytkowania,
  poprawne powtórzenia, zmienne opóźnienia. Inny seed sam nie daje nowego typu
  zachowania. Scenariusze i profile testowe nie mogą być kopiami treningu.
- Obecny kontrakt 1.0 dopuszcza wyłącznie `gas_signal` w sensorach. Kontakty,
  prąd i zdarzenia wymagają jawnej ewolucji kontraktu, jednostek, znaczników czasu,
  reguł zgodności oraz testów. Nie kodujemy ich jako znormalizowany gaz.
- Krok 1 s może pominąć cały ruch serwa. Pilot ustali rozdzielczość zdarzeń
  i próbkowania; GUI może odświeżać się rzadziej niż kolektor. Rozdzielamy czas
  urządzenia, czas odbioru i niepewność synchronizacji.
- Cechy budujemy z informacji dostępnych detektorowi w danej chwili. Etykiety,
  harmonogram awarii, seed i ukryty stan modelu pozostają poza wejściem ML.
  Brak próbki ma maskę i wiek, nie jest zerem; nie uzupełniamy go przyszłością.
- Warianty z różną liczbą ESP32 opisują możliwości i rolę mechanizmu. Nie
  uzależniamy wymiaru wejścia od stałej liczby węzłów ani od ich numerów ID.
- Dane treningowe zapisuje kolektor/runner, nie ograniczony bufor wykresów.
  Wspólna logika cech i modelu działa poza Qt i umożliwia eksperyment bez GUI.

## Eksperymenty, które tworzą wkład pracy

1. Te same niezależne przebiegi testowe dla reguł, Isolation Forest i GRU.
   Trening na normalnych przebiegach; walidacja służy do ustawień modeli/progów.
   Podział całymi sesjami przed tworzeniem okien; brak przenikania nakładających
   się okien. Preprocessing dopasowany wyłącznie do treningu.
2. Ablacje: sama komunikacja vs komunikacja z feedbackiem, krótka vs dłuższa
   historia, opcjonalnie pozycja vs pozycja i prąd. Pozwala to sprawdzić,
   która informacja wnosi korzyść, zamiast przypisywać wszystko nazwie sieci.
3. Test nowych wariantów zdarzeń, legalnych intensywnych sesji i awarii.
   Powtórzenia z różnymi przebiegami; raport rozrzutu, nie tylko najlepszego wyniku.
4. Transfer: model z symulacji testowany bez zmian na sprzęcie oraz osobny
   wariant adaptowany na wydzielonych normalnych danych fizycznych. Końcowy
   fizyczny test pozostaje nietknięty. Publiczny zbiór może być osobnym
   benchmarkiem po weryfikacji semantyki i licencji, nie automatyczną domieszką.
5. Precision/recall zdarzeń, false alarms/h, czas wykrycia z raportem pominięć,
   metryki próbek jako uzupełnienie, koszt inferencji p50/p95, RAM/CPU i rozmiar
   modelu na Raspberry Pi. Z góry określić łączenie alarmów i granice zdarzeń.
   Nie poprawiać całego przedziału etykiet na podstawie pojedynczego trafienia.

Ilość danych oceniamy krzywymi uczenia, liczbą niezależnych sesji/cykli i czasem
normalnej pracy. 50 tys. silnie skorelowanych rekordów nie oznacza 50 tys.
niezależnych przykładów. Pełny trening na laptopie; inferencja i pomiary na Pi.

## Aktualizacja modelu na ostatnich danych — plan z 18.09.2026

Rozważamy okresowe ponowne trenowanie na przesuwającym się oknie historii,
np. ostatnich 60 dni. To inny parametr niż 60 sekund kontekstu pojedynczej
predykcji. Najpierw uruchamiamy i oceniamy model stały; adaptacja jest kolejnym
eksperymentem, a nie już działającą funkcją ani uczeniem po każdej wiadomości.

Proponowany cykl: zbieranie danych -> wybór dopuszczonych sesji -> trening
wersji kandydującej na laptopie -> walidacja -> wdrożenie na Raspberry Pi.
W trakcie treningu inferencja nadal korzysta z dotychczasowego modelu.
Częstotliwość, np. raz w tygodniu, oraz okno 7/30/60 dni dobierzemy w badaniu.
Jeśli danych jest za mało, zachowujemy dotychczasowy model; nie udajemy pełnej
historii ani nie uzupełniamy jej powielonymi sesjami.

- Podejrzane i uszkodzone przebiegi kierujemy do osobnej oceny. Brak alarmu
  nie potwierdza poprawności danych. Zapisujemy źródło decyzji o dopuszczeniu
  do treningu; nie utożsamiamy legalnej zmiany nawyków z awarią lub atakiem.
- Nową wersję porównujemy z aktywną na walidacji dostępnej przed wdrożeniem,
  w tym na kontrolnych scenariuszach. Kryteria fałszywych alarmów, wykrywalności
  i kosztu inferencji ustalamy przed porównaniem. Zachowujemy wersję do rollbacku.
- W badaniu kroczącym każda predykcja powstaje przed ewentualnym użyciem danej
  próbki do uczenia. Podziały całymi sesjami i brak przecieku okien nadal obowiązują;
  końcowego zbioru testowego nie używamy do treningu ani wyboru wersji.
- Pełny trening od nowej inicjalizacji na wybranym oknie pozwala zbadać wariant
  „tylko ostatnie 60 dni”. Douczanie starych wag może zachować wpływ starszych
  danych, więc ewentualnie raportujemy je jako osobną metodę.
- Porównujemy model stały i aktualizowany przy legalnej zmianie sposobu
  użytkowania oraz kontrolowanych nieprawidłowościach. Raportujemy także
  koszt treningu i przypadki, w których adaptacja pogorszyła detekcję.

W interfejsie planujemy pokazać datę i zakres treningu, liczbę dopuszczonych
sesji, wersję modelu oraz wynik walidacji kandydata. Symulator może przyspieszyć
czas logiczny; symulowane 60 dni nie zastępuje 60 dni fizycznych obserwacji.

## Pomysły użytkownika: życie rodziny i dodatkowe AI — 21.09.2026

**Status: zapis propozycji i rekomendacji do pilota, bez implementacji oraz bez
rozszerzania obowiązkowego zakresu pracy o kamerę i mikrofon.** Użytkownik proponuje
wygenerowanie np. trzech lat życia rodziny w makiecie, trening na tych danych,
sterowanie dźwiękiem/głosem oraz kamerę rozpoznającą tablicę kartonowego samochodzika.
Pomysły rozwijają dotychczasowy plan; nie zastępują badania odpowiedzi mechanizmu.

### Generator codziennego użytkowania jako źródło danych ML

Rekomendacja: przygotować konfigurowalny generator **różnych prawidłowych dni**.
Łączyć kalendarz i rytm aktywności z istniejącym modelem urządzeń:

| Rodzaj dnia / zdarzenia | Przykładowe obserwowalne następstwa |
|---|---|
| Dzień roboczy | Poranne światła, otwarcie i zamknięcie drzwi/bramy, okresy bezczynności, powrót i wieczorne światła |
| Weekend / praca z domu | Inne pory, więcej aktywności w domu, krótsze wyjścia |
| Goście / wyjazd / powrót po zapomnianą rzecz | Legalne intensywne używanie, dłuższa cisza, poprawne powtórzenie operacji |
| Zmiana nawyków / sezonu | Stopniowe lub nagłe przesunięcie pór i częstości działań |
| Działanie urządzeń i komunikacji | Zmienny czas odpowiedzi, pomiary kontaktów po ich dodaniu, opóźnienia i braki wiadomości |

Pory, odstępy i kolejność losujemy z opisanych rozkładów zależnych od profilu
rodziny, zachowując związki między zdarzeniami. Nie losujemy niezależnie każdego
światła co sekundę. Nie kopiujemy jednego dnia 1095 razy. Scenariusz rodziny może
być generatorem regułowym/probabilistycznym; uczącym się elementem jest detektor.
Nie potrzebujemy LLM do produkowania wiarygodnie wyglądających, lecz niesprawdzonych
odczytów. Parametry i źródła założeń zapisujemy, a później konfrontujemy z pomiarami.

Odczyty gazu pozostają osobnym kanałem: normalna zmienność i jawnie wydzielone
scenariusze nieprawidłowości. Bez pomiarów nie zakładamy, że gotowanie oznacza
określone stężenie ani że obecny model opisuje fizykę MQ-9 i wentylacji.
Wewnętrzna wiedza generatora „rodzina wyszła” nie jest cechą detektora, dopóki
nie mamy odpowiadającej jej dostępnej obserwacji. Harmonogram, etykiety i seed
pozostają oddzielone od wejść ML.

**Co model ma wykrywać:** niezgodne z kontekstem sekwencje i rytm poleceń,
powtórzenia operacji oraz niezgodność polecenia z czasem/rodzajem odpowiedzi.
Przykład badawczy: seria cykli bramy poniżej prostego limitu częstości, lecz
o nietypowym przebiegu, zestawiona z legalnym intensywnym używaniem. Samo otwarcie
o 02:00 nie dowodzi ataku; późny powrót lub praca zmianowa są kontrprzykładami.
Anomalia jest wskazaniem do oceny, nie automatyczną klasyfikacją intencji.

Krótka historia mechanizmu i rytm dobowy mają różne skale czasu. Okno GRU 60 s
nie obejmuje dnia: w pilocie sprawdzimy jawny kontekst godziny/dnia tygodnia
i agregaty liczone wyłącznie z przeszłości obok szybkich pomiarów mechanizmu.
Kalendarz wymaga dostępnego źródła czasu; zapisujemy strefę i obsługę zmian czasu,
a brak zsynchronizowanego czasu na urządzeniu nie może być ukrycie uzupełniany
przyszłą wiedzą. Porównanie obejmie także reguły czasowe i prosty statystyczny
model częstości zależnej od pory dnia, nie tylko pojedyncze stałe progi.

### Trzy lata są wariantem eksperymentu, nie wymaganym rozmiarem

Najpierw mały pilot, np. 30–90 dni logicznych z kilkoma profilami rodziny.
Jeżeli dane są użyteczne, porównamy większe zakresy, np. 365 i 1095 dni,
krzywe uczenia oraz koszt przechowywania i treningu. Te liczby są punktami
startowymi do badań, nie gwarancją wystarczającej ilości danych.

Przy założeniu 365 dni/rok i jednej pełnej wiadomości na sekundę trzy lata to
**94 608 000 wiadomości na węzeł**, a dla trzech węzłów 283 824 000. Liczba
zdarzeń nie jest liczbą niezależnych przykładów. Potrzebujemy generatora
zdarzeń i strumieniowego zapisu porcjami, bez renderowania każdego kroku Qt
i bez czekania lat w czasie rzeczywistym. Szybkie próbki ruchu i wolniejsze
podsumowania dnia muszą zachować jednostki, kolejność, braki i granice sesji.
Zmniejszanie częstotliwości nie może ukryć krótkich awarii mechanizmu.

Obecny model ma limit 10 000 kroków, 1000 akcji i bufor 3000 wiadomości,
a odbiornik poleceń 256 wyników na węzeł. **Nie obsługuje jeszcze wieloletniej
generacji.** Potrzebny będzie runner sesji z trwałym zapisem, zarządzaniem
stanem i identyfikatorami przebiegów oraz wznowieniem. Nie wystarczy zwiększyć
limitów ani skleić niezależnych restartów, udając ciągłe życie domu.
Architektura dalej wspiera 1–3 fizyczne ESP32 i dodatkowe węzły symulowane.

Podział na trening, walidację i test robimy przed tworzeniem okien, całymi
sesjami/blokami czasu, z rozłącznymi wariantami zachowania i parametrami.
Okna i ich kontekst historyczny nie przekraczają granic podziału. Osobno badamy
przyszłość znanej rodziny oraz nieznany profil; sama zmiana seeda to zbyt słaby
test uogólnienia. Trening detektora normalności korzysta z dopuszczonych
normalnych przebiegów, walidacja służy doborowi progu, a test obejmuje legalne
odstępstwa, awarie i kontrolowane scenariusze cybernetyczne. Porównujemy GRU,
Isolation Forest i metody odniesienia na tych samych dostępnych obserwacjach.
Trzy lata syntetyczne nadal nie zastępują fizycznej walidacji i pomiarów na Pi.

Do sprawdzenia założeń aktywności można rozważyć [zbiory CASAS, Washington
State University](https://casas.wsu.edu/datasets/), zawierające m.in. codzienne
życie i aktywności wielu mieszkańców. To kandydat do przeglądu, nie pobrany
zbiór ani gotowe dane naszych aktuatorów; przed użyciem sprawdzimy warunki
dostępu, licencję, czujniki i zgodność znaczenia danych.

### Opcjonalny moduł: tablica kartonowego samochodzika

**Preferowany dodatek demonstracyjny po pilocie głównego ML:** obraz → lokalizacja
tablicy → OCR znaków → ocena jakości/odmowa → lista dopuszczonych oznaczeń →
żądanie otwarcia bramy przez istniejącą ścieżkę poleceń. Wkład ML to rozpoznawanie
obrazu i tekstu; sprawdzenie listy uprawnień pozostaje zwykłą regułą. Użycie
gotowego modelu opisujemy jako integrację, nie własny trening od zera.

Pracę można zacząć bez elektroniki od sztucznych tablic, plików obrazów i nagrań;
później dodać zdjęcia samochodzika i kamerę. Badamy różne kąty, odległości,
oświetlenie, rozmycie i częściowe zasłonięcia. Dzielimy dane całymi sesjami
fotografowania/nagrywania, nie sąsiednimi klatkami; sprawdzamy także niewidziane
oznaczenia. Mierzymy poprawność całego odczytu, błędne dopuszczenia i odmowy,
opóźnienie oraz zasoby na docelowym sprzęcie. Nie zakładamy, że Pi 3 obsłuży
równocześnie OCR i główny detektor bez pomiaru.

Niski wynik jakości lub brak odczytu nie otwierają bramy. W makiecie można
pokazać rozpoznanie własnej sztucznej tablicy; sam napis można skopiować, więc
OCR nie potwierdza tożsamości samochodu i nie jest samodzielnym zabezpieczeniem
rzeczywistych drzwi. Kontrolowany pokaz kopii tablicy pozwala omówić tę granicę
zaufania. Wynik rozpoznawania i żądanie sterowania wymagają jawnego kontraktu
zdarzeń; nie dopisujemy ich do pól czujnika gazu. ML anomalii nadal obserwuje
komendy i odpowiedź bramy, ale nie obiecujemy, że wykryje poprawnie skopiowaną tablicę.

### Alternatywa: sterowanie dźwiękiem / głosem

Zapisujemy dwa warianty: rozpoznawanie krótkich poleceń mówionych (np. „włącz
światło w garażu”) oraz klasyfikację umówionego dźwięku. Proste wykrywanie
głośności/klaskania progiem nie jest samo w sobie ML. Dla wersji głosowej:
przycisk nagrywania → rozpoznanie mowy → ograniczony zestaw intencji → walidacja
urządzenia/nastawy → dotychczasowy kontrakt polecenia. Transkrypcja nie daje
uprawnień; głos/nagranie nie uwierzytelniają osoby. Otwarcie wejścia wymagałoby
osobnego uprawnienia/potwierdzenia, nie swobodnego wykonania tekstu przez LLM.
Ocenialibyśmy pomyłki intencji, fałszywe aktywacje, odmowy i opóźnienia dla
różnych głosów i hałasu. To alternatywa dla kamery, nie równoległy obowiązek.

### Rekomendowana kolejność

1. Dokończyć trwały zapis poleceń/odpowiedzi i profil ruchu mechanizmu.
2. Zbudować generator różnych dni rodziny i pilot danych; pokazać rzeczywiste
   predykcje i błędy modelu w obecnej konsoli. To najbliższe głównemu tematowi AI.
3. Porównać metody, sprawdzić fałszywe alarmy i transfer na dostępny sprzęt.
4. Dopiero przy zapasie czasu wybrać **jeden** dodatek: preferencyjnie tablice
   samochodzika, alternatywnie głos. Większa ilość danych i nowe moduły mają
   uzasadnienie dopiero po ocenie pilota, nie służą samej liczbie funkcji.

## Dalsze kierunki AI — 23.09.2026

[Pięć kierunków AI i etapy rozbudowy makiety](ai-directions.md) zapisują
aktywną diagnozę jako rozwinięcie oraz opcjonalne szukanie trudnych testów.
Najbliższy krok to pilot obserwowalności bramy. Pozostałe pomysły są alternatywami,
nie równoległymi obowiązkami. Protokół oceny i wymagania interfejsu pozostają aktualne.

## Interfejs jako część laboratorium ML

Docelowo w istniejącym czarnym pulpicie:

- rzeczywisty odczyt i predykcja na wspólnym wykresie, wynik anomalii i próg;
- oś czasu poleceń, kontaktów i alarmów, z widocznym brakiem danych;
- model i wersja cech, źródło danych: symulacja / sprzęt / odtwarzanie;
- szczegóły alarmu: obserwowane zdarzenia oraz kanały o największym błędzie
  predykcji, opisane jako wskazówki, nie dowód przyczyny;
- porównanie metod na zapisanym eksperymencie i eksport danych do pracy;
- osobny widok etykiet eksperymentu, nigdy podawanych detektorowi jako wejście.

Obecny pulpit i wszystkie wykresy zachowujemy. Nowe elementy pokażą rzeczywiste
wyniki dopiero po implementacji odpowiednich usług. Wybór modelu nie zmienia
sterowania urządzeniami; przy braku modelu interfejs jasno pokazuje jego brak.

## Kolejność realizacji

1. Specyfikacja jednego eksperymentu: obserwacje, zaufanie, normalne przebiegi,
   etykiety, reguły odniesienia i protokół oceny. Wczesna konsultacja z promotorem.
2. Kontrakty zdarzeń/pomiarów oraz MQTT -> kolektor -> SQLite, z testem
   integracji i trwałym zapisem; konfiguracja działa bez sprzętu.
3. Profil mechanizmu i runner wielu sesji, podział danych, proste metody
   odniesienia. Gdy dostępny sprzęt: wcześnie jeden ESP32 i pomiar odpowiedzi.
4. Pierwszy pełny trening i ocena GRU oraz Isolation Forest; pilot określa
   użyteczność danych, koszt inferencji i potrzebę opcjonalnego oprzyrządowania.
5. Integracja wyników ML z Qt, kontrolowane eksperymenty, walidacja fizyczna
   i Raspberry Pi, analiza i rozdziały pracy. UI rozwijamy przy tych etapach.

Zmiana mechanizmu, kontraktów i trening nie są wykonane w tym przyroście.
Nie zmieniamy teraz fizycznej makiety ani nie zamawiamy komponentów.

## Źródła do uzasadnienia i dalszego przeglądu

- [Garg i in., ocena detekcji i diagnozy w wielowymiarowych szeregach](https://arxiv.org/abs/2109.11428):
  znaczenie sposobu wyznaczania wyniku anomalii i oceny zdarzeń.
- [Sehili i Zhang, problemy metodyki oceny](https://arxiv.org/abs/2308.13068):
  ryzyko zawyżania wyników i potrzeba mocnych metod odniesienia.
- [Littelfuse, Door & Window Sensors](https://www.littelfuse.com/assetdocs/door-window-sensor-design-guide?assetguid=e9e19885-2741-4758-affc-fae9516eacbc):
  zastosowanie czujników magnetycznych do wykrywania położenia.
- [Pololu, serwo z osobnym wyjściem pozycji](https://www.pololu.com/product/3441):
  przykład dostępnego sprzężenia zwrotnego, nie wybór konkretnego napędu.
- [Texas Instruments, INA219](https://www.ti.com/product/INA219): pomiar prądu
  i napięcia; dobór modułu wymaga sprawdzenia obwodu docelowego.

Źródła wspierają metodykę i możliwości pomiarów, nie potwierdzają skuteczności
proponowanego modelu ani gotowości naszej instalacji.
