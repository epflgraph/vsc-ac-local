from pathlib import Path
import sys

path = Path(sys.argv[1])
s = path.read_text()

MARKER = "// [CONTINUE-PATCH:LOGGING-V3] applied"
AST_MARKER = "// [CONTINUE-PATCH:LOGGING-V3:AST-SPAM] applied"
TRANSPORT_MARKER = "// [CONTINUE-PATCH:LOGGING-V3:TRANSPORT] applied"


def replace_once(old, new, label):
    global s

    count = s.count(old)

    if count != 1:
        raise RuntimeError(
            f"{label}: expected exactly 1 anchor, found {count}"
        )

    s = s.replace(old, new, 1)


if MARKER in s:
    print("ℹ️ Continue logging v3 patch already applied; nothing to do.")
    raise SystemExit(0)


# ===========================================================================
# 1. OpenAI /completions request + response summary
# ===========================================================================

old = '''        const response = await this.fetch(this._getEndpoint("completions"), {
          method: "POST",
          headers: this._getHeaders(),
          body: JSON.stringify({
            ...args2,
            stream: true,
            ...this.extraBodyProperties()
          }),
          signal
        });
        for await (const value2 of streamSse(response)) {
          if (value2.choices?.[0]?.text && value2.finish_reason !== "eos") {
            yield value2.choices[0].text;
          }
        }'''

new = '''        console.log("📤 [Continue LLM → API] /completions request", {
          endpoint: this._getEndpoint("completions"),
          model: options.model,
          raw: options.raw,
          promptLength:
            typeof args2.prompt === "string"
              ? args2.prompt.length
              : null,
          maxTokens: args2.max_tokens,
          temperature: args2.temperature
        });

        const response = await this.fetch(this._getEndpoint("completions"), {
          method: "POST",
          headers: this._getHeaders(),
          body: JSON.stringify({
            ...args2,
            stream: true,
            ...this.extraBodyProperties()
          }),
          signal
        });

        console.log("📡 [Continue LLM ← API] /completions response", {
          status: response.status,
          contentType: response.headers?.get?.("content-type")
        });

        for await (const value2 of streamSse(response)) {
          if (value2.choices?.[0]?.text && value2.finish_reason !== "eos") {
            yield value2.choices[0].text;
          }
        }'''

replace_once(
    old,
    new,
    "/completions request/response diagnostics"
)


# ===========================================================================
# 2. OpenAI /chat/completions request + response summary
# ===========================================================================

old = '''        const body4 = this._convertArgs(options, messages);
        const response = await this.fetch(this._getEndpoint("chat/completions"), {
          method: "POST",
          headers: this._getHeaders(),
          body: JSON.stringify({
            ...body4,
            ...this.extraBodyProperties()
          }),
          signal
        });'''

new = '''        const body4 = this._convertArgs(options, messages);

        console.log("📤 [Continue LLM → API] /chat/completions request", {
          endpoint: this._getEndpoint("chat/completions"),
          model: options.model,
          raw: options.raw,
          messageCount: messages?.length ?? 0,
          maxTokens: body4.max_tokens,
          temperature: body4.temperature
        });

        const response = await this.fetch(this._getEndpoint("chat/completions"), {
          method: "POST",
          headers: this._getHeaders(),
          body: JSON.stringify({
            ...body4,
            ...this.extraBodyProperties()
          }),
          signal
        });

        console.log("📡 [Continue LLM ← API] /chat/completions response", {
          status: response.status,
          contentType: response.headers?.get?.("content-type")
        });'''

replace_once(
    old,
    new,
    "/chat/completions request/response diagnostics"
)


# ===========================================================================
# 3. CompletionStreamer timing
# ===========================================================================

old = '''      async *streamCompletionWithFilters(token, llm, prefix, suffix, prompt2, multiline, completionOptions, helper) {
        const fullStop = () => this.generatorReuseManager.currentGenerator?.cancel();
        const generator = this.generatorReuseManager.getGenerator('''

new = '''      async *streamCompletionWithFilters(token, llm, prefix, suffix, prompt2, multiline, completionOptions, helper) {
        const fullStop = () => this.generatorReuseManager.currentGenerator?.cancel();

        let requestStartedAt = Date.now();
        let firstChunkSeen = false;
        let freshRequestStarted = false;

        const generator = this.generatorReuseManager.getGenerator('''

