"""Tests für den OpenAI-kompatiblen Client – ohne Internet.

Statt eines echten Servers beantwortet ein httpx.MockTransport die Anfragen.
So prüfen wir, was wir senden und wie wir die Antwort lesen.
"""

import json

import httpx
import openai
import pytest

from core.konfig import konfig_laden
from core.llm_client import (
    BudgetErschoepft,
    KontingentErschoepft,
    LLMFehler,
    OpenAIKompatiblerClient,
    wartezeit_aus_fehler,
)
from core.tools import ToolSchema

TOOL = ToolSchema("abstimmen", "Stimme ab.", {"ziel": {"type": "string"}}, ("ziel",))


def antwort_json(tool_calls: list[dict] | None, content: str | None = None) -> dict:
    return {
        "id": "x",
        "object": "chat.completion",
        "created": 0,
        "model": "test",
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {"role": "assistant", "content": content, "tool_calls": tool_calls},
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
    }


def tool_call(name: str, argumente: str) -> dict:
    return {"id": "c1", "type": "function", "function": {"name": name, "arguments": argumente}}


def client_mit(handler, **kwargs) -> tuple[OpenAIKompatiblerClient, list[dict]]:
    """Baut einen Client, dessen HTTP-Anfragen `handler` beantwortet."""
    gesendet: list[dict] = []

    def mitschreiben(request: httpx.Request) -> httpx.Response:
        gesendet.append(json.loads(request.content))
        return handler(request)

    sdk = openai.OpenAI(
        base_url="https://test.invalid/v1",
        api_key="test",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(mitschreiben)),
    )
    client = OpenAIKompatiblerClient("https://test.invalid/v1", "test-modell", "test", sdk=sdk, **kwargs)
    return client, gesendet


def test_tool_call_wird_gelesen() -> None:
    client, gesendet = client_mit(
        lambda r: httpx.Response(200, json=antwort_json([tool_call("abstimmen", '{"ziel": "Ben"}')]))
    )
    antwort = client.anfragen("System", "Nachricht", [TOOL])

    assert antwort.tool_call is not None
    assert antwort.tool_call.name == "abstimmen"
    assert antwort.tool_call.argumente == {"ziel": "Ben"}

    # Was an den Anbieter ging:
    anfrage = gesendet[0]
    assert anfrage["model"] == "test-modell"
    assert anfrage["messages"][0] == {"role": "system", "content": "System"}
    assert anfrage["tools"][0]["function"]["name"] == "abstimmen"
    assert anfrage["tool_choice"] == "required"

    assert client.statistik.aufrufe == 1
    assert client.statistik.input_tokens == 100
    assert client.statistik.output_tokens == 20
    assert client.statistik.gecachte_tokens == 0  # Antwort ohne Cache-Angabe


def test_gecachte_tokens_werden_gezaehlt() -> None:
    daten = antwort_json([tool_call("abstimmen", '{"ziel": "Ben"}')])
    daten["usage"]["prompt_tokens_details"] = {"cached_tokens": 64}
    client, _ = client_mit(lambda r: httpx.Response(200, json=daten))
    client.anfragen("S", "N", [TOOL])
    client.anfragen("S", "N", [TOOL])
    assert client.statistik.gecachte_tokens == 128


@pytest.mark.parametrize("tool_calls", [None, [tool_call("abstimmen", "{kaputt")]])
def test_kein_oder_kaputter_tool_call(tool_calls) -> None:
    client, _ = client_mit(lambda r: httpx.Response(200, json=antwort_json(tool_calls, "Hallo")))
    antwort = client.anfragen("S", "N", [TOOL])
    assert antwort.tool_call is None
    assert antwort.text == "Hallo"
    assert client.statistik.ohne_tool_call == 1


def test_serverfehler_wird_zu_llmfehler() -> None:
    client, _ = client_mit(lambda r: httpx.Response(500, json={"error": {"message": "kaputt"}}))
    with pytest.raises(LLMFehler):
        client.anfragen("S", "N", [TOOL])
    assert client.statistik.fehler == 1
    assert "kaputt" in client.statistik.letzter_fehler


