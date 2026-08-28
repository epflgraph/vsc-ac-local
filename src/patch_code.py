from pathlib import Path
import sys

path = Path(sys.argv[1])
s = path.read_text()

LOGGING_MARKER = "// [CONTINUE-PATCH:LOGGING-V3] applied"
MARKER = "// [CONTINUE-PATCH:BEHAVIOR-V3] applied"

OPERATIONAL_MARKER = "// [CONTINUE-PATCH:OPERATIONAL] applied"
TRANSPORT_ABORT_MARKER = "// [CONTINUE-PATCH:TRANSPORT-ABORT] applied"
LATE_CANCEL_MARKER = "// [CONTINUE-PATCH:LATE-CANCEL-GRACE] applied"
COMPLETION_GUARD_MARKER = "// [CONTINUE-PATCH:COMPLETION-MATCH-GUARD] applied"
NO_REPO_WAIT_MARKER = "// [CONTINUE-PATCH:AUTOCOMPLETE-NO-REPO-WAIT] applied"
AUTOCOMPLETE_STATUS_MARKER = "// [CONTINUE-PATCH:AUTOCOMPLETE-STATUS] applied"


def replace_once(old, new, label):
    global s

    count = s.count(old)

    if count != 1:
        raise RuntimeError(
            f"{label}: expected exactly 1 anchor, found {count}"
        )

    s = s.replace(old, new, 1)


# ===========================================================================
# Preconditions
# ===========================================================================

if MARKER in s:
    print("ℹ️ Continue behavior v3 patch already applied; nothing to do.")
    raise SystemExit(0)

if LOGGING_MARKER not in s:
    raise RuntimeError(
        "Continue logging v3 patch was not detected.\n"
        "Apply patch_logs.sh first."
    )

print("🔎 Continue logging v3 detected.")


# ===========================================================================
# 1. Disable GeneratorReuseManager reuse
#
# Always start a fresh generator.
# ===========================================================================