replace_once(
    old,
    new,
    "CompletionStreamer timing state"
)


old = '''          prefix,
          (abortSignal) => {
            const generator2 = llm.supportsFim() ? llm.streamFim(prefix, suffix, abortSignal, completionOptions) : llm.streamComplete(prompt2, abortSignal, {'''

new = '''          prefix,
          (abortSignal) => {
            requestStartedAt = Date.now();
            firstChunkSeen = false;
            freshRequestStarted = true;

            console.log("🚀 [Continue AC → Model] Starting generation", {
              model: llm.model,
              provider: llm.underlyingProviderName,
              supportsFim: llm.supportsFim(),
              multiline,
              prefixLength: prefix?.length ?? 0,
              suffixLength: suffix?.length ?? 0,
              promptLength: prompt2?.length ?? 0
            });

            const generator2 = llm.supportsFim() ? llm.streamFim(prefix, suffix, abortSignal, completionOptions) : llm.streamComplete(prompt2, abortSignal, {'''

replace_once(
    old,
    new,
    "generation-start diagnostics"
)


# ===========================================================================
# 4. TTFT + cancellation
# ===========================================================================

old = '''        const generatorWithCancellation = async function* () {
          for await (const update2 of generator) {
            if (token.aborted) {
              return;
            }
            yield update2;
          }
        };'''

new = '''        const generatorWithCancellation = async function* () {
          for await (const update2 of generator) {
            const elapsed = Date.now() - requestStartedAt;

            if (!firstChunkSeen) {
              firstChunkSeen = true;

              console.log("⏱️ [Continue AC ← Model] First chunk / TTFT", {
                elapsedMs: elapsed,
                source: freshRequestStarted
                  ? "fresh request"
                  : "reused generator"
              });
            }

            if (token.aborted) {
              console.log(
                "🛑 [Continue AC] Stream discarded after cancellation",
                {
                  elapsedMs: elapsed
                }
              );

              return;
            }

            yield update2;
          }
        };'''

replace_once(
    old,
    new,
    "TTFT/cancellation diagnostics"
)


# ===========================================================================
# 5. Prompt/cursor summary
# ===========================================================================

old = '''          const { prompt: prompt2, prefix, suffix, completionOptions } = renderPromptWithTokenLimit({
            snippetPayload,
            workspaceDirs,
            helper,
            llm
          });
          let completion = "";'''

new = '''          const { prompt: prompt2, prefix, suffix, completionOptions } = renderPromptWithTokenLimit({
            snippetPayload,
            workspaceDirs,
            helper,
            llm
          });

          console.log("🧭 [Continue AC] Prompt/cursor state", {
            inputPos: input.pos,
            helperPos: helper.pos,
            model: llm.model,
            provider: llm.underlyingProviderName,
            prefixLength: prefix?.length ?? 0,
            suffixLength: suffix?.length ?? 0,
            promptLength: prompt2?.length ?? 0,
            prunedPrefixTail: helper.prunedPrefix?.slice(-120),
            prunedSuffixHead: helper.prunedSuffix?.slice(0, 120)
          });

          let completion = "";'''

replace_once(
    old,
    new,
    "prompt/cursor diagnostics"
)


# ===========================================================================
# 6. Raw completion
# ===========================================================================

old = '''            for await (const update2 of completionStream) {
              completion += update2;
            }
            if (token.aborted) {'''

new = '''            for await (const update2 of completionStream) {
              completion += update2;
            }

            console.log(
              "📝 [Continue AC] Raw model completion",
              JSON.stringify(completion)
            );

            if (token.aborted) {'''

replace_once(
    old,
    new,
    "raw completion diagnostics"
)


# ===========================================================================
# 7. Completion outcome
# ===========================================================================

old = '''          if (ideType === "jetbrains") {
            this.markDisplayed(input.completionId, outcome);
          }
          return outcome;'''

