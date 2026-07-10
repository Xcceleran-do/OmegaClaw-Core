(= (getSkills)
   (;INTERNAL:
    "- Remember a particular string such as skills and memories: remember string"
    "- Query long-term embedding memory with a short search phrase only. This is semantic recall, not logical question answering; do not use it for the query part of atomization: query string"
    "- Episodes searches history for episodes around a time stamp, time format is same as in TIME: episodes time_string"
    "- Pin a certain string as short-term working memory item to keep track of task state: pin string"
    ;SHELL AND FILE I/O:
    "- Execute shell command without apostrophe in string, it returns the command output to you: shell string"
    "- Read file to string: read-file filename"
    "- Write string to file: write-file filename string"
    "- Append line to file: append-file filename string",
    ;COMMUNICATION CHANNELS:
    "- Send message to user: send string"
    "- Search the web: search string"
    "- Search the web using the Tavily Search Agent: tavily-search string"
    "- Get technical analysis for a stock ticker using the Technical Analysis Agent: technical-analysis ticker"
    ;CODE EXECUTION:
    "- Extract article-level inference metadata such as topic, sentiment, tone, style, domain, scope, temporal framing, main claim, and evidence quality. Use only for article/corpus-length text, never for short messages or isolated claims: extract-metadata string"
    "- Atomize the full reasoning text into a compact staged semantic workspace plus NAL/PLN facts, rules, and queries. Include all premises and the query in one call. workspace stages are provisional; items[].pln and items[].nal are atoms, not metta calls. If you call atomize, do not call anything else in that response; wait for its result: atomize string"
    "- Execute MeTTa only after atomize/search/query results are visible in LAST_SKILL_USE_RESULTS. For atomize output, build the metta expression yourself from returned items. A PLN |~ call needs two supported truth-valued premises from items[].pln; a NAL |- call needs two supported truth-valued premises from items[].nal: metta sexpression"
    "NAL example: metta (|- ((--> pingu ([] feathered)) (stv 1.0 0.8)) ((==> (--> $1 ([] feathered)) (--> $1 bird)) (stv 1.0 0.8)))"
    "PLN example: metta (|~ ((Inheritance pingu (IntSet feathered)) (stv 1.0 0.8)) ((Implication (Inheritance $1 (IntSet feathered)) (Inheritance $1 bird)) (stv 1.0 0.8)))"
    "PLN format: use links consumed by lib_pln.metta, especially Inheritance, Implication, Similarity, Evaluation, Not, Equivalence, and Member. Multi-condition rules use nested Implication, not And."
    ))


(= (read-file $file)
   (progn (translatePredicate (exists_file $file))
          (translatePredicate (read_file_to_string $file $content ()))
          $content))

(= (write-file $file $str)
   (progn (translatePredicate (open $file write $Out))
          (translatePredicate (write $Out $str))
          (translatePredicate (close $Out))
          WRITE-FILE-SUCCESS))

(= (append-file $file $str)
   (progn (translatePredicate (exists_file $file))
          (translatePredicate (open $file append $Out))
          (translatePredicate (write $Out $str))
          (translatePredicate (nl $Out)),
          (translatePredicate (close $Out))
          APPEND-FILE-SUCCESS))

(= (tavily-search $query)
   (py-call (agentverse.tavily_search $query)))

(= (technical-analysis $ticker)
   (py-call (agentverse.technical_analysis $ticker)))

(= (extract-metadata $str)
   (py-call (metadata_extractor.extract_metadata $str)))

(= (atomize $str)
   (py-call (semantic_parser.atomize $str)))

!(import_prolog_functions_from_file (library OmegaClaw-Core ./src/skills.pl) (shell first_char gc read_file_tail))

(= (metta $str)
   (let $code (sread $str)
        (repr (swrite (eval $code)))))

(= (pin $x)
   PIN-SUCCESS)
