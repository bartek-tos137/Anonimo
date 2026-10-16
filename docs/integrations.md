# Integracje

## Zakres

| Klient / transport | Implementacja | Zweryfikowano |
| --- | --- | --- |
| ChatGPT WWW | Tekst w `messages[].content.parts`, JSON pozostałych endpointów | Syntetyczne JSON + rzeczywiste proxy TLS |
| Claude WWW | `prompt` w completion, ogólny JSON | Syntetyczne JSON + rzeczywiste proxy TLS |
| Gemini WWW | Tekstowy `f.req` w StreamGenerate | Syntetyczny formularz + rzeczywiste proxy TLS |
| Codex / OpenAI API | JSON Responses i Chat Completions | Syntetyczne payloady + rzeczywiste proxy TLS |
| Claude Code / Anthropic API | JSON Messages, tekst i wyniki narzędzi w zagnieżdżonych polach | Syntetyczne payloady + rzeczywiste proxy TLS |
| GitHub Copilot | JSON API w domenach `*.githubcopilot.com` | Syntetyczne payloady + rzeczywiste proxy TLS |
| Microsoft Copilot | JSON HTTP i WebSocket JSON/SignalR | Testy formatu + rzeczywiste proxy WSS z lokalnym odbiorcą |
| Inne czaty | Domena w YAML + ogólny JSON | Wymaga testu konkretnego klienta |

To macierz obsługiwanych transportów, nie certyfikat zgodności z produktami. Różne wersje, logowanie, nowe endpointy i formaty binarne mogą wymagać zmian. Konta testowe nie są dołączone.

## Burp

Kolejność preferowana do debugowania: **klient → Anonimo → Burp → serwis**. Dzięki temu Burp powinien widzieć oczyszczoną treść żądania. Burp nadal widzi nagłówki uwierzytelnienia; traktuj projekt Burpa jako poufny.

1. Uruchom listener Burpa na `127.0.0.1:8081`.
2. Wyeksportuj certyfikat CA Burpa w formacie PEM. Jeżeli eksportujesz DER, przekonwertuj go np. `openssl x509 -inform DER -in burp.der -out burp.pem`.
3. Zatrzymaj poprzedni proces Anonimo, aby zwolnić porty. Uruchom:

```sh
uv run --frozen --extra proxy anonimo background --burp-upstream http://127.0.0.1:8081 --burp-ca /absolute/path/burp.pem
```

W Windows użyj pełnej ścieżki do PEM. Dla instalacji w tle zachowaj dodatkowo argumenty `--policy`, `--token-file` i `--state-dir` wskazujące katalog `%LOCALAPPDATA%\Anonimo`.

Anonimo nadal sprawdza TLS; plik PEM rozszerza zaufanie do wskazanego Burpa. Nie stosuj `ssl_insecure`, `verify=False` ani wyłączania weryfikacji certyfikatów. Nie konfiguruj Burpa tak, by kierował ruch ponownie do Anonimo, bo powstanie pętla. Burp GUI nie jest dostępny w środowisku testowym, więc pełny łańcuch z Burpem pozostaje do sprawdzenia.

## Codex, Claude Code, Copilot CLI i IDE

Przeglądarki zwykle honorują systemowe ustawienia proxy. Klient CLI/IDE może wymagać osobnej konfiguracji. Dostępny jest wrapper procesu dla Windows:

```powershell
.\scripts\Use-Anonimo.ps1 -Client claude
.\scripts\Use-Anonimo.ps1 -Client codex
.\scripts\Use-Anonimo.ps1 -Client copilot
```

Wrapper ustawia `HTTP_PROXY`, `HTTPS_PROXY`, lokalny `NO_PROXY` i `NODE_EXTRA_CA_CERTS` dla uruchamianego klienta, po czym przywraca ustawienia procesu nadrzędnego. Certyfikat Windows jest instalowany wcześniej przez `Install-Background.ps1`. Nie podaje ani nie kopiuje tokenów dostawców; klient korzysta ze swojego istniejącego uwierzytelnienia.

Obsługa zmiennych proxy i magazynów CA zależy od klienta oraz wersji. Ten wrapper nie gwarantuje, że każdy klient honoruje te zmienne. Dla VS Code ustaw `http.proxy` na `http://127.0.0.1:8877` zgodnie z polityką organizacji, zachowując weryfikację TLS. Dodatkowe domeny Copilota dla konkretnej organizacji dodaj do `protected_hosts`; nie zakładaj, że domeny logowania i domeny przesyłania promptów są identyczne.

Weryfikacja pilotażowa: użyj wyłącznie sztucznych danych, potwierdź oczyszczony payload po stronie kontrolowanego proxy/odbiorcy i sprawdź zachowanie po zatrzymaniu Anonimo. Samo działające połączenie lub odpowiedź klienta nie dowodzi, że ruch został przechwycony.

## Kod i narzędzia agentów

Wysyłanie całego kontekstu projektu bywa niezbędne dla Codexa, Claude Code i Copilota. Domyślna reguła `fenced-code` usuwa cały blok kodu Markdown. W lokalnym profilu dla programistów można ją usunąć i pozostawić reguły sekretów, a poufność kodu oceniać oddzielną polityką/modelowym detektorem. Usunięcie tej reguły oznacza mniejszy zakres ochrony kodu. Kod poza blokami Markdown nie ma uniwersalnego detektora w regułach tej wersji.

Filtr nie kontroluje działań wykonywanych lokalnie przez agenta ani jego narzędzi komunikujących się z innymi domenami. Wyniki narzędzi przesyłane jako tekst JSON do chronionego API są analizowane tak samo jak inne wartości tekstowe.
