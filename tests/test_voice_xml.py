"""Exercise the actual pure generator without starting Flask or loading secrets.

Importing main creates /app/data and initializes provider configuration. Select
only its generator AST so these standard-library tests have no such effects.
"""
import ast
import hashlib
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URL = "https://let-food-into-civic.contrived.com/static/dtmf5-2sec.wav"


def generate(url=DEFAULT_URL, iterations=3):
    source = ROOT / "src/main.py"
    tree = ast.parse(source.read_text(), filename=str(source))
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name == "generate_unlock_texml"]
    if len(functions) != 1:
        raise AssertionError("Expected exactly one production generator")
    module = ast.Module(body=functions, type_ignores=[])
    namespace = {"DTMF_AUDIO_URL": url, "ITERATIONS": iterations,
                 "PAUSE_DURATION": 0.5}
    exec(compile(module, str(source), "exec"), namespace)
    return namespace["generate_unlock_texml"]()


class VoiceXMLTests(unittest.TestCase):
    def test_query_parameters_round_trip_as_text(self):
        url = "https://audio.example.invalid/tone.wav?version=1&variant=two"
        xml = generate(url)
        self.assertIn("&amp;variant=two", xml)
        self.assertEqual([node.text for node in ET.fromstring(xml).findall("Play")],
                         [url] * 3)

    def test_configured_markup_cannot_add_instructions(self):
        url = "https://audio.example.invalid/</Play><Say>unexpected</Say><Play>"
        tree = ET.fromstring(generate(url))
        self.assertEqual([node.tag for node in tree],
                         ["Play", "Pause", "Play", "Pause", "Play", "Hangup"])
        self.assertEqual([node.text for node in tree.findall("Play")], [url] * 3)

    def test_default_response_stays_byte_identical(self):
        expected = '<?xml version="1.0" encoding="UTF-8"?>\n<Response>\n'
        expected += (f'    <Play>{DEFAULT_URL}</Play>\n'
                     '    <Pause length="0.5"/>\n') * 2
        expected += f'    <Play>{DEFAULT_URL}</Play>\n    <Hangup/>\n</Response>'
        self.assertEqual(generate(), expected)

    def test_fixed_six_tone_contract_is_preserved(self):
        tree = ET.fromstring(generate(iterations=6))
        self.assertEqual([node.text for node in tree.findall("Play")],
                         [DEFAULT_URL] * 6)
        self.assertEqual([node.attrib for node in tree.findall("Pause")],
                         [{"length": "0.5"}] * 5)
        self.assertEqual([node.tag for node in tree][-1], "Hangup")
        self.assertEqual(len(tree.findall("Hangup")), 1)

    def test_protected_recorded_audio_is_unchanged(self):
        audio = ROOT / "src/static/dtmf5-2sec.wav"
        self.assertEqual(hashlib.sha256(audio.read_bytes()).hexdigest(),
                         "17e3284bdb52f1bcdf51b35aa551ca70e835ce109f408e48d1a9fb24a061f5f0")


if __name__ == "__main__":
    unittest.main()
