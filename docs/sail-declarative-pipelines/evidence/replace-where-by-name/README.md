# REPLACE WHERE BY NAME

The AST now retains optional BY NAME on predicate replacement. InsertMode::Replace carries a default-false flag, omitted when serializing false to preserve legacy JSON. The resolver maps true to the existing WriteColumnMatch::ByName and continues to use the existing TruncateIf writer; no writer/backend/catalog-specific path is introduced. Ordinary positional replacement retains its behavior.

Qualification:436 native+syntax/fmt/strictClippy, fresh300+67, four registration cases on each engine, two Sail Delta row tests (positional and reversed-column BY NAME), and an unchanged native flag-retention control. The row tests are Sail integration evidence, not a paired Spark Delta-runtime claim. The full16-vector replay reaches15matches; REPLACE USING remains the next parser/pipeline unit, and broader syntax recovery/context gaps remain open.

The first native run failed only the INSERT-plan golden: one existing32-case input newly parses successfully, agreeing with its unchanged recorded Spark exception=null. Official regeneration changes that output plus the syntax descriptor for the optional clause; all inputs, recorded Spark exceptions and unrelated outputs stay unchanged. The failed run is retained. No original inventory-site promotion or streaming/CDC activation is claimed; Fable owns CDC independently.