def test_budget_stoppt_weitere_aufrufe() -> None:
    client, gesendet = client_mit(
        lambda r: httpx.Response(200, json=antwort_json([tool_call("abstimmen", '{"ziel": "Ben"}')])),
        max_aufrufe=2,
    )
    client.anfragen("S", "N", [TOOL])
    client.anfragen("S", "N", [TOOL])
    with pytest.raises(BudgetErschoepft):
        client.anfragen("S", "N", [TOOL])
    assert len(gesendet) == 2  # der dritte Aufruf ging nie raus


def test_konfig_aus_umgebung(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "https://api.beispiel.de/v1")
    monkeypatch.setenv("LLM_MODEL", "modell-x")
    monkeypatch.setenv("LLM_API_KEY", "geheim")
    monkeypatch.setenv("LLM_MAX_AUFRUFE", "50")
    konfig = konfig_laden(env_datei=None)
    assert konfig.modell == "modell-x"
    assert konfig.max_aufrufe == 50


def test_konfig_meldet_fehlende_werte(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValueError, match="LLM_BASE_URL"):
        konfig_laden(env_datei=None)


def test_lokaler_server_braucht_keinen_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("LLM_MODEL", "qwen3:4b")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert konfig_laden(env_datei=None).api_key == "lokal"


class FakeUhr:
    """Ersetzt time.monotonic und time.sleep: Warten stellt nur die Uhr vor."""

    def __init__(self) -> None:
        self.jetzt = 0.0
        self.pausen: list[float] = []

    def __call__(self) -> float:
        return self.jetzt

    def schlafen(self, sekunden: float) -> None:
        self.pausen.append(sekunden)
        self.jetzt += sekunden


def ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=antwort_json([tool_call("abstimmen", '{"ziel": "Ben"}')]))


def zu_viele(request: httpx.Request) -> httpx.Response:
    return httpx.Response(429, json={"error": {"message": "Quota exceeded", "code": 429}})


def test_tempolimit_haelt_abstand() -> None:
    uhr = FakeUhr()
    client, gesendet = client_mit(ok, max_pro_minute=15, uhr=uhr, schlafen=uhr.schlafen)
    for _ in range(3):
        client.anfragen("S", "N", [TOOL])

    assert len(gesendet) == 3
    # Erste Anfrage sofort, danach je 60/15 = 4 Sekunden Abstand.
    assert uhr.pausen == [4.0, 4.0]
    assert client.statistik.gewartet == 8.0


def test_ohne_tempolimit_kein_warten() -> None:
    uhr = FakeUhr()
    client, _ = client_mit(ok, uhr=uhr, schlafen=uhr.schlafen)
    client.anfragen("S", "N", [TOOL])
    client.anfragen("S", "N", [TOOL])
    assert uhr.pausen == []


def test_429_wird_nach_pause_wiederholt() -> None:
    uhr = FakeUhr()
    antworten = [zu_viele, zu_viele, ok]
    client, gesendet = client_mit(
        lambda r: antworten.pop(0)(r), uhr=uhr, schlafen=uhr.schlafen
    )
    antwort = client.anfragen("S", "N", [TOOL])

    assert antwort.tool_call is not None
    assert len(gesendet) == 3
    assert uhr.pausen == [10.0, 20.0]
    assert client.statistik.fehler == 0
    assert client.statistik.aufrufe == 1  # Wiederholungen zählen nicht ins Budget


def test_429_gibt_nach_allen_versuchen_auf() -> None:
    uhr = FakeUhr()
    client, gesendet = client_mit(zu_viele, uhr=uhr, schlafen=uhr.schlafen)
    with pytest.raises(LLMFehler, match="Quota"):
        client.anfragen("S", "N", [TOOL])
    assert len(gesendet) == 4  # 1 Versuch + 3 Wiederholungen
    assert uhr.pausen == [10.0, 20.0, 40.0]
    assert client.statistik.fehler == 1


def test_konfig_liest_tempolimit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "https://api.beispiel.de/v1")
    monkeypatch.setenv("LLM_MODEL", "modell-x")
    monkeypatch.setenv("LLM_API_KEY", "geheim")
    monkeypatch.setenv("LLM_MAX_PRO_MINUTE", "14")
    assert konfig_laden(env_datei=None).max_pro_minute == 14


def tageslimit(request: httpx.Request) -> httpx.Response:
    return httpx.Response(429, json=[{"error": {
        "code": 429,
        "message": "Quota exceeded, quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier",
        "details": [{"retryDelay": "41195s"}],
    }}])


