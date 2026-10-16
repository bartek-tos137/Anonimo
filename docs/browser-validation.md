# Odbiór pierwszej wersji: Windows, Firefox i Chrome

Priorytet pierwszy obejmuje Windows z Firefoxem i Chrome. Linux i macOS są drugim etapem wdrożenia użytkowego. Ten dokument określa plan; nie jest raportem wykonanych testów na Windowsie.

## Macierz

| Środowisko | Priorytet | Stan |
| --- | --- | --- |
| Windows + Firefox Stable | Pierwszy | Do sprawdzenia na Windows |
| Windows + Firefox ESR, jeśli używany w firmie | Pierwszy, dla wdrożenia ESR | Do sprawdzenia na Windows |
| Windows + Chrome Stable | Pierwszy | Do sprawdzenia na Windows |
| Windows + IDE/CLI: Copilot, Codex, Claude Code | Pierwszy, integracje API | Do sprawdzenia z rzeczywistymi klientami |
| Linux i macOS | Drugi | Brak odebranego instalatora i integracji systemowej |

Zapisuj dokładną wersję systemu, przeglądarki/klienta, Anonimo i polityki. Pomiar docelowy wykonuj na laptopie z 16 GB RAM oraz na słabszym komputerze; CPU, RAM, p50/p95 i błędy analizy należy mierzyć także z właściwym lokalnym modelem.

## Scenariusze dla każdej przeglądarki

1. Zainstaluj Anonimo i potwierdź autostart po ponownym logowaniu bez ręcznego uruchamiania procesu.
2. Sprawdź skuteczne proxy oraz zaufanie do lokalnego CA, bez wyjątków TLS. Dla Firefoxa sprawdź także jego ustawienia sieci i polityki certyfikatów.
3. W ChatGPT, Claude, Gemini i Microsoft Copilot otwórz nowy czat, wklej syntetyczną fakturę i kliknij zwykłe **Wyślij**. W kontrolowanym odbiorcy lub Burpie za Anonimo potwierdź zamienniki i brak oryginalnych wykrywanych danych. Widok wiadomości w przeglądarce może nadal zawierać oryginał; nie jest dowodem treści wysłanej na serwer.
4. Sprawdź kontynuację rozmowy, ponowienia wysyłki i odpowiedzi strumieniowe. Treści przesyłane w historii rozmowy również muszą być analizowane.
5. Sprawdź załączniki, nieobsługiwane formaty i błędny wynik modelu: takie żądanie ma zostać zatrzymane. Oceń także komunikat widoczny dla użytkownika; prototyp nie zapewnia jeszcze czytelnej informacji w każdym czacie.
6. Sprawdź zatrzymanie procesu, wznowienie po uśpieniu i restart komputera. Odróżniaj błąd połączenia przez proxy od niepożądanego wysłania oryginalnej treści poza nim.
7. Potwierdź brak odszyfrowywania zwykłych stron poza domenami chronionymi i sprawdź współpracę z istniejącym firmowym proxy w uzgodnionej konfiguracji.
8. Odinstaluj pilotaż; potwierdź odtworzenie ustawień proxy, usunięcie dodanego zaufania CA i działanie obu przeglądarek. Osobno przywróć ewentualne ręczne ustawienia Firefoxa.

Dla GitHub Copilot, Codexa i Claude Code wykonaj analogiczne testy wysyłki przez skonfigurowane proxy/API. Zaliczenie testu przeglądarki nie potwierdza przechwytywania ruchu klienta CLI lub IDE. Żadnego testu nie należy prowadzić na rzeczywistych danych poufnych przed potwierdzeniem działania toru ochrony.
