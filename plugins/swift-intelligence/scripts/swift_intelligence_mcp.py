#!/usr/bin/env python3

import atexit
import fcntl
import gzip
import hashlib
import json
import os
import re
from pathlib import Path
import select
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import quote, unquote, urlparse
import xml.etree.ElementTree as ElementTree


SERVER_NAME = "swift-intelligence"
SERVER_VERSION = "0.1.0"
INDEX_TIMEOUT_SECONDS = 60
INDEX_SETTLE_SECONDS = 10
WORKSPACE_SYMBOL_LIMIT = 200
DIAGNOSTICS_TIMEOUT_SECONDS = 20
# Default Xcode scheme(s)/configuration for fixed automation. SCHEME_ENV accepts a
# comma-separated list; the index settings of every scheme are merged.
SCHEME_ENV = "SWIFT_INTELLIGENCE_XCODE_SCHEME"
CONFIGURATION_ENV = "SWIFT_INTELLIGENCE_XCODE_CONFIGURATION"
# Opt-in: restrict the index to units of the loaded targets' own files. Removes stale
# results left by other configurations' units, but also drops references living in
# modules that are not part of the selected schemes.
EXPLICIT_UNITS_ENV = "SWIFT_INTELLIGENCE_EXPLICIT_UNITS"
TRACE_ENV = "SWIFT_INTELLIGENCE_TRACE"
INDEX_SETTINGS_CACHE = Path.home() / "Library" / "Caches" / "swift-intelligence"


class SourceKitError(Exception):
    pass


class SourceKitRPCError(SourceKitError):
    def __init__(self, method, code, message):
        self.method = method
        self.code = code
        self.message = message
        super().__init__(f"SourceKit-LSP error {code}: {message}")


def trace_enabled():
    return os.environ.get(TRACE_ENV, "").lower() in {"1", "true", "yes"}


def append_trace(path, payload):
    if not path:
        return
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"time": time.time(), **payload}, ensure_ascii=False) + "\n")


