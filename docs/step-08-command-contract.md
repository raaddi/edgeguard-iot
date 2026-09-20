# Krok 8 — polecenia i odpowiedzi węzła

Gotowy jest format wiadomości i walidacja. Ten krok **nie dodaje jeszcze**
wysyłania poleceń z Qt, odbiornika MQTT ani sterowania ESP32. Pozwala przygotować
je według jednego kontraktu, zamiast osobno dla symulatora i sprzętu.

Aktualizacja: odbiór i wysyłanie MQTT w symulatorze są już dostępne w
[kroku 9](step-09-mqtt-control.md). Poniżej pozostaje opis kontraktu i jego założeń.

## Trzy różne informacje

1. **MQTT PUBACK**: broker potwierdził odebranie publikacji. Nie dowodzi to
   przyjęcia polecenia przez węzeł.
2. **Wynik polecenia**: węzeł przyjął zmianę nastawy/trybu albo odrzucił żądanie.
3. **Telemetria**: raportowana odpowiedź elementu. Dopiero dostępny pomiar
   sprzężenia zwrotnego może potwierdzać fizyczny ruch. `simulated` oznacza model.

Nie dodajemy statusu „brama otwarta” do potwierdzenia przyjęcia polecenia.
To rozróżnienie będzie podstawą porównania poleceń z pomiarami w badaniu ML.

## Kontrakt 1.0

| Wiadomość | Topic | Znaczenie |
|---|---|---|
| Polecenie | `edgeguard/devices/{device_id}/commands` | Zmiana nastawy konkretnego komponentu albo przywrócenie AUTO wentylatora |
| Wynik | `edgeguard/devices/{device_id}/command-results` | `accepted` lub `rejected`, identyfikator polecenia i powód odrzucenia |

Polecenie zawiera wersję, `command_id` (UUID), węzeł, `target_boot_id`, komponent,
operację, wartość i przedział ważności w milisekundach czasu pracy węzła.
Operacja `set` ma wartość całkowitą 0–180, a `auto` ma `value: null`.
Sam zakres formatu nie uprawnia do ustawienia każdego kąta: lokalna konfiguracja
węzła definiuje dozwolone nastawy. Obecny profil makiety dopuszcza dla serwa
0/110°, dla lamp i wentylatorów 0/1. Czujnik nie jest celem sterowania.

Wynik zawiera ten sam `command_id` i komponent, rzeczywisty `boot_id` odbiorcy,
`handled_uptime_ms`, status i powód. `accepted` ma `reason: null` i oznacza
przyjęcie nastawy/trybu przez sterownik, nie ukończenie ruchu. `rejected` wymaga
powodu z zamkniętej listy, np. `wrong_boot`, `expired` lub `value_out_of_range`.
Odpowiedź po restarcie może mieć nowy `boot_id` i powód `wrong_boot`.

Przykłady są w `contracts/examples/command.json` i `command-result.json`.
Schematy JSON i walidatory odrzucają dodatkowe pola, duplikaty kluczy,
niepoprawny UTF-8, liczby niefinitywne, błędne ID i wiadomości większe niż 4 KiB.
Weryfikacja topicu sprawdza jego zgodność z `device_id`, nie tożsamość nadawcy.

## Ważność bez synchronizacji zegara ESP32

Wybraliśmy czas pracy węzła zamiast terminu UTC, ponieważ obecny kontrakt
telemetrii pozwala na brak zsynchronizowanego zegara urządzenia.

- Nadawca wykorzystuje `boot_id` i `uptime_ms` z ostatniej dostępnej telemetrii.
- `observed_uptime_ms` to zaobserwowany uptime, `expires_uptime_ms` to deadline
  w tej samej sesji. Okno musi mieć długość większą od 0 i nie większą niż 60 s.
- Odbiorca sprawdza **własny bieżący uptime**: musi być większy lub równy
  początkowi i mniejszy od końca okna. Dokładnie na końcu żądanie jest wygasłe.
- Okno nie przesuwa się przy dostarczeniu czy ponowieniu. Przykład: obserwacja
  500 ms, koniec 5500 ms, odbiór przy 700 ms — ważne; przy 5500 ms — odrzucone.
- Nie dodajemy czasu logicznego symulatora do zegara systemowego. Planowany
  odbiornik symulatora porówna go z własnym czasem logicznym; ESP32 z uptime.

Stara telemetria może prowadzić do odrzucenia polecenia — nadawca powinien
wtedy najpierw odświeżyć obserwację. Nowy start urządzenia musi dostać nowe UUID.
Licznik uptime musi być 64-bitowy lub prawidłowo rozszerzony po przepełnieniu,
a nie resetowany bez zmiany `boot_id`.

To ochrona przed przypadkowym wykonaniem spóźnionego żądania, **nie mechanizm
uwierzytelniania ani kompletna ochrona przed replay**. Uprawniony złośliwy klient
może tworzyć nowe ID i ważne okna; właśnie takie zachowania będziemy badać.

## Warunki następnego kroku — odbiornik MQTT

Poniższe zasady są planem implementacji, nie gotową funkcją tego przyrostu:

- QoS 1, `retain=false`; odbiornik odrzuca migawki z flagą retained dostarczone
  przy subskrypcji (ograniczenia MQTT 3.1.1 opisuje krok 9). Najpierw kontrakt,
  topic, właściwy węzeł/sesja, ważność i lokalne możliwości, potem zmiana nastawy.
- Deduplikacja po sesji odbiorcy i `command_id`. Ten sam ID i treść nie wykonują
  operacji ponownie; odbiornik odsyła zapisany wynik. Inna treść pod tym samym ID
  daje konflikt. Nie odświeżamy daty obsługi przy ponowieniu.
- Pamięć wyników musi mieć limit; nie wolno usuwać jeszcze ważnych wpisów tak,
  aby umożliwić ponowne wykonanie. Przy braku miejsca odrzucamy nowe polecenie.
- `accepted` publikujemy dopiero po udanej zmianie nastawy. Błąd sterowania
  nie może być potwierdzony jako sukces. Uszkodzona wiadomość bez wiarygodnego
  ID jest odrzucana i liczona, bez wymyślania odpowiedzi.
- Brak odpowiedzi oznacza wynik nieznany, a nie automatycznie niepowodzenie
  wykonania. Odczyt bieżącej telemetrii i jawne ponowienie muszą to uwzględniać.
- Gateway zapisze polecenia i odpowiedzi jako oddzielne obserwacje do badań.
  Poświadczenia klientów i ACL pozostają wymagane przed pracą poza loopbackiem.

## Ćwiczenie bez sprzętu i brokera

W katalogu repozytorium:

```powershell
.\.venv\Scripts\python.exe -m contracts.commands contracts/examples/command.json
.\.venv\Scripts\python.exe -m contracts.commands contracts/examples/command-result.json --result
.\.venv\Scripts\python.exe -m pytest tests/test_command_contract.py -q
```

Walidator CLI sprawdza format i długość okna; niczego nie wysyła ani nie wykonuje.
`--topic` dodatkowo sprawdza adres MQTT. Funkcja `target_rejection` pozwala
odbiornikowi sprawdzić aktualny uptime, sesję i możliwości lokalnego komponentu.
Zwrócone `None` oznacza przejście tych kontroli, nie potwierdzenie wykonania,
autoryzację ani sprawdzenie duplikatu. Ta funkcja nie zmienia stanu modelu.