def test_tageslimit_bricht_sofort_ab() -> None:
    uhr = FakeUhr()
    client, gesendet = client_mit(tageslimit, uhr=uhr, schlafen=uhr.schlafen)
    with pytest.raises(KontingentErschoepft):
        client.anfragen("S", "N", [TOOL])
    assert len(gesendet) == 1  # kein erneuter Versuch
    assert uhr.pausen == []  # und kein Warten
    assert client.statistik.fehler == 1


def test_kontingent_ist_kein_llmfehler() -> None:
    # Sonst würde der LLMSpieler daraus still eine Zufallsaktion machen.
    assert not issubclass(KontingentErschoepft, LLMFehler)


@pytest.mark.parametrize("text, sekunden", [
    ("'retryDelay': '41195s'", 41195.0),
    ('"retryDelay": "0.5s"', 0.5),
    ("Please retry later", None),
])
def test_wartezeit_aus_fehler(text: str, sekunden: float | None) -> None:
    assert wartezeit_aus_fehler(text) == sekunden


def responses_json(ausgabe: list[dict]) -> dict:
    """Eine Antwort im Format der Responses-Schnittstelle (/v1/responses)."""
    return {
        "id": "resp_1", "object": "response", "created_at": 0, "model": "gpt-6-sol", "status": "completed",
        "output": ausgabe, "parallel_tool_calls": True, "tool_choice": "required", "tools": [],
        "usage": {"input_tokens": 300, "output_tokens": 50, "total_tokens": 350,
                  "input_tokens_details": {"cached_tokens": 200}, "output_tokens_details": {"reasoning_tokens": 30}},
    }


def test_responses_schnittstelle() -> None:
    # GPT-6 nutzt Tools beim Nachdenken nur über /responses (bei /chat/completions: Fehler 400).
    pfade: list[str] = []

    def antworten(request: httpx.Request) -> httpx.Response:
        pfade.append(request.url.path)
        return httpx.Response(200, json=responses_json([
            {"type": "reasoning", "id": "rs_1", "summary": []},  # Nachdenken: wird übersprungen
            {"type": "function_call", "id": "fc_1", "call_id": "c1", "name": "abstimmen",
             "arguments": '{"ziel": "Ben"}', "status": "completed"},
        ]))

    client, gesendet = client_mit(antworten, schnittstelle="responses")
    antwort = client.anfragen("System", "Nachricht", [TOOL])

    assert pfade == ["/v1/responses"]
    anfrage = gesendet[0]
    assert anfrage["instructions"] == "System" and anfrage["input"] == [{"role": "user", "content": "Nachricht"}]
    # Tools flach statt unter "function", nicht strikt (die Begründung ist freiwillig).
    assert anfrage["tools"][0]["name"] == "abstimmen" and anfrage["tools"][0]["strict"] is False
    assert "temperature" not in anfrage and anfrage["store"] is False
    assert antwort.tool_call is not None and antwort.tool_call.argumente == {"ziel": "Ben"}
    assert (client.statistik.input_tokens, client.statistik.output_tokens, client.statistik.gecachte_tokens) == (300, 50, 200)


def test_responses_ohne_tool_call_zaehlt() -> None:
    client, _ = client_mit(lambda r: httpx.Response(200, json=responses_json([
        {"type": "message", "id": "m1", "role": "assistant", "status": "completed",
         "content": [{"type": "output_text", "text": "Ich überlege noch.", "annotations": []}]},
    ])), schnittstelle="responses")
    antwort = client.anfragen("S", "N", [TOOL])
    assert antwort.tool_call is None and antwort.text == "Ich überlege noch."
    assert client.statistik.ohne_tool_call == 1


def test_konfig_liest_schnittstelle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("LLM_MODEL", "gpt-6.1-sol")
    monkeypatch.setenv("LLM_API_KEY", "x")
    monkeypatch.delenv("LLM_SCHNITTSTELLE", raising=False)
    assert konfig_laden(env_datei=None).schnittstelle == "chat"  # Standard: wie bisher
    monkeypatch.setenv("LLM_SCHNITTSTELLE", "Responses")
    assert konfig_laden(env_datei=None).client().schnittstelle == "responses"
    monkeypatch.setenv("LLM_SCHNITTSTELLE", "irgendwas")
    with pytest.raises(ValueError):
        konfig_laden(env_datei=None)