new = '''          if (ideType === "jetbrains") {
            this.markDisplayed(input.completionId, outcome);
          }

          console.log("✅ [Continue AC] Completion outcome ready", {
            completionId: outcome.completionId,
            model: outcome.modelName,
            provider: outcome.modelProvider,
            elapsedMs: outcome.time,
            cacheHit: outcome.cacheHit,
            completionLength: outcome.completion?.length ?? 0
          });

          return outcome;'''

replace_once(
    old,
    new,
    "completion outcome diagnostics"
)


# ===========================================================================
# 8. Provider entry + VS Code invocation
# ===========================================================================

old = '''      async provideInlineCompletionItems(document2, position, context2, token) {
        const enableTabAutocomplete = getStatusBarStatus() === 1 /* Enabled */;'''

new = '''      async provideInlineCompletionItems(document2, position, context2, token) {
        const providerStartedAt = Date.now();

        if (!globalThis.__continueAutocompleteDiagnosticsBannerShown) {
          globalThis.__continueAutocompleteDiagnosticsBannerShown = true;

          console.log("🟢 [Continue DIAG] Autocomplete diagnostics active", {
            logs:
              "provider timing, invocation, cancellation, model lifecycle, TTFT, final completion, display decision, transport abort"
          });
        }

        console.log("⏱️ [Continue AC] Provider entered", {
          documentVersion: document2.version,
          position
        });

        console.log("⌨️ [Continue AC] VS Code invocation", {
          document: document2.uri.toString(),
          documentVersion: document2.version,
          line: position.line,
          character: position.character,
          lineText:
            position.line >= 0 && position.line < document2.lineCount
              ? document2.lineAt(position.line).text
              : "<out-of-range>"
        });

        const enableTabAutocomplete = getStatusBarStatus() === 1 /* Enabled */;'''

replace_once(
    old,
    new,
    "provider-entry/invocation diagnostics"
)


# ===========================================================================
# 9. Debounce timing
# ===========================================================================

old = '''          if (!force) {
            if (await this.debouncer.delayAndShouldDebounce(options.debounceDelay)) {
              return void 0;
            }
          }
          if (llm.promptTemplates?.autocomplete) {'''

new = '''          if (!force) {
            const debounceStartedAt = Date.now();

            const shouldDebounce =
              await this.debouncer.delayAndShouldDebounce(
                options.debounceDelay
              );

            console.log("⏱️ [Continue AC] Debounce finished", {
              elapsedMs: Date.now() - debounceStartedAt,
              configuredDelayMs: options.debounceDelay,
              shouldDebounce
            });

            if (shouldDebounce) {
              return void 0;
            }
          }

          if (llm.promptTemplates?.autocomplete) {'''

replace_once(
    old,
    new,
    "debounce timing diagnostics"
)


# ===========================================================================
# 10. HelperVars.create timing
# ===========================================================================

old = '''          const helper = await HelperVars.create(
            input,
            options,
            llm.model,
            this.ide
          );
          if (await shouldPrefilter(helper, this.ide)) {'''

new = '''          const helperStartedAt = Date.now();

          const helper = await HelperVars.create(
            input,
            options,
            llm.model,
            this.ide
          );

          console.log("⏱️ [Continue AC] HelperVars.create finished", {
            elapsedMs: Date.now() - helperStartedAt
          });

          if (await shouldPrefilter(helper, this.ide)) {'''

replace_once(
    old,
    new,
    "HelperVars.create timing diagnostics"
)


# ===========================================================================
# 11. VS Code cancellation
# ===========================================================================

old = '''          token.onCancellationRequested(() => {
            abortController.abort();
            if (this.isNextEditActive) {'''

new = '''          token.onCancellationRequested(() => {
            console.log("🛑 [Continue AC] VS Code cancelled invocation", {
              completionId,
              document: document2.uri.toString(),
              documentVersion: document2.version,
              line: position.line,
              character: position.character
            });

            abortController.abort();

            if (this.isNextEditActive) {'''

replace_once(
    old,
    new,
    "VS Code cancellation diagnostics"
)


# ===========================================================================
# 12. Ghost-text decision + provider total time
# ===========================================================================

old = '''          const willDisplay = this.willDisplay(
            document2,
            selectedCompletionInfo,
            signal,
            outcome
          );
          if (!willDisplay) {'''

