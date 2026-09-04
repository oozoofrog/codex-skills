import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).parents[1] / "scripts" / "swift_intelligence_mcp.py"
SPEC = importlib.util.spec_from_file_location("swift_intelligence_mcp", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RecoveringSession(MODULE.SourceKitSession):
    def __init__(self, error):
        super().__init__("/")
        self.error = error
        self.request_count = 0
        self.restart_count = 0

    def prepare_document(self, file_path, refresh=False):
        return Path(file_path).as_uri()

    def request(self, method, params, timeout=60):
        self.request_count += 1
        if self.request_count == 1:
            raise self.error
        return {"method": method, "params": params}

    def restart(self):
        self.restart_count += 1


class PullDiagnosticsSession(MODULE.SourceKitSession):
    def __init__(self):
        super().__init__("/")
        self.server_capabilities = {"diagnosticProvider": {}}

    def prepare_document(self, file_path, refresh=False):
        return Path(file_path).as_uri()

    def request_document(self, method, file_path, params=None, until_nonempty=False):
        self.method = method
        return {"kind": "full", "items": [{"message": "test diagnostic"}]}


class PrepareDocumentSession(MODULE.SourceKitSession):
    def __init__(self, workspace):
        super().__init__(workspace)
        self.notifications = []

    def start(self):
        return None

    def notify(self, method, params):
        self.notifications.append((method, params))


class SourceKitSessionTests(unittest.TestCase):
    def test_document_request_restarts_once_for_missing_language_service(self):
        error = MODULE.SourceKitRPCError(
            "textDocument/hover",
            -32001,
            "No language service found",
        )
        session = RecoveringSession(error)

        result = session.request_document(
            "textDocument/hover",
            "/tmp/Test.swift",
            {"position": {"line": 0, "character": 0}},
        )

        self.assertEqual(session.restart_count, 1)
        self.assertEqual(session.request_count, 2)
        self.assertEqual(
            result["params"]["textDocument"]["uri"],
            "file:///tmp/Test.swift",
        )

    def test_document_request_does_not_restart_for_other_rpc_errors(self):
        session = RecoveringSession(
            MODULE.SourceKitRPCError("textDocument/hover", -32601, "Method not found")
        )

        with self.assertRaises(MODULE.SourceKitRPCError):
            session.request_document("textDocument/hover", "/tmp/Test.swift")

        self.assertEqual(session.restart_count, 0)
        self.assertEqual(session.request_count, 1)

    def test_diagnostics_prefers_pull_when_advertised(self):
        session = PullDiagnosticsSession()

        result = session.diagnostics_for_document("/tmp/Test.swift")

        self.assertEqual(result, [{"message": "test diagnostic"}])
        self.assertEqual(session.method, "textDocument/diagnostic")

    def test_prepare_document_only_changes_when_contents_change(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Test.swift"
            path.write_text("let value = 1\n", encoding="utf-8")
            session = PrepareDocumentSession(directory)

            session.prepare_document(path, refresh=True)
            session.prepare_document(path, refresh=True)
            path.write_text("let value = 2\n", encoding="utf-8")
            session.prepare_document(path, refresh=True)

        self.assertEqual(
            [method for method, _ in session.notifications],
            ["textDocument/didOpen", "textDocument/didChange"],
        )

    def test_diagnostics_rejects_stale_document_version(self):
        self.assertFalse(MODULE.SourceKitSession._diagnostics_version_matches(
            {"version": 1, "items": []},
            2,
        ))
        self.assertTrue(MODULE.SourceKitSession._diagnostics_version_matches(
            {"version": 2, "items": []},
            2,
        ))


class XcodeProjectTests(unittest.TestCase):
    def test_infers_index_store_from_build_argument(self):
        with tempfile.TemporaryDirectory() as directory:
            derived_data = Path(directory)
            build_product = derived_data / "Build" / "Products" / "Debug"
            index_store = derived_data / "Index.noindex" / "DataStore"
            build_product.mkdir(parents=True)
            (index_store / "v5").mkdir(parents=True)

            result = MODULE.XcodeProject._index_store_from_arguments([
                "-F" + str(build_product),
            ])

        self.assertEqual(result, index_store)

    def test_guesses_unselected_scheme_from_source_path(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = (Path(directory) / "workspace").resolve()
            workspace.mkdir()
            project = MODULE.XcodeProject(
                workspace,
                workspace / "Talk.xcworkspace",
                "TalkSound",
            )
            project._schemes = ["TalkSound", "TalkMarkdown"]
            source = workspace / "Projects" / "TalkMarkdown" / "Sources" / "Text.swift"

            scheme = project.guess_scheme(source)
            project.extra_schemes.append(scheme)

        self.assertEqual(scheme, "TalkMarkdown")
        self.assertEqual(project.selected_schemes(), ["TalkSound", "TalkMarkdown"])

    def test_retargets_configuration_to_built_simulator(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            products = root / "Build" / "Products"
            configuration = "Inhouse(iTeam)-Debug"
            (products / f"{configuration}-iphonesimulator").mkdir(parents=True)
            values = {
                "swiftASTCommandArguments": [
                    str(products / "Debug-iphoneos" / "TalkSound.framework")
                ],
                "outputFilePath": str(
                    root / "Build" / "TalkSound.build" / "Debug-iphoneos" / "Sound.o"
                ),
            }
            settings = {"TalkSound": {"/tmp/Sound.swift": values}}
            project = MODULE.XcodeProject(root, root / "Talk.xcworkspace", "TalkSound")
            project._scheme_configuration = lambda _: configuration

            project._retarget_configuration(settings, "TalkSound")

        self.assertIn(
            f"{configuration}-iphonesimulator",
            values["swiftASTCommandArguments"][0],
        )
        self.assertIn(f"{configuration}-iphonesimulator", values["outputFilePath"])

    def test_shared_index_database_falls_back_when_locked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            first = MODULE.XcodeProject(root, root / "Talk.xcworkspace")
            second = MODULE.XcodeProject(root, root / "Talk.xcworkspace")
            with patch.object(MODULE, "INDEX_SETTINGS_CACHE", root / "cache"):
                shared = first._index_database(root / "lsp-one", root / "IndexStore")
                fallback = second._index_database(root / "lsp-two", root / "IndexStore")
            first.release_index_lock()
            second.release_index_lock()

        self.assertEqual(shared.parent, root / "cache")
        self.assertEqual(fallback, root / "lsp-two" / "IndexDatabase")


class WorkspaceSymbolTests(unittest.TestCase):
    def test_exact_symbols_are_ranked_first_and_duplicates_are_removed(self):
        symbols = [
            {
                "name": "UnrelatedSoundSourceBuilder",
                "kind": 5,
                "location": {
                    "uri": "file:///tmp/Other.swift",
                    "range": {"start": {"line": 2, "character": 0}},
                },
            },
            {
                "name": "SoundSource",
                "kind": 11,
                "location": {
                    "uri": "file:///tmp/SoundSource.swift",
                    "range": {"start": {"line": 0, "character": 0}},
                },
            },
            {
                "name": "SoundSource",
                "kind": 11,
                "location": {
                    "uri": "file:///tmp/SoundSource.swift",
                    "range": {"start": {"line": 0, "character": 0}},
                },
            },
        ]

        result = MODULE.rank_workspace_symbols(symbols, "SoundSource")

        self.assertEqual([symbol["name"] for symbol in result], [
            "SoundSource",
            "UnrelatedSoundSourceBuilder",
        ])


if __name__ == "__main__":
    unittest.main()