class SourceKitSession:
    def __init__(self, workspace, xcode_project=None):
        self.workspace = Path(workspace).resolve()
        self.xcode_project = xcode_project
        self.process = None
        self.lsp_root = None
        self.stderr_handle = None
        self.stderr_path = None
        self.trace_path = None
        self.last_trace_path = None
        self.buffer = bytearray()
        self.next_id = 1
        self.open_documents = {}
        self.document_contents = {}
        self.diagnostics = {}
        self.server_capabilities = {}
        self.index_ready = False

    def start(self):
        if self.process and self.process.poll() is None:
            return
        if self.process or self.lsp_root:
            self.close()
        arguments = ["sourcekit-lsp"]
        root = self.workspace
        self.lsp_root = Path(tempfile.mkdtemp(prefix="swift-intelligence-lsp-"))
        initialization_options = None
        bsp_trace_path = None
        if trace_enabled():
            trace_root = Path(tempfile.mkdtemp(prefix="swift-intelligence-trace-"))
            trace_directory = trace_root / "lsp-mirror"
            trace_directory.mkdir()
            self.trace_path = trace_root / "session-trace.jsonl"
            self.last_trace_path = self.trace_path
            self.stderr_path = trace_root / "sourcekit-lsp.stderr.log"
            bsp_trace_path = trace_root / "bsp-trace.jsonl"
            initialization_options = {
                "logging": {
                    "level": "debug",
                    "privacyLevel": "public",
                    "inputMirrorDirectory": str(trace_directory / "input"),
                    "outputMirrorDirectory": str(trace_directory / "output"),
                }
            }
        else:
            self.stderr_path = self.lsp_root / "sourcekit-lsp.stderr.log"
        if self.xcode_project:
            self.xcode_project.write_build_server(
                self.lsp_root,
                trace_path=bsp_trace_path,
            )
            root = self.lsp_root
            arguments += ["--default-workspace-type", "buildServer"]
        self.stderr_handle = self.stderr_path.open("ab")
        self.process = subprocess.Popen(
            ["/usr/bin/xcrun", *arguments],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.stderr_handle,
            bufsize=0,
            cwd=root,
        )
        initialize_params = {
            "processId": os.getpid(),
            "clientInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "rootUri": root.as_uri(),
            "capabilities": {
                "textDocument": {
                    "documentSymbol": {"hierarchicalDocumentSymbolSupport": True},
                    "definition": {"linkSupport": True},
                    "implementation": {"linkSupport": True},
                    "hover": {"contentFormat": ["markdown", "plaintext"]},
                    "diagnostic": {
                        "dynamicRegistration": False,
                        "relatedDocumentSupport": False,
                    },
                    "publishDiagnostics": {},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "symbol": {"dynamicRegistration": False},
                    "diagnostics": {"refreshSupport": False},
                },
            },
            "workspaceFolders": [
                {"uri": root.as_uri(), "name": self.workspace.name}
            ],
        }
        if initialization_options:
            initialize_params["initializationOptions"] = initialization_options
        initialize_result = self.request(
            "initialize",
            initialize_params,
        )
        self.server_capabilities = (initialize_result or {}).get("capabilities", {})
        self._trace({
            "event": "initialized",
            "pid": self.process.pid,
            "rootUri": root.as_uri(),
            "workspace": str(self.workspace),
            "serverCapabilities": self.server_capabilities,
        })
        self.notify("initialized", {})

    def close(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None
        if self.stderr_handle:
            self.stderr_handle.close()
        self.stderr_handle = None
        if self.lsp_root:
            shutil.rmtree(self.lsp_root, ignore_errors=True)
        self.lsp_root = None
        if self.xcode_project:
            self.xcode_project.release_index_lock()
        self.stderr_path = None
        self.trace_path = None
        self.buffer.clear()
        self.next_id = 1
        self.open_documents.clear()
        self.document_contents.clear()
        self.diagnostics.clear()
        self.server_capabilities = {}
        self.index_ready = False

    def restart(self):
        self.close()
        self.start()

    def request(self, method, params, timeout=60):
        if method != "initialize":
            self.start()
        request_id = self.next_id
        self.next_id += 1
        self._send({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        })
        deadline = time.monotonic() + timeout

        while True:
            message = self._read_message(deadline)
            if message is None:
                raise SourceKitError(f"SourceKit-LSP timeout: {method}")
            if "method" in message:
                self._handle_server_message(message)
                continue
            if message.get("id") != request_id:
                continue
            if "error" in message:
                error = message["error"]
                raise SourceKitRPCError(
                    method,
                    error.get("code", -1),
                    error.get("message", "unknown error"),
                )
            return message.get("result")

    def request_until_nonempty(self, method, params):
        if self.index_ready:
            return self.request(method, params)
        deadline = time.monotonic() + INDEX_TIMEOUT_SECONDS
        result = self.request(method, params)
        signature = self._result_signature(result)
        last_change = time.monotonic()
        while time.monotonic() < deadline:
            if result not in (None, []) and time.monotonic() - last_change >= INDEX_SETTLE_SECONDS:
                self.index_ready = True
                return result
            time.sleep(1)
            updated = self.request(method, params)
            updated_signature = self._result_signature(updated)
            if updated_signature != signature:
                result = updated
                signature = updated_signature
                last_change = time.monotonic()
        return result

    @staticmethod
    def _result_signature(result):
        return json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def notify(self, method, params):
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def prepare_document(self, file_path, refresh=False):
        self.start()
        path = resolve_swift_file(self.workspace, file_path)
        if self.xcode_project and str(path) not in self.xcode_project.source_paths:
            # A path component that names a shared scheme (Projects/TalkMediaKit/...)
            # is merged into this session instead of opening another sourcekit-lsp.
            scheme = self.xcode_project.guess_scheme(path)
            if scheme:
                self.xcode_project.extra_schemes.append(scheme)
                self.restart()
        if self.xcode_project and str(path) not in self.xcode_project.source_paths:
            raise SourceKitError(
                f"Xcode BSP build settings do not include {path.relative_to(self.workspace)}. "
                f"Add its scheme to {SCHEME_ENV} or pass xcode_scheme."
            )
        uri = path.as_uri()
        text = path.read_text(encoding="utf-8")
        version = self.open_documents.get(uri)

        if version is None:
            self.notify("textDocument/didOpen", {
                "textDocument": {
                    "uri": uri,
                    "languageId": "swift",
                    "version": 1,
                    "text": text,
                }
            })
            self.open_documents[uri] = 1
            self.document_contents[uri] = text
        elif refresh and self.document_contents.get(uri) != text:
            version += 1
            self.notify("textDocument/didChange", {
                "textDocument": {"uri": uri, "version": version},
                "contentChanges": [{"text": text}],
            })
            self.open_documents[uri] = version
            self.document_contents[uri] = text
        return uri

    def request_document(self, method, file_path, params=None, until_nonempty=False):
        for attempt in range(2):
            uri = self.prepare_document(file_path, refresh=True)
            request_params = dict(params or {})
            request_params["textDocument"] = {"uri": uri}
            try:
                if until_nonempty:
                    return self.request_until_nonempty(method, request_params)
                return self.request(method, request_params)
            except SourceKitError as error:
                if attempt or not self._is_recoverable_document_error(error):
                    raise
                self._trace({
                    "event": "restart",
                    "reason": str(error),
                    "document": uri,
                })
                self.restart()

    @staticmethod
    def _is_recoverable_document_error(error):
        if isinstance(error, SourceKitRPCError):
            return error.code == -32001
        message = str(error).lower()
        return "process exited" in message or "sourcekit-lsp is unavailable" in message

    def diagnostics_for_document(self, file_path):
        uri = self.prepare_document(file_path, refresh=True)
        expected_version = self.open_documents.get(uri)
        diagnostic_provider = self.server_capabilities.get("diagnosticProvider")
        if diagnostic_provider is not None and diagnostic_provider is not False:
            result = self.request_document(
                "textDocument/diagnostic",
                file_path,
            )
            if not result:
                return []
            if result.get("kind") == "unchanged":
                return self.diagnostics.get(uri, {}).get("items", [])
            items = result.get("items", [])
            self.diagnostics[uri] = {"version": expected_version, "items": items}
            return items
        published = self.diagnostics.get(uri)
        if published and self._diagnostics_version_matches(published, expected_version):
            return published["items"]
        return self.wait_for_diagnostics(uri, expected_version)

    def wait_for_diagnostics(
        self,
        uri,
        expected_version,
        timeout=DIAGNOSTICS_TIMEOUT_SECONDS,
    ):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            published = self.diagnostics.get(uri)
            if published and self._diagnostics_version_matches(published, expected_version):
                return published["items"]
            message = self._read_message(deadline)
            if message is None:
                break
            self._handle_server_message(message)
        raise SourceKitError("SourceKit-LSP timeout: textDocument/publishDiagnostics")

    @staticmethod
    def _diagnostics_version_matches(published, expected_version):
        version = published.get("version")
        return version is None or expected_version is None or version >= expected_version

    def _trace(self, payload):
        append_trace(self.trace_path, payload)

    def _send(self, message):
        if not self.process or self.process.poll() is not None or not self.process.stdin:
            raise SourceKitError("Xcode toolchain sourcekit-lsp is unavailable")
        body = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode()
        frame = f"Content-Length: {len(body)}\r\n\r\n".encode() + body
        try:
            self.process.stdin.write(frame)
            self.process.stdin.flush()
        except (BrokenPipeError, OSError) as error:
            raise SourceKitError("Xcode toolchain sourcekit-lsp is unavailable") from error

    def _read_message(self, deadline):
        separator = b"\r\n\r\n"
        while True:
            header_end = self.buffer.find(separator)
            if header_end >= 0:
                header = self.buffer[:header_end].decode("ascii", errors="replace")
                content_length = None
                for line in header.split("\r\n"):
                    name, _, value = line.partition(":")
                    if name.lower() == "content-length":
                        content_length = int(value.strip())
                        break
                if content_length is None:
                    raise SourceKitError("Malformed SourceKit-LSP frame")
                body_start = header_end + len(separator)
                body_end = body_start + content_length
                if len(self.buffer) >= body_end:
                    body = bytes(self.buffer[body_start:body_end])
                    del self.buffer[:body_end]
                    return json.loads(body)

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            if not self.process or not self.process.stdout:
                raise SourceKitError("SourceKit-LSP process is unavailable")
            ready, _, _ = select.select([self.process.stdout.fileno()], [], [], remaining)
            if not ready:
                return None
            chunk = os.read(self.process.stdout.fileno(), 65536)
            if not chunk:
                raise SourceKitError("SourceKit-LSP process exited")
            self.buffer.extend(chunk)

    def _handle_server_message(self, message):
        method = message.get("method")
        if method == "textDocument/publishDiagnostics":
            params = message.get("params", {})
            self.diagnostics[params.get("uri", "")] = {
                "version": params.get("version"),
                "items": params.get("diagnostics", []),
            }
        if "id" in message:
            result = [] if method == "workspace/configuration" else None
            self._send({"jsonrpc": "2.0", "id": message["id"], "result": result})


class XcodeProject:
    def __init__(self, workspace, container, scheme=None):
        self.workspace = Path(workspace).resolve()
        self.container = Path(container).resolve()
        self.scheme = scheme
        self.source_paths = set()
        self.index_lock = None
        self.extra_schemes = []
        self._schemes = None

    @classmethod
    def detect(cls, workspace, scheme=None):
        workspace = Path(workspace).resolve()
        containers = sorted(workspace.glob("*.xcworkspace"))
        if not containers:
            containers = sorted(workspace.glob("*.xcodeproj"))
        if not containers:
            return None
        if len(containers) > 1:
            names = ", ".join(path.name for path in containers)
            raise SourceKitError(
                f"Multiple Xcode projects detected ({names}); pass a workspace_path "
                "containing exactly one .xcworkspace or .xcodeproj."
            )
        return cls(workspace, containers[0], scheme)

    @property
    def xcode_arguments(self):
        option = "-workspace" if self.container.suffix == ".xcworkspace" else "-project"
        return [option, str(self.container)]

    def write_build_server(self, root, trace_path=None):
        root = Path(root)
        config = self._configuration(root)
        if trace_path:
            config["tracePath"] = str(trace_path)
        config_path = root / "bsp-config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        build_server = {
            "name": SERVER_NAME,
            "version": SERVER_VERSION,
            "bspVersion": "2.2.0",
            "languages": ["swift"],
            "argv": [sys.executable, str(Path(__file__).resolve()), "--bsp", str(config_path)],
        }
        (root / "buildServer.json").write_text(
            json.dumps(build_server), encoding="utf-8"
        )

    def _configuration(self, root):
        schemes = self.selected_schemes()
        scheme = ", ".join(schemes)
        settings = {}
        for name in schemes:
            settings.update(self._index_settings(name))
        if not settings:
            raise SourceKitError(f"No index build settings found for Xcode scheme {scheme}")

        targets = []
        index_store = None
        for target_name, documents in settings.items():
            options = {}
            output_paths = {}
            for source, values in documents.items():
                path = Path(source).resolve()
                arguments = values.get("swiftASTCommandArguments")
                if path.suffix != ".swift" or not path.is_file() or not arguments:
                    continue
                options[str(path)] = arguments
                # Unit names hash the -index-unit-output-path Xcode passed, which is exactly
                # this project-relative outputFilePath (verified with libIndexStore).
                if values.get("outputFilePath"):
                    output_paths[str(path)] = values["outputFilePath"]
                if "-index-store-path" in arguments:
                    index_store = Path(arguments[arguments.index("-index-store-path") + 1])
                else:
                    # ponytail: one DerivedData per workspace, so infer once and reuse;
                    # per-file inference walked ~12M Path objects (130 s on 3.8k files).
                    if index_store is None:
                        index_store = self._index_store_from_arguments(arguments)
                    if index_store:
                        arguments.extend(["-index-store-path", str(index_store)])
            if not options:
                continue
            target_id = f"swift-intelligence://xcode/{quote(target_name, safe='')}"
            targets.append({
                "id": target_id,
                "metadata": {
                    "id": {"uri": target_id},
                    "displayName": target_name,
                    "baseDirectory": self.workspace.as_uri(),
                    "tags": ["test" if target_name.endswith("Tests") else "application"],
                    "languageIds": ["swift"],
                    "dependencies": [],
                    "capabilities": {"canCompile": False},
                },
                "sources": sorted(options),
                "options": options,
                "outputPaths": output_paths,
            })
        if not targets:
            raise SourceKitError(
                f"No Swift index settings found for Xcode scheme {scheme}. "
                "Build the scheme once and retry."
            )
        if not index_store or not (index_store / "v5").is_dir():
            raise SourceKitError(
                f"Xcode index store is missing for scheme {scheme}. "
                f"Build it first: xcodebuild {' '.join(self.xcode_arguments)} "
                f"-scheme {shlex.quote(scheme)} build-for-testing"
            )
        self.source_paths = {
            source for target in targets for source in target["sources"]
        }

        return {
            "workspace": str(self.workspace),
            "indexStorePath": str(index_store),
            "indexDatabasePath": str(self._index_database(root, index_store)),
            "targets": targets,
        }

    def _index_database(self, root, index_store):
        # IndexStoreDB is incremental when it reopens the same database, so keep one per
        # index store across server restarts. flock keeps two live servers off the same
        # LMDB; the loser uses a throwaway database under its temp root as before.
        key = hashlib.sha1(str(index_store).encode()).hexdigest()[:12]
        shared = INDEX_SETTINGS_CACHE / f"IndexDatabase-{key}"
        shared.mkdir(parents=True, exist_ok=True)
        self.release_index_lock()
        self.index_lock = (INDEX_SETTINGS_CACHE / f"IndexDatabase-{key}.lock").open("w")
        try:
            fcntl.flock(self.index_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return shared
        except OSError:
            self.release_index_lock()
            return root / "IndexDatabase"

    def release_index_lock(self):
        if self.index_lock:
            self.index_lock.close()
        self.index_lock = None

    def schemes(self):
        if self._schemes is None:
            container_kind = "workspace" if self.container.suffix == ".xcworkspace" else "project"
            schemes = self._xcode_json("-list").get(container_kind, {}).get("schemes", [])
            if not schemes:
                raise SourceKitError(f"No shared scheme found in {self.container.name}")
            self._schemes = schemes
        return self._schemes

    def guess_scheme(self, path):
        selected = set(self.selected_schemes())
        for part in Path(path).relative_to(self.workspace).parts[:-1]:
            if part in self.schemes() and part not in selected:
                return part
        return None

    def selected_schemes(self):
        schemes = self.schemes()
        selected = split_schemes(self.scheme or os.environ.get(SCHEME_ENV))
        if not selected and self.container.stem in schemes:
            selected = [self.container.stem]
        if not selected:
            raise SourceKitError(
                f"Xcode scheme selection required for {self.container.name}. "
                f"Available: {', '.join(schemes)}. Retry with xcode_scheme "
                "(comma-separated for several)."
            )
        for scheme in selected:
            if scheme not in schemes:
                source = "xcode_scheme" if self.scheme else SCHEME_ENV
                raise SourceKitError(
                    f"Xcode scheme {scheme!r} from {source} is not shared by "
                    f"{self.container.name}. Available: {', '.join(schemes)}"
                )
        return selected + [s for s in self.extra_schemes if s not in selected]

    def _index_settings(self, scheme):
        # -showBuildSettingsForIndex takes ~1 min per scheme on large workspaces, so the
        # raw result is cached on disk, keyed by the content hash of every project.pbxproj
        # under the workspace (a Tuist regeneration with identical output keeps the cache).
        key = hashlib.sha1(f"{self.container}\0{scheme}\0v2".encode()).hexdigest()
        cache = INDEX_SETTINGS_CACHE / f"{key}.json.gz"
        stamp = hashlib.sha1()
        for path in sorted(self.workspace.rglob("project.pbxproj")):
            stamp.update(path.read_bytes())
        stamp = stamp.hexdigest()
        cached = None
        if cache.is_file():
            with gzip.open(cache, "rt", encoding="utf-8") as handle:
                cached = json.load(handle)
        if isinstance(cached, dict) and cached.get("stamp") == stamp:
            settings = cached["settings"]
        else:
            arguments = ["-scheme", scheme, "-configuration", "Debug"]
            try:
                settings = self._xcode_json(*arguments, "test", "-showBuildSettingsForIndex")
            except SourceKitError:
                settings = self._xcode_json(*arguments, "-showBuildSettingsForIndex")
            # Keep only what _configuration reads; the raw payload is >1 GB for big apps.
            settings = {
                target: {
                    source: {
                        "swiftASTCommandArguments": values["swiftASTCommandArguments"],
                        "outputFilePath": values.get("outputFilePath"),
                    }
                    for source, values in documents.items()
                    if source.endswith(".swift") and values.get("swiftASTCommandArguments")
                }
                for target, documents in settings.items()
            }
            cache.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(cache, "wt", encoding="utf-8") as handle:
                json.dump({"stamp": stamp, "settings": settings}, handle)
        return self._retarget_configuration(settings, scheme)

    def _retarget_configuration(self, settings, scheme):
        # -showBuildSettingsForIndex ignores -configuration and emits paths for one
        # fixed configuration. Prefer the explicit environment override, then the
        # selected scheme's TestAction configuration, so imports resolve to products
        # produced by build-for-testing.
        wanted = os.environ.get(CONFIGURATION_ENV) or self._scheme_configuration(scheme)
        if not wanted:
            return settings
        # "<config>-<sdk>" segments only; "Objects-normal" and friends must stay untouched.
        pattern = re.compile(
            r"(/(?:Build/Products|\w+\.build)/)([^/]+?)(-(?:[a-z]+os|[a-z]+simulator|macosx))(?=/|$)"
        )
        sdk = self._built_sdk_suffix(settings, pattern, wanted)

        def retarget(text):
            return pattern.sub(lambda m: m.group(1) + wanted + (sdk or m.group(3)), text)

        for documents in settings.values():
            for values in documents.values():
                arguments = values.get("swiftASTCommandArguments")
                if arguments:
                    values["swiftASTCommandArguments"] = [retarget(arg) for arg in arguments]
                if values.get("outputFilePath"):
                    values["outputFilePath"] = retarget(values["outputFilePath"])
        return settings

    @staticmethod
    def _built_sdk_suffix(settings, pattern, configuration):
        # -showBuildSettingsForIndex may pick a device destination while the index store
        # was built for the simulator. Use the sdk suffix whose products directory exists.
        for documents in settings.values():
            for values in documents.values():
                for argument in values.get("swiftASTCommandArguments") or []:
                    match = pattern.search(argument)
                    if match and match.group(1) == "/Build/Products/":
                        products = Path(argument[: match.start()]) / "Build" / "Products"
                        for suffix in ("-iphonesimulator", match.group(3)):
                            if (products / f"{configuration}{suffix}").is_dir():
                                return suffix
                        return None
        return None

    def _scheme_configuration(self, scheme):
        for scheme_path in self.workspace.rglob(f"{scheme}.xcscheme"):
            try:
                root = ElementTree.parse(scheme_path).getroot()
            except (ElementTree.ParseError, OSError):
                continue
            test_action = root.find("TestAction")
            if test_action is not None:
                configuration = test_action.get("buildConfiguration")
                if configuration:
                    return configuration
        return None

    @staticmethod
    def _index_store_from_arguments(arguments):
        for argument in arguments:
            if not isinstance(argument, str):
                continue
            value = argument[2:] if argument.startswith(("-I/", "-F/", "-L/")) else argument
            path = Path(value)
            if not path.is_absolute():
                continue
            for parent in (path, *path.parents):
                if parent.name != "Build":
                    continue
                candidate = parent.parent / "Index.noindex" / "DataStore"
                if (candidate / "v5").is_dir():
                    return candidate
                break
        return None

    def _xcode_json(self, *arguments):
        command = [
            "/usr/bin/xcodebuild",
            *self.xcode_arguments,
            *arguments,
            "-json",
        ]
        result = subprocess.run(
            command,
            cwd=self.workspace,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode != 0:
            detail = result.stderr.strip().splitlines()
            message = detail[-1] if detail else "unknown xcodebuild error"
            raise SourceKitError(f"Failed to read {self.container.name}: {message}")
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise SourceKitError(
                f"xcodebuild returned invalid JSON for {self.container.name}"
            ) from error

class WorkspacePool:
    def __init__(self):
        self.sessions = {}

    def session_for_file(self, workspace_path, file_path, xcode_scheme=None):
        workspace = resolve_workspace(workspace_path)
        source = resolve_swift_file(workspace, file_path)
        current = source.parent
        package_root = None
        while True:
            if (current / "Package.swift").is_file():
                package_root = current
                break
            if current == workspace:
                break
            current = current.parent
        root = package_root or workspace
        return self.session(root, xcode_scheme), str(source)

    def session(self, workspace, xcode_scheme=None):
        root = str(Path(workspace).resolve())
        is_package = (Path(root) / "Package.swift").is_file()
        scheme = None if is_package else xcode_scheme or os.environ.get(SCHEME_ENV)
        key = (root, scheme, None if is_package else os.environ.get(CONFIGURATION_ENV))
        if key not in self.sessions:
            project = None if is_package else XcodeProject.detect(root, xcode_scheme)
            self.sessions[key] = SourceKitSession(root, project)
        return self.sessions[key]

    def close(self):
        for session in self.sessions.values():
            session.close()


POOL = WorkspacePool()
atexit.register(POOL.close)


def resolve_workspace(path):
    workspace = Path(path).expanduser().resolve()
    if not workspace.is_dir():
        raise ValueError(f"workspace_path is not a directory: {path}")
    return workspace


def resolve_swift_file(workspace, file_path):
    workspace = Path(workspace).resolve()
    candidate = Path(file_path).expanduser()
    if not candidate.is_absolute():
        candidate = workspace / candidate
    candidate = candidate.resolve()
    try:
        candidate.relative_to(workspace)
    except ValueError as error:
        raise ValueError(f"file_path must be inside workspace_path: {file_path}") from error
    if candidate.suffix.lower() != ".swift" or not candidate.is_file():
        raise ValueError(f"file_path is not a readable Swift file: {file_path}")
    return candidate


def position_params(uri, arguments):
    line = arguments.get("line")
    character = arguments.get("character")
    if not isinstance(line, int) or line < 0:
        raise ValueError("line must be a non-negative integer")
    if not isinstance(character, int) or character < 0:
        raise ValueError("character must be a non-negative integer")
    return {
        "textDocument": {"uri": uri},
        "position": {"line": line, "character": character},
    }


def split_schemes(value):
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def rank_workspace_symbols(symbols, query):
    query_lower = query.lower()
    unique = {}
    for symbol in symbols or []:
        location = symbol.get("location", {})
        start = location.get("range", {}).get("start", {})
        key = (
            symbol.get("name"),
            symbol.get("kind"),
            location.get("uri"),
            start.get("line"),
            start.get("character"),
        )
        unique.setdefault(key, symbol)

    def score(symbol):
        name = symbol.get("name", "")
        name_lower = name.lower()
        if name == query:
            match_rank = 0
        elif name_lower == query_lower:
            match_rank = 1
        elif name_lower.startswith(query_lower):
            match_rank = 2
        elif query_lower in name_lower:
            match_rank = 3
        else:
            match_rank = 4
        location = symbol.get("location", {})
        start = location.get("range", {}).get("start", {})
        return (
            match_rank,
            len(name),
            name_lower,
            location.get("uri", ""),
            start.get("line", -1),
            start.get("character", -1),
        )

    return sorted(unique.values(), key=score)[:WORKSPACE_SYMBOL_LIMIT]


def tool_schema(properties, required, include_scheme=True):
    base = {
        "workspace_path": {
            "type": "string",
            "description": "Absolute repository or workspace root path",
        }
    }
    if include_scheme:
        base["xcode_scheme"] = {
            "type": "string",
            "minLength": 1,
            "description": "Shared Xcode scheme(s) selected by the user, comma-separated to merge several; ignored for SwiftPM",
        }
    base.update(properties)
    return {
        "type": "object",
        "properties": base,
        "required": ["workspace_path", *required],
        "additionalProperties": False,
    }


FILE_PROPERTY = {
    "file_path": {
        "type": "string",
        "description": "Swift file path relative to workspace_path, or an absolute path inside it",
    }
}
POSITION_PROPERTIES = {
    **FILE_PROPERTY,
    "line": {"type": "integer", "minimum": 0, "description": "Zero-based line"},
    "character": {
        "type": "integer",
        "minimum": 0,
        "description": "Zero-based UTF-16 character offset",
    },
}


def descriptor(name, description, schema):
    return {
        "name": name,
        "description": description,
        "inputSchema": schema,
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    }


TOOLS = [
    descriptor(
        "swift_xcode_schemes",
        "List shared Xcode schemes and report whether the user must select one.",
        tool_schema({}, [], include_scheme=False),
    ),
    descriptor(
        "swift_symbols",
        "List declarations in one Swift file using SourceKit-LSP.",
        tool_schema(FILE_PROPERTY, ["file_path"]),
    ),
    descriptor(
        "swift_workspace_symbols",
        "Search indexed Swift symbols by name. Requires current build settings and index.",
        tool_schema({"query": {"type": "string"}}, ["query"]),
    ),
    descriptor(
        "swift_definition",
        "Find the compiler-resolved definition at a Swift source position.",
        tool_schema(POSITION_PROPERTIES, ["file_path", "line", "character"]),
    ),
    descriptor(
        "swift_references",
        "Find semantic references to the Swift symbol at a source position.",
        tool_schema({
            **POSITION_PROPERTIES,
            "include_declaration": {"type": "boolean", "default": True},
        }, ["file_path", "line", "character"]),
    ),
    descriptor(
        "swift_implementations",
        "Find implementations of a Swift protocol requirement or method.",
        tool_schema(POSITION_PROPERTIES, ["file_path", "line", "character"]),
    ),
    descriptor(
        "swift_hover",
        "Return compiler-resolved Swift type and documentation at a source position.",
        tool_schema(POSITION_PROPERTIES, ["file_path", "line", "character"]),
    ),
    descriptor(
        "swift_diagnostics",
        "Return SourceKit-LSP compiler diagnostics for one Swift file.",
        tool_schema(FILE_PROPERTY, ["file_path"]),
    ),
]


def call_tool(name, arguments):
    workspace_path = arguments.get("workspace_path")
    if not isinstance(workspace_path, str):
        raise ValueError("workspace_path is required")

    xcode_scheme = arguments.get("xcode_scheme")
    if xcode_scheme is not None and (
        not isinstance(xcode_scheme, str) or not xcode_scheme.strip()
    ):
        raise ValueError("xcode_scheme must be a non-empty string")

    if name == "swift_xcode_schemes":
        project = XcodeProject.detect(resolve_workspace(workspace_path))
        if project is None:
            raise SourceKitError("No .xcworkspace or .xcodeproj found in workspace_path")
        schemes = project.schemes()
        selected = split_schemes(os.environ.get(SCHEME_ENV)) or (
            [project.container.stem] if project.container.stem in schemes else []
        )
        for scheme in selected:
            if scheme not in schemes:
                raise SourceKitError(
                    f"Xcode scheme {scheme!r} from {SCHEME_ENV} is not shared by "
                    f"{project.container.name}. Available: {', '.join(schemes)}"
                )
        return {
            "container": project.container.name,
            "schemes": schemes,
            "selected": selected,
            "selectionRequired": not selected,
        }

    if name == "swift_workspace_symbols":
        query = arguments.get("query")
        if not isinstance(query, str):
            raise ValueError("query is required")
        session = POOL.session(resolve_workspace(workspace_path), xcode_scheme)
        session.start()
        symbols = session.request_until_nonempty("workspace/symbol", {"query": query})
        return rank_workspace_symbols(symbols, query)

    file_path = arguments.get("file_path")
    if not isinstance(file_path, str):
        raise ValueError("file_path is required")
    session, resolved_file = POOL.session_for_file(
        workspace_path, file_path, xcode_scheme
    )

    if name == "swift_symbols":
        return session.request_document(
            "textDocument/documentSymbol",
            resolved_file,
        )
    if name == "swift_diagnostics":
        return session.diagnostics_for_document(resolved_file)

    uri = Path(resolved_file).as_uri()
    params = position_params(uri, arguments)
    if name == "swift_definition":
        return session.request_document(
            "textDocument/definition",
            resolved_file,
            params,
        )
    if name == "swift_references":
        params["context"] = {
            "includeDeclaration": arguments.get("include_declaration", True)
        }
        return session.request_document(
            "textDocument/references",
            resolved_file,
            params,
            until_nonempty=True,
        )
    if name == "swift_implementations":
        return session.request_document(
            "textDocument/implementation",
            resolved_file,
            params,
            until_nonempty=True,
        )
    if name == "swift_hover":
        return session.request_document(
            "textDocument/hover",
            resolved_file,
            params,
        )
    raise ValueError(f"Unknown tool: {name}")


def response(request_id, result=None, error=None):
    payload = {"jsonrpc": "2.0", "id": request_id}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def handle(request):
    request_id = request.get("id")
    method = request.get("method")
    if request_id is None:
        return
    if method == "initialize":
        requested_version = request.get("params", {}).get("protocolVersion", "2025-06-18")
        response(request_id, {
            "protocolVersion": requested_version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })
    elif method == "ping":
        response(request_id, {})
    elif method == "tools/list":
        response(request_id, {"tools": TOOLS})
    elif method == "tools/call":
        params = request.get("params", {})
        try:
            result = call_tool(params.get("name"), params.get("arguments") or {})
            response(request_id, {
                "content": [{
                    "type": "text",
                    "text": json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
                }]
            })
        except Exception as error:
            response(request_id, {
                "content": [{"type": "text", "text": str(error)}],
                "isError": True,
            })
    else:
        response(request_id, error={"code": -32601, "message": f"Method not found: {method}"})


def read_bsp_message(stream):
    headers = {}
    while True:
        line = stream.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        name, separator, value = line.decode("ascii").partition(":")
        if not separator:
            raise SourceKitError("Malformed BSP header")
        headers[name.lower()] = value.strip()
    length = headers.get("content-length")
    if length is None:
        raise SourceKitError("BSP Content-Length header is missing")
    body = stream.read(int(length))
    if len(body) != int(length):
        raise SourceKitError("Incomplete BSP message")
    return json.loads(body)


def write_bsp_message(stream, message):
    body = json.dumps(message, separators=(",", ":")).encode()
    stream.write(f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
    stream.flush()


def run_bsp(config_path):
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    targets = {target["id"]: target for target in config["targets"]}
    explicit_units = bool(os.environ.get(EXPLICIT_UNITS_ENV)) and all(
        t.get("outputPaths") for t in targets.values()
    )
    workspace_uri = Path(config["workspace"]).as_uri()
    trace_path = config.get("tracePath")

    while True:
        message = read_bsp_message(sys.stdin.buffer)
        if message is None:
            return
        method = message.get("method")
        request_id = message.get("id")
        params = message.get("params", {})
        append_trace(trace_path, {
            "event": "bsp-request",
            "method": method,
            "id": request_id,
            "target": params.get("target", {}).get("uri"),
            "document": params.get("textDocument", {}).get("uri"),
        })

        if method == "build/exit":
            return
        if request_id is None:
            continue
        if method == "build/initialize":
            result = {
                "displayName": SERVER_NAME,
                "version": SERVER_VERSION,
                "bspVersion": "2.2.0",
                "capabilities": {"buildTargetChangedProvider": False},
                "dataKind": "sourceKit",
                "data": {
                    "indexDatabasePath": config["indexDatabasePath"],
                    "indexStorePath": config["indexStorePath"],
                    "sourceKitOptionsProvider": True,
                    "outputPathsProvider": explicit_units,
                },
            }
        elif method == "workspace/buildTargets":
            result = {"targets": [target["metadata"] for target in targets.values()]}
        elif method == "buildTarget/sources":
            result = {"items": []}
            for identifier in message.get("params", {}).get("targets", []):
                target = targets.get(identifier.get("uri"))
                if not target:
                    continue
                result["items"].append({
                    "target": identifier,
                    "sources": [
                        {
                            "uri": Path(path).as_uri(),
                            "kind": 1,
                            "generated": False,
                            "dataKind": "sourceKit",
                            "data": {"outputPath": target["outputPaths"][path]},
                        } if explicit_units and path in target.get("outputPaths", {}) else
                        {"uri": Path(path).as_uri(), "kind": 1, "generated": False}
                        for path in target["sources"]
                    ],
                    "roots": [workspace_uri],
                })
        elif method in (
            "sourcekit/textDocument/sourceKitOptions",
            "textDocument/sourceKitOptions",
        ):
            requested_target = params.get("target", {}).get("uri")
            target = targets.get(requested_target)
            document_uri = params.get("textDocument", {}).get("uri", "")
            document_path = Path(unquote(urlparse(document_uri).path)).resolve()
            document = str(document_path)
            if not target or document not in target["sources"]:
                matching_targets = [
                    candidate
                    for candidate in targets.values()
                    if document in candidate["sources"]
                ]
                target = matching_targets[0] if len(matching_targets) == 1 else None
            if not target:
                result = None
            else:
                result = {
                    "compilerArguments": target["options"][document],
                    "workingDirectory": config["workspace"],
                }
        elif method in (
            "sourcekit/workspace/waitForBuildSystemUpdates",
            "workspace/waitForBuildSystemUpdates",
        ):
            result = {}
        elif method == "build/shutdown":
            result = None
        else:
            write_bsp_message(sys.stdout.buffer, {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            })
            continue
        summary = {"event": "bsp-response", "method": method, "id": request_id}
        if method in (
            "sourcekit/textDocument/sourceKitOptions",
            "textDocument/sourceKitOptions",
        ):
            summary.update({
                "found": result is not None,
                "resolvedTarget": target["id"] if target else None,
                "compilerArgumentCount": len(result.get("compilerArguments", [])) if result else 0,
            })
        elif method == "workspace/buildTargets":
            summary["targetCount"] = len(result["targets"])
        elif method == "buildTarget/sources":
            summary["sourceCounts"] = [len(item["sources"]) for item in result["items"]]
        append_trace(trace_path, summary)
        write_bsp_message(
            sys.stdout.buffer,
            {"jsonrpc": "2.0", "id": request_id, "result": result},
        )


def main():
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            handle(json.loads(line))
        except Exception as error:
            response(None, error={"code": -32603, "message": str(error)})


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--bsp":
        run_bsp(sys.argv[2])
    else:
        main()
