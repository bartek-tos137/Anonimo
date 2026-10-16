# Windows: uruchamianie bez pamiętania o aplikacji

Pierwszy cel wdrożenia: Windows 10/11 z Firefoxem i Chrome, CPU, około 16 GB RAM, z pomiarami także na słabszym sprzęcie. Linux i macOS są drugim etapem. Reguły i proxy nie potrzebują GPU. Rozmiar i zużycie pamięci lokalnego modelu wymagają osobnych pomiarów. Ta wersja ma proces w tle i autostart przy logowaniu; nie zawiera jeszcze interfejsu tray ani instalatora MSI.

## Pilotaż na pojedynczym komputerze

1. Zainstaluj Python 3.12+ i `uv`, pobierz repozytorium do stałego katalogu użytkownika.
2. W PowerShell w katalogu projektu uruchom:

```powershell
uv sync --locked --extra proxy
.\.venv\Scripts\python.exe -m pytest -q
.\scripts\Install-Background.ps1 -EnableSystemProxy
```

Jeżeli polityka PowerShell lub polityka firmowa zabrania skryptów, użyj zatwierdzonego przez IT sposobu instalacji. Nie wyłączaj kontroli systemowych.

Skrypt wykonuje jednorazowo:

- tworzy własny CA na tym komputerze i ufa mu w magazynie certyfikatów bieżącego użytkownika;
- ogranicza uprawnienia katalogu `%LOCALAPPDATA%\Anonimo` zawierającego prywatny klucz CA, token i lokalną politykę;
- rejestruje zadanie `Anonimo-Background`, uruchamiane przy logowaniu jako bieżący użytkownik, przez `pythonw.exe` bez okna konsoli;
- uruchamia usługę i sprawdza anonimizację syntetycznych danych przez API;
- zapisuje poprzednie ustawienia proxy i ustawia lokalne proxy HTTP/HTTPS;
- pozostawia lokalne adresy poza proxy.

Istniejący proxy/PAC lub wykryta polityka zarządzana zatrzyma instalację. Nie należy nadpisywać firmowego proxy. Integrację z nim trzeba uzgodnić i przetestować w pilotażu.

Uruchom ponownie przeglądarkę. Od tej chwili przeglądarka korzystająca z proxy wysyła żądania przez Anonimo. Nie ma dodatkowego przycisku „anonimizuj”. Pozostałe domeny są tunelowane bez odszyfrowywania przez Anonimo; chronione domeny określa YAML. Sam proxy nie wysyła telemetrii i nie zapisuje treści przepływów.

Konfiguracja użytkownika: `%LOCALAPPDATA%\Anonimo\policy.yaml`. Po zmianach zrestartuj zadanie w Harmonogramie zadań. Plik w repozytorium pozostaje wzorcem, a ponowna instalacja nie nadpisuje lokalnej polityki.

## Chrome i Firefox

Chrome korzysta z proxy Windows i zaufanych lokalnych certyfikatów systemowych, o ile ustawienia firmowe nie wskazują innej konfiguracji. Po instalacji uruchom ponownie przeglądarkę i potwierdź przechwytywanie sztucznego promptu według [planu odbioru](browser-validation.md).

Firefox wymaga potwierdzenia dwóch niezależnych ustawień:

1. W **Ustawienia → Ogólne → Ustawienia sieci → Ustawienia** wybierz **Używaj systemowych ustawień proxy**, jeżeli IT nie ustawiło już właściwej konfiguracji. Sam certyfikat nie kieruje ruchu przez Anonimo.
2. Włącz korzystanie z zaufanych certyfikatów Windows. W pilotażu odpowiada za to preferencja `security.enterprise_roots.enabled = true` w `about:config`; w środowisku zarządzanym użyj polityki `Certificates.ImportEnterpriseRoots`. Zapisz poprzednią wartość preferencji przed zmianą. Wersja Firefoxa lub polityka organizacji może już ją włączać.

Przykład dla IT znajduje się w [examples/firefox/policies.json](../examples/firefox/policies.json). Wskazuje systemowe proxy i zaufanie do certyfikatów systemowych. Jest szablonem do połączenia z istniejącymi politykami, nie plikiem do nadpisania konfiguracji firmowej. Po wdrożeniu polityki sprawdź `about:policies` i uruchom ponownie Firefoxa. Instalator Anonimo nie modyfikuje profili ani polityk przeglądarki.

Nie dodawaj wyjątków dla błędów TLS. Jeżeli Firefox nie ufa certyfikatowi, zweryfikuj obecność lokalnego CA w magazynie bieżącego użytkownika Windows oraz skuteczną politykę Firefoxa. Obie przeglądarki wymagają osobnego testu: sukces Chrome nie potwierdza działania Firefoxa.

## Awarie i odinstalowanie

Gdy Anonimo nie działa, systemowe proxy może blokować przeglądanie stron. Zadanie ma ograniczoną liczbę prób ponownego uruchomienia. Ochrona nie przełącza automatycznie ruchu na połączenie bezpośrednie. W pilotażu trzeba sprawdzić start po restarcie, uśpienie/wybudzenie i zachowanie po awarii.

```powershell
.\scripts\Uninstall-Background.ps1
```

Skrypt odtwarza zapisane ustawienia, usuwa własne zadanie oraz tylko własny certyfikat zaufania, o ile został dodany przez instalator. Nie usuwa lokalnej polityki ani kluczy z dysku. Jeżeli ustawienia proxy zostały później zmienione przez kogoś innego, wymaga ich uzgodnienia z IT.

Ręczne zmiany preferencji Firefoxa lub wdrożoną osobno politykę IT trzeba przywrócić osobno do poprzedniego stanu. Nie usuwaj ustawień zaufania wymaganych przez inne narzędzia firmowe. Po odinstalowaniu uruchom ponownie obie przeglądarki.

## Stan walidacji

Kod silnika i rzeczywiste proxy TLS zostały sprawdzone na Linuxie. Skrypty PowerShell, magazyn certyfikatów Windows, autostart i żywe sesje Firefoxa oraz Chrome wymagają testu na docelowym Windowsie. Nie ma jeszcze podpisanego instalatora ani centralnego zarządzania. Docelowe wdrożenie firmowe powinno obejmować podpisany pakiet, aktualizacje, status ochrony i polityki dystrybuowane przez IT.
