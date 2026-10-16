# Architektura i granice pierwszej wersji

## Wybór głównego mechanizmu

Głównym wejściem jest lokalne proxy, ponieważ obejmuje przeglądarki i klientów API bez przycisku wymagającego uwagi użytkownika. Przetwarzanie, polityka i adapter modelu są oddzielone od transportu. API tekstowe pozwala użyć tego samego silnika np. dla poczty lub wycen. Wtyczka przeglądarki może zostać później dodana do podglądu zmian i komunikatów, ale nie jest wymagana przez bieżący prototyp.

Proces w tle jest warstwą pomocniczą. Nie jest agentem odpornym na manipulację i nie wymusza przechwytywania całego ruchu komputera. Pełne wdrożenie wymagałoby zarządzania ustawieniami proxy, CA i wyjątkami dla innych aplikacji.

## Obsługa danych

- Silnik nie zapisuje promptów, mapowania zamienników ani historii żądań. Proces i bibliotekę proxy należy nadal traktować jako komponenty mające dostęp do danych jawnych w pamięci.
- Domyślne logowanie dostępu API oraz dumper przepływów proxy są wyłączone. Komunikaty błędów analizy zawierają stałe kody, bez tekstów wejściowych.
- API jest dostępne tylko na loopback i wymaga losowego tokenu. Nie włącza ogólnego CORS. Proxy nasłuchuje na loopback; lokalne procesy mogą z niego korzystać.
- Token i prywatny klucz CA nie są częścią repozytorium. Na Windows katalog stanu jest ograniczony ACL do użytkownika i SYSTEM.
- Certyfikat CA jest unikalny dla instalacji. Prywatnego klucza nie należy dystrybuować jako wspólnego klucza firmowego.
- Żądanie trafia do zewnętrznego dostawcy dopiero po analizie. Dane oryginalne mogą pozostać w UI i lokalnej pamięci przeglądarki; serwer otrzymuje zmodyfikowaną wersję.

## Ograniczenia protokołu

Anonimo analizuje treść POST/PUT/PATCH/DELETE dla domen z YAML i wychodzące tekstowe wiadomości WebSocket. Odpowiedzi HTTP mogą płynąć strumieniowo (SSE). Treści żądań są buforowane do analizy, z limitem 256 KiB, a tekst analizowany przez silnik ma domyślnie limit 50 tys. znaków.

Nieobsługiwane formaty, kompresowane requesty i znane załączniki są zatrzymywane. GET z promptem w URL, alternatywne domeny, niestandardowe kodowanie, pinning certyfikatów, HTTP/3 bez proxy i bezpośrednie połączenia są poza potwierdzonym zakresem. Ogólny adapter JSON analizuje wartości, ale nie nazwy pól. Część protokołów wymaga niezmienionych podpisanych payloadów; anonimizacja może je unieważnić. Specyficzne adaptery powinny być dodawane wraz z przykładami i testami.

## Następne etapy produktu

1. Priorytet pierwszy: instalacja i praca w tle na Windows oraz osobny odbiór Firefoxa i Chrome. Testy rzeczywistych sesji docelowych czatów i klientów API wykonuj z danymi syntetycznymi, według [planu odbioru](browser-validation.md).
2. Dobór i trening lokalnego detektora na etykietowanych danych PL/EN, ocena recall i wpływu na zadania użytkownika.
3. Ekstrakcja tekstu i OCR dla załączników, polityki per aplikacja/rola, rozróżnienie sekretów od dozwolonego kontekstu kodu.
4. Podpisany instalator i aktualizacje, widoczny status w trayu, czytelne powiadomienia o zatrzymanym żądaniu oraz zarządzanie polityką przez IT.
5. Priorytet platformowy drugi: Linux i macOS, ze wspólnym silnikiem i osobnymi integracjami autostartu, certyfikatów oraz proxy. Działający deweloperski proces na Linuxie nie oznacza gotowej instalacji użytkowej dla tej platformy.

Nazwy osób/firm mogą być wrażliwe tylko w określonym kontekście. Znaczenie pseudonimu dla dalszego zadania i utrata użyteczności wymagają oceny obok samej detekcji. Wdrożenie nie powinno deklarować „100% accuracy” ani „wszystkie czaty” na podstawie samych testów transportu.
