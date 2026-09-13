# GitHub, Overleaf i praca bez internetu

## Jedno repozytorium jako punkt odniesienia

GitHub przechowuje źródła pracy pod thesis/, specyfikację, narzędzia i późniejszy
kod systemu. ZIP do Overleaf zawiera samodzielny projekt z main.tex w katalogu
głównym. **Wgranie ZIP nie uruchamia dwukierunkowej synchronizacji.**

## Gdy piszesz w Overleaf

1. Wgraj ZIP i wybierz XeLaTeX/main.tex.
2. Po sesji pobierz źródła projektu z Overleaf jako ZIP.
3. Rozpakuj pobraną kopię do osobnego katalogu.
4. Przenieś tylko zmienione źródła rozdziałów, bibliografii i rysunków do thesis/.
   Nie zastępuj całego repozytorium zawartością ZIP.
5. Sprawdź git diff, skompiluj dokument, zrób commit i push.

Katalog assets/ w paczce zawiera kopię przykładowego manifestu na potrzeby
samodzielnej kompilacji. Jego źródłem w Git jest experiments/templates/.
Nie nadpisuj lokalnego config/private.tex danymi z pobranego archiwum.

Nie edytuj tych samych rozdziałów jednocześnie w dwóch rozbieżnych kopiach.
Przed zmianą miejsca pracy zsynchronizuj własne zmiany.
Wbudowana integracja GitHub w Overleaf nie jest wymagana dla tego przepływu.

## Przed podróżą

Po zatwierdzeniu własnych lokalnych zmian:

~~~powershell
git pull --ff-only
.\scripts\build-thesis.ps1
.\scripts\build-thesis.ps1 -Offline
~~~

Pobierz też potrzebne publikacje i pliki danych zgodnie z ich licencjami.

## W pociągu bez internetu

~~~powershell
.\scripts\build-thesis.ps1 -Offline
git diff
git add thesis/chapters/01-introduction.tex
git commit -m "docs(thesis): expand introduction"
~~~

Commity są lokalne. Po powrocie do sieci wykonaj git pull --ff-only, a następnie
git push. Jeśli historie się rozeszły, sprawdź je i rozwiąż konflikt; nie używaj
automatycznie reset --hard ani push --force.

## Połączenie z przyszłą symulacją

Konfiguracja/seed -> symulator -> MQTT -> kolektor/dane -> ewaluacja ->
manifest i CSV -> eksport tabeli -> LaTeX -> PDF.

Obecnie działają część dokumentacyjna i eksporter tabel.
Symulator, kolektor i ewaluacja wymagają implementacji Milestone 1 i etapu ML.
Po ich zbudowaniu zależności również trzeba pobrać przed pracą offline.

Źródła, konfiguracje bez sekretów i małe zatwierdzone eksporty trafiają do Git.
Surowe dane, bazy, modele, lokalne dane autora i pliki kompilacji są ignorowane.
Wykonuj osobne kopie danych badawczych, których nie ma w Git.
