# Trippi — Smart Trip Planner

Asistent de călătorii bazat pe AI: un chat conversațional care planifică
călătorii și învață preferințele utilizatorului din conversație. Construit cu
Django 6 + MySQL.

## Arhitectura AI (2 agenți)

Toată logica AI stă în aplicația `agents/`, în spatele unei singure funcții
(`orchestrator.handle_user_message`), astfel încât `trips/views.py` să nu depindă
de detaliile providerului.

- **Concierge** (`agents/concierge.py`) — asistentul conversațional (răspunde în
  română).
- **Data Architect** (`agents/data_architect.py`) — extrage tăcut preferințele
  din conversație (JSON strict → validare → merge în `UserPreference`).

Design patterns folosite:

- **Strategy** — `LLMClient` (în `agents/llm_client.py`) cu implementări
  interschimbabile: `AnthropicClient`, `GeminiClient`, `EchoClient`.
- **Factory** — `make_llm_client()` alege providerul din mediu și cade pe
  `EchoClient` (offline) dacă nu există cheie/SDK.
- **Facade** — `orchestrator.handle_user_message()` ascunde tot subsistemul de
  agenți după un singur apel.

## Cerințe

- Python 3.12+
- MySQL (server pornit, cu o bază de date creată)

## Instalare

```bash
# 1. Mediu virtual + dependențe
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. Configurare mediu
cp .env.example .env              # apoi completează valorile (vezi mai jos)

# 3. Migrații
python manage.py migrate

# 4. (opțional) cont de admin
python manage.py createsuperuser

# 5. Pornește serverul
python manage.py runserver
```

Aplicația rulează la http://127.0.0.1:8000/.

## Variabile de mediu (`.env`)

Vezi `.env.example` pentru lista completă. Cele esențiale:

| Variabilă | Rol |
|---|---|
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | conexiunea MySQL |
| `ANTHROPIC_API_KEY` | cheie Claude (pentru Concierge) |
| `GOOGLE_API_KEY` | cheie Gemini (pentru Data Architect) |
| `LLM_PROVIDER` | `anthropic` (implicit) sau `gemini` — providerul Concierge |
| `ANTHROPIC_MODEL`, `GEMINI_MODEL` | suprascriu modelele implicite |

**Fără chei AI aplicația tot funcționează**: agenții cad pe un client offline
(`EchoClient`) care întoarce un răspuns demo, deci poți rula și testa local fără
cont la vreun provider.

## Teste

```bash
python manage.py test agents
```

Testele rulează complet offline (LLM-ul e înlocuit cu un client fake), deci nu au
nevoie de cheie API sau rețea.

> Notă: testele care ating baza de date (`OrchestratorTests`) necesită ca
> utilizatorul MySQL să poată crea baza de test (`test_<DB_NAME>`). Testele de
> logică pură rulează oricum.

## Structura proiectului

```
agents/    # logica AI: orchestrator, agenți, client LLM, prompturi, teste
trips/     # chat: modele ChatSession/ChatMessage, view-uri, istoric călătorii
users/     # autentificare, preferințe utilizator, setări cont
resurse/   # fișiere statice (css, js, media)
```
