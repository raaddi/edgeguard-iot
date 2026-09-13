# Magisterka: Overleaf i laptop

To kompilowalny szkielet po polsku z dziewięcioma rozdziałami, załącznikami,
bibliografią oraz spisami treści, rysunków i tabel.
Wskazówki do pisania są oznaczone jako „Do opracowania”.
Nie ma wymyślonych wyników ani deklaracji ukończenia systemu.

## Overleaf: najprostszy start

1. Pobierz paczkę EdgeGuard_Magisterka_Overleaf.zip przygotowaną z repozytorium.
2. W Overleaf utwórz nowy projekt przez przesłanie ZIP (Upload Project).
3. W ustawieniach projektu wybierz kompilator XeLaTeX i plik główny main.tex.
4. Uruchom Recompile. Overleaf obsłuży bibliografię i odwołania.
5. Zacznij od config/metadata.tex i chapters/01-introduction.tex.

Paczka ma main.tex bezpośrednio w katalogu głównym i wszystkie potrzebne źródła.
Nie wgrywaj samego main.tex. Numer albumu, promotora i rok uzupełnisz później.

## Gdzie pisać

- config/metadata.tex: dane autora, uczelni, promotora i roboczy tytuł.
- config/preamble.tex: font, marginesy, interlinia i pakiety.
- frontmatter/: strona tytułowa, streszczenia PL/EN, skróty.
- chapters/: rozdziały 01-09.
- bibliography/references.bib: źródła.
- figures/: schematy i późniejsze wykresy.
- tables/: tabele opisowe, w tym plan eksperymentów.
- generated/: zatwierdzone eksporty prawdziwych wyników.
- appendices/: odtwarzanie badań, kontrakty i sprzęt.

W repozytorium te katalogi znajdują się pod thesis/. W paczce do Overleaf są
bezpośrednio w katalogu głównym. Pełny plan jest w docs/thesis-outline.md
w repozytorium.

## WSB Merito Wrocław

Uwzględniono nazwę uczelni i kierunek. **Nie jest to oficjalny wzór uczelni.**
Nie dostarczono aktualnych wymagań edytorskich ani wzoru z Extranetu.
Robocze ustawienia to A4, 12 pt, TeX Gyre Termes, interlinia 1,5, margines lewy
3 cm, pozostałe 2,5 cm oraz bibliografia numeryczna.
Tytuł, wydział, stronę tytułową, oświadczenia, numerację i styl cytowań należy
potwierdzić z promotorem. Ustawienia są oddzielone od treści i łatwe do zmiany.

## Bez internetu: Windows

Overleaf służy do pracy online. Do pracy w pociągu bez sieci możesz używać tych
samych źródeł lokalnie. W PowerShell, w katalogu repozytorium, przygotuj raz:

~~~powershell
.\scripts\setup-latex.ps1
.\scripts\build-thesis.ps1
.\scripts\build-thesis.ps1 -Offline
~~~

Pierwsze dwa polecenia wymagają internetu. Instalator pobiera Tectonic 0.17.0,
sprawdza SHA-256 i umieszcza kompilator w .tools/, bez instalacji systemowej.
Pierwszy build pobiera używane pakiety do lokalnego cache.

Potem możesz pisać w dowolnym edytorze i budować bez sieci:

~~~powershell
.\scripts\build-thesis.ps1 -Offline -Open
~~~

PDF: thesis/build/main.pdf. Nowy pakiet lub font może wymagać kolejnego builda
online. Nie usuwaj lokalnego cache ani .tools/ przed podróżą.
Do budowy pracy nie potrzebujesz Python, Docker ani elektroniki.
Uruchamialna symulacja będzie dostępna dopiero po implementacji Milestone 1.

Jeżeli PowerShell blokuje skrypty:

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-latex.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-thesis.ps1 -Open
~~~

To opcja dla pojedynczego polecenia; nie zmienia trwale ustawień systemu.
Opcjonalnie możesz otworzyć repozytorium w VS Code z LaTeX Workshop.
Konfiguracja zawiera osobne polecenia online/offline.

Linux/macOS z zainstalowanym Tectonic:

~~~sh
cd thesis
mkdir -p build
tectonic --untrusted --keep-logs --outdir build main.tex
tectonic --only-cached --untrusted --keep-logs --outdir build main.tex
~~~

## Bibliografia i wyniki

Przykłady w tekście pokazują użycie citep i ref. Wpisy bibliograficzne dodawaj po
sprawdzeniu publikacji. Początkowe trzy źródła nie zastępują przeglądu literatury.

Eksporter CSV wymaga Python 3, ale nie dodatkowych pakietów:

~~~powershell
python scripts/export-thesis-results.py experiments/runs/RUN_ID/summary.csv
~~~

Uruchom go z katalogu repozytorium po wykonaniu rzeczywistych pomiarów.
Wygenerowana tabela zostanie automatycznie włączona do rozdziału 7.
Opis formatu i pochodzenia danych: experiments/README.md.
Eksporter nie wykonuje symulacji ani treningu.

## Synchronizacja

Import ZIP jest kopią, a nie automatyczną synchronizacją z GitHubem.
Zasady pracy w obu miejscach opisano w docs/workflow.md.
ZIP odtworzysz poleceniem scripts/export-overleaf.ps1.

GitHub Actions buduje PDF po zmianach źródeł:
Actions -> Build thesis -> wybrany przebieg -> Artifacts:
edgeguard-thesis-pdf zawiera PDF, a edgeguard-overleaf zawiera paczkę do Overleaf.
Artefakt jest przechowywany przez 30 dni; źródła pozostają w Git.

Lokalne dane autora możesz nadpisać w ignorowanym config/private.tex.
Ten plik nie trafia do eksportu ZIP ani GitHub Actions.
