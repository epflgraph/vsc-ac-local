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
DUPLICATE_COMMENT_MARKER = "// [CONTINUE-PATCH:DUPLICATE-COMMENT-PREFIX] applied"
NEXT_EDIT_CHAIN_MARKER = "// [CONTINUE-PATCH:NEXT-EDIT-CHAIN] applied"
COMMENT_FIRST_SENTENCE_MARKER = "// [CONTINUE-PATCH:COMMENT-FIRST-SENTENCE] applied"
SUPPRESS_AFTER_ACCEPT_MARKER = "// [CONTINUE-PATCH:SUPPRESS-AFTER-ACCEPT] applied"
SUPPRESS_AFTER_SAVE_MARKER = "// [CONTINUE-PATCH:SUPPRESS-AFTER-SAVE] applied"


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
# 4a. Safely strip <COMPLETION>...</COMPLETION>
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
# 4b. Remove duplicated comment prefix
# ===========================================================================

old = '''          if (!completion) {
            return void 0;
          }
          const outcome = {'''

new = '''          if (!completion) {
            return void 0;
          }

          // [CONTINUE-PATCH:DUPLICATE-COMMENT-PREFIX]
          //
          // If the existing text before the cursor already ends with "#"
          // and the generated completion starts with another "#", remove
          // the generated duplicate while preserving spacing.
          if (
            /#[ \\t]*$/.test(prefix) &&
            /^[ \\t]*#[ \\t]*(?=\\S)/.test(completion)
          ) {
            const prefixAlreadyHasSpace = /#[ \\t]+$/.test(prefix);

            completion = completion.replace(
              /^[ \\t]*#[ \\t]*/,
              prefixAlreadyHasSpace ? "" : " "
            );

            console.log(
              "✂️ [Continue OP] Removed duplicate comment prefix"
            );
          }

          if (!completion) {
            return void 0;
          }

          const outcome = {'''

replace_once(
    old,
    new,
    "duplicate comment-prefix cleanup"
)

print("✂️ Added duplicate comment-prefix cleanup.")


# ===========================================================================
# 4c. Truncate comment autocomplete after first complete sentence
# ===========================================================================

old = '''            console.log(
              "✂️ [Continue OP] Removed duplicate comment prefix"
            );
          }

          if (!completion) {
            return void 0;
          }

          const outcome = {'''

new = '''            console.log(
              "✂️ [Continue OP] Removed duplicate comment prefix"
            );
          }

          if (!completion) {
            return void 0;
          }

          // [CONTINUE-PATCH:COMMENT-FIRST-SENTENCE]
          //
          // When completing a comment, keep only the first complete sentence.
          if (/#[^\\\\n]*$/.test(prefix)) {
            const sentenceEnd = completion.search(/\\.(?=\\s|$)/);

            if (sentenceEnd !== -1) {
              completion = completion.slice(0, sentenceEnd + 1);

              console.log(
                "✂️ [Continue OP] Truncated comment after first sentence"
              );
            }
          }

          if (!completion) {
            return void 0;
          }

          const outcome = {'''

replace_once(
    old,
    new,
    "comment first-sentence truncation"
)

print("💬 Added comment first-sentence truncation.")


# ===========================================================================
# 4d. Suppress automatic autocomplete after acceptance or save
# ===========================================================================

old = '''        const enableTabAutocomplete = getStatusBarStatus() === 1 /* Enabled */;'''

