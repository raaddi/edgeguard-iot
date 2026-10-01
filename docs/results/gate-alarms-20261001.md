# Pierwsze porównanie alarmów — 01.10.2026

**W tym pilocie reguły wykryły więcej zdarzeń niż GRU.** GRU uzyskało wyższą
wykrywalność niż Isolation Forest i referencja powtarzająca ostatni odczyt.
To wynik rozwojowy, nie końcowy test pracy ani potwierdzenie skuteczności na sprzęcie.

## Pochodzenie i warunki

- Kod: [93f0e2b2a9b4335c10f174639902822a516fb636](https://github.com/raaddi/edgeguard-iot/commit/93f0e2b2a9b4335c10f174639902822a516fb636),
  czyste drzewo robocze, `status: completed`.
- Lokalny wynik: `experiments/runs/gate-alarms-20261001-verified`.
- Raport SHA-256: `f90fd9c5e78971e8fe3cd0368425954c309912a448d704311c623c3370ee1c78`.
- Wczytany GRU: `gate-gru-20260930-verified`, bez ponownego treningu lub zmiany wag.
  Manifest GRU SHA-256: `7a14d76cb62a9e39c2eebd207c06c11281438a1cbf37c25b9bc1f602950da56d`.
- Skale błędów: 6768 normalnych okien treningowych. IF/reguły: 7728 wierszy
  tych samych 48 normalnych sesji. Próg każdej metody: maksimum na 2256 normalnych
  próbkach walidacyjnych. Szczegóły i powody opisuje [krok 16](../step-16-gru-alarms.md).
- Alarm wymaga trzech kolejnych ścisłych przekroczeń. Wspólna ocena od 1000
  do 8000 ms, bez skracania zdarzeń i bez przesuwania początku alarmu wstecz.
- Powtórzenie z czystego commita odtworzyło identyczne raporty, wyniki próbek,
  flagi alarmów i etykiety z przebiegu roboczego. Nie zmieniano progów pod test.

## Wynik na rozwojowym podziale testowym

Oceniono 64 sesje: po 16 na każdy przypadek, w czterech grupach seedów
i czterech profilach użytkowania. **64 zdarzenia to przedziały obserwowalnej
rozbieżności od sparowanej poprawnej symulacji**, a nie 64 cyberataki lub
niezależne awarie. Jeden przebieg może mieć kilka przedziałów lub żadnego.

| Metoda | Wykryte zdarzenia | Pominięte | Niedopasowane alarmy | Alarmy na normalnych sesjach |
|---|---:|---:|---:|---:|
| GRU | 27/64 | 37 | 5 | 0 |
| Ostatni odczyt | 0/64 | 64 | 0 | 0 |
| Isolation Forest | 13/64 | 51 | 6 | 2 |
| Reguły czasowe/prądowe | 52/64 | 12 | 8 | 0 |

Czas normalnej pracy objęty oceną wynosi **112 s**. Zero alarmów w tym czasie
nie gwarantuje niezawodności. Referencja „ostatni odczyt” także ma zero takich
alarmów, a nie wykryła żadnego zdarzenia. Niedopasowane alarmy mogą oznaczać
ponowne zgłoszenie w już wykrytym przedziale usterki; nie są tożsame z alarmami
na normalnych sesjach. Pełne liczniki oraz opóźnienia pozostają w lokalnym JSON.

| Rodzaj przypadku | GRU | Ostatni odczyt | Isolation Forest | Reguły |
|---|---:|---:|---:|---:|
| Opóźnienie polecenia | 3/28 | 0/28 | 9/28 | 28/28 |
| Zablokowanie ruchu | 12/24 | 0/24 | 3/24 | 12/24 |
| Krańcówka otwarcia stale nieaktywna | 12/12 | 0/12 | 1/12 | 12/12 |

Różnica 25 wykrytych zdarzeń między regułami i GRU w całości przypada tu na
opóźnienie polecenia. To lokalizacja słabości w metrykach, nie dowód jej przyczyny.
Nie wyciągamy z tego wniosku, że model będzie rozpoznawał wszystkie fizyczne
uszkodzenia krańcówek: mały symulator zawiera tylko jeden uproszczony wariant.

Na walidacji wykryto: GRU 28/69, ostatni odczyt 0/69, IF 9/69, reguły 52/69.
Wszystkie metody miały zero alarmów na normalnych sesjach walidacyjnych zgodnie
z polityką kalibracji. Walidacja wcześniej służyła także wyborowi epoki GRU.

## Ograniczenia i kolejny krok

To znane profile i rodzina parametrów, jedna inicjalizacja GRU oraz próg wybrany
z krótkiej normalnej walidacji. Test oglądano wcześniej przy rozwoju metod.
Nie deklarujemy uogólnienia ani statystycznie potwierdzonej przewagi. Obecna
implementacja wymaga kompletu pomiarów; nie wykazano odporności na brak czujnika.
Porównanie nie obejmuje scenariuszy cybernetycznych, Qt ani sprzętu.

Kolejny krok badawczy: prześledzić na walidacji pominięte opóźnienia poleceń,
rozdzielić wpływ celu prognozy od polityki alarmu i przygotować nowe legalne
warunki użytkowania. Osobny zbiór kalibracyjny i nowy zamrożony test końcowy
muszą poprzedzać silniejsze wnioski. Zachowujemy reguły jako mocną metodę
odniesienia; nie zmieniamy scenariuszy tylko po to, aby zapewnić zwycięstwo ML.
