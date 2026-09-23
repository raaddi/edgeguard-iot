# Kierunki AI i rozbudowa makiety — 23.09.2026

Status: plan do pilota, nie gotowe modele ani wyniki. Zachowujemy EdgeGuard,
interfejs, MQTT, SQLite oraz niezależność od sprzętu. ML jest głównym wkładem
pracy. System nadal wspiera rozwój dla 1–3 fizycznych ESP32 i dodatkowych
węzłów symulowanych, bez stałego limitu architektury.

## Pięć pomysłów

| Kierunek | Element uczący się | Eksperyment i punkt odniesienia |
|---|---|---|
| **Aktywna diagnoza — kierunek główny** | Model przewiduje odpowiedź mechanizmu; polityka wybiera dozwolony test zmniejszający niepewność | Opóźnienie komunikacji, zatrzymanie ruchu, awaria kontaktu; porównanie ze stałą listą testów: poprawność, odmowy diagnozy, liczba testów, czas |
| Spójność wielu pomiarów | Przewidywanie brakującego kanału z poleceń, kontaktów i opcjonalnego prądu | Reguły spójności vs model, ablacja kanałów, braki danych, manipulacja i fałszywe alarmy |
| **Automatyczne szukanie trudnych testów — opcjonalne rozszerzenie** | Optymalizacja z uczonym modelem zastępczym szuka parametrów awarii, przy których detektor zawodzi | Porównanie z losowym wyszukiwaniem przy równym budżecie; oddzielny zamrożony test końcowy |
| Oceniany agent diagnostyczny LLM | Gotowy model wybiera ograniczone narzędzia odczytu historii i proponuje testy | Poprawność narzędzi, odmowa przy braku danych, odporność na instrukcje w danych; integracja LLM nie jest własnym treningiem ML |
| Adaptacja przy małej liczbie etykiet | Active learning wybiera informacyjne cykle do oceny po zmianie napędu/profilu | Liczba etykiet vs losowy wybór, fałszywe alarmy, zachowanie wykrywalności usterek, osobny test nowego urządzenia |

Nie realizujemy pięciu osobnych prac. Najpierw obserwowalność i detekcja jednego
mechanizmu; aktywna diagnoza rozwija plan reguły / Isolation Forest / mały model
sekwencyjny. Metodę wybierzemy po pilocie. Model może odpowiedzieć „brak danych”.
Jeżeli reguła wystarcza, raportujemy to uczciwie. Kolejne trudniejsze przypadki
muszą mieć uzasadnienie w działaniu systemu, a nie służyć wygranej ML za wszelką cenę.

## Warunki badania

- Brama porusza się w czasie. Przyjęcie polecenia nie oznacza osiągnięcia pozycji.
- Zatrzymana brama i uszkodzony kontakt mogą dać identyczne odczyty. Sprawdzimy,
  czy dodatkowy sygnał lub kolejny test wnosi informację.
- Prąd i czasy w symulatorze są ilustracyjne do czasu kalibracji. Rozdzielenie
  sztucznych klas nie potwierdza działania na makiecie.
- Etykiety, wewnętrzny kąt, seed i harmonogram awarii nie są cechami ML.
  Podział całymi sesjami i rodzinami parametrów przed budową okien;
  powiązane warianty trafiają do tego samego podzbioru.
- Wspólny zegar symulacji nie rozwiązuje synchronizacji ESP32. Nowe pomiary
  wymagają jawnego kontraktu; nie udają kanału `gas_signal`.

## Cyberbezpieczeństwo

Po pilocie usterek zestawimy legalne opóźnienia i intensywne używanie
z kontrolowanym replayem/manipulacją feedbacku oraz nadużyciem poprawnych poleceń.
Usterka mechaniczna sama nie jest eksperymentem cyberbezpieczeństwa. Określamy
dostęp przeciwnika i wiarygodne kanały. Drugi ESP32 może obserwować kontakty,
ale inny identyfikator nie gwarantuje niezależnego zaufania. Spójne sfałszowanie
wszystkich obserwacji może być nierozróżnialne od legalnej pracy. Alarm nie
dowodzi intencji. ML nie zastępuje ACL, uwierzytelniania i zabezpieczeń sprzętu.

Aktywne próby najpierw wyłącznie w symulacji. Fizyczne testy wymagają limitów
cykli, czasu, obciążenia i dozwolonych działań. Nie blokujemy napędu siłą.
Agent LLM nie otrzymuje swobodnego sterowania sprzętem.

## Stopniowe zakupy

| Etap | Zakres | Warunek |
|---|---|---|
| 0 | Laptop i pilot bramy; bez zakupów | Przydatne obserwacje, powtarzalne dane i pierwsze porównanie metod |
| 1 | Jeden ESP32, istniejący mechanizm, dwa kontakty krańcowe | Dobór zasilania, sterowania i zgodności 3,3 V; pomiar realnej odpowiedzi |
| 2 | Opcjonalny pomiar prądu | Ablacja uzasadnia kanał; dobór modułu do obwodu |
| 3 | Drugi ESP32 dla feedbacku lub drugi napęd | Konkretny eksperyment zaufania albo adaptacji |

Nie wybieramy teraz modułów ani cen. Kamera z tablicą kartonowego samochodu
i głos pozostają dodatkami w [planie ML](ml-research-plan.md). Generator dni
rodziny urozmaici legalne używanie; trzy lata syntetyczne nie są warunkiem badań
i nie zastępują walidacji fizycznej oraz pomiarów inferencji na Raspberry Pi.

## Małe kroki i commity

1. Ten zapis kierunków i ograniczeń.
2. Niezależny model ruchu, kontaktów i usterek, z testami.
3. Runner obserwacji, poleceń i osobnych etykiet; krótki pilot bez GUI.
4. Różnorodne profile normalności, podziały danych i metody odniesienia.
5. Trening i ocena modelu sekwencyjnego oraz Isolation Forest; wyniki w Qt.
6. Aktywna diagnoza, gdy obserwacje pozwalają rozróżniać hipotezy.
7. Walidacja fizyczna i Pi; opcjonalnie wyszukiwanie trudnych testów.

Każdy gotowy przyrost: przegląd zmian, właściwe testy, commit i push na gałąź
funkcjonalną. Lista nie oznacza ukończenia tych etapów.

## Inspiracje do dalszego przeglądu

- [psy-taliro](https://github.com/cpslab-asu/psy-taliro): wyszukiwanie testów systemów cyberfizycznych.
- [TS2Vec](https://arxiv.org/abs/2106.10466): samonadzorowane reprezentacje szeregów.
- [NIST: Building Evaluation Probes for Agentic AI](https://www.nist.gov/programs-projects/building-evaluation-probes-agentic-ai): ocena agentów.

To inspiracje, nie dowód unikalności ani gwarancja zatrudnienia. Wartość portfolio
ma wynikać z danych, porównań i umiejętności wyjaśnienia ograniczeń.
