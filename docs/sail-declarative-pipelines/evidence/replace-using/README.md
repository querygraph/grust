# REPLACE USING AST and pipeline policy

InsertIntoReplaceUsing retains CTE, BY NAME and ordered keys in a distinct AST variant. Pipeline registration preserves raw Flow-name validation before overwrite rejection, then target validation. Ordinary declarations receive the correct InsertIntoStatement/UnresolvedWith node diagnostic. Ordinary USING execution explicitly returns unsupported; it cannot fall through to append or discard its match keys. Transactional USING row replacement is not implemented by this parser unit.

Qualification:438 native+syntax/fmt/strictClippy, fresh300+67, paired8, the two existing Sail BY NAME replacement-row regressions and an unchanged-test producer control. The full16-vector packet now matches the compared outcome/error-type/condition/SQLSTATE/parameter fields; full query-context text and general recovery hints are outside that comparison. The only generated snapshot change describes the new AST variant; existing command-plan goldens and their inputs remain unchanged.

No original inventory-site promotion or CDC effects follow. Broader SDP acceptance, empty-statement/lexical/recovery/context behavior and the remaining batch/catalog/runtime work are still required. Fable owns CDC independently.