new = '''        // [CONTINUE-PATCH:SUPPRESS-AFTER-ACCEPT]
        //
        // The custom Tab-accept command records the document version before
        // inserting the inline completion. The accepted insertion normally
        // increments that version once. Suppress only the resulting automatic
        // invocation for that document state.
        const suppressAfterAccept =
          globalThis.__continueSuppressAutocompleteAfterAccept;

        if (suppressAfterAccept) {
          const isAutomatic =
            context2.triggerKind !==
            vscode11.InlineCompletionTriggerKind.Invoke;

          const sameDocument =
            document2.uri.toString() ===
            suppressAfterAccept.document;

          const isAcceptedInsertion =
            document2.version ===
            suppressAfterAccept.versionBeforeAccept + 1;

          if (
            isAutomatic &&
            sameDocument &&
            isAcceptedInsertion
          ) {
            globalThis.__continueSuppressAutocompleteAfterAccept =
              void 0;

            console.log(
              "🛑 [Continue OP] Suppressed automatic invocation after acceptance",
              {
                versionBeforeAccept:
                  suppressAfterAccept.versionBeforeAccept,
                currentVersion:
                  document2.version
              }
            );

            return null;
          }

          if (
            !sameDocument ||
            document2.version >
              suppressAfterAccept.versionBeforeAccept + 1 ||
            context2.triggerKind ===
              vscode11.InlineCompletionTriggerKind.Invoke
          ) {
            globalThis.__continueSuppressAutocompleteAfterAccept =
              void 0;
          }
        }

        // [CONTINUE-PATCH:SUPPRESS-AFTER-SAVE]
        //
        // onWillSaveTextDocument records the exact document/version before
        // VS Code performs the save. A save does not normally change the
        // document version, so suppress only an automatic invocation for that
        // same document/version.
        const suppressAfterSave =
          globalThis.__continueSuppressAutocompleteAfterSave;

        if (suppressAfterSave) {
          const isAutomatic =
            context2.triggerKind !==
            vscode11.InlineCompletionTriggerKind.Invoke;

          const sameDocument =
            document2.uri.toString() ===
            suppressAfterSave.document;

          const sameVersion =
            document2.version ===
            suppressAfterSave.version;

          if (
            isAutomatic &&
            sameDocument &&
            sameVersion
          ) {
            globalThis.__continueSuppressAutocompleteAfterSave =
              void 0;

            console.log(
              "🛑 [Continue OP] Suppressed automatic invocation after save",
              {
                document:
                  document2.uri.toString(),
                documentVersion:
                  document2.version
              }
            );

            return null;
          }

          // If anything changed after the save, this state is stale and must
          // not suppress a genuine later edit or manual invocation.
          if (
            !sameDocument ||
            !sameVersion ||
            context2.triggerKind ===
              vscode11.InlineCompletionTriggerKind.Invoke
          ) {
            globalThis.__continueSuppressAutocompleteAfterSave =
              void 0;
          }
        }

        const enableTabAutocomplete = getStatusBarStatus() === 1 /* Enabled */;'''

replace_once(
    old,
    new,
    "post-accept and post-save provider suppression"
)

print("🛑 Added post-accept provider suppression.")
print("💾 Added post-save provider suppression.")




# Custom acceptance command
#
# This is called by the Tab keybinding. It records the editor state before
# committing the inline suggestion.
# ---------------------------------------------------------------------------

old = '''        "continue.forceAutocomplete": async () => {
          await vscode14.commands.executeCommand("editor.action.inlineSuggest.hide");
          await vscode14.commands.executeCommand(
            "editor.action.inlineSuggest.trigger"
          );
        },'''

new = '''        "continue.acceptAutocompleteWithoutRetrigger": async () => {
          const activeEditor =
            vscode14.window.activeTextEditor;

          if (activeEditor) {
            globalThis.__continueSuppressAutocompleteAfterAccept = {
              document:
                activeEditor.document.uri.toString(),
              versionBeforeAccept:
                activeEditor.document.version
            };

            console.log(
              "🛑 [Continue OP] Armed autocomplete suppression before acceptance",
              {
                document:
                  activeEditor.document.uri.toString(),
                versionBeforeAccept:
                  activeEditor.document.version
              }
            );
          }

          await vscode14.commands.executeCommand(
            "editor.action.inlineSuggest.commit"
          );
        },

        "continue.saveWithoutAutocomplete": async () => {
          const activeEditor =
            vscode14.window.activeTextEditor;

          if (activeEditor) {
            globalThis.__continueSuppressAutocompleteAfterSave = {
              document:
                activeEditor.document.uri.toString()
            };

            console.log(
              "🛑 [Continue OP] Armed autocomplete suppression before save",
              {
                document:
                  activeEditor.document.uri.toString()
              }
            );
          }

          await vscode14.commands.executeCommand(
            "workbench.action.files.save"
          );
        },

        "continue.forceAutocomplete": async () => {
          await vscode14.commands.executeCommand("editor.action.inlineSuggest.hide");
          await vscode14.commands.executeCommand(
            "editor.action.inlineSuggest.trigger"
          );
        },'''

