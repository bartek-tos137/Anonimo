# Lokalny detektor i wydajność

## Podział odpowiedzialności

YAML obsługuje formaty deterministyczne oraz jawne listy firmowe. Model wskazuje fragmenty zawierające osoby, organizacje i poufne informacje kontekstowe. Silnik dokonuje podmiany; model nie przepisuje wiadomości. Nakładające się detekcje są łączone, aby krótsza detekcja nie pozostawiła fragmentu dłuższego sekretu.

Własny model nie jest dołączony. Nie ma również danych treningowych ani deklaracji jakości rozpoznawania nazw. Włączenie małego ogólnego modelu bez ewaluacji nie zastępuje dostrojenia i testów.

## Interfejs

Adapter korzysta z lokalnego serwera zgodnego z OpenAI, np. odpowiednio skonfigurowanego `llama.cpp`. Serwer ma nasłuchiwać wyłącznie na loopback, bez logowania promptów i bez automatycznego pobierania danych do chmury. Po lokalnym zainstalowaniu wybranego, zweryfikowanego modelu zmień kopię polityki:

```yaml
model:
  enabled: true
  base_url: http://127.0.0.1:8080/v1
  model: local-dlp
  timeout_seconds: 6
  labels: [PERSON, ORGANIZATION, CONFIDENTIAL]
```

Adresy zewnętrzne, nazwa DNS `localhost`, przekierowania HTTP i proxy ze zmiennych środowiska są wyłączone dla detektora. Akceptowane są literalne adresy loopback. To ograniczenie aplikacji; wybrany serwer inferencji również musi być skonfigurowany lokalnie.

Wejście do modelu to tablica tekstów. Odpowiedź zawiera wyłącznie:

```json
{"findings":[{"item":0,"start":0,"end":4,"text":"Anna","label":"PERSON"}]}
```

Offsety są indeksami punktów kodowych Unicode; `end` jest wyłączny. Zwrócony fragment musi dokładnie odpowiadać wejściu, indeksy muszą mieścić się w zakresie, a etykiety muszą znajdować się w polityce. Błędy, timeout, ucięta odpowiedź i nieprawidłowe wyniki zatrzymują żądanie. Pusta poprawna lista oznacza brak detekcji modelu, nie dowód braku wrażliwych danych. Instrukcje zawarte w analizowanym tekście mogą wpływać na model; zestaw oceny powinien zawierać próby prompt injection.

## Minimalny sprzęt i dobór modelu

Punkt odniesienia to firmowy laptop z 16 GB RAM, CPU, z uwzględnieniem słabszych maszyn. Do porównania nadają się dwa warianty: mały model etykietujący tokeny (NER) dla nazw osób/firm oraz kwantyzowany mały LLM do szerszego kontekstu. NER wymagałby dodatkowego adaptera — obecna implementacja zawiera adapter generatywnego lokalnego API. Rozmiar rzędu 0,5–3B parametrów można traktować jako zakres eksperymentów, nie zapewnienie opóźnienia lub jakości.

Pomiar musi obejmować start zimny/ciepły, RAM procesu z cache, obciążenie CPU, długość wejścia, p50/p95 opóźnienia i wpływ na pracę użytkownika. Kwantyzacja może pogarszać recall i wymaga ponownej oceny. Przekroczenie timeoutu nie przełącza systemu potajemnie na słabszą ochronę.

## Ewaluacja

Zestaw testowy powinien być odseparowany od treningowego, obejmować PL/EN, odmianę nazw, faktury, maile, kod, długie prompty, tekst bez wrażliwych danych i próby obejścia. Najważniejsze pomiary: recall per kategoria, precision, błędy analizy, opóźnienie i użyteczność oczyszczonego promptu. Wysokie średnie accuracy przy przewadze zwykłych tokenów może ukrywać słaby recall sekretów.

```sh
uv run --frozen --extra proxy python scripts/evaluate_detector.py --policy .local/model-policy.yaml --dataset .local/evaluation.jsonl
```

Format JSONL (dane powinny pozostać lokalne):

```json
{"text":"Anna pracuje w firmie Przykład.","entities":[{"start":0,"end":4,"label":"PERSON"},{"start":22,"end":30,"label":"ORGANIZATION"}]}
```

Skrypt mierzy dokładne dopasowanie spanów i etykiet, zwraca liczniki i opóźnienia bez drukowania tekstów. Błąd modelu liczy jako niewykrycie etykiet w danej próbce dla metryki jakości detektora, chociaż sam Anonimo blokuje wtedy wysyłkę. Nie tworzy danych treningowych ani nie ocenia pełnego bezpieczeństwa produktu.

## Zmierzona baza reguł

W środowisku deweloperskim Linux, 100 powtórzeń po rozgrzewce, syntetyczny tekst faktury:

| Długość | p50 | p95 |
| --- | --- | --- |
| 1 000 znaków | 0,63 ms | 0,68 ms |
| 5 000 znaków | 2,82 ms | 2,99 ms |
| 20 000 znaków | 10,64 ms | 15,32 ms |

To pomiar samych reguł, bez sieci i bez modelu. Nie stanowi prognozy dla laptopa Windows. Powtórzenie: `python scripts/benchmark.py`. Środowisko Pythona z zależnościami proxy zajęło około 129 MB na dysku; nie jest to pomiar RAM ani rozmiar modelu.
