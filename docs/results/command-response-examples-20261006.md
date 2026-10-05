# Przykłady odpowiedzi bramy — wyniki 06.10.2026

Wykonano wcześniej zapisany [protokół kroku 19](../step-19-command-response-targets.md).
Powstały dane do przyszłej ablacji celu prognozy: osobne czasy ACK i potwierdzenia
krańcówką. Nie trenowano modelu, nie kalibrowano alarmów i nie mierzono nowej
skuteczności detekcji.

## Pochodzenie i odtworzenie

- Protokół zapisano w `2cd624f4e3bf4faed209938cdc7557cae6f3cac8`; ograniczenie
  wspólnie zamkniętej sesji doprecyzowano przed eksportem w `ea83435…`.
- Eksporter uruchomiono z czystego commita
  `28233a554b4e38444e525647a103464ee52f9c3e`, Python 3.12.14.
- Lokalny katalog: `experiments/runs/response-examples-20261006`.
- SHA-256 `report.json`:
  `4856d911699fa0c062644d8298254ec4b24810c4e8b0567d7c01122dfe8b0556`.
- SHA-256 kopii protokołu `protocol.md`:
  `a1fa6a323bf4681c3fab20db11c88b799ff51377ab693b5e6c2597912a9c6194`.
  Kopia zachowuje protokół sprzed dopisania wyników do dokumentacji.

Z katalogu repozytorium, z zainstalowanymi zależnościami bazowymi `requirements.txt`:

~~~powershell
.\.venv\Scripts\python.exe -m ml.gate_response_export --output experiments/runs/response-examples-new
~~~

Katalog musi być nowy. Eksporter odmawia nadpisania poprzedniego przebiegu.
Nie potrzebuje PyTorch, scikit-learn, NumPy, Qt, brokera ani elektroniki.
`manifest.json` zapisuje role, seedy, konfiguracje i wersje; `raw/<rola>/<run_id>`
zawiera obserwacje, zdarzenia oraz oddzielne etykiety, a `examples/<rola>` —
wejścia i cele. `report.json` liczy cele i powody cenzurowania per rola,
przypadek, warunek i sesja. Błąd zachowuje manifest ze statusem `failed`.
Wygenerowane dane pozostają poza Git zgodnie z `.gitignore`.

## Zweryfikowana zawartość

440 sesji po 30 s zawiera **264 440 próbek** i **1872 polecenia**.
Każde polecenie utworzyło przykład; wyłączeń wejścia było zero.
Wszystkie 1872 ACK zaobserwowano i wszystkie przyjęły polecenie.
Potwierdzenie krańcówką zaobserwowano w 1392 przykładach; pozostałe 480
ocenzurowano z powodem `superseded`, po przyjęciu przeciwnego polecenia.

| Rola | Sesje | Przykłady / ACK | Krańcówka obserwowana | Krańcówka cenzurowana |
|---|---:|---:|---:|---:|
| Przyszły trening | 48 | 160 | 160 | 0 |
| Przyszły wybór checkpointu | 24 | 80 | 80 | 0 |
| Przyszła kalibracja | 48 | 160 | 160 | 0 |
| Ocena rozwojowa | 320 | 1472 | 992 | 480 |

Pierwsze trzy role zawierają wyłącznie normalne `cycles/repeats/idle`.
Wszystkie warianty seeda pozostają w tej samej roli, rozłącznej z wcześniejszymi
zbiorami. 104 sesje bez poleceń (`idle`) mają poprawnie zero przykładów;
pozostają w manifestach i raportach. To zbiór prognoz wystawianych na polecenie,
nie pełna oś prognoz odczytów co 50 ms.

| Przypadek w ocenie | Sesje | Przykłady | Krańcówka obserwowana | `superseded` |
|---|---:|---:|---:|---:|
| normal | 80 | 368 | 336 | 32 |
| command_delay | 80 | 368 | 336 | 32 |
| motion_stall | 80 | 368 | 160 | 208 |
| open_contact_stuck_low | 80 | 368 | 160 | 208 |

**Cenzurowanie nie jest etykietą awarii.** 32 poprawne ruchy też zostały
przerwane legalnym przeciwnym poleceniem. Powtórzenia mogą współdzielić
potwierdzenie; liczba przykładów nie oznacza niezależnych cykli.

## Weryfikacja i ograniczenia

Po eksporcie sprawdzono 1762 hashe: cztery pliki każdej sesji, raport i kopię
protokołu. Wszystkie 1872 przykłady odtworzono z surowych obserwacji/zdarzeń
i porównano z zapisanym JSON. Skontrolowano liczbę próbek, rozłączność ról
oraz brak usterek poza oceną. Testy jednostkowe obejmują zmianę przyszłości,
prefiksy, powtórzenia, odwrócenia, luki, odrzucenia i końce obserwacji.
Lokalnie pełny zestaw z wyłączeniem `tests/test_mqtt_path.py`: 376 zaliczonych,
7 pominiętych i 8 zaliczonych podtestów. Integracja MQTT wymaga sprawdzenia CI
z brokerem; lokalny wynik jej nie potwierdza.

Domyślne 440 sesji nie wytwarza odrzuconych/brakujących ACK ani luk pomiarów;
te przypadki są sprawdzone testami, a nie tym przebiegiem. Wersja 1 odrzuca
zdarzenia po ostatniej próbce pomiarowej. Osobne końce kanałów wymagają
kolejnego kontraktu. Nowe pliki przykładów nie zawierają prognoz ani alarmów
i nie są formatem obecnego widoku zapisanych wyników ML w Qt.

To ten sam generator syntetyczny i dane rozwojowe. Nie potwierdzają transferu
na sprzęt ani przewagi nowego celu. Przed treningiem trzeba zamrozić loss,
maski/cenzurowanie, hiperparametry, checkpoint i protokół przyczynowego alarmu.
Inferencja na żywo, końcowy test, walidacja fizyczna i pomiary Pi pozostają do wykonania.