replace_once(
    old,
    new,
    "custom autocomplete acceptance and save commands"
)

print("⌨️ Added custom Tab-accept command.")
print("💾 Added custom save-without-autocomplete command.")


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
# 6. Abort actual model transport when autocomplete is cancelled
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
# 11. Show native Continue status-bar spinner while LLM requests are active
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
        // Reuse Continue's native autocomplete status-bar item.
        globalThis.__continueAutocompleteActiveRequests =
          (globalThis.__continueAutocompleteActiveRequests ?? 0) + 1;

        setupStatusBar(void 0, true);

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
            stopStatusBarLoading();
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
    "native autocomplete status-bar spinner"
)

print("⏳ Connected LLM requests to Continue's native status-bar spinner.")


# ===========================================================================
# 12. Hide status-bar spinner when transport finishes
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
# 13. Prevent ordinary autocomplete from creating Next Edit chains
# ===========================================================================

old = '''          } else {
            this.nextEditProvider.startChain();
            const input = {'''

new = '''          } else {
            // [CONTINUE-PATCH:NEXT-EDIT-CHAIN]
            //
            // Ordinary autocomplete must not create a Next Edit chain.
            // Otherwise a cancelled autocomplete leaves a stale chain that
            // causes the following invocation to be swallowed.
            if (this.isNextEditActive) {
              this.nextEditProvider.startChain();
            }

            const input = {'''

replace_once(
    old,
    new,
    "Next Edit chain creation guard"
)

print("🔗 Guarded Next Edit chain creation.")

# ===========================================================================
# 14. Arm one-shot autocomplete suppression before a document is saved
#
# This observes VS Code's normal save lifecycle. Cmd+S is not overridden.
# It also works for saves initiated through menus or other VS Code commands.
# ===========================================================================

old = '''        context2.subscriptions.push(
          vscode41.languages.registerInlineCompletionItemProvider(
            [{ pattern: "**" }],
            this.completionProvider
          )
        );
        this.uriHandler.event((uri) => {'''

new = '''        context2.subscriptions.push(
          vscode41.languages.registerInlineCompletionItemProvider(
            [{ pattern: "**" }],
            this.completionProvider
          )
        );

        // [CONTINUE-PATCH:SUPPRESS-AFTER-SAVE]
        context2.subscriptions.push(
          vscode41.workspace.onWillSaveTextDocument((event) => {
            globalThis.__continueSuppressAutocompleteAfterSave = {
              document:
                event.document.uri.toString(),
              version:
                event.document.version
            };

            console.log(
              "🛑 [Continue OP] Armed autocomplete suppression before save",
              {
                document:
                  event.document.uri.toString(),
                documentVersion:
                  event.document.version
              }
            );
          })
        );

        this.uriHandler.event((uri) => {'''

replace_once(
    old,
    new,
    "save autocomplete suppression listener"
)

print("💾 Added save-event autocomplete suppression listener.")

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
    DUPLICATE_COMMENT_MARKER,
    NEXT_EDIT_CHAIN_MARKER,
    COMMENT_FIRST_SENTENCE_MARKER,
    SUPPRESS_AFTER_ACCEPT_MARKER,
    SUPPRESS_AFTER_SAVE_MARKER,
):
    if marker not in s:
        s += marker + "\n"


# ===========================================================================
# Write patched JavaScript
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
print("  ✂️ duplicate comment prefix removed")
print("  💬 comments truncated after first sentence")
print("  🛡️ defensive document.lineAt() bounds checks")
print("  🧨 cancellation aborts underlying model transport")
print("  🕊️ conservative late-cancellation grace")
print("  ⚡ autocomplete does not wait for getRepoName()")
print("  ⏳ status-bar spinner during Continue → LLM requests")
print("  🔗 ordinary autocomplete does not create Next Edit chains")
print("  ⌨️ custom Tab-accept command installed")
print("  🛑 automatic autocomplete suppressed after Tab acceptance")
print("  💾 automatic autocomplete suppressed after file save")