new = '''          const willDisplay = this.willDisplay(
            document2,
            selectedCompletionInfo,
            signal,
            outcome
          );

          console.log("⏱️ [Continue AC] Provider completed", {
            elapsedMs: Date.now() - providerStartedAt
          });

          console.log("👻 [Continue AC] Ghost-text display decision", {
            completionId,
            willDisplay,
            completionLength: outcome.completion?.length ?? 0
          });

          if (!willDisplay) {'''

replace_once(
    old,
    new,
    "ghost-text/provider timing diagnostics"
)


# ===========================================================================
# 13. Generator reuse diagnostics
# ===========================================================================

old = '''      shouldReuseExistingGenerator(prefix) {
        return !!this.currentGenerator && !!this.pendingGeneratorPrefix && (this.pendingGeneratorPrefix + this.pendingCompletion).startsWith(
          prefix
        ) && // for e.g. backspace
        this.pendingGeneratorPrefix?.length <= prefix?.length;
      }'''

new = '''      shouldReuseExistingGenerator(prefix) {
        const reuseCandidate =
          !!this.currentGenerator &&
          !!this.pendingGeneratorPrefix &&
          (this.pendingGeneratorPrefix + this.pendingCompletion).startsWith(
            prefix
          ) &&
          this.pendingGeneratorPrefix?.length <= prefix?.length;

        console.log("🔄 [Continue OP?] Generator reuse decision", {
          operationalPatchDetected: false,
          reuseCandidate,
          hasCurrentGenerator: !!this.currentGenerator,
          pendingPrefixLength: this.pendingGeneratorPrefix?.length ?? 0,
          pendingCompletionLength: this.pendingCompletion?.length ?? 0,
          incomingPrefixLength: prefix?.length ?? 0
        });

        return reuseCandidate;
      }'''

replace_once(
    old,
    new,
    "GeneratorReuseManager diagnostics"
)


# ===========================================================================
# 14. Transport lifecycle diagnostics
# ===========================================================================

function_start_anchor = '''      async *_legacystreamComplete(prompt2, signal, options) {'''
function_end_anchor = '''      async *_streamChat(messages, signal, options) {'''

if s.count(function_start_anchor) != 1:
    raise RuntimeError(
        "transport diagnostics: expected exactly one "
        "_legacystreamComplete() function"
    )

start = s.index(function_start_anchor)

try:
    end = s.index(function_end_anchor, start)
except ValueError:
    raise RuntimeError(
        "transport diagnostics: could not locate _streamChat() "
        "after _legacystreamComplete()"
    )

block = s[start:end]


entry_anchor = '''      async *_legacystreamComplete(prompt2, signal, options) {
        const args2 = this._convertArgs(options, []);'''

entry_replacement = '''      async *_legacystreamComplete(prompt2, signal, options) {
        const transportRequestId =
          `continue-completions-${Date.now()}-${Math.random().toString(16).slice(2)}`;

        console.log("🔌 [Continue TRANSPORT] /completions entered", {
          transportRequestId,
          hasSignal: !!signal,
          signalAborted: signal?.aborted ?? null,
          model: options?.model
        });

        const onTransportAbort = () => {
          console.log("💥 [Continue TRANSPORT] AbortSignal fired", {
            transportRequestId,
            signalAborted: signal?.aborted ?? null,
            signalReason: signal?.reason ?? null
          });
        };

        if (signal) {
          signal.addEventListener(
            "abort",
            onTransportAbort,
            { once: true }
          );
        }

        const args2 = this._convertArgs(options, []);'''

if entry_anchor not in block:
    raise RuntimeError(
        "transport diagnostics: could not find function-entry anchor"
    )

block = block.replace(
    entry_anchor,
    entry_replacement,
    1
)


fetch_anchor = '''        const response = await this.fetch(this._getEndpoint("completions"), {'''

fetch_replacement = '''        console.log("🌐 [Continue TRANSPORT] Starting fetch", {
          transportRequestId,
          signalAborted: signal?.aborted ?? null
        });

        const response = await this.fetch(this._getEndpoint("completions"), {'''

if fetch_anchor not in block:
    raise RuntimeError(
        "transport diagnostics: could not find fetch anchor"
    )

