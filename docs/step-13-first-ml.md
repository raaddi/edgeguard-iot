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

Następny przyrost w tym kroku doda runner, trening Isolation Forest, reguły
odniesienia i raport. Sam moduł etykiet/metryk nie jest jeszcze treningiem ML.