logged_reuse = '''      shouldReuseExistingGenerator(prefix) {
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

operational_reuse = '''      shouldReuseExistingGenerator(prefix) {
        // [CONTINUE-PATCH:OPERATIONAL]
        //
        // Always start a fresh model request.
        //
        // Reusing an existing generator can replay chunks generated for an
        // earlier cursor/prefix state into a newer autocomplete invocation.
        console.log("🛡️ [Continue OP] Generator reuse blocked", {
          operationalPatchDetected: true,
          hasCurrentGenerator: !!this.currentGenerator,
          pendingPrefixLength: this.pendingGeneratorPrefix?.length ?? 0,
          pendingCompletionLength: this.pendingCompletion?.length ?? 0,
          incomingPrefixLength: prefix?.length ?? 0
        });

        return false;
      }'''

replace_once(
    logged_reuse,
    operational_reuse,
    "disable GeneratorReuseManager reuse"
)

print("🛡️ Disabled generator reuse.")


# ===========================================================================
# 2. Drop invocation if cancelled during debounce
# ===========================================================================

old = '''            if (shouldDebounce) {
              return void 0;
            }
          }

          if (llm.promptTemplates?.autocomplete) {'''

new = '''            if (shouldDebounce) {
              return void 0;
            }
          }

          // [CONTINUE-PATCH:OPERATIONAL]
          //
          // VS Code may cancel this autocomplete invocation while Continue is
          // waiting for debounce. Do not continue using stale editor state.
          if (token.aborted) {
            console.log("🚫 [Continue OP] Stale invocation dropped after debounce", {
              pos: input.pos,
              filepath: input.filepath
            });

            return void 0;
          }

          if (llm.promptTemplates?.autocomplete) {'''

replace_once(
    old,
    new,
    "stale-after-debounce guard"
)

print("🛡️ Added stale-after-debounce guard.")


# ===========================================================================
# 3. Drop invocation if cancelled during HelperVars.create()
# ===========================================================================

old = '''          console.log("⏱️ [Continue AC] HelperVars.create finished", {
            elapsedMs: Date.now() - helperStartedAt
          });

          if (await shouldPrefilter(helper, this.ide)) {'''

new = '''          console.log("⏱️ [Continue AC] HelperVars.create finished", {
            elapsedMs: Date.now() - helperStartedAt
          });

          // [CONTINUE-PATCH:OPERATIONAL]
          //
          // HelperVars construction is asynchronous. The invocation may have
          // become stale while prefix/suffix/context was being assembled.
          if (token.aborted) {
            console.log("🚫 [Continue OP] Stale invocation dropped after helper construction", {
              pos: input.pos,
              filepath: input.filepath
            });

            return void 0;
          }

          if (await shouldPrefilter(helper, this.ide)) {'''

replace_once(
    old,
    new,
    "stale-after-helper guard"
)

print("🛡️ Added stale-after-helper guard.")


# ===========================================================================
# 4. Safely strip <COMPLETION>...</COMPLETION>
# ===========================================================================

old = '''            completion = processedCompletion;
          }
          if (!completion) {'''

new = '''            completion = processedCompletion;
          }

          // [CONTINUE-PATCH:OPERATIONAL]
          //
          // Cancellation or postprocessing can leave completion undefined.
          // Never call .match() until its type has been verified.
          if (typeof completion !== "string" || !completion) {
            return void 0;
          }

          // Some OpenAI-compatible models return the completion protocol
          // wrapper itself. Keep only the actual completion body.
          const completionMatch = completion.match(
            /<COMPLETION>([\\s\\S]*?)(?:<\\/COMPLETION>|$)/
          );

          if (completionMatch) {
            console.log("✂️ [Continue OP] Stripped <COMPLETION> wrapper", {
              beforeLength: completion.length,
              afterLength: completionMatch[1].length
            });

            completion = completionMatch[1];
          }

          if (!completion) {'''

replace_once(
    old,
    new,
    "safe <COMPLETION> wrapper cleanup"
)

print("🛡️ Added completion.match() guard.")
print("✂️ Added <COMPLETION> wrapper cleanup.")


# ===========================================================================
# 5. Defensive document.lineAt() bounds
# ===========================================================================

old = '''        const isFullLineSelection = selection.start.character === 0 && (selection.end.line > selection.start.line ? selection.end.character === 0 : selection.end.character === document2.lineAt(selection.end.line).text.length);
        const isLineEmpty = (lineNumber) => {
          return document2.lineAt(lineNumber).text.trim().length === 0;
        };
        const getLineEndChar = (lineNumber) => {
          return document2.lineAt(lineNumber).text.trimEnd().length;
        };'''

new = '''        // [CONTINUE-PATCH:OPERATIONAL]
        //
        // Guard document.lineAt() against transient/stale selection
        // coordinates while VS Code is updating the editor buffer.
        const endLineIsValid =
          selection.end.line >= 0 &&
          selection.end.line < document2.lineCount;

        const isFullLineSelection =
          selection.start.character === 0 &&
          (
            selection.end.line > selection.start.line
              ? selection.end.character === 0
              : endLineIsValid &&
                selection.end.character ===
                  document2.lineAt(selection.end.line).text.length
          );

        const isLineEmpty = (lineNumber) => {
          if (lineNumber < 0 || lineNumber >= document2.lineCount) {
            console.log("🛡️ [Continue OP] Prevented out-of-range document.lineAt()", {
              operation: "isLineEmpty",
              requestedLine: lineNumber,
              lineCount: document2.lineCount
            });

            return true;
          }

          return document2.lineAt(lineNumber).text.trim().length === 0;
        };

        const getLineEndChar = (lineNumber) => {
          if (lineNumber < 0 || lineNumber >= document2.lineCount) {
            console.log("🛡️ [Continue OP] Prevented out-of-range document.lineAt()", {
              operation: "getLineEndChar",
              requestedLine: lineNumber,
              lineCount: document2.lineCount
            });

            return 0;
          }

          return document2.lineAt(lineNumber).text.trimEnd().length;
        };'''

replace_once(
    old,
    new,
    "document.lineAt bounds hardening"
)

print("🛡️ Added defensive document.lineAt() bounds guards.")


# ===========================================================================
# 6. Abort the actual model transport when autocomplete is cancelled
# ===========================================================================

full_stop_anchor = '''        const fullStop = () => this.generatorReuseManager.currentGenerator?.cancel();'''

if s.count(full_stop_anchor) != 1:
    raise RuntimeError(
        "transport abort: expected exactly one CompletionStreamer fullStop(), "
        f"found {s.count(full_stop_anchor)}"
    )


old = '''            if (token.aborted) {
              console.log(
                "🛑 [Continue AC] Stream discarded after cancellation",
                {
                  elapsedMs: elapsed
                }
              );

              return;
            }

            yield update2;'''

new = '''            if (token.aborted) {
              console.log(
                "🛑 [Continue AC] Stream discarded after cancellation",
                {
                  elapsedMs: elapsed
                }
              );

              // [CONTINUE-PATCH:TRANSPORT-ABORT]
              //
              // Cancel the GeneratorReuseManager-owned generator as well as
              // abandoning this consumer. Its AbortController is the one
              // whose signal reaches llm.streamComplete()/fetch().
              console.log("🧨 [Continue OP] Cancelling underlying model transport", {
                reason: "autocomplete token aborted"
              });

              fullStop();
              return;
            }

            yield update2;'''

replace_once(
    old,
    new,
    "transport abort on token cancellation"
)

print("🧨 Added underlying model transport cancellation.")


# ===========================================================================
# 7. Capture document version at provider invocation
# ===========================================================================

old = '''      async provideInlineCompletionItems(document2, position, context2, token) {
        const providerStartedAt = Date.now();'''

new = '''      async provideInlineCompletionItems(document2, position, context2, token) {
        const providerStartedAt = Date.now();
        const invocationDocumentVersion = document2.version;'''

replace_once(
    old,
    new,
    "invocation document-version tracking"
)

print("🕊️ Added invocation document-version tracking.")


# ===========================================================================
# 8. Pass original invocation state into willDisplay()
# ===========================================================================

old = '''          const willDisplay = this.willDisplay(
            document2,
            selectedCompletionInfo,
            signal,
            outcome
          );'''

new = '''          const willDisplay = this.willDisplay(
            document2,
            selectedCompletionInfo,
            signal,
            outcome,
            invocationDocumentVersion,
            position
          );'''

replace_once(
    old,
    new,
    "late-cancel willDisplay call"
)

print("🕊️ Passed invocation state into willDisplay().")


# ===========================================================================
# 9. Conservative late-cancellation grace
# ===========================================================================

old = '''      willDisplay(document2, selectedCompletionInfo, abortSignal, outcome) {
        if (selectedCompletionInfo) {
          const { text: text5, range: range4 } = selectedCompletionInfo;
          if (!outcome.completion.startsWith(text5)) {
            return false;
          }
        }
        if (abortSignal.aborted) {
          return false;
        }
        return true;
      }'''

new = '''      willDisplay(document2, selectedCompletionInfo, abortSignal, outcome, invocationDocumentVersion, invocationPosition) {
        if (selectedCompletionInfo) {
          const { text: text5, range: range4 } = selectedCompletionInfo;

          if (!outcome.completion.startsWith(text5)) {
            return false;
          }
        }

        if (abortSignal.aborted) {
          const activeEditor = vscode11.window.activeTextEditor;

          const sameDocumentVersion =
            document2.version === invocationDocumentVersion;

          const sameActiveDocument =
            !!activeEditor &&
            activeEditor.document.uri.toString() ===
              document2.uri.toString();

          const sameCursorPosition =
            !!activeEditor &&
            activeEditor.selection.active.line ===
              invocationPosition.line &&
            activeEditor.selection.active.character ===
              invocationPosition.character;

          if (
            !sameDocumentVersion ||
            !sameActiveDocument ||
            !sameCursorPosition
          ) {
            console.log("🚫 [Continue OP] Late-cancelled completion rejected", {
              sameDocumentVersion,
              sameActiveDocument,
              sameCursorPosition,
              invocationDocumentVersion,
              currentDocumentVersion: document2.version,
              invocationPosition,
              currentPosition: activeEditor
                ? {
                    line: activeEditor.selection.active.line,
                    character: activeEditor.selection.active.character
                  }
                : null
            });

            return false;
          }

          console.log(
            "🕊️ [Continue OP] Late cancellation ignored for completed autocomplete",
            {
              documentVersion: document2.version,
              position: invocationPosition,
              completionLength: outcome.completion?.length ?? 0
            }
          );
        }

        return true;
      }'''

replace_once(
    old,
    new,
    "late-cancel willDisplay implementation"
)

print("🕊️ Added conservative late-cancellation grace.")


# ===========================================================================
# 10. Remove blocking Git repository lookup from autocomplete
# ===========================================================================

old = '''            gitRepo: await this.ide.getRepoName(helper.filepath),
            uniqueId: await this.ide.getUniqueId(),'''

new = '''            // [CONTINUE-PATCH:AUTOCOMPLETE-NO-REPO-WAIT]
            //
            // getRepoName() can block for up to 20 seconds while waiting for
            // the VS Code Git extension/repository HEAD state.
            //
            // Repository metadata is not required to display autocomplete.
            gitRepo: void 0,
            uniqueId: await this.ide.getUniqueId(),'''

replace_once(
    old,
    new,
    "remove blocking autocomplete getRepoName lookup"
)

print("⚡ Removed blocking getRepoName() from autocomplete outcome.")


# ===========================================================================
# 11. Show status-bar spinner while Continue → LLM requests are active
#
# Uses an in-flight counter because autocomplete requests can overlap briefly.
# The spinner disappears only when the final active request finishes/aborts.
# ===========================================================================

old = '''        console.log("🔌 [Continue TRANSPORT] /completions entered", {
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
        };'''

new = '''        console.log("🔌 [Continue TRANSPORT] /completions entered", {
          transportRequestId,
          hasSignal: !!signal,
          signalAborted: signal?.aborted ?? null,
          model: options?.model
        });

        // [CONTINUE-PATCH:AUTOCOMPLETE-STATUS]
        //
        // Visible indication that an autocomplete request is currently
        // talking to the LLM.
        if (!globalThis.__continueAutocompleteStatusBar) {
          globalThis.__continueAutocompleteStatusBar =
            vscode11.window.createStatusBarItem(
              vscode11.StatusBarAlignment.Right,
              100
            );
        }

        globalThis.__continueAutocompleteActiveRequests =
          (globalThis.__continueAutocompleteActiveRequests ?? 0) + 1;

        const autocompleteStatusBar =
          globalThis.__continueAutocompleteStatusBar;

        autocompleteStatusBar.text = "$(loading~spin) Continue";
        autocompleteStatusBar.tooltip =
          `Autocomplete request in progress\\nModel: ${options?.model ?? "unknown"}`;
        autocompleteStatusBar.show();

        let autocompleteStatusRequestClosed = false;

        const closeAutocompleteStatusRequest = () => {
          if (autocompleteStatusRequestClosed) {
            return;
          }

          autocompleteStatusRequestClosed = true;

          globalThis.__continueAutocompleteActiveRequests = Math.max(
            0,
            (globalThis.__continueAutocompleteActiveRequests ?? 1) - 1
          );

          if (globalThis.__continueAutocompleteActiveRequests === 0) {
            autocompleteStatusBar.hide();
          }
        };

        const onTransportAbort = () => {
          console.log("💥 [Continue TRANSPORT] AbortSignal fired", {
            transportRequestId,
            signalAborted: signal?.aborted ?? null,
            signalReason: signal?.reason ?? null
          });

          closeAutocompleteStatusRequest();
        };'''

replace_once(
    old,
    new,
    "autocomplete status-bar spinner"
)

print("⏳ Added Continue → LLM status-bar spinner.")


# ===========================================================================
# 12. Hide status-bar spinner when transport finishes
#
# This uses the actual finally block emitted by patch_logs.sh.
# Abort cleanup is also handled safely because closeAutocompleteStatusRequest()
# is idempotent.
# ===========================================================================

old = '''          if (signal) {
            signal.removeEventListener(
              "abort",
              onTransportAbort
            );
          }
        }
      }'''

new = '''          if (signal) {
            signal.removeEventListener(
              "abort",
              onTransportAbort
            );
          }

          // [CONTINUE-PATCH:AUTOCOMPLETE-STATUS]
          closeAutocompleteStatusRequest();
        }
      }'''

replace_once(
    old,
    new,
    "autocomplete status-bar completion cleanup"
)

print("⏳ Added status-bar cleanup after completed requests.")


# ===========================================================================
# Markers
# ===========================================================================

s += "\n" + MARKER + "\n"

for marker in (
    OPERATIONAL_MARKER,
    TRANSPORT_ABORT_MARKER,
    LATE_CANCEL_MARKER,
    COMPLETION_GUARD_MARKER,
    NO_REPO_WAIT_MARKER,
    AUTOCOMPLETE_STATUS_MARKER,
):
    if marker not in s:
        s += marker + "\n"


# ===========================================================================
# Write temporary patched JavaScript
# ===========================================================================

path.write_text(s)

print("")
print("✅ Built consolidated Continue behavior patch.")
print("")
print("Behavior enabled:")
print("  🛡️ generator reuse disabled")
print("  🚫 stale invocation dropped after debounce")
print("  🚫 stale invocation dropped after HelperVars construction")
print("  🛡️ completion.match() protected against undefined")
print("  ✂️ <COMPLETION> wrapper cleanup")
print("  🛡️ defensive document.lineAt() bounds checks")
print("  🧨 cancellation aborts underlying model transport")
print("  🕊️ conservative late-cancellation grace")
print("  ⚡ autocomplete does not wait for getRepoName()")
print("  ⏳ status-bar spinner during Continue → LLM requests")
