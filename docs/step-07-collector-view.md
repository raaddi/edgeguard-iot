# Krok 7 — historia kolektora w konsoli Qt

Jedna aplikacja ma teraz dwa obszary pracy. **Makieta lokalna** pozwala prowadzić
dotychczasową symulację. **Kolektor — dane z API** odczytuje wiadomości zapisane
przez kolektor MQTT w SQLite. Nie odczytuje wewnętrznego stanu makiety.

## Uruchomienie i pierwsze ćwiczenie

1. Przygotuj dane według [ćwiczenia MQTT](step-05-mqtt.md).
2. Uruchom aktualne [API](step-06-api.md) na tej samej bazie:

   ```powershell
   .\.venv\Scripts\python.exe -m edge.api --database data/telemetry.sqlite3
   ```

   Jeśli API było uruchomione przed aktualizacją kodu, zatrzymaj je Ctrl+C
   i uruchom ponownie. Nowy widok wymaga endpointu `/telemetry/recent`.
3. Uruchom `start-laboratory.cmd`. Na górze wybierz **Kolektor — dane z API**.
4. Kliknij **Połącz / lista węzłów**, a następnie wybierz węzeł. Domyślny port
   to 8000; dla innego portu API zmień go w konsoli.
5. Obejrzyj wykresy, tabelę **Ostatni raport sesji** i zakładkę **Telemetria JSON**.
   Porównaj czas urządzenia z czasem odbioru kolektora.
6. Zaznacz **Odświeżaj co 5 s** i uruchom kolejny przebieg publishera z kroku 5.
   Po zapisie nowych wiadomości wrócą one przez API do konsoli. Wybierz nowy
   `boot_id`, jeśli przeglądasz dotychczasową sesję — wybrana sesja jest zachowywana,
   dopóki występuje w pobranym oknie historii.

Nie trzeba mieć elektroniki ani dostępu do Internetu po instalacji zależności.
API może pokazywać wcześniejsze dane bez działającego brokera i kolektora.
Przy nowej bazie, do której nic nie zapisano, lista będzie pusta.

## Jak czytać ten widok

- Pobieramy ostatnie **200 raportów wybranego węzła**. Starsza historia pozostaje
  w bazie; jeśli istnieje, konsola wyświetla informację. To podgląd, nie eksport
  pełnego zbioru treningowego. Wybór sesji obejmuje sesje obecne w tych raportach.
- Lista węzłów ma strony po maksymalnie 200 pozycji. **Następne węzły** przechodzi
  dalej, **Połącz / lista węzłów** wraca do początku i odświeża spis. Automatyczne
  odświeżanie dotyczy raportów wybranego węzła, nie wykrywania nowych węzłów.
- Wszystkie komponenty występujące w pobranych raportach wybranej sesji mają
  wykresy. Kanały identyfikujemy na podstawie telemetrii, bez sztywnego mapowania
  do pokojów, konfiguracji domu ani numeru ESP32.
- Oś X to **numer wiadomości**, nie sekundy. Przerwa w sekwencji przerywa linię;
  nie znamy dokładnego czasu brakujących próbek. Różne sesje `boot_id` są osobnymi
  wykresami, bez łączenia linii przez restart urządzenia.
- Gaz pozostaje umownym sygnałem 0–1. Dla aktuatorów linia przerywana oznacza
  polecenie, a ciągła raport. Źródło `simulated`, `measured` albo `unavailable`
  jest podane w tabeli i JSON. Brak raportu pozostaje brakiem.
- „API dostępne” opisuje udany odczyt HTTP. **Nie potwierdza**, że węzeł, kolektor
  lub broker pracuje teraz. Oceniając dane, sprawdź datę ostatniego odbioru.

## Przełączanie i błędy

Przejście do kolektora zatrzymuje zegar makiety, ale zachowuje jej stan i niezapisane
zmiany. Menu eksperymentu jest wtedy nieaktywne, żeby nie pomylić operacji na
lokalnej symulacji z historią kolektora. Powrót nie uruchamia zegara automatycznie.
Opuszczenie widoku kolektora wyłącza odświeżanie i anuluje oczekujące zapytanie.

Przy błędzie połączenia poprzedni podgląd pozostaje widoczny z informacją o braku
odświeżenia. Zmiana węzła lub portu usuwa poprzedni podgląd. Odpowiedź starego
zapytania nie może zastąpić danych nowo wybranego węzła. Pusta lub niezgodna
odpowiedź ma jawny komunikat; aplikacja nie generuje zastępczych pomiarów.

Zapytania wykonuje asynchroniczny `QNetworkAccessManager`, z limitem 5 s i 8 MiB
na odpowiedź oraz jednym aktywnym zapytaniem. Połączenia ograniczamy do
`127.0.0.1`, bez proxy i przekierowań. Podgląd waliduje format telemetrii i ID;
w obrębie jednej sesji obsługuje do 128 różnych komponentów o niezmiennych typach.
Zmianę typu lub przekroczenie limitu odrzuca jako niezgodną odpowiedź.

## Co pozostaje do wykonania

Lokalne przyciski nie wysyłają jeszcze poleceń MQTT, a działająca makieta Qt nie
publikuje do brokera. Wiadomości do kolektora nadal wysyła osobny publisher.
Ten przyrost łączy **odczyt**, nie kończy integracji sterowania i statusów.
Wspólny kontrakt poleceń, uwierzytelnienie, rejestr eksperymentów, modele ML
oraz podgląd wszystkich węzłów jednocześnie pozostają dalszymi etapami.

Testy:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_collector_view.py tests/test_api.py -q
```

Sprawdzamy rzeczywiste HTTP i SQLite, odświeżanie po dopisaniu raportu, restart
węzła, przerwy i niedostępny feedback, anulowanie opóźnionych odpowiedzi,
timeout, limit danych, błędny JSON/HTTP i zachowanie lokalnego eksperymentu.
Testy nie potwierdzają jeszcze działania ESP32 ani wydajności Raspberry Pi.

Dokumentacja mechanizmu sieciowego:
[Qt Network](https://doc.qt.io/qtforpython-6/PySide6/QtNetwork/QNetworkAccessManager.html).
