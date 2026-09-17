# Rozpiska pracy

Tytuł roboczy: Detekcja anomalii w rozproszonym systemie SmartHome
z wykorzystaniem uczenia maszynowego i analizy wielowymiarowych szeregów
czasowych na urządzeniu brzegowym.

[Plan badań ML i proponowane zmiany makiety](ml-research-plan.md) określa
główny eksperyment: predykcja sekwencyjna GRU, Isolation Forest i reguły,
polecenia zestawione z pomiarem odpowiedzi mechanizmu, ablacje oraz transfer
na sprzęt. To zakres planowany; tytuł i metodykę należy uzgodnić z promotorem.

| Rozdział | Sekcje i zakres |
|---|---|
| 1. Wstęp | Kontekst, motywacja, cel, problem, RQ1-RQ5, zakres |
| 2. Podstawy i literatura | IoT/Edge, MQTT, typy anomalii, reguły i ML, stan badań i luka badawcza |
| 3. Założenia i wymagania | Inżynierka jako punkt wyjścia, wymagania funkcjonalne/niefunkcjonalne, model zagrożeń, ograniczenia |
| 4. Architektura | Role, identyfikatory i możliwości węzłów, kontrakty MQTT, baza/API, modele, niezawodność |
| 5. Realizacja | Narzędzia, symulator, scenariusze, kolektor i API, firmware, integracja ML |
| 6. Dane i metodyka | Trzy źródła danych, cechy, podziały, reguły/model, hipotezy, metryki, plan eksperymentów |
| 7. Eksperymenty i wyniki | Warunki, skuteczność, fałszywe alarmy, transfer na dane fizyczne, liczba węzłów, Raspberry Pi, błędne detekcje |
| 8. Dyskusja | Odpowiedzi na RQ, korzyść ML, wiarygodność, ograniczenia bezpieczeństwa, znaczenie praktyczne |
| 9. Podsumowanie | Wkład własny, realizacja celu, wnioski, dalsze prace |

Przed rozdziałami: strona tytułowa, streszczenia PL/EN, spis treści i skróty.
Po rozdziałach: bibliografia, spisy rysunków i tabel oraz załączniki:
odtwarzanie środowiska/badań i kontrakty/konfiguracja sprzętu.

## Materiały i powiązanie z kodem

- PROJECT_SPEC.md: źródło uzgodnionego zakresu.
- Przyszły simulator/edge/firmware: opis realizacji i testów w rozdziale 5.
- Przyszłe ml/, data/ i experiments/: dane i wyniki do rozdziałów 6-8.
- thesis/generated/: niewielkie zatwierdzone eksporty pomiarów.
- tests/: weryfikacja techniczna; liczby testowe nie są wynikami naukowymi.

## Od czego zacząć

Teraz można pisać wstęp, opisywać poprzedni prototyp, czytać literaturę,
uzasadniać architekturę i planować eksperymenty.
Realizację opisuj wraz z uruchamianiem komponentów.
Wyniki i wnioski uzupełniaj dopiero na podstawie pomiarów.

## Orientacyjny harmonogram

1-2 miesiąc: literatura, wymagania i podstawy oprogramowania.
3-4: pierwsze ESP32 i zbieranie danych fizycznych.
5-6: reguły, modele i procedury eksperymentalne.
7-8: pomiary, analiza i porównania na Raspberry Pi.
9: konsultacje, uzupełnienie tekstu i dokumentacji.
10: bufor na poprawki i przygotowanie obrony.

Pisanie trwa przez cały okres. Liczbę stron i ostateczny układ uzgodnij z promotorem.
