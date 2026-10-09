# Krok 21 — przyczynowe timeouty odpowiedzi bramy

Status: protokół przed oceną alarmów. Korzystamy z prognoz
[kroku 20](step-20-response-models.md), bez nowego treningu ani wyboru seeda.

## Decyzja i dostępne informacje

Przy wysłaniu polecenia zamrażamy dwie nieujemne prognozy: czas ACK i czas
potwierdzenia właściwą krańcówką. Każdy cel ma osobny monitor i margines.
Termin to czas wysłania + prognoza + margines, w milisekundach czasu logicznego.

Timeout występuje przy pierwszej dostępnej chwili przekraczającej termin.
Równość nie uruchamia alarmu. Nie cofamy czasu alarmu do teoretycznego terminu.
Odpowiedź dokładnie w terminie jest poprawna; późniejsza kończy oczekiwanie,
ale zachowuje timeout. Jedno oczekiwanie emituje najwyżej jeden alarm.

ACK to wynik polecenia, nie dowód wykonania fizycznego. Kontakt potwierdzamy
po zaakceptowanym ACK, zgodnie z krokiem 19. Odrzucenie, zaakceptowane przeciwne
polecenie lub luka pomiarowa kończą oczekiwanie na kontakt. Powtórzenie tego
samego celu go nie kasuje. Luka pomiarowa nie cenzuruje ACK. Koniec sesji
cenzuruje oczekiwania. Przerwanie w terminie nie jest alarmem; przerwanie po
terminie nie usuwa timeoutu. Przerwanie i potwierdzenie są wzajemnie wykluczające.

Adapter przekazuje wyłącznie informacje dostępne w aktualnej chwili i przetwarza
wszystkie zdarzenia o tym samym czasie przed decyzją. Nie podaje przyszłego czasu
odpowiedzi, etykiet, seeda ani powodu usterki. Brak odpowiedzi nie dowodzi ataku.

## Zamrożona kalibracja do przyszłego eksperymentu

Dla każdej metody i celu margines wyniesie
`max(0, max(actual_ms - predicted_ms))` na obserwowanych odpowiedziach osobnych
normalnych sesji `calibration`. Brak obserwowanych celów oznacza błąd kalibracji.
Cenzury raportujemy osobno, bez podstawiania zera lub pełnego czasu odpowiedzi.
Marginesy zapisujemy przed odczytem `evaluation`. Maksimum chroni obserwowane
odpowiedzi kalibracyjne, bez gwarancji dla przyszłych danych.

Porównanie obejmie trzy inicjalizacje GRU odpowiedzi i mediany kontekstowe kroku
20, te same sesje, zegar oraz zasady grupowania zdarzeń. Nie wybieramy najlepszego
seeda na ocenie. Raport pokaże wykrycia, pominięcia, fałszywe alarmy/h i opóźnienia,
osobno dla legalnego wolnego ruchu i odwróceń. Porównanie z alarmami prognoz
odczytów wymaga wspólnego protokołu oceny zdarzeń; MAE nie dowodzi przewagi.

## Granice przyrostu

Najbliższa implementacja to monitor jednego celu niezależny od Qt, MQTT, liczby
węzłów i modelu. Testy sprawdzą granicę terminu, opóźnienie, brak odpowiedzi,
przerwanie, pojedynczą emisję i monotoniczność zegara. Adapter zdarzeń,
wykonanie kalibracji, pełna ocena alarmów, live ML i sprzęt pozostają osobnymi
pracami. Ten protokół nie stanowi wyniku eksperymentu ani wdrożenia modelu.