block = block.replace(
    fetch_anchor,
    fetch_replacement,
    1
)


fetch_end_anchor = '''          signal
        });'''

if block.count(fetch_end_anchor) != 1:
    raise RuntimeError(
        "transport diagnostics: expected exactly one fetch-end anchor, "
        f"found {block.count(fetch_end_anchor)}"
    )

fetch_end_replacement = '''          signal
        });

        console.log("📨 [Continue TRANSPORT] Fetch resolved", {
          transportRequestId,
          status: response.status,
          signalAborted: signal?.aborted ?? null,
          hasBody: !!response.body
        });'''

block = block.replace(
    fetch_end_anchor,
    fetch_end_replacement,
    1
)


loop_anchor = '''        for await (const value2 of streamSse(response)) {'''

if block.count(loop_anchor) != 1:
    raise RuntimeError(
        "transport diagnostics: expected exactly one streamSse loop, "
        f"found {block.count(loop_anchor)}"
    )

loop_replacement = '''        let transportSseChunks = 0;
        let transportSawStop = false;
        let transportLoopCompletedNormally = false;

        try {
          console.log("🌊 [Continue TRANSPORT] SSE loop starting", {
            transportRequestId,
            signalAborted: signal?.aborted ?? null
          });

          for await (const value2 of streamSse(response)) {
            transportSseChunks++;

            if (
              value2?.choices?.some?.(
                (choice) =>
                  choice?.finish_reason === "stop" ||
                  choice?.finish_reason === "eos"
              )
            ) {
              transportSawStop = true;
            }'''

block = block.replace(
    loop_anchor,
    loop_replacement,
    1
)


tail_anchor = '''        }
      }
'''

if not block.endswith(tail_anchor):
    raise RuntimeError(
        "transport diagnostics: unexpected _legacystreamComplete() tail"
    )

tail_replacement = '''          }

          transportLoopCompletedNormally = true;

        } catch (error) {

          console.log("💣 [Continue TRANSPORT] SSE loop threw", {
            transportRequestId,
            signalAborted: signal?.aborted ?? null,
            signalReason: signal?.reason ?? null,
            errorName: error?.name,
            errorMessage: error?.message
          });

          throw error;

        } finally {

          console.log("🏁 [Continue TRANSPORT] SSE loop exited", {
            transportRequestId,
            chunks: transportSseChunks,
            sawStop: transportSawStop,
            completedNormally: transportLoopCompletedNormally,
            signalAborted: signal?.aborted ?? null
          });

          if (signal) {
            signal.removeEventListener(
              "abort",
              onTransportAbort
            );
          }
        }
      }
'''

block = block[:-len(tail_anchor)] + tail_replacement

s = s[:start] + block + s[end:]


# ===========================================================================
# 15. Suppress benign AST tracker spam
# ===========================================================================

ast_error = '''          console.error(`Document ${documentPath} not found in AST tracker`);'''

ast_count = s.count(ast_error)

if ast_count != 3:
    raise RuntimeError(
        "AST tracker spam suppression: expected exactly 3 anchors, "
        f"found {ast_count}"
    )

s = s.replace(
    ast_error,
    '''          // 🔇 [Continue AST] Suppressed benign "document not found in AST tracker" race.'''
)

print("🔇 Suppressed 3 benign AST tracker errors.")


# ===========================================================================
# Markers
# ===========================================================================

s += "\n" + MARKER + "\n"
s += TRANSPORT_MARKER + "\n"
s += AST_MARKER + "\n"

path.write_text(s)

print("")
print("✅ Built consolidated Continue logging patch.")
print("")
print("Diagnostics:")
print("  ⏱️ provider total timing")
print("  ⏱️ debounce timing")
print("  ⏱️ HelperVars.create timing")
print("  ⌨️ VS Code invocation")
print("  🛑 VS Code cancellation")
print("  🧭 prompt/cursor summary")
print("  🚀 model generation start")
print("  ⏱️ TTFT")
print("  📝 raw completion")
print("  ✅ completion outcome")
print("  👻 ghost-text decision")
print("  🔄 generator reuse decision")
print("  🔌/🌐/📨/🌊 transport lifecycle")
print("  💥 transport abort")
print("  🏁 transport exit summary")
